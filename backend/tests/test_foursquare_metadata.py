"""Step 15 contracts for optional Foursquare rating and opening hours."""

from __future__ import annotations

import json
import math
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    ATTRACTION_CATEGORIES,
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    RESTAURANT_CATEGORY_ID,
)
from app.recommendation_models import (  # noqa: E402
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient


class FoursquareMetadataTests(unittest.IsolatedAsyncioTestCase):
    def _raw_place(self, **overrides: Any) -> dict[str, Any]:
        place: dict[str, Any] = {
            "fsq_place_id": "provider-place",
            "name": "Provider Place",
            "categories": [
                {
                    "fsq_category_id": RESTAURANT_CATEGORY_ID,
                    "name": "Restaurant",
                }
            ],
            "location": {
                "locality": "Kandy",
                "country": "LK",
            },
            "latitude": 7.291,
            "longitude": 80.634,
            "distance": 75,
        }
        place.update(overrides)
        return place

    def _request(self) -> RecommendationRequest:
        request = RecommendationRequest(
            recommendationType="restaurant",
            location=RecommendationLocation(
                displayName="Kandy, Sri Lanka",
                localityName="Kandy",
                latitude=7.2906,
                longitude=80.6337,
                source="selected",
                countryCode="LK",
            ),
            categories=[RecommendationCategory(name="Restaurant")],
        )
        request.attach_provider_filters(
            [
                FoursquareProviderFilter(
                    query=None,
                    categoryIds=(RESTAURANT_CATEGORY_ID,),
                    provenanceKey="restaurant",
                )
            ]
        )
        request.attach_route_origin(None)
        return request

    async def _captured_search_request(self) -> httpx.Request:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                content=json.dumps({"results": []}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "metadata-contract-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            await foursquare.search_places(
                query=None,
                latitude=7.2906,
                longitude=80.6337,
                near="Kandy, Sri Lanka",
                category_ids=[RESTAURANT_CATEGORY_ID],
                radius=12_000,
            )

        self.assertEqual(len(requests), 1)
        return requests[0]

    async def test_search_requests_rating_hours_and_existing_fields(self) -> None:
        request = await self._captured_search_request()
        fields = request.url.params["fields"].split(",")

        self.assertIn("rating", fields)
        self.assertIn("hours", fields)
        for required_field in (
            "fsq_place_id",
            "name",
            "categories",
            "location",
            "latitude",
            "longitude",
            "distance",
        ):
            self.assertIn(required_field, fields)
        for declined_field in ("tel", "website", "description"):
            self.assertNotIn(declined_field, fields)

        self.assertEqual(request.url.params["near"], "Kandy, Sri Lanka")
        self.assertNotIn("query", request.url.params)
        self.assertEqual(
            request.url.params["fsq_category_ids"],
            RESTAURANT_CATEGORY_ID,
        )

    def test_valid_rating_uses_native_foursquare_scale(self) -> None:
        place = foursquare._normalize_place(self._raw_place(rating=8.7))

        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(place["rating"], 8.7)
        self.assertNotIn("stars", place)
        self.assertNotIn("starRating", place)
        self.assertNotIn("hotelStars", place)

    def test_missing_and_invalid_ratings_remain_unavailable(self) -> None:
        invalid_ratings = (
            None,
            "8.7",
            {"value": 8.7},
            True,
            math.nan,
            math.inf,
            -math.inf,
            -0.1,
            10.1,
        )

        for rating in invalid_ratings:
            with self.subTest(rating=rating):
                place = foursquare._normalize_place(
                    self._raw_place(rating=rating)
                )
                self.assertIsNotNone(place)
                assert place is not None
                self.assertIsNone(place["rating"])

    def test_single_and_multiple_regular_intervals_are_preserved(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                hours={
                    "regular": [
                        {"day": 1, "open": "0900", "close": "1200"},
                        {"day": 1, "open": "14:00", "close": "18:00"},
                        {"day": 2, "open": "0800", "close": "1700"},
                    ],
                    "open_now": True,
                    "is_local_holiday": False,
                    "display": "  Mon 9:00 AM-6:00 PM  ",
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(
            place["hours"],
            {
                "regular": [
                    {
                        "day": 1,
                        "openingTime": "09:00",
                        "closingTime": "12:00",
                        "overnight": False,
                        "allDay": False,
                    },
                    {
                        "day": 1,
                        "openingTime": "14:00",
                        "closingTime": "18:00",
                        "overnight": False,
                        "allDay": False,
                    },
                    {
                        "day": 2,
                        "openingTime": "08:00",
                        "closingTime": "17:00",
                        "overnight": False,
                        "allDay": False,
                    },
                ],
                "openNow": True,
                "isLocalHoliday": False,
                "display": "Mon 9:00 AM-6:00 PM",
            },
        )

    def test_overnight_and_explicit_all_day_intervals_are_preserved(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                hours={
                    "regular": [
                        {"day": 5, "open": "1800", "close": "+0200"},
                        {"day": 6, "open": "18:00", "close": "02:00"},
                        {"day": 7, "open": "0000", "close": "2400"},
                    ]
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        intervals = place["hours"]["regular"]
        self.assertEqual(
            intervals[0],
            {
                "day": 5,
                "openingTime": "18:00",
                "closingTime": "02:00",
                "overnight": True,
                "allDay": False,
            },
        )
        self.assertTrue(intervals[1]["overnight"])
        self.assertEqual(
            intervals[2],
            {
                "day": 7,
                "openingTime": "00:00",
                "closingTime": "24:00",
                "overnight": False,
                "allDay": True,
            },
        )

    def test_missing_or_wholly_malformed_hours_remain_unavailable(self) -> None:
        malformed_hours = (
            None,
            "09:00-17:00",
            [],
            {},
            {"regular": "not-a-list"},
            {"regular": [{"day": 8, "open": "0900", "close": "1700"}]},
        )

        for hours in malformed_hours:
            with self.subTest(hours=hours):
                place = foursquare._normalize_place(self._raw_place(hours=hours))
                self.assertIsNotNone(place)
                assert place is not None
                self.assertIsNone(place["hours"])

    def test_malformed_intervals_are_skipped_without_fabrication(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                hours={
                    "regular": [
                        {"day": 1, "open": "not-time", "close": "1700"},
                        {"day": 1, "open": "0:900", "close": "1700"},
                        {"day": True, "open": "0900", "close": "1700"},
                        {"day": 2, "open": "0900", "close": "1760"},
                        {"day": 3, "open": "1000", "close": "1900"},
                    ]
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(
            place["hours"]["regular"],
            [
                {
                    "day": 3,
                    "openingTime": "10:00",
                    "closingTime": "19:00",
                    "overnight": False,
                    "allDay": False,
                }
            ],
        )

    async def test_verified_metadata_serializes_in_recommendation_output(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                rating=9.1,
                hours={
                    "regular": [
                        {"day": 1, "open": "0900", "close": "1700"}
                    ]
                },
            )
        )
        self.assertIsNotNone(place)

        with patch.object(
            recommendation_engine,
            "search_places",
            return_value=[place],
        ):
            result = await recommendation_engine.generate_recommendations(
                self._request()
            )

        self.assertEqual(result["count"], 1)
        candidate = result["topRecommendations"][0]
        self.assertEqual(candidate["rating"], 9.1)
        self.assertEqual(candidate["hours"]["regular"][0]["day"], 1)

    async def test_missing_metadata_serializes_as_null_without_rejection(self) -> None:
        place = foursquare._normalize_place(self._raw_place())
        self.assertIsNotNone(place)

        with patch.object(
            recommendation_engine,
            "search_places",
            return_value=[place],
        ):
            result = await recommendation_engine.generate_recommendations(
                self._request()
            )

        self.assertEqual(result["count"], 1)
        candidate = result["topRecommendations"][0]
        self.assertIsNone(candidate["rating"])
        self.assertIsNone(candidate["hours"])

    def test_hours_are_not_inferred_from_name_category_or_query(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(name="24 Hour Breakfast Restaurant")
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertIsNone(place["hours"])

    async def test_current_closed_status_is_not_future_closure_proof(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                hours={
                    "regular": [
                        {"day": 1, "open": "0900", "close": "1700"}
                    ],
                    "open_now": False,
                }
            )
        )
        self.assertIsNotNone(place)

        with patch.object(
            recommendation_engine,
            "search_places",
            return_value=[place],
        ):
            result = await recommendation_engine.generate_recommendations(
                self._request()
            )

        self.assertEqual(result["count"], 1)
        candidate = result["topRecommendations"][0]
        self.assertFalse(candidate["hours"]["openNow"])
        self.assertNotIn("openingHoursFeasibility", candidate)
        self.assertNotIn("closed", candidate["explanation"].casefold())

    def test_rating_does_not_invent_a_new_scoring_weight(self) -> None:
        base_candidate = {
            "id": "one",
            "name": "Same Place",
            "categories": [{"id": RESTAURANT_CATEGORY_ID, "name": "Restaurant"}],
            "matchedCategories": [],
            "bestSearchPosition": 0,
            "route": {"available": False},
            "weather": None,
        }
        rated_candidate = deepcopy(base_candidate)
        rated_candidate["id"] = "rated"
        rated_candidate["rating"] = 10.0
        unrated_candidate = deepcopy(base_candidate)
        unrated_candidate["id"] = "unrated"
        unrated_candidate["rating"] = None
        candidates = [rated_candidate, unrated_candidate]

        recommendation_engine._score_candidates(self._request(), candidates)

        scores = {candidate["id"]: candidate["score"] for candidate in candidates}
        self.assertEqual(scores["rated"], scores["unrated"])
        for candidate in candidates:
            self.assertNotIn("rating", candidate["scoreBreakdown"])

    def test_metadata_change_preserves_provider_and_scope_invariants(self) -> None:
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(len(ATTRACTION_CATEGORIES), 76)
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )
        self.assertEqual(
            recommendation_engine.SEARCH_RADIUS_BY_TYPE,
            {"attraction": 25_000, "hotel": 20_000, "restaurant": 12_000},
        )
        self.assertEqual(recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES, 19)


if __name__ == "__main__":
    unittest.main()
