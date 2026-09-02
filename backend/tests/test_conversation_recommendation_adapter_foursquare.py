"""Foursquare category contracts for conversation recommendation tasks."""

from __future__ import annotations

import inspect
import re
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
    FOURSQUARE_CATEGORY_IDS_BY_TRAVEL_REQUEST_KIND,
    FOURSQUARE_CATEGORY_GROUPS_BY_TRAVEL_REQUEST_KIND,
    ConversationRecommendationTask,
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    INTENT_CATEGORY_PRESETS,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")

OFFICIAL_FOURSQUARE_CATEGORY_IDS = {
    TravelRequestKind.HOTEL: ("4bf58dd8d48988d1fa931735",),
    TravelRequestKind.RESTAURANT: ("4d4b7105d754a06374d81259",),
    TravelRequestKind.ATTRACTION: tuple(
        category_id
        for category_group in GENERIC_ATTRACTION_GROUPS.values()
        for category_id in category_group
    ),
}


class ConversationRecommendationFoursquareTests(unittest.IsolatedAsyncioTestCase):
    def _build_task(
        self,
        *,
        kind: TravelRequestKind,
        query: str,
        preferences: list[str] | None = None,
    ) -> ConversationRecommendationTask:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        context = TravelContext(
            stage=TravelContextStage.CONFIRMED,
            startingLocation=TravelLocation(
                displayName="Colombo",
                source=TravelLocationSource.SEARCHED,
                latitude=6.9271,
                longitude=79.8612,
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
                    id=f"{kind.value}-request",
                    kind=kind,
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
    ) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"results": []},
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

        self.assertEqual(candidates, [])
        return requests

    def test_centralized_mapping_uses_official_foursquare_category_ids(self) -> None:
        self.assertEqual(
            FOURSQUARE_CATEGORY_IDS_BY_TRAVEL_REQUEST_KIND,
            OFFICIAL_FOURSQUARE_CATEGORY_IDS,
        )
        self.assertEqual(
            FOURSQUARE_CATEGORY_GROUPS_BY_TRAVEL_REQUEST_KIND,
            {
                TravelRequestKind.HOTEL: (
                    (OFFICIAL_FOURSQUARE_CATEGORY_IDS[TravelRequestKind.HOTEL][0],),
                ),
                TravelRequestKind.RESTAURANT: (
                    (
                        OFFICIAL_FOURSQUARE_CATEGORY_IDS[
                            TravelRequestKind.RESTAURANT
                        ][0],
                    ),
                ),
                TravelRequestKind.ATTRACTION: tuple(
                    GENERIC_ATTRACTION_GROUPS.values()
                ),
            },
        )

    def test_hotel_task_uses_hotel_filter_and_valid_query(self) -> None:
        task = self._build_task(
            kind=TravelRequestKind.HOTEL,
            query="hotels",
        )

        self.assertEqual(task.request.category_ids, [])
        self.assertEqual(task.request.category_names, ["hotel"])
        self.assertEqual(
            [provider_filter.category_ids for provider_filter in task.request.provider_filters],
            [("4bf58dd8d48988d1fa931735",)],
        )

    def test_restaurant_task_uses_restaurant_filter_without_generic_query(self) -> None:
        task = self._build_task(
            kind=TravelRequestKind.RESTAURANT,
            query="restaurants",
        )

        self.assertEqual(task.request.category_ids, [])
        self.assertEqual(task.request.category_names, ["restaurants"])
        self.assertIsNone(task.request.provider_filters[0].query)
        self.assertEqual(
            [provider_filter.category_ids for provider_filter in task.request.provider_filters],
            [("4d4b7105d754a06374d81259",)],
        )

    def test_attraction_task_uses_four_generic_filters_and_valid_query(self) -> None:
        task = self._build_task(
            kind=TravelRequestKind.ATTRACTION,
            query="attractions",
        )

        self.assertEqual(task.request.category_ids, [])
        self.assertEqual(task.request.category_names, ["attractions"])
        self.assertEqual(
            {provider_filter.query for provider_filter in task.request.provider_filters},
            {None},
        )
        self.assertEqual(
            [provider_filter.category_ids for provider_filter in task.request.provider_filters],
            list(GENERIC_ATTRACTION_GROUPS.values()),
        )
        self.assertEqual(
            [
                provider_filter.provenance_key
                for provider_filter in task.request.provider_filters
            ],
            [f"generic:{group_name}" for group_name in GENERIC_ATTRACTION_GROUPS],
        )

    def test_traveller_preferences_remain_in_provider_queries(self) -> None:
        restaurant_task = self._build_task(
            kind=TravelRequestKind.RESTAURANT,
            query="restaurants",
            preferences=["seafood"],
        )
        attraction_task = self._build_task(
            kind=TravelRequestKind.ATTRACTION,
            query="attractions",
            preferences=["temples"],
        )

        self.assertEqual(
            restaurant_task.request.category_names,
            ["restaurants"],
        )
        self.assertEqual(
            attraction_task.request.category_names,
            ["temples"],
        )
        self.assertEqual(
            {
                provider_filter.query
                for provider_filter in restaurant_task.request.provider_filters
            },
            {"seafood"},
        )
        self.assertEqual(
            {
                provider_filter.query
                for provider_filter in attraction_task.request.provider_filters
            },
            {"temples"},
        )
        self.assertEqual(
            [
                provider_filter.category_ids
                for provider_filter in attraction_task.request.provider_filters
            ],
            [INTENT_CATEGORY_PRESETS["temples"]],
        )

    def test_recommendation_type_category_mappings_do_not_overlap(self) -> None:
        category_sets = {
            kind: set(category_ids)
            for kind, category_ids in (
                FOURSQUARE_CATEGORY_IDS_BY_TRAVEL_REQUEST_KIND.items()
            )
        }

        for kind, category_ids in category_sets.items():
            unrelated_ids = set().union(
                *(
                    other_ids
                    for other_kind, other_ids in category_sets.items()
                    if other_kind is not kind
                )
            )
            with self.subTest(kind=kind.value):
                self.assertTrue(category_ids.isdisjoint(unrelated_ids))

    async def test_adapter_categories_reach_foursquare_http_parameters(self) -> None:
        task_inputs = (
            (
                TravelRequestKind.HOTEL,
                "hotels",
                "hotel",
                ((OFFICIAL_FOURSQUARE_CATEGORY_IDS[TravelRequestKind.HOTEL][0],),),
            ),
            (
                TravelRequestKind.RESTAURANT,
                "restaurants",
                None,
                (
                    (
                        OFFICIAL_FOURSQUARE_CATEGORY_IDS[
                            TravelRequestKind.RESTAURANT
                        ][0],
                    ),
                ),
            ),
            (
                TravelRequestKind.ATTRACTION,
                "attractions",
                None,
                tuple(GENERIC_ATTRACTION_GROUPS.values()),
            ),
        )

        for kind, group_query, provider_query, category_groups in task_inputs:
            with self.subTest(kind=kind.value):
                task = self._build_task(kind=kind, query=group_query)

                requests = await self._collect_provider_requests(task)

                self.assertEqual(
                    [
                        request.url.params["fsq_category_ids"]
                        for request in requests
                    ],
                    [",".join(category_group) for category_group in category_groups],
                )
                if provider_query is None:
                    self.assertTrue(
                        all("query" not in request.url.params for request in requests)
                    )
                else:
                    self.assertEqual(
                        {request.url.params["query"] for request in requests},
                        {provider_query},
                    )
                self.assertEqual(
                    len(requests),
                    len(category_groups),
                )

    def test_recommendation_engine_contains_no_foursquare_id_literals(self) -> None:
        engine_source = inspect.getsource(recommendation_engine)

        self.assertIsNone(
            re.search(r"\b[0-9a-f]{24}\b", engine_source)
        )


if __name__ == "__main__":
    unittest.main()
