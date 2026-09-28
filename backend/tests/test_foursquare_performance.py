"""Step 16 Foursquare provider quality and performance contracts."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    ATTRACTION_CATEGORIES,
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
)
from app.recommendation_models import (  # noqa: E402
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")
Handler = Callable[[httpx.Request], httpx.Response]


class FoursquarePerformanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        foursquare._reset_premium_metadata_capability()

    def tearDown(self) -> None:
        foursquare._reset_premium_metadata_capability()

    @staticmethod
    def _settings() -> SimpleNamespace:
        secret = Mock()
        secret.get_secret_value.return_value = "performance-test-key"
        return SimpleNamespace(foursquare_api_key=secret)

    @staticmethod
    def _raw_place(
        place_id: str,
        *,
        latitude: float = 7.2906,
        longitude: float = 80.6337,
        location: Any = None,
        rating: Any = None,
        hours: Any = None,
    ) -> dict[str, Any]:
        place = {
            "fsq_place_id": place_id,
            "name": f"Place {place_id}",
            "categories": [],
            "location": (
                {"locality": "Kandy", "country": "LK"}
                if location is None
                else location
            ),
            "latitude": latitude,
            "longitude": longitude,
            "distance": 100,
        }

        if rating is not None:
            place["rating"] = rating

        if hours is not None:
            place["hours"] = hours

        return place

    @staticmethod
    def _candidate(place_id: str) -> dict[str, Any]:
        return {
            "id": place_id,
            "name": f"Place {place_id}",
            "categories": [],
            "location": {
                "address": None,
                "locality": "Kandy",
                "region": "Central Province",
                "country": "Sri Lanka",
                "displayAddress": "Kandy, Central Province, Sri Lanka",
            },
            "latitude": 7.2906,
            "longitude": 80.6337,
            "distanceMeters": 100,
            "telephone": None,
            "website": None,
            "rating": None,
            "hours": None,
        }

    def _request(
        self,
        *,
        recommendation_type: str = "attraction",
        provider_filters: tuple[FoursquareProviderFilter, ...] | None = None,
    ) -> RecommendationRequest:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        fields: dict[str, Any] = {
            "recommendationType": recommendation_type,
            "location": RecommendationLocation(
                displayName="Kandy",
                localityName="Kandy",
                latitude=7.2906,
                longitude=80.6337,
                source="selected",
                countryCode="LK",
            ),
            "travelMode": "driving",
            "travelPartner": "couple",
            "categories": [RecommendationCategory(name=recommendation_type)],
        }

        if recommendation_type != "hotel":
            fields.update(
                {
                    "visitDate": tomorrow,
                    "startTime": "09:00:00",
                    "visitDurationMinutes": 180,
                }
            )

        request = RecommendationRequest(**fields)

        if provider_filters is None:
            if recommendation_type == "hotel":
                provider_filters = (
                    FoursquareProviderFilter(
                        query="hotel",
                        categoryIds=(HOTEL_CATEGORY_ID,),
                    ),
                )
            elif recommendation_type == "restaurant":
                provider_filters = (
                    FoursquareProviderFilter(
                        categoryIds=(RESTAURANT_CATEGORY_ID,),
                    ),
                )
            else:
                provider_filters = tuple(
                    FoursquareProviderFilter(
                        categoryIds=category_ids,
                        provenanceKey=f"generic:{group_name}",
                    )
                    for group_name, category_ids in GENERIC_ATTRACTION_GROUPS.items()
                )

        request.attach_provider_filters(provider_filters)
        return request

    async def _transport_candidates(
        self,
        request: RecommendationRequest,
        handler: Handler,
    ) -> tuple[list[dict[str, Any]], list[httpx.Request], list[httpx.AsyncClient]]:
        requests: list[httpx.Request] = []
        clients: list[httpx.AsyncClient] = []

        def captured_handler(http_request: httpx.Request) -> httpx.Response:
            requests.append(http_request)
            return handler(http_request)

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            client = REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(captured_handler),
                **kwargs,
            )
            clients.append(client)
            return client

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=self._settings()),
            patch.object(foursquare.asyncio, "sleep", new=AsyncMock()),
        ):
            candidates = await recommendation_engine._collect_candidates(request)

        return candidates, requests, clients

    async def test_grouped_searches_share_one_closed_task_client(self) -> None:
        request = self._request()

        candidates, requests, clients = await self._transport_candidates(
            request,
            lambda http_request: httpx.Response(
                200,
                json={
                    "results": [
                        self._raw_place(
                            http_request.url.params["fsq_category_ids"].split(",")[0]
                        )
                    ]
                },
                request=http_request,
            ),
        )

        self.assertEqual(len(requests), 4)
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].is_closed)
        self.assertEqual(len(candidates), 4)

    async def test_direct_search_owns_and_closes_one_client(self) -> None:
        clients: list[httpx.AsyncClient] = []

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            client = REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"results": []},
                        request=request,
                    )
                ),
                **kwargs,
            )
            clients.append(client)
            return client

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=self._settings()),
        ):
            places = await foursquare.search_places(
                latitude=7.2906,
                longitude=80.6337,
                category_ids=[RESTAURANT_CATEGORY_ID],
            )

        self.assertEqual(places, [])
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].is_closed)

    async def test_groups_run_concurrently_but_results_keep_filter_order(self) -> None:
        request = self._request()
        groups = list(GENERIC_ATTRACTION_GROUPS.values())
        group_index_by_ids = {
            tuple(category_ids): index
            for index, category_ids in enumerate(groups)
        }
        started: set[int] = set()
        completed: list[int] = []
        all_started = asyncio.Event()
        releases = [asyncio.Event() for _ in groups]

        async def search(**kwargs: Any) -> list[dict[str, Any]]:
            index = group_index_by_ids[tuple(kwargs["category_ids"])]
            started.add(index)

            if len(started) == len(groups):
                all_started.set()

            await releases[index].wait()
            completed.append(index)
            return [self._candidate(f"group-{index}")]

        async def release_in_reverse_order() -> None:
            await asyncio.wait_for(all_started.wait(), timeout=1.0)

            for index in reversed(range(len(groups))):
                releases[index].set()
                await asyncio.sleep(0)

        releaser = asyncio.create_task(release_in_reverse_order())

        with patch.object(recommendation_engine, "search_places", new=search):
            candidates = await recommendation_engine._collect_candidates(request)

        await releaser

        self.assertEqual(started, set(range(4)))
        self.assertEqual(completed, [3, 2, 1, 0])
        self.assertEqual(
            [candidate["id"] for candidate in candidates],
            ["group-0", "group-1", "group-2", "group-3"],
        )

    async def test_identical_filters_share_one_call_and_keep_provenance(self) -> None:
        category_ids = tuple(
            GENERIC_ATTRACTION_GROUPS["heritage_and_culture"]
        )
        request = self._request(
            provider_filters=(
                FoursquareProviderFilter(
                    query="museums",
                    categoryIds=category_ids,
                    provenanceKey="intent:first",
                ),
                FoursquareProviderFilter(
                    query="museums",
                    categoryIds=tuple(reversed(category_ids)),
                    provenanceKey="intent:second",
                ),
            )
        )
        search = AsyncMock(return_value=[self._candidate("shared")])

        with patch.object(recommendation_engine, "search_places", new=search):
            candidates = await recommendation_engine._collect_candidates(request)

        self.assertEqual(search.await_count, 1)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            {
                match["providerFilterKey"]
                for match in candidates[0]["matchedCategories"]
            },
            {"intent:first", "intent:second"},
        )

    async def test_place_ids_are_merged_before_downstream_enrichment(self) -> None:
        groups = list(GENERIC_ATTRACTION_GROUPS.values())[:2]
        request = self._request(
            provider_filters=tuple(
                FoursquareProviderFilter(
                    categoryIds=category_ids,
                    provenanceKey=f"intent:{index}",
                )
                for index, category_ids in enumerate(groups)
            )
        )
        search = AsyncMock(
            side_effect=[
                [self._candidate("duplicate")],
                [self._candidate("duplicate")],
            ]
        )
        route = AsyncMock(return_value=None)

        with (
            patch.object(recommendation_engine, "search_places", new=search),
            patch.object(recommendation_engine, "_load_route_information", new=route),
            patch.object(
                recommendation_engine,
                "_load_location_weather_summary",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                recommendation_engine,
                "_load_candidate_weather_information",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await recommendation_engine.generate_recommendations(request)

        enriched_candidates = route.await_args.args[1]
        self.assertEqual(len(enriched_candidates), 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(
            {
                match["providerFilterKey"]
                for match in enriched_candidates[0]["matchedCategories"]
            },
            {"intent:0", "intent:1"},
        )

    async def test_partial_group_failure_keeps_verified_sibling_candidates(
        self,
    ) -> None:
        groups = list(GENERIC_ATTRACTION_GROUPS.values())[:2]
        request = self._request(
            provider_filters=tuple(
                FoursquareProviderFilter(categoryIds=category_ids)
                for category_ids in groups
            )
        )
        search = AsyncMock(
            side_effect=[
                [self._candidate("verified")],
                HTTPException(status_code=503, detail="provider unavailable"),
            ]
        )

        with patch.object(recommendation_engine, "search_places", new=search):
            candidates = await recommendation_engine._collect_candidates(request)

        self.assertEqual([candidate["id"] for candidate in candidates], ["verified"])

    async def test_total_group_failure_raises_the_first_provider_error(self) -> None:
        groups = list(GENERIC_ATTRACTION_GROUPS.values())[:2]
        request = self._request(
            provider_filters=tuple(
                FoursquareProviderFilter(categoryIds=category_ids)
                for category_ids in groups
            )
        )
        first_error = HTTPException(status_code=504, detail="first timeout")
        search = AsyncMock(
            side_effect=[
                first_error,
                HTTPException(status_code=503, detail="second failure"),
            ]
        )

        with (
            patch.object(recommendation_engine, "search_places", new=search),
            self.assertRaises(HTTPException) as raised,
        ):
            await recommendation_engine._collect_candidates(request)

        self.assertIs(raised.exception, first_error)

    async def test_empty_and_nonempty_groups_remain_deterministic_without_padding(
        self,
    ) -> None:
        request = self._request()
        search = AsyncMock(
            side_effect=[
                [],
                [self._candidate("second")],
                [],
                [self._candidate("fourth")],
            ]
        )

        with patch.object(recommendation_engine, "search_places", new=search):
            candidates = await recommendation_engine._collect_candidates(request)

        self.assertEqual(
            [candidate["id"] for candidate in candidates],
            ["second", "fourth"],
        )

    async def test_malformed_rows_do_not_discard_valid_optional_null_sibling(
        self,
    ) -> None:
        valid = self._raw_place(
            "valid",
            location="malformed location",
            rating="bad rating",
            hours={"regular": [{"day": 1, "open": "bad", "close": "1700"}]},
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"name": "Missing ID"},
                        self._raw_place("bad-coordinate", latitude=91),
                        valid,
                    ]
                },
                request=request,
            )

        request = self._request(recommendation_type="restaurant")
        candidates, _, _ = await self._transport_candidates(request, handler)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "valid")
        self.assertIsNone(candidates[0]["location"]["displayAddress"])
        self.assertIsNone(candidates[0]["rating"])
        self.assertIsNone(candidates[0]["hours"])

    async def test_concurrent_groups_share_one_premium_probe_and_one_client(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return httpx.Response(
                    403,
                    json={
                        "message": (
                            "rating and hours are not available on this plan"
                        )
                    },
                    request=request,
                )

            return httpx.Response(
                200,
                json={"results": []},
                request=request,
            )

        _, requests, clients = await self._transport_candidates(
            self._request(),
            handler,
        )
        premium_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS
        ]
        base_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.BASE_SEARCH_FIELDS
        ]

        self.assertEqual(len(clients), 1)
        self.assertEqual(len(premium_requests), 1)
        self.assertEqual(len(base_requests), 4)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNAVAILABLE,
        )

    async def test_client_closes_when_an_unexpected_group_failure_propagates(
        self,
    ) -> None:
        clients: list[httpx.AsyncClient] = []

        def make_client() -> httpx.AsyncClient:
            client = REAL_ASYNC_CLIENT()
            clients.append(client)
            return client

        with (
            patch.object(
                recommendation_engine,
                "create_search_client",
                side_effect=make_client,
            ),
            patch.object(
                recommendation_engine,
                "search_places",
                new=AsyncMock(side_effect=RuntimeError("unexpected")),
            ),
            self.assertRaises(RuntimeError),
        ):
            await recommendation_engine._collect_candidates(self._request())

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].is_closed)

    async def test_client_closes_when_group_collection_is_cancelled(self) -> None:
        clients: list[httpx.AsyncClient] = []

        def make_client() -> httpx.AsyncClient:
            client = REAL_ASYNC_CLIENT()
            clients.append(client)
            return client

        with (
            patch.object(
                recommendation_engine,
                "create_search_client",
                side_effect=make_client,
            ),
            patch.object(
                recommendation_engine,
                "search_places",
                new=AsyncMock(side_effect=asyncio.CancelledError()),
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await recommendation_engine._collect_candidates(self._request())

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].is_closed)

    async def test_call_budgets_and_prior_stage_invariants_are_unchanged(self) -> None:
        self.assertEqual(
            recommendation_engine._provider_search_result_limit(1),
            19,
        )
        self.assertEqual(
            recommendation_engine._provider_search_result_limit(4),
            5,
        )
        self.assertEqual(recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES, 19)
        self.assertEqual(recommendation_engine.DEFAULT_RECOMMENDATION_RESULTS, 6)
        self.assertEqual(len(GENERIC_ATTRACTION_GROUPS), 4)
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )
        self.assertEqual(len(ATTRACTION_CATEGORIES), 76)
        self.assertEqual(len(INTENT_CATEGORY_PRESETS), 15)
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(
            foursquare.BASE_SEARCH_FIELDS.split(","),
            [
                "fsq_place_id",
                "name",
                "categories",
                "location",
                "latitude",
                "longitude",
                "distance",
            ],
        )
        self.assertEqual(
            foursquare.APPROVED_PREMIUM_SEARCH_FIELDS,
            ("rating", "hours"),
        )
        self.assertTrue(
            {"tel", "website", "description"}.isdisjoint(
                foursquare.SEARCH_FIELDS.split(",")
            )
        )


if __name__ == "__main__":
    unittest.main()
