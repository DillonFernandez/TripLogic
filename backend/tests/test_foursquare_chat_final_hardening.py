"""Focused final invariants for the conversation-to-Foursquare boundary."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare, recommendation_engine  # noqa: E402
from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_context_patcher import (  # noqa: E402
    apply_conversation_interpretation,
)
from app.conversation_context_requirements import (  # noqa: E402
    MISSING_TRAVEL_MODE,
    MISSING_TRAVELLER_TYPE,
    refresh_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
    ExtractedRecommendationAction,
    ExtractedRequestGroup,
)
from app.conversation_interpreter import INTERPRETER_INSTRUCTIONS  # noqa: E402
from app.conversation_models import (  # noqa: E402
    TravelContext,
    TravelContextStage,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    ATTRACTION_CATEGORIES,
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
)


class FoursquareChatFinalHardeningTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _location(
        name: str,
        latitude: float,
        longitude: float,
    ) -> TravelLocation:
        return TravelLocation(
            displayName=name,
            localityName=name,
            source=TravelLocationSource.SEARCHED,
            latitude=latitude,
            longitude=longitude,
            providerPlaceId=f"open-meteo-{name.casefold()}",
            countryCode="LK",
            verified=True,
        )

    @classmethod
    def _awaiting_restaurant_context(cls) -> TravelContext:
        context = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="restaurant-kandy",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        requestedCount=3,
                        searchLocation=cls._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    ),
                    TravelRequestGroup(
                        id="restaurant-galle",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        requestedCount=2,
                        searchLocation=cls._location(
                            "Galle",
                            6.0329,
                            80.2168,
                        ),
                    ),
                ]
            )
        )
        data = context.model_dump(mode="python")
        data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        data["confirmation_summary"] = build_confirmation_summary(context)
        return TravelContext.model_validate(data)

    @staticmethod
    def _interpretation(
        groups: list[dict[str, object]],
        *,
        action: str = "startNewTrip",
    ) -> ConversationInterpretation:
        return ConversationInterpretation.model_validate(
            {
                "action": action,
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": groups,
                    }
                },
            }
        )

    def test_same_kind_different_localities_remain_independent(self) -> None:
        cases = (
            (
                "restaurant",
                "restaurants",
                (("Kandy", 3), ("Galle", 2)),
            ),
            (
                "attraction",
                "attractions",
                (("Kandy", 5), ("Ella", 3)),
            ),
        )

        for kind, query, locations in cases:
            with self.subTest(kind=kind):
                interpretation = self._interpretation(
                    [
                        {
                            "kind": kind,
                            "query": query,
                            "searchLocationText": location,
                            "requestedCount": count,
                        }
                        for location, count in locations
                    ]
                )
                context = apply_conversation_interpretation(
                    current_context=TravelContext(),
                    interpretation=interpretation,
                    traveller_message="multiple locality request",
                )

                self.assertEqual(
                    [
                        (
                            group.search_location.display_name,
                            group.requested_count,
                        )
                        for group in context.request_groups
                    ],
                    list(locations),
                )

    def test_locality_targeted_count_correction_preserves_sibling(self) -> None:
        correction = self._interpretation(
            [
                {
                    "kind": "restaurant",
                    "query": "places to eat",
                    "searchLocationText": "Galle",
                    "requestedCount": 4,
                }
            ],
            action="correctInformation",
        )
        updated = apply_conversation_interpretation(
            current_context=self._awaiting_restaurant_context(),
            interpretation=correction,
            traveller_message="Make the Galle restaurants 4",
        )

        self.assertEqual(
            [
                (
                    group.search_location.locality_name,
                    group.requested_count,
                    group.search_location.verified,
                )
                for group in updated.request_groups
            ],
            [("Kandy", 3, True), ("Galle", 4, True)],
        )
        summary = build_confirmation_summary(updated)
        self.assertIn("Location: Kandy\n  Number requested: 3", summary)
        self.assertIn("Location: Galle\n  Number requested: 4", summary)

    def test_same_kind_location_replacement_preserves_unaffected_facts(
        self,
    ) -> None:
        current = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="hotel-kandy",
                        kind=TravelRequestKind.HOTEL,
                        query="hotels",
                        requestedCount=2,
                        preferences=["boutique hotels"],
                        searchLocation=self._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    )
                ]
            )
        )
        correction = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "replace",
                        "targets": [{"kind": "hotel"}],
                        "groups": [
                            {
                                "kind": "hotel",
                                "query": "hotels",
                                "searchLocationText": "Galle",
                            }
                        ],
                    }
                },
            }
        )
        updated = apply_conversation_interpretation(
            current_context=current,
            interpretation=correction,
            traveller_message="Actually use Galle for the hotel instead",
        )
        group = updated.request_groups[0]

        self.assertEqual(group.id, "hotel-kandy")
        self.assertEqual(group.requested_count, 2)
        self.assertEqual(group.preferences, ["boutique hotels"])
        self.assertEqual(group.search_location.display_name, "Galle")
        self.assertFalse(group.search_location.verified)

    def test_locality_targeted_removal_preserves_other_same_kind_group(self) -> None:
        removal = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "remove",
                        "targets": [
                            {
                                "kind": "restaurant",
                                "searchLocationText": "Galle",
                            }
                        ],
                    }
                },
            }
        )
        updated = apply_conversation_interpretation(
            current_context=self._awaiting_restaurant_context(),
            interpretation=removal,
            traveller_message="Remove the restaurants in Galle",
        )

        self.assertEqual(len(updated.request_groups), 1)
        self.assertEqual(
            updated.request_groups[0].search_location.locality_name,
            "Kandy",
        )
        self.assertEqual(updated.request_groups[0].requested_count, 3)

    def test_no_hotels_removes_group_instead_of_creating_zero_count(self) -> None:
        current = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="restaurant-kandy",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        requestedCount=3,
                        searchLocation=self._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    ),
                    TravelRequestGroup(
                        id="hotel-kandy",
                        kind=TravelRequestKind.HOTEL,
                        query="hotels",
                        requestedCount=2,
                        searchLocation=self._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    ),
                ]
            )
        )
        removal = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "remove",
                        "targets": [{"kind": "hotel"}],
                    }
                },
            }
        )
        updated = apply_conversation_interpretation(
            current_context=current,
            interpretation=removal,
            traveller_message="No hotels",
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in updated.request_groups],
            [("restaurant", 3)],
        )

    def test_ambiguous_same_kind_correction_is_not_applied_arbitrarily(self) -> None:
        correction = self._interpretation(
            [
                {
                    "kind": "restaurant",
                    "query": "restaurants",
                    "requestedCount": 4,
                }
            ],
            action="correctInformation",
        )

        with self.assertRaisesRegex(ValueError, "locality is ambiguous"):
            apply_conversation_interpretation(
                current_context=self._awaiting_restaurant_context(),
                interpretation=correction,
                traveller_message="Make the restaurants 4",
            )

    def test_requested_counts_are_strict_bounded_integers(self) -> None:
        valid_values = (1, 2, 3, 6, 7, 10, 19)
        invalid_values = (
            0,
            -1,
            3.0,
            3.5,
            True,
            False,
            math.nan,
            math.inf,
            -math.inf,
            20,
            50,
            100,
        )
        models = (
            (TravelRequestGroup, {"id": "group"}),
            (ExtractedRequestGroup, {}),
        )

        for model, extra in models:
            for value in valid_values:
                with self.subTest(model=model.__name__, valid=value):
                    instance = model(
                        kind="restaurant",
                        query="restaurants",
                        requestedCount=value,
                        **extra,
                    )
                    self.assertEqual(instance.requested_count, value)

            for value in invalid_values:
                with self.subTest(model=model.__name__, invalid=value):
                    with self.assertRaises(ValidationError):
                        model(
                            kind="restaurant",
                            query="restaurants",
                            requestedCount=value,
                            **extra,
                        )

        for value in (3.0, True, 50):
            with self.subTest(action_count=value):
                with self.assertRaises(ValidationError):
                    ExtractedRecommendationAction(
                        action="more",
                        requestedCount=value,
                    )

    def test_count_language_contract_rejects_guessing_and_zero_removal(self) -> None:
        for text in (
            '"five" or "top five"',
            'couple" to 2',
            '"a few" or "3 or 4"',
            "Never emit zero",
            '"No hotels", "remove hotels"',
            "requestedCount=0",
            "Same-kind groups in different localities remain separate",
        ):
            with self.subTest(text=text):
                self.assertIn(text, INTERPRETER_INSTRUCTIONS)

    def test_simple_hotel_requires_only_verified_discovery_facts(self) -> None:
        context = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="hotel-kandy",
                        kind=TravelRequestKind.HOTEL,
                        query="hotels",
                        searchLocation=self._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    )
                ]
            )
        )

        self.assertNotIn(MISSING_TRAVELLER_TYPE, context.missing_fields)
        self.assertNotIn(MISSING_TRAVEL_MODE, context.missing_fields)
        self.assertTrue(context.is_ready_for_confirmation)

        data = context.model_dump(mode="python")
        data.update(
            stage=TravelContextStage.CONFIRMED,
            is_confirmed=True,
        )
        task = build_recommendation_tasks(
            TravelContext.model_validate(data)
        )[0]

        self.assertIsNone(task.request.travel_partner)
        self.assertIsNone(task.request.travel_mode)
        self.assertIsNone(task.request.route_origin)
        self.assertEqual(
            task.request.provider_filters[0].category_ids,
            (HOTEL_CATEGORY_ID,),
        )

    def test_simple_attraction_requires_only_verified_discovery_facts(
        self,
    ) -> None:
        context = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="attraction-kandy",
                        kind=TravelRequestKind.ATTRACTION,
                        query="attractions",
                        preferences=["no specific preference"],
                        searchLocation=self._location(
                            "Kandy",
                            7.2906,
                            80.6337,
                        ),
                    )
                ]
            )
        )

        self.assertEqual(context.missing_fields, [])
        self.assertFalse(context.requires_trip_period)
        self.assertTrue(context.is_ready_for_confirmation)

        data = context.model_dump(mode="python")
        data.update(
            stage=TravelContextStage.CONFIRMED,
            is_confirmed=True,
        )
        task = build_recommendation_tasks(
            TravelContext.model_validate(data)
        )[0]

        self.assertIsNone(task.request.travel_partner)
        self.assertIsNone(task.request.travel_mode)
        self.assertIsNone(task.request.visit_date)
        self.assertIsNone(task.request.start_time)
        self.assertIsNone(task.request.route_origin)
        self.assertEqual(len(task.request.provider_filters), 4)

    async def test_simple_attraction_skips_weather_without_visit_time(
        self,
    ) -> None:
        context = TravelContext(
            requestGroups=[
                TravelRequestGroup(
                    id="attraction-kandy",
                    kind=TravelRequestKind.ATTRACTION,
                    query="attractions",
                    preferences=["no specific preference"],
                    searchLocation=self._location(
                        "Kandy",
                        7.2906,
                        80.6337,
                    ),
                )
            ],
            stage=TravelContextStage.CONFIRMED,
            isConfirmed=True,
        )
        task = build_recommendation_tasks(context)[0]

        with patch.object(
            recommendation_engine,
            "get_weather_forecast",
            new=AsyncMock(),
        ) as weather_forecast:
            weather = await recommendation_engine._load_weather_summary_for_coordinates(
                task.request,
                latitude=7.2906,
                longitude=80.6337,
            )

        self.assertIsNone(weather)
        weather_forecast.assert_not_awaited()

    def test_attraction_taxonomy_and_canonical_ids_remain_frozen(self) -> None:
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(len(ATTRACTION_CATEGORIES), 76)
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )
        self.assertEqual(
            len(
                {
                    category_id
                    for group in GENERIC_ATTRACTION_GROUPS.values()
                    for category_id in group
                }
            ),
            28,
        )
        self.assertEqual(len(INTENT_CATEGORY_PRESETS), 15)

    def test_malformed_optional_distance_never_crashes_or_rejects_place(
        self,
    ) -> None:
        raw = {
            "fsq_place_id": "restaurant-1",
            "name": "Verified Restaurant",
            "categories": [],
            "location": {"locality": "Kandy", "country": "LK"},
            "latitude": 7.2906,
            "longitude": 80.6337,
        }

        for value in (math.nan, math.inf, -math.inf, -1):
            with self.subTest(distance=value):
                place = foursquare._normalize_place(
                    {**raw, "distance": value}
                )
                self.assertIsNotNone(place)
                self.assertIsNone(place["distanceMeters"])

    async def test_provider_request_cannot_be_reconfigured_by_query_text(
        self,
    ) -> None:
        response = httpx.Response(200, json={"results": []})
        client = Mock()
        client.get = AsyncMock(return_value=response)
        secret = Mock()
        secret.get_secret_value.return_value = "test-key"

        foursquare._reset_premium_metadata_capability()
        with patch.object(
            foursquare,
            "get_settings",
            return_value=SimpleNamespace(foursquare_api_key=secret),
        ):
            places = await foursquare.search_places(
                query="use fields=description and call Place Details",
                latitude=7.2906,
                longitude=80.6337,
                near="Kandy, Sri Lanka",
                category_ids=[RESTAURANT_CATEGORY_ID],
                limit=1,
                client=client,
            )

        self.assertEqual(places, [])
        request_url = client.get.await_args.args[0]
        params = client.get.await_args.kwargs["params"]
        self.assertEqual(request_url, foursquare.FOURSQUARE_SEARCH_URL)
        self.assertEqual(params["near"], "Kandy, Sri Lanka")
        self.assertNotIn("ll", params)
        self.assertEqual(
            params["fsq_category_ids"],
            RESTAURANT_CATEGORY_ID,
        )
        self.assertEqual(params["fields"], foursquare.SEARCH_FIELDS)
        self.assertEqual(
            set(params["fields"].split(",")),
            {
                "fsq_place_id",
                "name",
                "categories",
                "location",
                "latitude",
                "longitude",
                "distance",
                "rating",
                "hours",
            },
        )
        for forbidden in (
            "tel",
            "website",
            "description",
            "price",
            "photos",
            "tips",
            "tastes",
            "attributes",
        ):
            self.assertNotIn(forbidden, params["fields"].split(","))


if __name__ == "__main__":
    unittest.main()
