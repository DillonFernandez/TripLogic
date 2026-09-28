"""Hotel place-discovery contracts independent of accommodation planning."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.conversation_context_requirements import (  # noqa: E402
    MISSING_FINAL_ENDING_LOCATION,
    MISSING_STARTING_LOCATION,
    MISSING_TRAVELLER_COUNT,
    MISSING_TRIP_END_DATE,
    MISSING_TRIP_START_DATE,
    compute_missing_fields,
)
from app.conversation_models import (  # noqa: E402
    FixedTravelPlace,
    FixedTravelPlaceRole,
    TravelContext,
    TravelContextStage,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
    TravellerType,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    RESTAURANT_CATEGORY_ID,
)
from app.openrouteservice import MAXIMUM_MATRIX_LOCATIONS  # noqa: E402
from app.recommendation_models import (  # noqa: E402
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class HotelDiscoveryFoursquareTests(unittest.IsolatedAsyncioTestCase):
    def _location(
        self,
        name: str,
        latitude: float,
        longitude: float,
    ) -> TravelLocation:
        return TravelLocation(
            displayName=name,
            source=TravelLocationSource.SEARCHED,
            latitude=latitude,
            longitude=longitude,
            countryCode="LK",
            verified=True,
        )

    def _context(
        self,
        *,
        search_location: TravelLocation,
        origin: TravelLocation | None = None,
        trip_start_date: object = None,
        trip_end_date: object = None,
        traveller_count: int | None = None,
        fixed_places: list[FixedTravelPlace] | None = None,
        confirmed: bool = True,
        complete_itinerary: bool = False,
        query: str = "hotels",
    ) -> TravelContext:
        return TravelContext(
            stage=(
                TravelContextStage.CONFIRMED
                if confirmed
                else TravelContextStage.COLLECTING
            ),
            startingLocation=origin,
            tripStartDate=trip_start_date,
            tripEndDate=trip_end_date,
            travellerType=TravellerType.COUPLE,
            travellerCount=traveller_count,
            travelModes=["driving"],
            requestGroups=[
                TravelRequestGroup(
                    id="hotel-request",
                    kind=TravelRequestKind.HOTEL,
                    query=query,
                    searchLocation=search_location,
                )
            ],
            fixedPlaces=fixed_places or [],
            missingFields=[],
            uncertainties=[],
            isConfirmed=confirmed,
            requiresCompleteItinerary=complete_itinerary,
        )

    def _direct_request(self, **hotel_fields: Any) -> RecommendationRequest:
        fields: dict[str, Any] = {
            "recommendationType": "hotel",
            "location": RecommendationLocation(
                displayName="Kandy",
                latitude=7.2906,
                longitude=80.6336,
                source="selected",
            ),
            "travelMode": "driving",
            "travelPartner": "couple",
            "categories": [RecommendationCategory(name="hotel")],
        }
        fields.update(hotel_fields)
        return RecommendationRequest(**fields)

    @staticmethod
    def _place(
        place_id: str = "hotel-1",
        name: str = "Verified Hotel",
    ) -> dict[str, Any]:
        return {
            "id": place_id,
            "name": name,
            "categories": [{"id": HOTEL_CATEGORY_ID, "name": "Hotel"}],
            "location": {
                "address": None,
                "locality": "Kandy",
                "region": "Central Province",
                "country": "Sri Lanka",
                "displayAddress": "Kandy, Sri Lanka",
            },
            "latitude": 7.2906,
            "longitude": 80.6336,
            "distanceMeters": 100,
            "telephone": None,
            "website": None,
        }

    def test_simple_hotel_discovery_needs_no_stay_or_guest_metadata(self) -> None:
        context = self._context(
            search_location=self._location("Kandy", 7.2906, 80.6336),
        )

        missing_fields = compute_missing_fields(context)
        task = build_recommendation_tasks(context)[0]

        self.assertNotIn(MISSING_STARTING_LOCATION, missing_fields)
        self.assertNotIn(MISSING_TRIP_START_DATE, missing_fields)
        self.assertNotIn(MISSING_TRIP_END_DATE, missing_fields)
        self.assertNotIn(MISSING_TRAVELLER_COUNT, missing_fields)
        self.assertTrue(context.is_ready_for_confirmation)
        self.assertEqual(task.request.location.display_name, "Kandy")
        self.assertIsNone(task.request.check_in_date)
        self.assertIsNone(task.request.check_out_date)
        self.assertIsNone(task.request.travellers)

    def test_simple_hotel_phrasings_build_one_canonical_provider_filter(self) -> None:
        cases = (
            ("hotels in Kandy", "Kandy", 7.2906, 80.6336),
            ("show me some hotels in Galle", "Galle", 6.0461, 80.2103),
            ("good hotels in Ella", "Ella", 6.8756, 81.0463),
            (
                "find a hotel around Nuwara Eliya",
                "Nuwara Eliya",
                6.97078,
                80.78286,
            ),
        )

        for query, name, latitude, longitude in cases:
            with self.subTest(query=query):
                task = build_recommendation_tasks(
                    self._context(
                        search_location=self._location(
                            name,
                            latitude,
                            longitude,
                        ),
                        query=query,
                    )
                )[0]

                self.assertEqual(task.request.location.display_name, name)
                self.assertEqual(len(task.request.provider_filters), 1)
                self.assertEqual(
                    task.request.provider_filters[0].category_ids,
                    (HOTEL_CATEGORY_ID,),
                )
                self.assertEqual(task.request.provider_filters[0].query, "hotel")

    def test_request_accepts_missing_dates_and_travellers(self) -> None:
        request = self._direct_request()

        self.assertIsNone(request.check_in_date)
        self.assertIsNone(request.check_out_date)
        self.assertIsNone(request.travellers)
        self.assertIsNone(request.stay_duration_days)

    def test_partial_optional_stay_metadata_does_not_block_discovery(self) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        check_in_only = self._direct_request(checkInDate=tomorrow)
        travellers_only = self._direct_request(travellers=2)

        self.assertEqual(check_in_only.check_in_date, tomorrow)
        self.assertIsNone(check_in_only.check_out_date)
        self.assertEqual(travellers_only.travellers, 2)

    def test_same_day_metadata_is_valid_for_place_discovery(self) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        request = self._direct_request(
            checkInDate=tomorrow,
            checkOutDate=tomorrow,
        )

        self.assertEqual(request.check_in_date, tomorrow)
        self.assertEqual(request.check_out_date, tomorrow)
        self.assertEqual(request.stay_duration_days, 0)

        with self.assertRaises(ValidationError):
            self._direct_request(
                checkInDate=tomorrow + timedelta(days=1),
                checkOutDate=tomorrow,
            )

    async def test_same_day_context_reaches_foursquare_without_fake_checkout(
        self,
    ) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        task = build_recommendation_tasks(
            self._context(
                search_location=self._location("Galle", 6.0461, 80.2103),
                trip_start_date=tomorrow,
                trip_end_date=tomorrow,
            )
        )[0]
        search = AsyncMock(return_value=[])

        with patch.object(
            recommendation_engine,
            "search_places",
            new=search,
        ):
            await recommendation_engine._collect_candidates(task.request)

        self.assertIsNone(task.request.check_in_date)
        self.assertIsNone(task.request.check_out_date)
        self.assertEqual(search.await_count, 1)
        self.assertEqual(search.await_args.kwargs["latitude"], 6.0461)
        self.assertEqual(search.await_args.kwargs["longitude"], 80.2103)
        self.assertEqual(
            search.await_args.kwargs["category_ids"],
            [HOTEL_CATEGORY_ID],
        )
        self.assertNotIn("check_in_date", search.await_args.kwargs)
        self.assertNotIn("check_out_date", search.await_args.kwargs)

    async def test_http_request_contains_no_booking_or_guest_semantics(self) -> None:
        request = build_recommendation_tasks(
            self._context(
                search_location=self._location("Kandy", 7.2906, 80.6336),
            )
        )[0].request
        requests: list[httpx.Request] = []
        real_async_client = httpx.AsyncClient

        def handler(http_request: httpx.Request) -> httpx.Response:
            requests.append(http_request)
            return httpx.Response(
                200,
                json={"results": []},
                request=http_request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return real_async_client(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "hotel-contract-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(
                foursquare.httpx,
                "AsyncClient",
                side_effect=make_client,
            ),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            await recommendation_engine._collect_candidates(request)

        self.assertEqual(len(requests), 1)
        params = requests[0].url.params
        self.assertEqual(params["query"], "hotel")
        self.assertEqual(params["ll"], "7.2906,80.6336")
        self.assertEqual(params["fsq_category_ids"], HOTEL_CATEGORY_ID)
        self.assertEqual(params["radius"], "20000")
        for forbidden_parameter in (
            "availability",
            "checkInDate",
            "checkOutDate",
            "travellers",
            "rooms",
        ):
            self.assertNotIn(forbidden_parameter, params)

    def test_valid_multiday_dates_are_preserved_as_optional_metadata(self) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        checkout = tomorrow + timedelta(days=2)

        task = build_recommendation_tasks(
            self._context(
                search_location=self._location("Ella", 6.8756, 81.0463),
                trip_start_date=tomorrow,
                trip_end_date=checkout,
                traveller_count=2,
            )
        )[0]

        self.assertEqual(task.request.check_in_date, tomorrow)
        self.assertEqual(task.request.check_out_date, checkout)
        self.assertEqual(task.request.stay_duration_days, 2)
        self.assertEqual(task.request.travellers, 2)
        self.assertEqual(
            task.request.provider_filters[0].category_ids,
            (HOTEL_CATEGORY_ID,),
        )

    async def test_no_origin_discovers_and_keeps_route_and_weather_unavailable(
        self,
    ) -> None:
        request = build_recommendation_tasks(
            self._context(
                search_location=self._location("Kandy", 7.2906, 80.6336),
            )
        )[0].request
        route_matrix = AsyncMock()
        weather = AsyncMock()

        with (
            patch.object(
                recommendation_engine,
                "search_places",
                new=AsyncMock(return_value=[self._place()]),
            ),
            patch.object(
                recommendation_engine,
                "get_route_matrix",
                new=route_matrix,
            ),
            patch.object(
                recommendation_engine,
                "get_weather_forecast",
                new=weather,
            ),
        ):
            result = await recommendation_engine.generate_recommendations(request)

        returned = result["topRecommendations"][0]
        self.assertEqual(result["count"], 1)
        self.assertIsNone(result["weather"])
        self.assertFalse(returned["route"]["available"])
        self.assertIsNone(returned["route"]["durationSeconds"])
        route_matrix.assert_not_awaited()
        weather.assert_not_awaited()

    async def test_origin_and_search_locality_keep_distinct_provider_roles(
        self,
    ) -> None:
        origin = self._location("Colombo", 6.93548, 79.84868)
        search_location = self._location("Galle", 6.0461, 80.2103)
        final_end = FixedTravelPlace(
            id="end-matara",
            name="Matara",
            role=FixedTravelPlaceRole.END_POINT,
            location=self._location("Matara", 5.9485, 80.5353),
        )
        request = build_recommendation_tasks(
            self._context(
                search_location=search_location,
                origin=origin,
                fixed_places=[final_end],
            )
        )[0].request
        search = AsyncMock(return_value=[])

        with patch.object(
            recommendation_engine,
            "search_places",
            new=search,
        ):
            await recommendation_engine._collect_candidates(request)

        self.assertEqual(request.location.display_name, "Galle")
        self.assertEqual(request.route_origin.display_name, "Colombo")
        self.assertNotEqual(request.location.display_name, "Matara")
        self.assertEqual(search.await_args.kwargs["latitude"], 6.0461)
        self.assertEqual(search.await_args.kwargs["longitude"], 80.2103)

        candidate = self._place()
        route_matrix = AsyncMock(
            return_value={
                "durationsSeconds": [[0, 100], [100, 0]],
                "distancesMeters": [[0, 1000], [1000, 0]],
            }
        )
        with patch.object(
            recommendation_engine,
            "get_route_matrix",
            new=route_matrix,
        ):
            await recommendation_engine._load_route_information(
                request,
                [candidate],
            )

        self.assertEqual(
            route_matrix.await_args.kwargs["locations"][0],
            (6.93548, 79.84868),
        )

    def test_complete_itinerary_still_requires_route_dates_and_guest_count(
        self,
    ) -> None:
        context = self._context(
            search_location=self._location("Kandy", 7.2906, 80.6336),
            confirmed=False,
            complete_itinerary=True,
        )

        missing_fields = compute_missing_fields(context)

        self.assertIn(MISSING_STARTING_LOCATION, missing_fields)
        self.assertIn(MISSING_FINAL_ENDING_LOCATION, missing_fields)
        self.assertIn(MISSING_TRIP_START_DATE, missing_fields)
        self.assertIn(MISSING_TRIP_END_DATE, missing_fields)
        self.assertIn(MISSING_TRAVELLER_COUNT, missing_fields)
        self.assertFalse(context.is_ready_for_confirmation)

    def test_step_nine_through_eleven_contracts_remain_unchanged(self) -> None:
        self.assertEqual(
            recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES,
            MAXIMUM_MATRIX_LOCATIONS - 1,
        )
        self.assertEqual(recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES, 19)
        self.assertEqual(recommendation_engine.DEFAULT_RECOMMENDATION_RESULTS, 6)
        self.assertEqual(recommendation_engine._provider_search_result_limit(1), 19)
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )


if __name__ == "__main__":
    unittest.main()
