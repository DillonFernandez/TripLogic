"""Regression contracts for the removed room-count product concept."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import conversation_context_requirements  # noqa: E402
from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_extraction_models import (  # noqa: E402
    TravelContextPatch,
)
from app.conversation_interpreter import ConversationInterpreter  # noqa: E402
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
from app.foursquare_categories import HOTEL_CATEGORY_ID  # noqa: E402
from app.recommendation_models import (  # noqa: E402
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


class RoomCountRemovalTests(unittest.TestCase):
    @staticmethod
    def _location(name: str = "Kandy") -> TravelLocation:
        return TravelLocation(
            displayName=name,
            localityName=name,
            source=TravelLocationSource.SEARCHED,
            latitude=7.2906,
            longitude=80.6336,
            countryCode="LK",
            verified=True,
        )

    def _hotel_context(
        self,
        *,
        complete_itinerary: bool = False,
        traveller_count: int | None = None,
        fixed_places: list[FixedTravelPlace] | None = None,
    ) -> TravelContext:
        return TravelContext(
            stage=(
                TravelContextStage.COLLECTING
                if complete_itinerary
                else TravelContextStage.CONFIRMED
            ),
            travellerType=TravellerType.COUPLE,
            travellerCount=traveller_count,
            travelModes=["driving"],
            requestGroups=[
                TravelRequestGroup(
                    id="hotel-request",
                    kind=TravelRequestKind.HOTEL,
                    query="hotels in Kandy",
                    preferences=["boutique hotel"],
                    searchLocation=self._location(),
                )
            ],
            fixedPlaces=fixed_places or [],
            missingFields=[],
            uncertainties=[],
            isConfirmed=not complete_itinerary,
            requiresCompleteItinerary=complete_itinerary,
        )

    def test_active_backend_schemas_have_no_room_count_target(self) -> None:
        self.assertNotIn("room_count", TravelContext.model_fields)
        self.assertNotIn("room_count", TravelContextPatch.model_fields)
        self.assertNotIn("rooms", RecommendationRequest.model_fields)
        self.assertFalse(
            hasattr(
                conversation_context_requirements,
                "MISSING_ROOM_COUNT",
            )
        )
        self.assertNotIn("roomCount", QUESTION_BY_MISSING_FIELD)

        extraction_schema = json.dumps(
            TravelContextPatch.model_json_schema(),
            sort_keys=True,
        )
        self.assertNotIn("roomCount", extraction_schema)
        self.assertNotIn("room_count", extraction_schema)

    def test_hotel_discovery_and_confirmation_need_no_room_count(self) -> None:
        context = self._hotel_context()

        self.assertTrue(context.is_ready_for_confirmation)
        self.assertFalse(
            any("room" in field.casefold() for field in context.missing_fields)
        )

        summary = build_confirmation_summary(context)
        self.assertIn("Hotel recommendations", summary)
        self.assertIn("Kandy", summary)
        self.assertNotIn("room", summary.casefold())

        task = build_recommendation_tasks(context)[0]
        request_payload = task.request.model_dump(by_alias=True)
        self.assertNotIn("rooms", request_payload)
        self.assertEqual(
            task.request.provider_filters[0].category_ids,
            (HOTEL_CATEGORY_ID,),
        )

    def test_complete_itinerary_retains_guest_requirement_not_room_count(self) -> None:
        context = self._hotel_context(complete_itinerary=True)

        missing_fields = conversation_context_requirements.compute_missing_fields(
            context
        )

        self.assertIn(
            conversation_context_requirements.MISSING_TRAVELLER_COUNT,
            missing_fields,
        )
        self.assertFalse(any("room" in value.casefold() for value in missing_fields))

    def test_traveller_count_and_accommodation_preference_remain_supported(
        self,
    ) -> None:
        context = self._hotel_context(traveller_count=4)

        self.assertEqual(context.traveller_count, 4)
        self.assertEqual(
            context.request_groups[0].preferences,
            ["boutique hotel"],
        )

        task = build_recommendation_tasks(context)[0]
        self.assertEqual(task.request.travellers, 4)
        self.assertNotIn("rooms", task.request.model_dump(by_alias=True))

    def test_existing_booked_daily_base_remains_supported(self) -> None:
        booked_hotel = FixedTravelPlace(
            id="booked-hotel",
            name="Existing booking",
            role=FixedTravelPlaceRole.DAILY_BASE,
            location=self._location(),
            confirmed=True,
        )
        context = self._hotel_context(fixed_places=[booked_hotel])

        self.assertEqual(context.fixed_places, [booked_hotel])
        self.assertTrue(context.has_route_ready_daily_base)

    def test_new_context_and_interpreter_payload_emit_no_room_count(self) -> None:
        context = self._hotel_context(traveller_count=2)
        serialized = context.model_dump(by_alias=True, mode="json")

        self.assertNotIn("roomCount", serialized)
        self.assertEqual(serialized["travellerCount"], 2)

        interpreter_payload = json.loads(
            ConversationInterpreter._build_input_payload(
                traveller_message="We need two rooms",
                current_context=context,
                recent_messages=[],
                traveller_name="Dillon",
            )
        )
        self.assertNotIn(
            "roomCount",
            interpreter_payload["currentTravelContext"],
        )

    def test_historical_room_count_is_ignored_and_not_reemitted(self) -> None:
        context = TravelContext.model_validate(
            {
                "revision": 3,
                "travellerCount": 4,
                "roomCount": 2,
                "missingFields": ["roomCount", "travelMode"],
            }
        )

        self.assertEqual(context.traveller_count, 4)
        self.assertEqual(context.missing_fields, ["travelMode"])

        serialized = context.model_dump(by_alias=True, mode="json")
        self.assertNotIn("roomCount", serialized)
        self.assertEqual(serialized["travellerCount"], 4)
        self.assertEqual(serialized["missingFields"], ["travelMode"])

    def test_unrelated_unknown_context_fields_remain_forbidden(self) -> None:
        with self.assertRaises(ValidationError):
            TravelContext.model_validate({"unrecognizedField": True})

    def test_public_recommendation_payload_cannot_send_rooms(self) -> None:
        with self.assertRaises(ValidationError):
            RecommendationRequest(
                recommendationType="hotel",
                location=RecommendationLocation(
                    displayName="Kandy",
                    latitude=7.2906,
                    longitude=80.6336,
                    source="selected",
                ),
                travelMode="driving",
                travelPartner="couple",
                categories=[RecommendationCategory(name="hotel")],
                rooms=2,
            )


if __name__ == "__main__":
    unittest.main()
