"""Grouped Foursquare provider-filter contracts for recommendations."""

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
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
)
from app.recommendation_models import (  # noqa: E402
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class GroupedFoursquareProviderFilterTests(unittest.IsolatedAsyncioTestCase):
    def _build_attraction_request(
        self,
        *,
        provider_filters: tuple[FoursquareProviderFilter, ...] = (),
        categories: list[RecommendationCategory] | None = None,
    ) -> RecommendationRequest:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        request = RecommendationRequest(
            recommendationType="attraction",
            location=RecommendationLocation(
                displayName="Kandy",
                latitude=7.2906,
                longitude=80.6337,
                source="selected",
            ),
            travelMode="driving",
            travelPartner="couple",
            categories=(
                categories
                if categories is not None
                else [RecommendationCategory(name="attractions")]
            ),
            visitDate=tomorrow,
            startTime="09:00:00",
            visitDurationMinutes=180,
        )
        request.attach_provider_filters(provider_filters)
        return request

    async def _collect_provider_requests(
        self,
        request: RecommendationRequest,
        *,
        results: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def handler(http_request: httpx.Request) -> httpx.Response:
            requests.append(http_request)
            return httpx.Response(
                200,
                json={"results": results or []},
                request=http_request,
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
            candidates = await recommendation_engine._collect_candidates(request)

        return candidates, requests

    async def test_eight_id_group_produces_exactly_one_http_request(self) -> None:
        category_ids = GENERIC_ATTRACTION_GROUPS["heritage_and_culture"]
        request = self._build_attraction_request(
            provider_filters=(
                FoursquareProviderFilter(
                    query="attractions",
                    categoryIds=category_ids,
                ),
            )
        )

        _, requests = await self._collect_provider_requests(request)

        self.assertEqual(len(category_ids), 8)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            ",".join(category_ids),
        )

    async def test_second_group_adds_one_request_not_one_per_id(self) -> None:
        first_group = GENERIC_ATTRACTION_GROUPS["heritage_and_culture"]
        second_group = GENERIC_ATTRACTION_GROUPS["landscapes_and_water"]
        request = self._build_attraction_request(
            provider_filters=(
                FoursquareProviderFilter(
                    query="attractions",
                    categoryIds=first_group,
                ),
                FoursquareProviderFilter(
                    query="nature attractions",
                    categoryIds=second_group,
                ),
            )
        )

        _, requests = await self._collect_provider_requests(request)

        self.assertEqual(len(first_group) + len(second_group), 16)
        self.assertEqual(len(requests), 2)
        self.assertEqual(
            [request.url.params["fsq_category_ids"] for request in requests],
            [",".join(first_group), ",".join(second_group)],
        )

    async def test_grouped_filter_preserves_supplied_query_text(self) -> None:
        request = self._build_attraction_request(
            provider_filters=(
                FoursquareProviderFilter(
                    query="temples",
                    categoryIds=GENERIC_ATTRACTION_GROUPS[
                        "heritage_and_culture"
                    ],
                ),
            )
        )

        _, requests = await self._collect_provider_requests(request)

        self.assertEqual(requests[0].url.params["query"], "temples")

    async def test_legacy_single_category_id_caller_remains_supported(self) -> None:
        request = self._build_attraction_request(
            categories=[
                RecommendationCategory(
                    id=HOTEL_CATEGORY_ID,
                    name="hotel",
                )
            ]
        )

        _, requests = await self._collect_provider_requests(request)

        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            HOTEL_CATEGORY_ID,
        )
        self.assertEqual(requests[0].url.params["query"], "hotel")

    async def test_grouped_search_still_deduplicates_provider_places(self) -> None:
        request = self._build_attraction_request(
            provider_filters=(
                FoursquareProviderFilter(
                    query="attractions",
                    categoryIds=GENERIC_ATTRACTION_GROUPS[
                        "heritage_and_culture"
                    ],
                ),
                FoursquareProviderFilter(
                    query="nature attractions",
                    categoryIds=GENERIC_ATTRACTION_GROUPS[
                        "landscapes_and_water"
                    ],
                ),
            )
        )
        place = {
            "fsq_place_id": "same-place",
            "name": "Same Place",
            "latitude": 7.2906,
            "longitude": 80.6337,
            "location": {"country": "LK"},
        }

        candidates, requests = await self._collect_provider_requests(
            request,
            results=[place],
        )

        self.assertEqual(len(requests), 2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0]["matchedCategories"]), 2)
        self.assertEqual(
            {match["name"] for match in candidates[0]["matchedCategories"]},
            {"attractions", "nature attractions"},
        )
        self.assertTrue(
            all(
                match["id"] is None
                for match in candidates[0]["matchedCategories"]
            )
        )

    def test_provider_filter_accepts_eight_ids_and_deduplicates(self) -> None:
        category_ids = GENERIC_ATTRACTION_GROUPS["heritage_and_culture"]

        provider_filter = FoursquareProviderFilter(
            query="attractions",
            categoryIds=(
                *category_ids,
                f" {category_ids[0]} ",
            ),
        )

        self.assertEqual(provider_filter.category_ids, category_ids)

    def test_provider_filter_allows_category_only_constraint(self) -> None:
        provider_filter = FoursquareProviderFilter(
            categoryIds=GENERIC_ATTRACTION_GROUPS["heritage_and_culture"],
        )

        self.assertIsNone(provider_filter.query)
        self.assertEqual(len(provider_filter.category_ids), 8)

    def test_provider_filter_rejects_an_unconstrained_search(self) -> None:
        for query in (None, "", "   "):
            with self.subTest(query=query):
                with self.assertRaises(ValidationError):
                    FoursquareProviderFilter(query=query)

    def test_provider_filters_are_not_public_request_fields(self) -> None:
        provider_filter = FoursquareProviderFilter(
            query="attractions",
            categoryIds=GENERIC_ATTRACTION_GROUPS[
                "heritage_and_culture"
            ],
        )
        request = self._build_attraction_request(
            provider_filters=(provider_filter,)
        )

        self.assertNotIn("providerFilters", request.model_dump(by_alias=True))
        self.assertNotIn(
            "providerFilters",
            RecommendationRequest.model_json_schema()["properties"],
        )

        public_payload = request.model_dump(by_alias=True)
        public_payload["providerFilters"] = [provider_filter.model_dump(by_alias=True)]

        with self.assertRaises(ValidationError):
            RecommendationRequest.model_validate(public_payload)

    def test_semantic_category_limit_remains_three(self) -> None:
        categories = [
            RecommendationCategory(name=f"semantic category {index}")
            for index in range(4)
        ]

        with self.assertRaises(ValidationError):
            self._build_attraction_request(categories=categories)


if __name__ == "__main__":
    unittest.main()
