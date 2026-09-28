"""Restaurant discovery and preference contracts for Foursquare."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("OPENROUTESERVICE_API_KEY", "restaurant-contract-test-key")

from app import foursquare, recommendation_engine  # noqa: E402
from app.conversation_context_patcher import (  # noqa: E402
    apply_conversation_interpretation,
)
from app.conversation_context_requirements import (  # noqa: E402
    MISSING_DAILY_END_TIME,
    MISSING_DAILY_START_TIME,
    MISSING_FINAL_ENDING_LOCATION,
    MISSING_STARTING_LOCATION,
    MISSING_TRAVEL_MODE,
    MISSING_TRAVELLER_TYPE,
    MISSING_TRIP_END_DATE,
    MISSING_TRIP_START_DATE,
    compute_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
)
from app.conversation_interpreter import INTERPRETER_INSTRUCTIONS  # noqa: E402
from app.conversation_models import (  # noqa: E402
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
from app.conversation_preference_rules import (  # noqa: E402
    build_request_preference_question,
)
from app.foursquare_categories import (  # noqa: E402
    ATTRACTION_CATEGORIES,
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient


class RestaurantDiscoveryFoursquareTests(unittest.IsolatedAsyncioTestCase):
    def _location(
        self,
        name: str = "Kandy",
        latitude: float = 7.2906,
        longitude: float = 80.6336,
    ) -> TravelLocation:
        return TravelLocation(
            displayName=name,
            localityName=name,
            source=TravelLocationSource.SEARCHED,
            latitude=latitude,
            longitude=longitude,
            countryCode="LK",
            verified=True,
        )

    def _context(
        self,
        *,
        query: str = "restaurants",
        cuisine_preferences: list[str] | None = None,
        dietary_requirements: list[str] | None = None,
        food_avoidances: list[str] | None = None,
        meal_intents: list[str] | None = None,
        preferences: list[str] | None = None,
        origin: TravelLocation | None = None,
        include_planning_context: bool = False,
    ) -> TravelContext:
        return TravelContext(
            stage=TravelContextStage.CONFIRMED,
            startingLocation=origin,
            travellerType=(
                TravellerType.COUPLE if include_planning_context else None
            ),
            travelModes=(
                ["driving"] if include_planning_context else []
            ),
            requestGroups=[
                TravelRequestGroup(
                    id="restaurant-request",
                    kind=TravelRequestKind.RESTAURANT,
                    query=query,
                    searchLocation=self._location(),
                    preferences=preferences or [],
                    cuisinePreferences=cuisine_preferences or [],
                    dietaryRequirements=dietary_requirements or [],
                    foodAvoidances=food_avoidances or [],
                    mealIntents=meal_intents or [],
                )
            ],
            missingFields=[],
            uncertainties=[],
            isConfirmed=True,
        )

    def _task(self, **kwargs: Any):
        tasks = build_recommendation_tasks(self._context(**kwargs))
        self.assertEqual(len(tasks), 1)
        return tasks[0]

    def test_structured_restaurant_semantics_avoid_redundant_preference_question(
        self,
    ) -> None:
        context = self._context(
            cuisine_preferences=["Sri Lankan"],
            dietary_requirements=["vegetarian"],
            meal_intents=["lunch"],
        )

        self.assertIsNone(build_request_preference_question(context))

    async def _http_requests(self, request) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def handler(raw_request: httpx.Request) -> httpx.Response:
            requests.append(raw_request)
            return httpx.Response(
                200,
                json={"results": []},
                request=raw_request,
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
            await recommendation_engine._collect_candidates(request)

        return requests

    def test_interpreter_patch_preserves_separate_restaurant_semantics(self) -> None:
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "startNewTrip",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "searchLocationText": "Kandy",
                                "cuisinePreferences": ["Sri Lankan"],
                                "dietaryRequirements": ["vegetarian"],
                                "foodAvoidances": ["seafood"],
                                "mealIntents": ["dinner"],
                            }
                        ],
                    }
                },
            }
        )

        context = apply_conversation_interpretation(
            current_context=TravelContext(),
            interpretation=interpretation,
            traveller_message=(
                "Vegetarian Sri Lankan dinner in Kandy, but no seafood"
            ),
        )
        group = context.request_groups[0]

        self.assertEqual(group.cuisine_preferences, ["Sri Lankan"])
        self.assertEqual(group.dietary_requirements, ["vegetarian"])
        self.assertEqual(group.food_avoidances, ["seafood"])
        self.assertEqual(group.meal_intents, ["dinner"])
        self.assertEqual(group.preferences, [])
        self.assertIn("cuisinePreferences", INTERPRETER_INSTRUCTIONS)
        self.assertIn("foodAvoidances", INTERPRETER_INSTRUCTIONS)
        self.assertIn("never claim provider", INTERPRETER_INSTRUCTIONS)

    def test_patching_merges_positive_and_negative_preferences_independently(self) -> None:
        current = TravelContext(
            requestGroups=[
                TravelRequestGroup(
                    id="restaurant-request",
                    kind=TravelRequestKind.RESTAURANT,
                    query="restaurants",
                    cuisinePreferences=["Italian"],
                    foodAvoidances=["fast food"],
                )
            ]
        )
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "modifyCurrentTrip",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "cuisinePreferences": ["Sri Lankan"],
                                "dietaryRequirements": ["halal"],
                                "foodAvoidances": ["seafood"],
                            }
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=current,
            interpretation=interpretation,
            traveller_message="Also Sri Lankan and halal, but avoid seafood",
        )
        group = updated.request_groups[0]

        self.assertEqual(group.cuisine_preferences, ["Italian", "Sri Lankan"])
        self.assertEqual(group.dietary_requirements, ["halal"])
        self.assertEqual(group.food_avoidances, ["fast food", "seafood"])

    def test_simple_restaurant_discovery_needs_no_trip_or_route_metadata(self) -> None:
        context = self._context()

        self.assertEqual(compute_missing_fields(context), [])

        task = build_recommendation_tasks(context)[0]
        request = task.request

        self.assertIsNone(request.visit_date)
        self.assertIsNone(request.start_time)
        self.assertIsNone(request.visit_duration_minutes)
        self.assertIsNone(request.travel_mode)
        self.assertIsNone(request.travel_partner)
        self.assertIsNone(request.route_origin)
        self.assertEqual(len(request.provider_filters), 1)
        self.assertEqual(
            request.provider_filters[0].category_ids,
            (RESTAURANT_CATEGORY_ID,),
        )

    def test_complete_itinerary_requirements_are_not_weakened(self) -> None:
        context = TravelContext(
            requiresCompleteItinerary=True,
            requestGroups=[
                TravelRequestGroup(
                    id="restaurant-request",
                    kind=TravelRequestKind.RESTAURANT,
                    query="restaurants",
                    searchLocation=self._location(),
                )
            ],
        )

        missing = set(compute_missing_fields(context))

        self.assertTrue(
            {
                MISSING_STARTING_LOCATION,
                MISSING_FINAL_ENDING_LOCATION,
                MISSING_TRIP_START_DATE,
                MISSING_TRIP_END_DATE,
                MISSING_DAILY_START_TIME,
                MISSING_DAILY_END_TIME,
                MISSING_TRAVELLER_TYPE,
                MISSING_TRAVEL_MODE,
            }.issubset(missing)
        )

    async def test_generic_restaurant_search_is_category_only_and_uses_near(self) -> None:
        task = self._task()

        self.assertIsNone(task.request.provider_filters[0].query)

        requests = await self._http_requests(task.request)

        self.assertEqual(len(requests), 1)
        params = requests[0].url.params
        self.assertNotIn("query", params)
        self.assertEqual(params["near"], "Kandy, Sri Lanka")
        self.assertNotIn("ll", params)
        self.assertEqual(params["fsq_category_ids"], RESTAURANT_CATEGORY_ID)

    def test_positive_cuisine_preferences_create_meaningful_queries(self) -> None:
        cases = (
            ("Sri Lankan food", "Sri Lankan food"),
            ("Italian", "Italian"),
            ("seafood", "seafood"),
        )

        for preference, expected in cases:
            with self.subTest(preference=preference):
                task = self._task(cuisine_preferences=[preference])
                self.assertEqual(
                    task.request.provider_filters[0].query,
                    expected,
                )

    def test_multiple_positive_preferences_are_normalized_and_deterministic(self) -> None:
        task = self._task(
            cuisine_preferences=[" Sri Lankan ", "Italian", "sri lankan"],
            preferences=["spicy"],
        )

        self.assertEqual(
            task.request.provider_filters[0].query,
            "Sri Lankan Italian spicy",
        )

    def test_dietary_requirements_are_preserved_without_false_certainty(self) -> None:
        searchable_cases = ("vegetarian", "vegan", "halal")

        for requirement in searchable_cases:
            with self.subTest(requirement=requirement):
                task = self._task(dietary_requirements=[requirement])
                self.assertEqual(
                    task.request.restaurant_dietary_requirements,
                    (requirement,),
                )
                self.assertEqual(
                    task.request.provider_filters[0].query,
                    requirement,
                )

        unverified = self._task(dietary_requirements=["gluten-free"])
        self.assertEqual(
            unverified.request.restaurant_dietary_requirements,
            ("gluten-free",),
        )
        self.assertIsNone(unverified.request.provider_filters[0].query)

    def test_food_avoidance_never_becomes_a_positive_provider_query(self) -> None:
        explicit = self._task(
            query="no seafood restaurants",
            food_avoidances=["seafood"],
        )
        conflicting = self._task(
            cuisine_preferences=["seafood"],
            food_avoidances=["seafood"],
        )

        self.assertIsNone(explicit.request.provider_filters[0].query)
        self.assertIsNone(conflicting.request.provider_filters[0].query)
        self.assertEqual(
            conflicting.request.restaurant_food_avoidances,
            ("seafood",),
        )

    def test_combined_cuisine_and_diet_reach_adapter_without_semantic_loss(self) -> None:
        task = self._task(
            cuisine_preferences=["Sri Lankan"],
            dietary_requirements=["vegetarian"],
        )

        self.assertEqual(
            task.request.provider_filters[0].query,
            "Sri Lankan",
        )
        self.assertEqual(
            task.request.restaurant_cuisine_preferences,
            ("Sri Lankan",),
        )
        self.assertEqual(
            task.request.restaurant_dietary_requirements,
            ("vegetarian",),
        )
        dumped = task.request.model_dump(by_alias=True)
        self.assertNotIn("restaurantDietaryRequirements", dumped)
        self.assertNotIn("providerFilters", dumped)

    def test_meal_intent_influences_discovery_without_hours_claim(self) -> None:
        task = self._task(meal_intents=["breakfast", "cafe", "dessert"])

        self.assertEqual(
            task.request.provider_filters[0].query,
            "breakfast cafe dessert",
        )
        self.assertEqual(
            task.request.restaurant_meal_intents,
            ("breakfast", "cafe", "dessert"),
        )
        self.assertNotIn("hours", task.request.model_dump())

    async def test_no_origin_skips_route_and_weather_without_fabrication(self) -> None:
        request = self._task(dietary_requirements=["vegan"]).request
        search = AsyncMock(
            return_value=[
                {
                    "id": "provider-place",
                    "name": "Provider Restaurant",
                    "categories": [{"id": "leaf", "name": "Restaurant"}],
                    "latitude": 7.291,
                    "longitude": 80.634,
                    "distanceMeters": 75,
                    "location": {},
                    "address": None,
                    "telephone": None,
                    "website": None,
                }
            ]
        )
        route_matrix = AsyncMock()
        weather = AsyncMock()

        with (
            patch.object(recommendation_engine, "search_places", new=search),
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

        route_matrix.assert_not_awaited()
        weather.assert_not_awaited()
        self.assertEqual(result["count"], 1)
        candidate = result["topRecommendations"][0]
        self.assertFalse(candidate["route"]["available"])
        self.assertIsNone(candidate["route"]["travelMode"])
        self.assertIsNone(candidate["weather"])
        self.assertNotIn("vegan", candidate["explanation"].casefold())
        self.assertNotIn("dietaryCompatibility", candidate)
        self.assertIsNone(candidate.get("hours"))

    async def test_origin_and_search_location_remain_separate(self) -> None:
        origin = self._location("Colombo", 6.93548, 79.84868)
        request = self._task(
            origin=origin,
            include_planning_context=True,
        ).request
        candidate = {
            "id": "place",
            "name": "Kandy Restaurant",
            "latitude": 7.291,
            "longitude": 80.634,
            "distanceMeters": 75,
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

        self.assertEqual(request.location.display_name, "Kandy")
        self.assertEqual(
            route_matrix.await_args.kwargs["locations"][0],
            (6.93548, 79.84868),
        )

    def test_prior_stage_contracts_remain_unchanged(self) -> None:
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(len(ATTRACTION_CATEGORIES), 76)
        self.assertEqual(len(GENERIC_ATTRACTION_GROUPS), 4)
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )
        self.assertEqual(len(INTENT_CATEGORY_PRESETS), 15)
        self.assertEqual(
            recommendation_engine.SEARCH_RADIUS_BY_TYPE["restaurant"],
            12_000,
        )
        self.assertEqual(recommendation_engine.DEFAULT_RECOMMENDATION_RESULTS, 6)
        self.assertEqual(recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES, 19)


if __name__ == "__main__":
    unittest.main()
