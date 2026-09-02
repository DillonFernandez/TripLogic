"""Foursquare discovery-pool and requested-output count contracts."""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import (  # noqa: E402
    conversation_recommendation_runner,
    recommendation_engine,
)
from app.conversation_models import (  # noqa: E402
    MAXIMUM_REQUESTED_RECOMMENDATIONS,
    TravelRequestGroup,
    TravelRequestKind,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    ConversationRecommendationTask,
)
from app.foursquare import MAXIMUM_SEARCH_RESULTS  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
)
from app.openrouteservice import MAXIMUM_MATRIX_LOCATIONS  # noqa: E402
from app.recommendation_models import (  # noqa: E402
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class RecommendationResultBudgetFoursquareTests(unittest.IsolatedAsyncioTestCase):
    def _provider_filters(
        self,
        recommendation_type: str,
    ) -> tuple[FoursquareProviderFilter, ...]:
        if recommendation_type == "hotel":
            return (
                FoursquareProviderFilter(
                    query="hotel",
                    categoryIds=(HOTEL_CATEGORY_ID,),
                ),
            )

        if recommendation_type == "restaurant":
            return (
                FoursquareProviderFilter(
                    query="restaurants",
                    categoryIds=(RESTAURANT_CATEGORY_ID,),
                ),
            )

        return tuple(
            FoursquareProviderFilter(
                categoryIds=category_ids,
                provenanceKey=f"generic:{group_name}",
            )
            for group_name, category_ids in GENERIC_ATTRACTION_GROUPS.items()
        )

    def _build_request(
        self,
        recommendation_type: str = "attraction",
        *,
        provider_filters: tuple[FoursquareProviderFilter, ...] | None = None,
    ) -> RecommendationRequest:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        common_fields: dict[str, Any] = {
            "recommendationType": recommendation_type,
            "location": RecommendationLocation(
                displayName="Kandy",
                latitude=7.2906,
                longitude=80.6337,
                source="selected",
            ),
            "travelMode": "driving",
            "travelPartner": "couple",
            "categories": [
                RecommendationCategory(name=f"{recommendation_type} search")
            ],
        }

        if recommendation_type == "hotel":
            common_fields["travellers"] = 2
        else:
            common_fields.update(
                {
                    "visitDate": tomorrow,
                    "startTime": "09:00:00",
                    "visitDurationMinutes": 180,
                }
            )

        request = RecommendationRequest(**common_fields)
        request.attach_provider_filters(
            provider_filters
            if provider_filters is not None
            else self._provider_filters(recommendation_type)
        )
        return request

    def _place(self, place_id: str) -> dict[str, Any]:
        return {
            "id": place_id,
            "name": f"Place {place_id}",
            "categories": [],
            "location": {
                "address": None,
                "locality": "Kandy",
                "region": "Central Province",
                "country": "Sri Lanka",
                "displayAddress": "Kandy, Sri Lanka",
            },
            "latitude": 7.2906,
            "longitude": 80.6337,
            "distanceMeters": 100,
            "telephone": None,
            "website": None,
        }

    async def _generate_from_candidate_count(
        self,
        *,
        candidate_count: int,
        requested_count: int | None,
    ) -> dict[str, Any]:
        candidates = [
            self._place(f"place-{index:02d}")
            | {
                "matchedCategories": [
                    {
                        "id": None,
                        "name": "attractions",
                        "providerFilterKey": "generic:heritage_and_culture",
                    }
                ],
                "bestSearchPosition": index,
            }
            for index in range(candidate_count)
        ]

        with (
            patch.object(
                recommendation_engine,
                "_collect_candidates",
                new=AsyncMock(return_value=candidates),
            ),
            patch.object(
                recommendation_engine,
                "_load_route_information",
                new=AsyncMock(return_value=None),
            ),
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
            return await recommendation_engine.generate_recommendations(
                self._build_request(),
                requested_count=requested_count,
            )

    @staticmethod
    def _returned_places(result: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            *result["topRecommendations"],
            *result["moreRecommendations"],
        ]

    def test_six_is_only_the_default_presentation_count(self) -> None:
        self.assertFalse(
            hasattr(recommendation_engine, "MAXIMUM_RECOMMENDATION_RESULTS")
        )
        self.assertEqual(recommendation_engine.DEFAULT_RECOMMENDATION_RESULTS, 6)
        self.assertEqual(
            recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES,
            MAXIMUM_MATRIX_LOCATIONS - 1,
        )
        self.assertEqual(
            recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES,
            19,
        )

    def test_requested_count_validation_matches_executable_capacity(self) -> None:
        self.assertEqual(MAXIMUM_REQUESTED_RECOMMENDATIONS, 19)
        self.assertEqual(
            MAXIMUM_REQUESTED_RECOMMENDATIONS,
            recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES,
        )

        for requested_count in (1, 19):
            with self.subTest(requested_count=requested_count):
                group = TravelRequestGroup(
                    id="request",
                    kind=TravelRequestKind.ATTRACTION,
                    query="attractions",
                    requestedCount=requested_count,
                )
                self.assertEqual(group.requested_count, requested_count)

        for requested_count in (0, 20):
            with self.subTest(requested_count=requested_count):
                with self.assertRaises(ValidationError):
                    TravelRequestGroup(
                        id="request",
                        kind=TravelRequestKind.ATTRACTION,
                        query="attractions",
                        requestedCount=requested_count,
                    )

    def test_provider_discovery_limits_follow_real_capacities(self) -> None:
        expected_limits = {
            1: 19,
            2: 10,
            4: 5,
        }

        for search_count, expected_limit in expected_limits.items():
            with self.subTest(search_count=search_count):
                actual_limit = (
                    recommendation_engine._provider_search_result_limit(
                        search_count
                    )
                )
                self.assertEqual(actual_limit, expected_limit)
                self.assertLessEqual(actual_limit, MAXIMUM_SEARCH_RESULTS)

    async def test_requested_counts_three_six_seven_and_ten_are_supported(self) -> None:
        for requested_count in (3, 6, 7, 10):
            with self.subTest(requested_count=requested_count):
                result = await self._generate_from_candidate_count(
                    candidate_count=10,
                    requested_count=requested_count,
                )

                self.assertEqual(result["count"], requested_count)
                self.assertEqual(
                    len(self._returned_places(result)),
                    requested_count,
                )

    async def test_executable_boundary_counts_return_exactly_without_padding(
        self,
    ) -> None:
        for requested_count in (1, 19):
            with self.subTest(requested_count=requested_count):
                result = await self._generate_from_candidate_count(
                    candidate_count=19,
                    requested_count=requested_count,
                )
                places = self._returned_places(result)

                self.assertEqual(result["count"], requested_count)
                self.assertEqual(len(places), requested_count)
                self.assertEqual(
                    len({place["id"] for place in places}),
                    requested_count,
                )

    async def test_engine_rejects_non_executable_twenty_before_discovery(
        self,
    ) -> None:
        collect = AsyncMock()

        with patch.object(
            recommendation_engine,
            "_collect_candidates",
            new=collect,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "between 1 and 19",
            ):
                await recommendation_engine.generate_recommendations(
                    self._build_request(),
                    requested_count=20,
                )

        collect.assert_not_awaited()

    async def test_ten_verified_candidates_can_return_ten(self) -> None:
        result = await self._generate_from_candidate_count(
            candidate_count=10,
            requested_count=10,
        )
        returned_places = self._returned_places(result)

        self.assertEqual(result["count"], 10)
        self.assertEqual(len(result["topRecommendations"]), 3)
        self.assertEqual(len(result["moreRecommendations"]), 7)
        self.assertEqual(len(returned_places), 10)
        self.assertEqual(
            len({place["id"] for place in returned_places}),
            10,
        )

    async def test_requested_ten_with_only_seven_returns_seven_without_padding(self) -> None:
        result = await self._generate_from_candidate_count(
            candidate_count=7,
            requested_count=10,
        )
        returned_places = self._returned_places(result)

        self.assertEqual(result["count"], 7)
        self.assertEqual(len(returned_places), 7)
        self.assertEqual(
            len({place["id"] for place in returned_places}),
            7,
        )

    async def test_absent_requested_count_preserves_default_six(self) -> None:
        result = await self._generate_from_candidate_count(
            candidate_count=10,
            requested_count=None,
        )

        self.assertEqual(result["count"], 6)
        self.assertEqual(len(result["topRecommendations"]), 3)
        self.assertEqual(len(result["moreRecommendations"]), 3)

    async def test_runner_passes_requested_output_count_to_engine(self) -> None:
        request = self._build_request()
        task = ConversationRecommendationTask(
            request_group_id="attraction-request",
            requested_count=10,
            required=True,
            request=request,
            traveller_query="attractions",
        )
        generated_result = {
            "count": 10,
            "topRecommendations": [self._place(f"top-{index}") for index in range(3)],
            "moreRecommendations": [
                self._place(f"more-{index}") for index in range(7)
            ],
        }
        generate = AsyncMock(return_value=generated_result)

        with (
            patch.object(
                conversation_recommendation_runner,
                "build_recommendation_tasks",
                return_value=[task],
            ),
            patch.object(
                conversation_recommendation_runner,
                "generate_recommendations",
                new=generate,
            ),
        ):
            grouped_results = await (
                conversation_recommendation_runner
                .generate_conversation_recommendations(Mock())
            )

        generate.assert_awaited_once_with(
            request,
            requested_count=10,
            include_internal_route_matrix=False,
        )
        self.assertEqual(grouped_results[0]["result"]["count"], 10)

    async def test_generic_collection_is_four_calls_and_fair_before_truncation(
        self,
    ) -> None:
        request = self._build_request()
        group_names = tuple(GENERIC_ATTRACTION_GROUPS)
        search_results = [
            [self._place(f"{group_name}-{index}") for index in range(5)]
            for group_name in group_names
        ]
        search = AsyncMock(side_effect=search_results)

        with patch.object(
            recommendation_engine,
            "search_places",
            new=search,
        ):
            candidates = await recommendation_engine._collect_candidates(request)

        self.assertEqual(search.await_count, 4)
        self.assertNotEqual(search.await_count, 28)
        self.assertEqual(len(candidates), 19)
        self.assertTrue(
            all(call.kwargs["limit"] == 5 for call in search.await_args_list)
        )
        self.assertTrue(
            all(call.kwargs["query"] is None for call in search.await_args_list)
        )
        self.assertEqual(
            [call.kwargs["category_ids"] for call in search.await_args_list],
            [list(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
        )

        provenance_counts = Counter(
            candidate["matchedCategories"][0]["providerFilterKey"]
            for candidate in candidates
        )
        self.assertEqual(sorted(provenance_counts.values()), [4, 5, 5, 5])
        self.assertEqual(
            set(provenance_counts),
            {f"generic:{group_name}" for group_name in group_names},
        )

    async def test_cross_group_deduplication_preserves_provenance_and_best_position(
        self,
    ) -> None:
        request = self._build_request()
        shared_place = self._place("shared")
        search_results = [
            [
                *[
                    self._place(f"group-{group_index}-{position}")
                    for position in range(shared_position)
                ],
                dict(shared_place),
                *[
                    self._place(f"tail-{group_index}-{position}")
                    for position in range(4 - shared_position)
                ],
            ]
            for group_index, shared_position in enumerate((4, 3, 2, 1))
        ]

        with patch.object(
            recommendation_engine,
            "search_places",
            new=AsyncMock(side_effect=search_results),
        ):
            candidates = await recommendation_engine._collect_candidates(request)

        shared_candidates = [
            candidate for candidate in candidates if candidate["id"] == "shared"
        ]

        self.assertEqual(len(shared_candidates), 1)
        self.assertEqual(shared_candidates[0]["bestSearchPosition"], 1)
        self.assertEqual(
            {
                match["providerFilterKey"]
                for match in shared_candidates[0]["matchedCategories"]
            },
            {
                f"generic:{group_name}"
                for group_name in GENERIC_ATTRACTION_GROUPS
            },
        )

    async def test_each_recommendation_type_retains_more_than_six_candidates(
        self,
    ) -> None:
        single_group_filters = {
            "hotel": self._provider_filters("hotel"),
            "restaurant": self._provider_filters("restaurant"),
            "attraction": (
                FoursquareProviderFilter(
                    query="museums",
                    categoryIds=INTENT_CATEGORY_PRESETS["museums"],
                    provenanceKey="intent:museums",
                ),
            ),
        }

        for recommendation_type, provider_filters in single_group_filters.items():
            with self.subTest(recommendation_type=recommendation_type):
                request = self._build_request(
                    recommendation_type,
                    provider_filters=provider_filters,
                )
                search = AsyncMock(
                    return_value=[
                        self._place(f"{recommendation_type}-{index}")
                        for index in range(10)
                    ]
                )

                with patch.object(
                    recommendation_engine,
                    "search_places",
                    new=search,
                ):
                    candidates = await recommendation_engine._collect_candidates(
                        request
                    )

                self.assertEqual(len(candidates), 10)
                self.assertEqual(search.await_count, 1)
                self.assertEqual(search.await_args.kwargs["limit"], 19)
                self.assertEqual(
                    search.await_args.kwargs["category_ids"],
                    list(provider_filters[0].category_ids),
                )


if __name__ == "__main__":
    unittest.main()
