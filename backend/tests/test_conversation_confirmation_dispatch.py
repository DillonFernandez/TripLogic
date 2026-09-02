"""Regression contracts for confirmation-to-recommendation dispatch."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import conversation_router  # noqa: E402
from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_context_requirements import (  # noqa: E402
    MISSING_FINAL_ENDING_LOCATION,
    MISSING_STARTING_LOCATION,
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
from app.conversation_store import ConversationState  # noqa: E402
from app.foursquare_categories import RESTAURANT_CATEGORY_ID  # noqa: E402


class ConversationConfirmationDispatchTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        self._turn_number = 0

    @staticmethod
    def _kandy() -> TravelLocation:
        return TravelLocation(
            displayName="Kandy",
            localityName="Kandy",
            source=TravelLocationSource.SEARCHED,
            latitude=7.2906,
            longitude=80.6337,
            providerPlaceId="open-meteo-kandy",
            countryCode="LK",
            admin1="Central Province",
            admin2="Kandy District",
            verified=True,
        )

    def _restaurant_context(
        self,
        *,
        stage: TravelContextStage = TravelContextStage.AWAITING_CONFIRMATION,
        meal_intents: list[str] | None = None,
        preferences: list[str] | None = None,
        revision: int = 0,
    ) -> TravelContext:
        context = refresh_missing_fields(
            TravelContext(
                revision=revision,
                stage=stage,
                requestGroups=[
                    TravelRequestGroup(
                        id="restaurant-kandy",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        preferences=(
                            preferences
                            if preferences is not None
                            else ["no specific preference"]
                        ),
                        mealIntents=meal_intents or [],
                        searchLocation=self._kandy(),
                    )
                ],
            )
        )

        context_data = context.model_dump(mode="python")
        context_data["stage"] = stage

        if stage is TravelContextStage.AWAITING_CONFIRMATION:
            context_data["confirmation_summary"] = (
                build_confirmation_summary(context)
            )
        elif stage is TravelContextStage.CONFIRMED:
            context_data["is_confirmed"] = True

        return TravelContext.model_validate(context_data)

    def _hotel_context(self) -> TravelContext:
        return refresh_missing_fields(
            TravelContext(
                requestGroups=[
                    TravelRequestGroup(
                        id="hotel-kandy",
                        kind=TravelRequestKind.HOTEL,
                        query="hotels",
                        searchLocation=self._kandy(),
                    )
                ],
            )
        )

    @staticmethod
    def _recommendation_groups() -> list[dict[str, object]]:
        return [
            {
                "requestGroupId": "restaurant-kandy",
                "recommendationType": "restaurant",
                "travellerQuery": "restaurants",
                "requestedCount": None,
                "required": True,
                "result": {
                    "topRecommendations": [
                        {
                            "name": "Verified Kandy Restaurant",
                            "category": "Restaurant",
                            "distanceKm": 0.4,
                        }
                    ],
                    "moreRecommendations": [],
                },
            }
        ]

    async def _run_turn(
        self,
        *,
        context: TravelContext,
        text: str,
        interpretation: ConversationInterpretation | None = None,
        runner: AsyncMock | None = None,
    ):
        self._turn_number += 1
        turn = self._turn_number

        request = ConversationTurnRequest(
            requestId=f"request-{turn}",
            operation=ConversationTurnOperation.SEND_MESSAGE,
            chatId="chat-confirmation-regression",
            travellerMessageId=f"traveller-{turn}",
            turnId=f"turn-{turn}",
            travellerMessageSequence=(turn - 1) * 2,
            text=text,
            clientCreatedAt=datetime.now(timezone.utc),
            expectedContextRevision=context.revision,
        )
        state = ConversationState(
            uid="traveller-1",
            chat_id=request.chat_id,
            chat_reference=Mock(),
            chat_data={"title": "Kandy restaurants"},
            context_revision=context.revision,
            context=context,
            recent_messages=(),
        )
        interpreter = SimpleNamespace(
            interpret=AsyncMock(
                return_value=(
                    interpretation
                    or ConversationInterpretation(
                        action="continueCurrentRequest",
                        responseIntent="socialChat",
                        assistantReply="Thanks.",
                    )
                )
            )
        )
        recommendation_runner = runner or AsyncMock(
            return_value=self._recommendation_groups()
        )

        with (
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
            patch.object(
                conversation_router,
                "generate_conversation_recommendations",
                recommendation_runner,
            ),
        ):
            response = await conversation_router.process_conversation_turn(
                request,
                {"uid": "traveller-1", "name": "Dillon"},
            )

        return response, recommendation_runner, interpreter

    def test_complete_restaurant_confirmation_summary(self) -> None:
        context = self._restaurant_context(
            meal_intents=["lunch"],
            preferences=["no specific preference", "best of the best"],
        )

        summary = build_confirmation_summary(context)

        self.assertIn("Restaurant recommendations", summary)
        self.assertIn("• Location: Kandy", summary)
        self.assertIn(
            "• Cuisine: No preference — Trip Logic chooses",
            summary,
        )
        self.assertIn("• Meal: Lunch", summary)
        self.assertIn("• Preferences: Best of the best", summary)
        self.assertNotIn("room", summary.casefold())
        self.assertNotIn("hotel", summary.casefold())
        self.assertNotIn("check-in", summary.casefold())

    def test_interpreter_contract_distinguishes_confirmation_from_correction(
        self,
    ) -> None:
        self.assertIn(
            "currentTravelContext.stage is awaitingConfirmation",
            INTERPRETER_INSTRUCTIONS,
        )
        self.assertIn("use action confirmSummary", INTERPRETER_INSTRUCTIONS)
        self.assertIn("use\ncorrectInformation", INTERPRETER_INSTRUCTIONS)
        self.assertIn(
            "Do not confirm the changed summary in the same turn",
            INTERPRETER_INSTRUCTIONS,
        )

    async def test_correction_during_confirmation_requires_updated_review(
        self,
    ) -> None:
        correction = ConversationInterpretation.model_validate(
            {
                "action": "confirmSummary",
                "responseIntent": "correctTripDetails",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "preferences": ["best of the best"],
                                "mealIntents": ["lunch"],
                            }
                        ],
                    }
                },
                "assistantReply": (
                    "Great Dillon. I will show the top lunch restaurants now."
                ),
            }
        )

        response, runner, _ = await self._run_turn(
            context=self._restaurant_context(),
            text=(
                "yes for lunch only give me the best of the best in kandy"
            ),
            interpretation=correction,
        )

        group = response.context.request_groups[0]
        message = response.assistant_messages[0]

        runner.assert_not_awaited()
        self.assertEqual(
            response.context.stage,
            TravelContextStage.AWAITING_CONFIRMATION,
        )
        self.assertFalse(response.context.is_confirmed)
        self.assertEqual(response.next_action, ConversationNextAction.REQUEST_CONFIRMATION)
        self.assertEqual(message.type, ConversationMessageType.CONFIRMATION)
        self.assertIn("Kandy", message.text)
        self.assertIn("Lunch", message.text)
        self.assertIn("No preference", message.text)
        self.assertIn("Best of the best", message.text)
        self.assertEqual(group.search_location.display_name, "Kandy")
        self.assertEqual(group.meal_intents, ["lunch"])
        self.assertEqual(
            group.preferences,
            ["no specific preference", "best of the best"],
        )
        self.assertNotIn("I will show", message.text)

    async def test_natural_clean_confirmations_dispatch_immediately(self) -> None:
        confirmations = (
            "yes",
            "yes please",
            "looks good",
            "correct",
            "confirmed",
            "go ahead",
            "okay go ahead and give it so",
            "okay",
            "ok",
            "okay thx",
            "sounds good",
            "do it",
            "give it to me",
            "proceed",
        )

        for confirmation in confirmations:
            with self.subTest(confirmation=confirmation):
                response, runner, interpreter = await self._run_turn(
                    context=self._restaurant_context(),
                    text=confirmation,
                )

                runner.assert_awaited_once()
                interpreter.interpret.assert_not_awaited()
                self.assertEqual(
                    response.context.stage,
                    TravelContextStage.CONFIRMED,
                )
                self.assertTrue(response.context.is_confirmed)
                self.assertEqual(response.next_action, ConversationNextAction.NONE)
                self.assertTrue(
                    response.assistant_messages[0].data["externalApisCalled"]
                )
                self.assertEqual(
                    response.assistant_messages[0].data[
                        "recommendationGroups"
                    ],
                    self._recommendation_groups(),
                )
                self.assertNotIn(
                    "i'll proceed",
                    response.assistant_messages[0].text.casefold(),
                )

    async def test_ready_collecting_context_shows_summary_before_dispatch(
        self,
    ) -> None:
        response, runner, interpreter = await self._run_turn(
            context=self._restaurant_context(
                stage=TravelContextStage.COLLECTING,
            ),
            text="go ahead",
        )

        runner.assert_not_awaited()
        interpreter.interpret.assert_not_awaited()
        self.assertEqual(
            response.context.stage,
            TravelContextStage.AWAITING_CONFIRMATION,
        )
        self.assertEqual(response.next_action, ConversationNextAction.REQUEST_CONFIRMATION)
        self.assertEqual(
            response.assistant_messages[0].type,
            ConversationMessageType.CONFIRMATION,
        )
        self.assertIn(
            "Restaurant recommendations",
            response.assistant_messages[0].text,
        )
        self.assertIn("Kandy", response.assistant_messages[0].text)

    async def test_ready_simple_hotel_ignores_optional_gpt_date_question(
        self,
    ) -> None:
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "continueCurrentRequest",
                "assistantReply": (
                    "Got it Dillon. When are you travelling to Kandy?"
                ),
                "requiresUserConfirmation": True,
            }
        )

        response, runner, interpreter = await self._run_turn(
            context=self._hotel_context(),
            text="hotels in Kandy",
            interpretation=interpretation,
        )

        interpreter.interpret.assert_awaited_once()
        runner.assert_not_awaited()
        self.assertEqual(
            response.context.stage,
            TravelContextStage.AWAITING_CONFIRMATION,
        )
        self.assertEqual(
            response.next_action,
            ConversationNextAction.REQUEST_CONFIRMATION,
        )
        self.assertEqual(
            response.assistant_messages[0].type,
            ConversationMessageType.CONFIRMATION,
        )
        self.assertIn(
            "Hotel recommendations",
            response.assistant_messages[0].text,
        )
        self.assertIn("Kandy", response.assistant_messages[0].text)
        self.assertNotIn(
            "when are you travelling",
            response.assistant_messages[0].text.casefold(),
        )
        self.assertNotIn(
            "room",
            response.assistant_messages[0].text.casefold(),
        )

    async def test_deterministic_next_question_replaces_unrelated_gpt_question(
        self,
    ) -> None:
        interpretation = ConversationInterpretation.model_validate(
            {
                "action": "continueCurrentRequest",
                "responseIntent": "askTravelQuestion",
                "assistantReply": "When are you travelling to Kandy?",
            }
        )

        response, runner, _ = await self._run_turn(
            context=self._restaurant_context(
                stage=TravelContextStage.COLLECTING,
                preferences=[],
            ),
            text="start in Colombo, find restaurants in Kandy",
            interpretation=interpretation,
        )

        assistant_text = response.assistant_messages[0].text
        self.assertIn("What would you like to eat?", assistant_text)
        self.assertNotIn("When are you travelling", assistant_text)
        self.assertEqual(
            response.next_action,
            ConversationNextAction.ASK_QUESTION,
        )
        runner.assert_not_awaited()

    async def test_physical_app_sequence_dispatches_without_acknowledgement_loop(
        self,
    ) -> None:
        ready_context = self._restaurant_context(
            stage=TravelContextStage.COLLECTING,
        )

        first_review, first_runner, _ = await self._run_turn(
            context=ready_context,
            text="go ahead",
        )
        first_runner.assert_not_awaited()

        correction = ConversationInterpretation.model_validate(
            {
                "action": "correctInformation",
                "responseIntent": "correctTripDetails",
                "contextPatch": {
                    "requestGroups": {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": "restaurant",
                                "query": "restaurants",
                                "preferences": ["best of the best"],
                                "mealIntents": ["lunch"],
                            }
                        ],
                    }
                },
            }
        )
        updated_review, correction_runner, _ = await self._run_turn(
            context=first_review.context,
            text=(
                "yes for lunch only give me the best of the best in kandy"
            ),
            interpretation=correction,
        )
        correction_runner.assert_not_awaited()

        final_response, final_runner, _ = await self._run_turn(
            context=updated_review.context,
            text="okay",
        )

        final_runner.assert_awaited_once()
        self.assertTrue(final_response.context.is_confirmed)
        self.assertEqual(
            len(
                final_response.assistant_messages[0].data[
                    "recommendationGroups"
                ]
            ),
            1,
        )
        self.assertIn(
            "recommendations are ready",
            final_response.assistant_messages[0].text.casefold(),
        )

    async def test_confirmed_request_builds_kandy_restaurant_task_once(self) -> None:
        async def inspect_confirmed_context(
            context: TravelContext,
            *,
            include_internal_route_matrix: bool,
        ) -> list[dict[str, object]]:
            self.assertFalse(include_internal_route_matrix)
            self.assertIsNone(context.starting_location)
            self.assertEqual(
                context.request_groups[0].search_location.display_name,
                "Kandy",
            )

            tasks = build_recommendation_tasks(context)
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task.request.location.display_name, "Kandy")
            self.assertIsNone(task.request.route_origin)
            self.assertEqual(len(task.request.provider_filters), 1)
            self.assertEqual(
                task.request.provider_filters[0].category_ids,
                (RESTAURANT_CATEGORY_ID,),
            )
            return self._recommendation_groups()

        runner = AsyncMock(side_effect=inspect_confirmed_context)

        response, runner, _ = await self._run_turn(
            context=self._restaurant_context(),
            text="okay",
            runner=runner,
        )

        runner.assert_awaited_once()
        self.assertIsNone(response.context.starting_location)
        self.assertEqual(
            response.context.request_groups[0].search_location.display_name,
            "Kandy",
        )

    async def test_repeated_acknowledgement_does_not_run_recommendations_twice(
        self,
    ) -> None:
        shared_runner = AsyncMock(return_value=self._recommendation_groups())
        first_response, _, _ = await self._run_turn(
            context=self._restaurant_context(),
            text="okay",
            runner=shared_runner,
        )

        social_ack = ConversationInterpretation(
            action="continueCurrentRequest",
            responseIntent="socialChat",
            assistantReply="You're welcome.",
        )
        second_response, _, _ = await self._run_turn(
            context=first_response.context,
            text="okay thx",
            interpretation=social_ack,
            runner=shared_runner,
        )

        shared_runner.assert_awaited_once()
        self.assertEqual(
            second_response.context.stage,
            TravelContextStage.CONFIRMED,
        )
        self.assertEqual(
            second_response.assistant_messages[0].data[
                "recommendationGroups"
            ],
            [],
        )

    def test_confirmation_matching_is_context_safe_and_rejects_corrections(
        self,
    ) -> None:
        self.assertTrue(conversation_router._is_simple_confirmation("okay thx"))
        self.assertTrue(
            conversation_router._is_simple_confirmation(
                "okay go ahead and give it so"
            )
        )
        self.assertFalse(
            conversation_router._is_simple_confirmation(
                "yes for lunch only give me the best of the best in Kandy"
            )
        )
        self.assertFalse(conversation_router._is_simple_confirmation("no"))
        self.assertFalse(
            conversation_router._is_simple_confirmation("no, change it")
        )

    def test_complete_itinerary_requirements_are_not_weakened(self) -> None:
        context = refresh_missing_fields(
            TravelContext(
                requiresCompleteItinerary=True,
                requestGroups=[
                    TravelRequestGroup(
                        id="restaurant-kandy",
                        kind=TravelRequestKind.RESTAURANT,
                        query="restaurants",
                        preferences=["no specific preference"],
                        searchLocation=self._kandy(),
                    )
                ],
            )
        )

        self.assertIn(MISSING_STARTING_LOCATION, context.missing_fields)
        self.assertIn(MISSING_FINAL_ENDING_LOCATION, context.missing_fields)
        self.assertFalse(context.is_ready_for_confirmation)
        with self.assertRaises(ValueError):
            build_confirmation_summary(context)


if __name__ == "__main__":
    unittest.main()
