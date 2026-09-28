"""Conversation-path contracts for active Foursquare attraction taxonomy."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.conversation_models import (  # noqa: E402
    TravelContext,
    TravelContextStage,
    TravellerType,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    ConversationRecommendationTask,
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    CATEGORIES_BY_ID,
    GENERIC_ATTRACTION_GROUPS,
    INTENT_CATEGORY_PRESETS,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class ConversationAttractionFoursquareTests(unittest.IsolatedAsyncioTestCase):
    def _build_task(
        self,
        *,
        query: str = "attractions",
        preferences: list[str] | None = None,
    ) -> ConversationRecommendationTask:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        context = TravelContext(
            stage=TravelContextStage.CONFIRMED,
            startingLocation=TravelLocation(
                displayName="Kandy",
                source=TravelLocationSource.SEARCHED,
                latitude=7.2906,
                longitude=80.6337,
                verified=True,
            ),
            tripStartDate=tomorrow,
            tripEndDate=tomorrow + timedelta(days=1),
            dailyStartTime="09:00:00",
            dailyEndTime="12:00:00",
            travellerType=TravellerType.COUPLE,
            travellerCount=2,
            travelModes=["driving"],
            requestGroups=[
                TravelRequestGroup(
                    id="attraction-request",
                    kind=TravelRequestKind.ATTRACTION,
                    query=query,
                    preferences=preferences or [],
                )
            ],
            isConfirmed=True,
        )

        tasks = build_recommendation_tasks(context)

        self.assertEqual(len(tasks), 1)
        return tasks[0]

    async def _collect_provider_requests(
        self,
        task: ConversationRecommendationTask,
        *,
        results: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"results": results or []},
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "contract-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            candidates = await recommendation_engine._collect_candidates(task.request)

        return candidates, requests

    def test_generic_discovery_uses_exact_four_verified_groups(self) -> None:
        task = self._build_task()
        category_groups = tuple(
            provider_filter.category_ids
            for provider_filter in task.request.provider_filters
        )
        grouped_ids = {
            category_id
            for category_group in category_groups
            for category_id in category_group
        }

        self.assertEqual(category_groups, tuple(GENERIC_ATTRACTION_GROUPS.values()))
        self.assertEqual([len(group) for group in category_groups], [8, 8, 8, 4])
        self.assertEqual(len(category_groups), 4)
        self.assertNotEqual(len(category_groups), 28)
        self.assertEqual(len(grouped_ids), 28)
        self.assertTrue(grouped_ids.issubset(CATEGORIES_BY_ID))

    async def test_generic_discovery_produces_four_grouped_http_requests(self) -> None:
        task = self._build_task()

        _, requests = await self._collect_provider_requests(task)

        self.assertEqual(len(requests), 4)
        self.assertEqual(
            [request.url.params["fsq_category_ids"] for request in requests],
            [",".join(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
        )
        self.assertEqual(
            {"query" in request.url.params for request in requests},
            {False},
        )

    def test_generic_signals_use_clean_broad_discovery(self) -> None:
        generic_signals = (
            "surprise me",
            "choose for me",
            "anything",
            "no preference",
            "I have no clue",
            "first time here, pick for me",
        )

        for signal in generic_signals:
            with self.subTest(signal=signal):
                task = self._build_task(preferences=[signal])

                self.assertEqual(len(task.request.provider_filters), 4)
                self.assertEqual(
                    {
                        provider_filter.query
                        for provider_filter in task.request.provider_filters
                    },
                    {None},
                )

    def test_query_only_generic_signals_are_not_sent_to_foursquare(self) -> None:
        for signal in ("surprise me", "anything", "choose for me"):
            with self.subTest(signal=signal):
                task = self._build_task(query=signal)

                self.assertEqual(task.request.category_names, ["attractions"])
                self.assertEqual(
                    {
                        provider_filter.query
                        for provider_filter in task.request.provider_filters
                    },
                    {None},
                )

    async def test_generic_signal_http_requests_omit_query(self) -> None:
        for signal in (
            "surprise me",
            "choose for me",
            "anything",
            "no preference",
            "I have no clue",
            "first time here",
        ):
            with self.subTest(signal=signal):
                task = self._build_task(query=signal)

                _, requests = await self._collect_provider_requests(task)

                self.assertEqual(len(requests), 4)
                self.assertTrue(
                    all("query" not in request.url.params for request in requests)
                )

    def test_all_fifteen_specific_intents_use_verified_presets(self) -> None:
        phrases_by_preset = {
            "temples": "temples",
            "historic_places": "historic places",
            "museums": "museums",
            "art_galleries": "art galleries",
            "waterfalls": "waterfalls",
            "beaches": "beaches",
            "wildlife": "wildlife",
            "nature": "nature",
            "scenic_places": "scenic places",
            "parks": "parks",
            "botanical_gardens": "botanical gardens",
            "hiking": "hiking",
            "family_attractions": "family attractions",
            "fun_things_to_do": "fun things to do",
            "romantic_scenic_places": "romantic scenic places",
        }

        self.assertEqual(set(phrases_by_preset), set(INTENT_CATEGORY_PRESETS))

        for preset_name, phrase in phrases_by_preset.items():
            with self.subTest(preset=preset_name):
                task = self._build_task(preferences=[phrase])
                provider_filters = task.request.provider_filters

                self.assertEqual(len(provider_filters), 1)
                self.assertEqual(
                    provider_filters[0].category_ids,
                    INTENT_CATEGORY_PRESETS[preset_name],
                )
                self.assertEqual(
                    provider_filters[0].provenance_key,
                    f"intent:{preset_name}",
                )
                self.assertTrue(
                    set(provider_filters[0].category_ids).issubset(CATEGORIES_BY_ID)
                )

    def test_intent_matching_uses_whole_tokens_and_not_exact_strings(self) -> None:
        botanical_task = self._build_task(
            preferences=["  Best   BoTaNiCaL    Gardens for couples  "]
        )
        substring_task = self._build_task(preferences=["parking areas"])

        self.assertEqual(
            botanical_task.request.provider_filters[0].category_ids,
            INTENT_CATEGORY_PRESETS["botanical_gardens"],
        )
        self.assertEqual(
            tuple(
                provider_filter.category_ids
                for provider_filter in substring_task.request.provider_filters
            ),
            tuple(GENERIC_ATTRACTION_GROUPS.values()),
        )

    def test_multiple_specific_intents_are_preserved_and_deduplicated(self) -> None:
        cases = (
            (
                "temples and waterfalls",
                {"intent:temples", "intent:waterfalls"},
            ),
            (
                "museums and historic places",
                {"intent:museums", "intent:historic_places"},
            ),
            (
                "beaches and scenic places",
                {"intent:beaches", "intent:scenic_places"},
            ),
            (
                "wildlife and nature",
                {"intent:wildlife", "intent:nature"},
            ),
        )

        for phrase, expected_keys in cases:
            with self.subTest(phrase=phrase):
                task = self._build_task(preferences=[phrase])
                provider_filters = task.request.provider_filters
                all_ids = [
                    category_id
                    for provider_filter in provider_filters
                    for category_id in provider_filter.category_ids
                ]

                self.assertEqual(
                    {
                        provider_filter.provenance_key
                        for provider_filter in provider_filters
                    },
                    expected_keys,
                )
                self.assertEqual(len(all_ids), len(set(all_ids)))

    async def test_multi_intent_searches_once_per_intent_not_per_leaf_id(self) -> None:
        task = self._build_task(preferences=["temples and waterfalls"])
        expected_groups = [
            INTENT_CATEGORY_PRESETS["temples"],
            INTENT_CATEGORY_PRESETS["waterfalls"],
        ]

        _, requests = await self._collect_provider_requests(task)

        self.assertEqual(len(requests), 2)
        self.assertEqual(
            [request.url.params["fsq_category_ids"] for request in requests],
            [",".join(group) for group in expected_groups],
        )
        self.assertNotEqual(
            len(requests),
            sum(len(group) for group in expected_groups),
        )

    def test_specific_preference_text_remains_in_provider_queries(self) -> None:
        cases = (
            ("Buddhist temples", "buddhist temples"),
            ("waterfalls", "waterfalls"),
            ("historic places", "historic places"),
            ("art galleries", "art galleries"),
            ("romantic scenic places", "romantic scenic places"),
        )

        for phrase, expected_query in cases:
            with self.subTest(phrase=phrase):
                task = self._build_task(preferences=[phrase])

                self.assertTrue(task.request.provider_filters)
                self.assertEqual(
                    {
                        provider_filter.query
                        for provider_filter in task.request.provider_filters
                    },
                    {expected_query},
                )

    async def test_specific_intent_http_requests_keep_useful_query(self) -> None:
        cases = (
            ("Buddhist temples", "buddhist temples"),
            ("waterfalls", "waterfalls"),
            ("historic places", "historic places"),
            ("art galleries", "art galleries"),
            ("romantic scenic places", "romantic scenic places"),
        )

        for phrase, expected_query in cases:
            with self.subTest(phrase=phrase):
                task = self._build_task(preferences=[phrase])

                _, requests = await self._collect_provider_requests(task)

                self.assertTrue(requests)
                self.assertEqual(
                    {request.url.params["query"] for request in requests},
                    {expected_query},
                )

    async def test_candidate_matches_preserve_generic_group_provenance(self) -> None:
        task = self._build_task()
        place = {
            "fsq_place_id": "same-place",
            "name": "Same Place",
            "latitude": 7.2906,
            "longitude": 80.6337,
            "location": {"country": "LK"},
        }

        candidates, requests = await self._collect_provider_requests(
            task,
            results=[place],
        )

        self.assertEqual(len(requests), 4)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            {
                match["providerFilterKey"]
                for match in candidates[0]["matchedCategories"]
            },
            {f"generic:{group_name}" for group_name in GENERIC_ATTRACTION_GROUPS},
        )


if __name__ == "__main__":
    unittest.main()
