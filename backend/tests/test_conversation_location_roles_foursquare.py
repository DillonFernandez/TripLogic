"""Location-role contracts for conversation-driven Foursquare discovery."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("OPENROUTESERVICE_API_KEY", "location-contract-test-key")

from app import (  # noqa: E402
    conversation_location_verifier,
    conversation_router,
    foursquare,
    open_meteo,
    recommendation_engine,
)
from app.conversation_context_patcher import (  # noqa: E402
    apply_conversation_interpretation,
)
from app.conversation_context_requirements import (  # noqa: E402
    MISSING_DAILY_END_TIME,
    MISSING_DAILY_START_TIME,
    MISSING_FINAL_ENDING_LOCATION,
    MISSING_STARTING_LOCATION,
    MISSING_TRIP_END_DATE,
    MISSING_TRIP_START_DATE,
    compute_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
    ConversationInterpretationAction,
)
from app.conversation_interpreter import INTERPRETER_INSTRUCTIONS  # noqa: E402
from app.conversation_location_verifier import (  # noqa: E402
    LocationResolution,
    LocationResolutionStatus,
    resolve_location_results,
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
from app.conversation_question_builder import (  # noqa: E402
    QUESTION_BY_MISSING_FIELD,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    RESTAURANT_CATEGORY_ID,
)


SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")
REAL_ASYNC_CLIENT = httpx.AsyncClient


class ConversationLocationRolesFoursquareTests(
    unittest.IsolatedAsyncioTestCase
):
    def _location(
        self,
        name: str,
        latitude: float,
        longitude: float,
        *,
        admin1: str | None = None,
        admin2: str | None = None,
        admin3: str | None = None,
        admin4: str | None = None,
    ) -> TravelLocation:
        return TravelLocation(
            displayName=name,
            source=TravelLocationSource.SEARCHED,
            latitude=latitude,
            longitude=longitude,
            countryCode="LK",
            admin1=admin1,
            admin2=admin2,
            admin3=admin3,
            admin4=admin4,
            verified=True,
        )

    def _context(
        self,
        *,
        kind: TravelRequestKind = TravelRequestKind.RESTAURANT,
        search_location: TravelLocation,
        origin: TravelLocation | None = None,
        fixed_places: list[FixedTravelPlace] | None = None,
        confirmed: bool = True,
        requires_complete_itinerary: bool = False,
    ) -> TravelContext:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        return TravelContext(
            stage=(
                TravelContextStage.CONFIRMED
                if confirmed
                else TravelContextStage.COLLECTING
            ),
            startingLocation=origin,
            tripStartDate=tomorrow,
            tripEndDate=tomorrow,
            dailyStartTime="09:00:00",
            dailyEndTime="13:00:00",
            travellerType=TravellerType.COUPLE,
            travellerCount=2,
            travelModes=["driving"],
            requestGroups=[
                TravelRequestGroup(
                    id=f"{kind.value}-request",
                    kind=kind,
                    query=(
                        "hotel"
                        if kind is TravelRequestKind.HOTEL
                        else f"{kind.value}s"
                    ),
                    searchLocation=search_location,
                )
            ],
            fixedPlaces=fixed_places or [],
            missingFields=[],
            uncertainties=[],
            isConfirmed=confirmed,
            requiresCompleteItinerary=requires_complete_itinerary,
        )

    def _interpretation(
        self,
        *,
        action: str = "startNewTrip",
        starting_location: str | None = None,
        final_ending_location: str | None = None,
        groups: list[dict[str, Any]],
        operation: str = "add",
        targets: list[dict[str, Any]] | None = None,
    ) -> ConversationInterpretation:
        context_patch: dict[str, Any] = {
            "requestGroups": {
                "operation": operation,
                "groups": groups,
                "targets": targets or [],
            }
        }

        if starting_location is not None:
            context_patch["startingLocation"] = {
                "operation": "set",
                "source": "searched",
                "searchText": starting_location,
            }

        if final_ending_location is not None:
            context_patch["finalEndingLocation"] = {
                "operation": "set",
                "source": "searched",
                "searchText": final_ending_location,
            }

        return ConversationInterpretation.model_validate(
            {
                "action": action,
                "contextPatch": context_patch,
            }
        )

    def _apply(
        self,
        interpretation: ConversationInterpretation,
        message: str,
        *,
        current_context: TravelContext | None = None,
    ) -> TravelContext:
        return apply_conversation_interpretation(
            current_context=current_context or TravelContext(),
            interpretation=interpretation,
            traveller_message=message,
        )

    def test_interpreter_contract_extracts_simple_search_locality(self) -> None:
        interpretation = self._interpretation(
            groups=[
                {
                    "kind": "restaurant",
                    "query": "restaurants",
                    "searchLocationText": "Kandy",
                }
            ]
        )

        context = self._apply(interpretation, "restaurants in Kandy")

        self.assertIsNone(context.starting_location)
        self.assertEqual(
            context.request_groups[0].search_location.display_name,
            "Kandy",
        )
        self.assertIn("searchLocationText", INTERPRETER_INSTRUCTIONS)
        self.assertIn("does not imply a route origin", INTERPRETER_INSTRUCTIONS)

    def test_interpreter_contract_separates_origin_and_search_locality(self) -> None:
        cases = (
            (
                "start in Colombo and find attractions in Galle",
                "Colombo",
                "Galle",
                "attraction",
            ),
            (
                "I'm in Negombo, show me hotels in Nuwara Eliya",
                "Negombo",
                "Nuwara Eliya",
                "hotel",
            ),
        )

        for message, origin, search_location, kind in cases:
            with self.subTest(message=message):
                interpretation = self._interpretation(
                    starting_location=origin,
                    groups=[
                        {
                            "kind": kind,
                            "query": f"{kind}s",
                            "searchLocationText": search_location,
                        }
                    ],
                )

                context = self._apply(interpretation, message)

                self.assertEqual(context.starting_location.display_name, origin)
                self.assertEqual(
                    context.request_groups[0].search_location.display_name,
                    search_location,
                )

    def test_final_end_and_multiple_group_localities_remain_distinct(self) -> None:
        interpretation = self._interpretation(
            starting_location="Colombo",
            final_ending_location="Matara",
            groups=[
                {
                    "kind": "hotel",
                    "query": "hotels",
                    "searchLocationText": "Galle",
                },
                {
                    "kind": "restaurant",
                    "query": "restaurants",
                    "searchLocationText": "Kandy",
                },
            ],
        )

        context = self._apply(
            interpretation,
            "start in Colombo, hotels in Galle, restaurants in Kandy, end in Matara",
        )
        end_point = next(
            place
            for place in context.fixed_places
            if place.role is FixedTravelPlaceRole.END_POINT
        )

        self.assertEqual(context.starting_location.display_name, "Colombo")
        self.assertEqual(end_point.location.display_name, "Matara")
        self.assertEqual(
            [group.search_location.display_name for group in context.request_groups],
            ["Galle", "Kandy"],
        )

    def test_search_locality_correction_does_not_overwrite_origin(self) -> None:
        origin = self._location("Colombo", 6.93548, 79.84868)
        original_search = self._location("Galle", 6.0461, 80.2103)
        current = self._context(
            kind=TravelRequestKind.HOTEL,
            search_location=original_search,
            origin=origin,
            confirmed=False,
        )
        interpretation = self._interpretation(
            action="correctInformation",
            operation="replace",
            targets=[{"kind": "hotel"}],
            groups=[
                {
                    "kind": "hotel",
                    "query": "hotels",
                    "searchLocationText": "Nuwara Eliya",
                }
            ],
        )

        updated = self._apply(
            interpretation,
            "Actually find the hotel in Nuwara Eliya instead",
            current_context=current,
        )

        self.assertEqual(updated.starting_location, origin)
        self.assertEqual(
            updated.request_groups[0].search_location.display_name,
            "Nuwara Eliya",
        )
        self.assertFalse(updated.request_groups[0].search_location.verified)

    def test_simple_place_discovery_does_not_require_starting_location(self) -> None:
        cases = (
            (TravelRequestKind.RESTAURANT, "Kandy", 7.2906, 80.6336),
            (TravelRequestKind.HOTEL, "Galle", 6.0461, 80.2103),
            (TravelRequestKind.ATTRACTION, "Ella", 6.8756, 81.0463),
        )

        for kind, name, latitude, longitude in cases:
            with self.subTest(kind=kind.value, name=name):
                context = self._context(
                    kind=kind,
                    search_location=self._location(name, latitude, longitude),
                    origin=None,
                    confirmed=False,
                )

                missing_fields = compute_missing_fields(context)

                self.assertNotIn(MISSING_STARTING_LOCATION, missing_fields)
                self.assertTrue(context.has_route_ready_search_locations)

    def test_complete_itinerary_keeps_hard_start_and_end_requirements(self) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        context = TravelContext(
            requiresCompleteItinerary=True,
            requestGroups=[
                TravelRequestGroup(
                    id="attractions",
                    kind="attraction",
                    query="attractions",
                    searchLocation=self._location(
                        "Galle",
                        6.0461,
                        80.2103,
                    ),
                )
            ],
            tripStartDate=tomorrow,
            tripEndDate=tomorrow,
            travellerType="couple",
            travelModes=["driving"],
        )

        missing_fields = compute_missing_fields(context)

        self.assertIn(MISSING_STARTING_LOCATION, missing_fields)
        self.assertIn(MISSING_FINAL_ENDING_LOCATION, missing_fields)
        self.assertIn(MISSING_DAILY_START_TIME, missing_fields)
        self.assertIn(MISSING_DAILY_END_TIME, missing_fields)
        self.assertIn("end", QUESTION_BY_MISSING_FIELD[MISSING_FINAL_ENDING_LOCATION])

        no_dates = context.model_copy(
            update={"trip_start_date": None, "trip_end_date": None}
        )
        date_missing_fields = compute_missing_fields(no_dates)
        self.assertIn(MISSING_TRIP_START_DATE, date_missing_fields)
        self.assertIn(MISSING_TRIP_END_DATE, date_missing_fields)

    async def test_open_meteo_geocoding_keeps_lk_filter_and_admin_metadata(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "name": "Nuwara Eliya",
                            "latitude": 6.97078,
                            "longitude": 80.78286,
                            "country_code": "LK",
                            "country": "Sri Lanka",
                            "admin1": "Central Province",
                            "admin2": "Nuwara Eliya District",
                            "admin3": "Nuwara Eliya Division",
                            "admin4": "Nuwara Eliya Central",
                            "feature_code": "PPL",
                            "population": 27500,
                        },
                        {
                            "id": 2,
                            "name": "Nuwara Eliya",
                            "latitude": 1.0,
                            "longitude": 2.0,
                            "country_code": "US",
                        },
                    ]
                },
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        with patch.object(
            open_meteo.httpx,
            "AsyncClient",
            side_effect=make_client,
        ):
            locations = await open_meteo.search_sri_lankan_locations(
                "Nuwara Eliya"
            )

        self.assertEqual(requests[0].url.params["countryCode"], "LK")
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["admin3"], "Nuwara Eliya Division")
        self.assertEqual(locations[0]["admin4"], "Nuwara Eliya Central")

    def test_verifier_prefers_corroborated_locality_and_preserves_admins(self) -> None:
        resolution = resolve_location_results(
            query="Ella",
            results=[
                {
                    "id": 1,
                    "name": "Ella",
                    "displayName": "Ella, Moneragala District",
                    "latitude": 6.8511,
                    "longitude": 81.5,
                    "countryCode": "LK",
                    "admin1": "Uva Province",
                    "admin2": "Moneragala District",
                    "admin3": "Siyambalanduwa Division",
                    "admin4": "Ethimale",
                    "featureCode": "PPL",
                },
                {
                    "id": 2,
                    "name": "Ella",
                    "displayName": "Ella, Elpitiya, Galle District",
                    "latitude": 6.2613,
                    "longitude": 80.1625,
                    "countryCode": "LK",
                    "admin1": "Southern Province",
                    "admin2": "Galle District",
                    "admin3": "Elpitiya",
                    "admin4": "Ella",
                    "featureCode": "PPL",
                },
                {
                    "id": 3,
                    "name": "Ella Town",
                    "displayName": "Ella Town, Ella Division, Badulla District",
                    "latitude": 6.8756,
                    "longitude": 81.0463,
                    "countryCode": "LK",
                    "admin1": "Uva Province",
                    "admin2": "Badulla District",
                    "admin3": "Ella Division",
                    "admin4": "Ella",
                    "featureCode": "PPL",
                    "population": 5000,
                },
            ],
        )

        self.assertTrue(resolution.is_verified)
        self.assertEqual(resolution.location.display_name, "Ella Town, Ella Division, Badulla District")
        self.assertEqual(resolution.location.latitude, 6.8756)
        self.assertEqual(resolution.location.longitude, 81.0463)
        self.assertEqual(resolution.location.admin1, "Uva Province")
        self.assertEqual(resolution.location.admin2, "Badulla District")
        self.assertEqual(resolution.location.admin3, "Ella Division")
        self.assertEqual(resolution.location.admin4, "Ella")

    def test_exact_name_without_corroboration_remains_ambiguous(self) -> None:
        resolution = resolve_location_results(
            query="Hiriketiya",
            results=[
                {
                    "id": 1,
                    "name": "Hiriketiya",
                    "displayName": "Hiriketiya, Polwathugoda, Ratnapura District",
                    "latitude": 6.6913,
                    "longitude": 80.6533,
                    "countryCode": "LK",
                    "admin1": "Sabaragamuwa Province",
                    "admin2": "Ratnapura District",
                    "admin3": "Balangoda Division",
                    "admin4": "Polwathugoda",
                    "featureCode": "PPL",
                }
            ],
        )

        self.assertEqual(resolution.status, LocationResolutionStatus.AMBIGUOUS)
        self.assertIsNone(resolution.location)

    def test_foreign_invalid_and_missing_coordinate_results_are_rejected(self) -> None:
        resolution = resolve_location_results(
            query="Kandy",
            results=[
                {
                    "name": "Kandy",
                    "displayName": "Kandy, United States",
                    "latitude": 40.0,
                    "longitude": -75.0,
                    "countryCode": "US",
                    "featureCode": "PPLA",
                },
                {
                    "name": "Kandy",
                    "displayName": "Kandy without longitude",
                    "latitude": 7.29,
                    "countryCode": "LK",
                    "featureCode": "PPLA",
                },
                {
                    "id": 3,
                    "name": "Kandy",
                    "displayName": "Kandy, Central Province",
                    "latitude": 7.2906,
                    "longitude": 80.6336,
                    "countryCode": "LK",
                    "admin1": "Central Province",
                    "featureCode": "PPLA",
                    "population": 111701,
                },
            ],
        )

        self.assertTrue(resolution.is_verified)
        self.assertEqual(resolution.location.latitude, 7.2906)
        self.assertEqual(resolution.location.longitude, 80.6336)

    async def test_router_verifies_origin_search_and_end_without_overwriting_roles(
        self,
    ) -> None:
        context = self._apply(
            self._interpretation(
                starting_location="Colombo",
                final_ending_location="Matara",
                groups=[
                    {
                        "kind": "attraction",
                        "query": "attractions",
                        "searchLocationText": "Galle",
                    }
                ],
            ),
            "start Colombo, attractions Galle, end Matara",
        )
        verified = {
            "Colombo": self._location("Colombo", 6.93548, 79.84868),
            "Galle": self._location("Galle", 6.0461, 80.2103),
            "Matara": self._location("Matara", 5.9485, 80.5353),
        }

        async def resolve(query: str) -> LocationResolution:
            return LocationResolution(
                status=LocationResolutionStatus.VERIFIED,
                location=verified[query],
            )

        with patch.object(
            conversation_router,
            "resolve_sri_lankan_location",
            new=AsyncMock(side_effect=resolve),
        ):
            updated, pending = await conversation_router._verify_context_locations(
                context
            )

        end_point = next(
            place
            for place in updated.fixed_places
            if place.role is FixedTravelPlaceRole.END_POINT
        )
        self.assertIsNone(pending)
        self.assertEqual(updated.starting_location, verified["Colombo"])
        self.assertEqual(
            updated.request_groups[0].search_location,
            verified["Galle"],
        )
        self.assertEqual(end_point.location, verified["Matara"])

    async def test_router_keeps_ambiguous_search_unverified(self) -> None:
        context = self._apply(
            self._interpretation(
                groups=[
                    {
                        "kind": "hotel",
                        "query": "hotels",
                        "searchLocationText": "Hiriketiya",
                    }
                ]
            ),
            "hotels in Hiriketiya",
        )
        ambiguous = LocationResolution(
            status=LocationResolutionStatus.AMBIGUOUS,
            candidates=("Hiriketiya, Ratnapura District",),
        )

        with patch.object(
            conversation_router,
            "resolve_sri_lankan_location",
            new=AsyncMock(return_value=ambiguous),
        ):
            updated, pending = await conversation_router._verify_context_locations(
                context
            )

        self.assertIsNotNone(pending)
        self.assertFalse(updated.request_groups[0].search_location.verified)
        self.assertIn(
            "hotel search",
            conversation_router._location_clarification_message(pending),
        )

    def test_adapter_uses_search_location_and_preserves_route_origin(self) -> None:
        origin = self._location("Colombo", 6.93548, 79.84868)
        search_location = self._location("Galle", 6.0461, 80.2103)
        final_end = FixedTravelPlace(
            id="end-matara",
            name="Matara",
            role=FixedTravelPlaceRole.END_POINT,
            location=self._location("Matara", 5.9485, 80.5353),
        )
        daily_base = FixedTravelPlace(
            id="base-kandy",
            name="Kandy hotel",
            role=FixedTravelPlaceRole.DAILY_BASE,
            location=self._location("Kandy", 7.2906, 80.6336),
        )
        context = self._context(
            kind=TravelRequestKind.ATTRACTION,
            search_location=search_location,
            origin=origin,
            fixed_places=[final_end, daily_base],
        )

        task = build_recommendation_tasks(context)[0]

        self.assertEqual(task.request.location.display_name, "Galle")
        self.assertEqual(task.request.location.latitude, 6.0461)
        self.assertEqual(task.request.location.longitude, 80.2103)
        self.assertEqual(task.request.route_origin.display_name, "Colombo")
        self.assertNotEqual(task.request.location.display_name, "Matara")
        self.assertNotEqual(task.request.location.display_name, "Kandy")

    def test_simple_search_has_no_fabricated_route_origin(self) -> None:
        context = self._context(
            search_location=self._location("Kandy", 7.2906, 80.6336),
            origin=None,
        )

        task = build_recommendation_tasks(context)[0]

        self.assertEqual(task.request.location.display_name, "Kandy")
        self.assertIsNone(task.request.route_origin)
        self.assertIsNone(context.starting_location)

    async def test_foursquare_http_ll_uses_verified_search_locality(self) -> None:
        context = self._context(
            kind=TravelRequestKind.ATTRACTION,
            search_location=self._location("Galle", 6.0461, 80.2103),
            origin=self._location("Colombo", 6.93548, 79.84868),
        )
        task = build_recommendation_tasks(context)[0]
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                content=json.dumps({"results": []}).encode("utf-8"),
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "location-contract-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            await recommendation_engine._collect_candidates(task.request)

        self.assertEqual(len(requests), 4)
        self.assertEqual(
            {request.url.params["ll"] for request in requests},
            {"6.0461,80.2103"},
        )
        self.assertEqual(
            [request.url.params["fsq_category_ids"] for request in requests],
            [",".join(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
        )

    async def test_category_only_generic_search_keeps_each_verified_center(
        self,
    ) -> None:
        cases = (
            ("Kandy", 7.2906, 80.6336),
            ("Ella", 6.8756, 81.0463),
            ("Sigiriya", 7.94946, 80.75037),
        )

        for name, latitude, longitude in cases:
            with self.subTest(name=name):
                context = self._context(
                    kind=TravelRequestKind.ATTRACTION,
                    search_location=self._location(
                        name,
                        latitude,
                        longitude,
                    ),
                    origin=None,
                )
                request = build_recommendation_tasks(context)[0].request
                search = AsyncMock(return_value=[])

                with patch.object(
                    recommendation_engine,
                    "search_places",
                    new=search,
                ):
                    await recommendation_engine._collect_candidates(request)

                self.assertEqual(search.await_count, 4)
                self.assertTrue(
                    all(
                        call.kwargs["latitude"] == latitude
                        and call.kwargs["longitude"] == longitude
                        and call.kwargs["query"] is None
                        for call in search.await_args_list
                    )
                )

    async def test_ors_uses_origin_while_foursquare_location_remains_search(self) -> None:
        context = self._context(
            search_location=self._location("Galle", 6.0461, 80.2103),
            origin=self._location("Colombo", 6.93548, 79.84868),
        )
        request = build_recommendation_tasks(context)[0].request
        candidate = {
            "id": "place",
            "name": "Place",
            "latitude": 6.05,
            "longitude": 80.22,
            "distanceMeters": 1000,
        }
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

        self.assertEqual(request.location.display_name, "Galle")
        self.assertEqual(
            route_matrix.await_args.kwargs["locations"][0],
            (6.93548, 79.84868),
        )

    async def test_missing_origin_keeps_route_unavailable_without_blocking_search(
        self,
    ) -> None:
        context = self._context(
            search_location=self._location("Kandy", 7.2906, 80.6336),
            origin=None,
        )
        request = build_recommendation_tasks(context)[0].request
        candidate = {
            "id": "restaurant",
            "name": "Restaurant",
            "latitude": 7.291,
            "longitude": 80.634,
            "distanceMeters": 75,
        }
        route_matrix = AsyncMock()

        with patch.object(
            recommendation_engine,
            "get_route_matrix",
            new=route_matrix,
        ):
            result = await recommendation_engine._load_route_information(
                request,
                [candidate],
            )

        self.assertIsNone(result)
        route_matrix.assert_not_awaited()
        self.assertFalse(candidate["route"]["available"])
        self.assertIsNone(candidate["route"]["durationSeconds"])
        self.assertIsNone(candidate["route"]["distanceMeters"])

    def test_canonical_hotel_and_restaurant_filters_are_unchanged(self) -> None:
        hotel_task = build_recommendation_tasks(
            self._context(
                kind=TravelRequestKind.HOTEL,
                search_location=self._location("Galle", 6.0461, 80.2103),
            )
        )[0]
        restaurant_task = build_recommendation_tasks(
            self._context(
                kind=TravelRequestKind.RESTAURANT,
                search_location=self._location("Kandy", 7.2906, 80.6336),
            )
        )[0]

        self.assertEqual(
            hotel_task.request.provider_filters[0].category_ids,
            (HOTEL_CATEGORY_ID,),
        )
        self.assertEqual(
            restaurant_task.request.provider_filters[0].category_ids,
            (RESTAURANT_CATEGORY_ID,),
        )

    def test_search_radius_strategy_remains_type_specific_and_unchanged(self) -> None:
        self.assertEqual(
            recommendation_engine.SEARCH_RADIUS_BY_TYPE,
            {
                "attraction": 25_000,
                "hotel": 20_000,
                "restaurant": 12_000,
            },
        )


if __name__ == "__main__":
    unittest.main()
