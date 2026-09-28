"""Regressions for duration semantics, per-group counts, and confirmation text."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import (  # noqa: E402
    conversation_recommendation_runner,
    conversation_router,
)
from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_context_patcher import (  # noqa: E402
    apply_conversation_interpretation,
)
from app.conversation_context_requirements import (  # noqa: E402
    refresh_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
)
from app.conversation_interpreter import INTERPRETER_INSTRUCTIONS  # noqa: E402
from app.conversation_models import (  # noqa: E402
    ConversationMessageType,
    ConversationNextAction,
    ConversationTurnOperation,
    ConversationTurnRequest,
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
from app.conversation_store import ConversationState  # noqa: E402
from app.recommendation_models import (  # noqa: E402
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)


SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class DurationCountConfirmationTests(unittest.IsolatedAsyncioTestCase):
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
            admin1="Central Province",
            verified=True,
        )

    @classmethod
    def _kandy(cls) -> TravelLocation:
        return cls._location("Kandy", 7.2906, 80.6337)

    @classmethod
    def _colombo(cls) -> TravelLocation:
        return cls._location("Colombo", 6.9271, 79.8612)

    @classmethod
    def _groups(
        cls,
        *,
        attraction_count: int | None = 5,
        restaurant_count: int | None = 3,
        hotel_count: int | None = 2,
    ) -> list[TravelRequestGroup]:
        return [
            TravelRequestGroup(
                id="attractions-kandy",
                kind=TravelRequestKind.ATTRACTION,
                query="attractions",
                preferences=["scenic places", "waterfalls"],
                requestedCount=attraction_count,
                searchLocation=cls._kandy(),
            ),
            TravelRequestGroup(
                id="restaurants-kandy",
                kind=TravelRequestKind.RESTAURANT,
                query="restaurants",
                preferences=["no specific preference"],
                dietaryRequirements=["vegetarian"],
                mealIntents=["lunch"],
                requestedCount=restaurant_count,
                searchLocation=cls._kandy(),
            ),
            TravelRequestGroup(
                id="hotels-kandy",
                kind=TravelRequestKind.HOTEL,
                query="hotels",
                preferences=["boutique hotels"],
                requestedCount=hotel_count,
                searchLocation=cls._kandy(),
            ),
        ]

    @classmethod
    def _confirmed_multi_context(cls) -> TravelContext:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        return TravelContext(
            stage=TravelContextStage.CONFIRMED,
            startingLocation=cls._colombo(),
            tripStartDate=tomorrow,
            tripEndDate=tomorrow,
            dailyStartTime="07:00:00",
            dailyEndTime="21:00:00",
            travellerType=TravellerType.COUPLE,
            travellerCount=2,
            travelModes=["driving"],
            requestGroups=cls._groups(),
            isConfirmed=True,
        )

    @classmethod
    def _awaiting_multi_context(cls) -> TravelContext:
        confirmed = cls._confirmed_multi_context()
        data = confirmed.model_dump(mode="python")
        data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        data["is_confirmed"] = False
        review_context = TravelContext.model_validate(data)
        data["confirmation_summary"] = build_confirmation_summary(review_context)

        return TravelContext.model_validate(data)

    def test_daily_window_is_not_one_place_visit_duration(self) -> None:
        context = self._confirmed_multi_context()

        tasks = build_recommendation_tasks(context)

        self.assertEqual(context.daily_start_time, "07:00:00")
        self.assertEqual(context.daily_end_time, "21:00:00")
        self.assertEqual(
            [task.request.visit_duration_minutes for task in tasks],
            [None, None, None],
        )

    async def test_runner_builds_all_requests_without_840_validation_error(
        self,
    ) -> None:
        observed: list[tuple[str, int | None, int | None]] = []

        async def fake_generate(
            request: RecommendationRequest,
            *,
            requested_count: int | None,
            include_internal_route_matrix: bool,
        ) -> dict[str, object]:
            self.assertFalse(include_internal_route_matrix)
            observed.append(
                (
                    request.recommendation_type,
                    request.visit_duration_minutes,
                    requested_count,
                )
            )
            return {
                "topRecommendations": [],
                "moreRecommendations": [],
                "count": 0,
            }

        with patch.object(
            conversation_recommendation_runner,
            "generate_recommendations",
            side_effect=fake_generate,
        ):
            groups = await (
                conversation_recommendation_runner
                .generate_conversation_recommendations(
                    self._confirmed_multi_context()
                )
            )

        self.assertEqual(
            observed,
            [
                ("attraction", None, 5),
                ("restaurant", None, 3),
                ("hotel", None, 2),
            ],
        )
        self.assertEqual(
            [group["requestedCount"] for group in groups],
            [5, 3, 2],
        )

    def test_explicit_visit_duration_contract_remains_validated(self) -> None:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)
        common = {
            "recommendationType": "attraction",
            "location": RecommendationLocation(
                displayName="Kandy",
                latitude=7.2906,
                longitude=80.6337,
                source="selected",
            ),
            "travelMode": "driving",
            "travelPartner": "couple",
            "categories": [RecommendationCategory(name="attractions")],
            "visitDate": tomorrow,
            "startTime": "09:00:00",
        }

        unspecified = RecommendationRequest(**common)
        valid = RecommendationRequest(**common, visitDurationMinutes=90)
        boundary = RecommendationRequest(**common, visitDurationMinutes=720)

        self.assertIsNone(unspecified.visit_duration_minutes)
        self.assertEqual(valid.visit_duration_minutes, 90)
        self.assertEqual(boundary.visit_duration_minutes, 720)

        with self.assertRaises(ValidationError):
            RecommendationRequest(**common, visitDurationMinutes=721)

    def test_interpreter_contract_assigns_counts_per_group(self) -> None:
        self.assertIn(
            "requestedCount belongs to one ExtractedRequestGroup only",
            INTERPRETER_INSTRUCTIONS,
        )
        self.assertIn(
            "requestedCount values 5, 3, and 2 respectively",
            INTERPRETER_INSTRUCTIONS,
        )
        self.assertIn(
            "preserve every unaffected group",
            INTERPRETER_INSTRUCTIONS,
        )

    def test_initial_multi_group_patch_preserves_independent_counts(self) -> None:
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "startNewTrip",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "attraction",
                                "query": "attractions",
                                "searchLocationText": "Kandy",
                                "requestedCount": 5,
                            },
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "searchLocationText": "Kandy",
                                "requestedCount": 3,
                            },
                            {
                                "kind": "hotel",
                                "query": "hotels",
                                "searchLocationText": "Kandy",
                                "requestedCount": 2,
                            },
                        ],
                    }
                },
            }
        )

        context = apply_conversation_interpretation(
            current_context=TravelContext(),
            interpretation=interpretation,
            traveller_message=(
                "Give me 5 attractions, 3 restaurants and 2 hotels in Kandy"
            ),
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in context.request_groups],
            [("attraction", 5), ("restaurant", 3), ("hotel", 2)],
        )
        self.assertEqual(
            [group.search_location.display_name for group in context.request_groups],
            ["Kandy", "Kandy", "Kandy"],
        )

    def test_explicit_scope_recovers_a_group_omitted_by_extraction(self) -> None:
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "startNewTrip",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "attraction",
                                "query": "attractions",
                                "searchLocationText": "Kandy",
                                "requestedCount": 5,
                            },
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "searchLocationText": "Kandy",
                                "requestedCount": 3,
                            },
                        ],
                    }
                },
            }
        )

        context = apply_conversation_interpretation(
            current_context=TravelContext(),
            interpretation=interpretation,
            traveller_message=(
                "5 attractions, 3 restaurants and 2 hotels in Kandy"
            ),
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in context.request_groups],
            [("attraction", 5), ("restaurant", 3), ("hotel", 2)],
        )
        self.assertEqual(
            [group.search_location.display_name for group in context.request_groups],
            ["Kandy", "Kandy", "Kandy"],
        )

    def test_preference_answer_does_not_remove_an_unmentioned_group(self) -> None:
        context_data = self._awaiting_multi_context().model_dump(mode="python")
        context_data.update(
            stage=TravelContextStage.COLLECTING,
            is_confirmed=False,
            confirmation_summary=None,
        )
        context = TravelContext.model_validate(context_data)
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "continueCurrentRequest",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "attraction",
                                "query": "attractions",
                                "preferences": ["no specific preference"],
                            },
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "cuisinePreferences": ["no preference"],
                            },
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=context,
            interpretation=interpretation,
            traveller_message=(
                "No preference for restaurants and surprise me for attractions"
            ),
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in updated.request_groups],
            [("attraction", 5), ("restaurant", 3), ("hotel", 2)],
        )

    def test_single_count_correction_preserves_other_groups(self) -> None:
        correction = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "attraction",
                                "query": "attractions",
                                "requestedCount": 7,
                            }
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=self._awaiting_multi_context(),
            interpretation=correction,
            traveller_message="Actually make it 7 attractions",
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in updated.request_groups],
            [("attraction", 7), ("restaurant", 3), ("hotel", 2)],
        )

    def test_count_only_correction_does_not_depend_on_reworded_query(self) -> None:
        correction = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "attraction",
                                "query": "seven attractions",
                                "requestedCount": 7,
                            }
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=self._awaiting_multi_context(),
            interpretation=correction,
            traveller_message="Actually make it 7 attractions",
        )

        self.assertEqual(len(updated.request_groups), 3)
        self.assertEqual(updated.request_groups[0].query, "attractions")
        self.assertEqual(
            [group.requested_count for group in updated.request_groups],
            [7, 3, 2],
        )

    def test_two_count_corrections_preserve_the_third(self) -> None:
        correction = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "hotel",
                                "query": "hotels",
                                "requestedCount": 1,
                            },
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "requestedCount": 4,
                            },
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=self._awaiting_multi_context(),
            interpretation=correction,
            traveller_message="Make restaurants 4 and hotels 1",
        )

        self.assertEqual(
            [(group.kind.value, group.requested_count) for group in updated.request_groups],
            [("attraction", 5), ("restaurant", 4), ("hotel", 1)],
        )

    def test_unspecified_count_does_not_steal_or_clear_another_count(self) -> None:
        addition = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "preferences": ["outdoor seating"],
                            }
                        ],
                    }
                },
            }
        )

        updated = apply_conversation_interpretation(
            current_context=self._awaiting_multi_context(),
            interpretation=addition,
            traveller_message="Make the restaurants outdoor seating",
        )

        self.assertEqual(
            [group.requested_count for group in updated.request_groups],
            [5, 3, 2],
        )
        self.assertIn("outdoor seating", updated.request_groups[1].preferences)

    def test_serialization_round_trip_preserves_group_counts(self) -> None:
        context = self._awaiting_multi_context()
        restored = TravelContext.model_validate(
            context.model_dump(by_alias=True, mode="json")
        )

        self.assertEqual(
            [group.requested_count for group in restored.request_groups],
            [5, 3, 2],
        )

    def test_multi_group_confirmation_is_structured_and_complete(self) -> None:
        summary = build_confirmation_summary(self._awaiting_multi_context())

        self.assertTrue(summary.startswith("Please confirm these trip details:"))
        self.assertIn("\n\nRecommendations\n", summary)
        self.assertIn(
            "• Attractions\n  Location: Kandy\n  Number requested: 5",
            summary,
        )
        self.assertIn(
            "• Restaurants\n  Location: Kandy\n  Number requested: 3",
            summary,
        )
        self.assertIn(
            "• Hotels\n  Location: Kandy\n  Number requested: 2",
            summary,
        )
        self.assertIn("Meal: Lunch", summary)
        self.assertIn("Dietary requirements: Vegetarian", summary)
        self.assertIn("Preferences: Scenic places, Waterfalls", summary)
        self.assertIn("Preferences: Boutique hotels", summary)
        self.assertNotIn("requestedCount", summary)
        self.assertNotIn("room", summary.casefold())
        self.assertNotIn("4d4b7105d754a06374d81259", summary)

    def test_simple_confirmation_remains_concise(self) -> None:
        context = refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="restaurants-kandy",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        preferences=["no specific preference"],
                        searchLocation=self._kandy(),
                    )
                ]
            )
        )

        summary = build_confirmation_summary(context)

        self.assertEqual(
            summary,
            "Please confirm these trip details:\n\n"
            "Restaurant recommendations\n\n"
            "• Location: Kandy\n"
            "• Cuisine: No preference — Trip Logic chooses\n\n"
            "Please confirm these details or tell me what you would like to change.",
        )

    def test_full_itinerary_confirmation_uses_human_labels(self) -> None:
        context = refresh_missing_fields(
            TravelContext(
                requiresCompleteItinerary=True,
                startingLocation=self._colombo(),
                tripStartDate=date(2026, 9, 5),
                tripEndDate=date(2026, 9, 7),
                dailyStartTime="07:00:00",
                dailyEndTime="21:00:00",
                travellerType=TravellerType.COUPLE,
                travellerCount=2,
                travelPartyDescription="two adults",
                travelModes=["driving"],
                requestGroups=self._groups(),
                fixedPlaces=[
                    FixedTravelPlace(
                        id="final-kandy",
                        name="Kandy",
                        role=FixedTravelPlaceRole.END_POINT,
                        location=self._kandy(),
                    )
                ],
            )
        )

        summary = build_confirmation_summary(context)

        self.assertIn("Trip details\n\n", summary)
        self.assertIn("• Starting location: Colombo", summary)
        self.assertIn("• Final ending location: Kandy", summary)
        self.assertIn("• Dates: 5 September 2026 to 7 September 2026", summary)
        self.assertIn("• Daily start time: 7:00 AM", summary)
        self.assertIn("• Final arrival deadline: 9:00 PM", summary)
        self.assertIn("• Travellers: 2 travellers, Couple, Two adults", summary)
        self.assertIn("• Travel mode: Driving", summary)

    async def test_router_preserves_confirmation_punctuation_and_spacing(
        self,
    ) -> None:
        context = self._confirmed_multi_context()
        context_data = context.model_dump(mode="python")
        context_data["stage"] = TravelContextStage.COLLECTING
        context_data["is_confirmed"] = False
        context = TravelContext.model_validate(context_data)

        response, runner = await self._run_router_turn(
            context=context,
            text="go ahead",
        )
        message = response.assistant_messages[0]

        runner.assert_not_awaited()
        self.assertEqual(message.type, ConversationMessageType.CONFIRMATION)
        self.assertEqual(
            response.next_action,
            ConversationNextAction.REQUEST_CONFIRMATION,
        )
        self.assertIn("Please confirm these trip details:", message.text)
        self.assertIn("\n\nRecommendations\n", message.text)
        self.assertIn("• Attractions", message.text)
        self.assertIn("No preference — Trip Logic chooses", message.text)
        self.assertIn("7:00 AM", message.text)

    async def test_confirmation_endpoint_dispatches_without_duration_500(
        self,
    ) -> None:
        context = self._awaiting_multi_context()
        observed_requests: list[RecommendationRequest] = []

        async def fake_generate(
            request: RecommendationRequest,
            *,
            requested_count: int | None,
            include_internal_route_matrix: bool,
        ) -> dict[str, object]:
            observed_requests.append(request)
            return {
                "topRecommendations": [],
                "moreRecommendations": [],
                "count": 0,
            }

        with patch.object(
            conversation_recommendation_runner,
            "generate_recommendations",
            side_effect=fake_generate,
        ):
            response, runner = await self._run_router_turn(
                context=context,
                text="okay",
                patch_router_runner=False,
            )

        self.assertIsNone(runner)
        self.assertTrue(response.context.is_confirmed)
        self.assertEqual(len(response.assistant_messages[0].data["recommendationGroups"]), 3)
        self.assertEqual(
            [request.visit_duration_minutes for request in observed_requests],
            [None, None, None],
        )

    async def _run_router_turn(
        self,
        *,
        context: TravelContext,
        text: str,
        patch_router_runner: bool = True,
    ):
        request = ConversationTurnRequest(
            requestId="request-physical-regression",
            operation=ConversationTurnOperation.SEND_MESSAGE,
            chatId="chat-physical-regression",
            travellerMessageId="traveller-physical-regression",
            turnId="turn-physical-regression",
            travellerMessageSequence=0,
            text=text,
            clientCreatedAt=datetime.now(timezone.utc),
            expectedContextRevision=context.revision,
        )
        state = ConversationState(
            uid="traveller-1",
            chat_id=request.chat_id,
            chat_reference=Mock(),
            chat_data={"title": "Kandy recommendations"},
            context_revision=context.revision,
            context=context,
            recent_messages=(),
        )
        interpreter = SimpleNamespace(interpret=AsyncMock())
        router_runner = AsyncMock(return_value=[])

        common_patches = (
            patch.object(
                conversation_router,
                "get_processed_response",
                return_value=None,
            ),
            patch.object(
                conversation_router,
                "load_conversation_state",
                return_value=state,
            ),
            patch.object(
                conversation_router,
                "validate_traveller_message",
                return_value={},
            ),
            patch.object(
                conversation_router,
                "persist_conversation_response",
                side_effect=lambda **kwargs: kwargs["response"],
            ),
            patch.object(
                conversation_router,
                "get_conversation_interpreter",
                return_value=interpreter,
            ),
        )

        with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4]:
            if patch_router_runner:
                with patch.object(
                    conversation_router,
                    "generate_conversation_recommendations",
                    router_runner,
                ):
                    response = await conversation_router.process_conversation_turn(
                        request,
                        {"uid": "traveller-1", "name": "Dillon"},
                    )
                return response, router_runner

            response = await conversation_router.process_conversation_turn(
                request,
                {"uid": "traveller-1", "name": "Dillon"},
            )
            return response, None


if __name__ == "__main__":
    unittest.main()
