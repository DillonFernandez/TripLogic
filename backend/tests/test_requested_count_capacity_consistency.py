"""Focused requested-count consistency at the current executable boundary."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_context_requirements import (  # noqa: E402
    refresh_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
    ExtractedRequestGroup,
)
from app.conversation_interpreter import INTERPRETER_INSTRUCTIONS  # noqa: E402
from app.conversation_models import (  # noqa: E402
    MAXIMUM_REQUESTED_RECOMMENDATIONS,
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
from app.conversation_router import (  # noqa: E402
    _uncertainty_clarification_message,
)
from app.recommendation_engine import (  # noqa: E402
    MAXIMUM_ROUTE_MATRIX_CANDIDATES,
)


SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")


class RequestedCountCapacityConsistencyTests(unittest.TestCase):
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
            verified=True,
        )

    def _attraction_context(self, count: int) -> TravelContext:
        tomorrow = (
            datetime.now(SRI_LANKA_TIMEZONE).date()
            + timedelta(days=1)
        )
        return refresh_missing_fields(
            TravelContext(
                tripStartDate=tomorrow,
                tripEndDate=tomorrow,
                dailyStartTime="09:00:00",
                dailyEndTime="17:00:00",
                travellerType=TravellerType.COUPLE,
                travelModes=["driving"],
                requestGroups=[
                    TravelRequestGroup(
                        id=f"attractions-{count}",
                        kind=TravelRequestKind.ATTRACTION,
                        query="attractions",
                        requestedCount=count,
                        searchLocation=self._kandy(),
                    )
                ],
            )
        )

    def test_chat_and_engine_capacity_are_the_same_nineteen(self) -> None:
        self.assertEqual(MAXIMUM_REQUESTED_RECOMMENDATIONS, 19)
        self.assertEqual(
            MAXIMUM_REQUESTED_RECOMMENDATIONS,
            MAXIMUM_ROUTE_MATRIX_CANDIDATES,
        )

    def test_supported_counts_include_existing_contract_and_boundaries(
        self,
    ) -> None:
        for count in (1, 3, 6, 7, 10, 19):
            with self.subTest(count=count):
                group = TravelRequestGroup(
                    id=f"group-{count}",
                    kind=TravelRequestKind.ATTRACTION,
                    query="attractions",
                    requestedCount=count,
                )
                extracted = ExtractedRequestGroup(
                    kind=TravelRequestKind.ATTRACTION,
                    query="attractions",
                    requestedCount=count,
                )
                self.assertEqual(group.requested_count, count)
                self.assertEqual(extracted.requested_count, count)

    def test_twenty_cannot_enter_confirmable_structured_state(self) -> None:
        for model, fields in (
            (
                TravelRequestGroup,
                {
                    "id": "group-20",
                    "kind": "attraction",
                    "query": "attractions",
                    "requestedCount": 20,
                },
            ),
            (
                ExtractedRequestGroup,
                {
                    "kind": "attraction",
                    "query": "attractions",
                    "requestedCount": 20,
                },
            ),
        ):
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.model_validate(fields)

    def test_twenty_intent_is_preserved_as_clarification_not_count(self) -> None:
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
                                "searchLocationText": "Kandy",
                            }
                        ],
                    }
                },
                "uncertainties": [
                    "The traveller requested 20 attractions; "
                    "the current verified capacity is 19."
                ],
                "requiresClarification": True,
                "proposedNextQuestion": (
                    "Would you like up to 19 attractions instead?"
                ),
            }
        )

        self.assertIsNone(
            interpretation.context_patch.request_groups.groups[0].requested_count
        )
        self.assertTrue(interpretation.requires_clarification)
        self.assertIn("requested 20", interpretation.uncertainties[0])

        for required_text in (
            "leave requestedCount null",
            "set requiresClarification true",
            "return up to\n    19 verified recommendations",
            "never a Foursquare provider limit",
        ):
            self.assertIn(required_text, INTERPRETER_INSTRUCTIONS)

    def test_twenty_clarification_is_user_facing_and_offers_nineteen(self) -> None:
        for uncertainty in (
            "requestedCount greater than 19",
            "requestedCount exceeds 19",
        ):
            with self.subTest(uncertainty=uncertainty):
                message = _uncertainty_clarification_message(uncertainty)

                self.assertIn("up to 19 verified recommendations", message)
                self.assertIn("Would you like me to use 19?", message)
                self.assertNotIn("requestedCount", message)
                self.assertNotIn("Foursquare", message)

    def test_confirmation_and_task_are_exact_at_nineteen(self) -> None:
        context = self._attraction_context(19)
        summary = build_confirmation_summary(context)

        self.assertIn("Number requested: 19", summary)
        self.assertNotIn("Number requested: 20", summary)

        data = context.model_dump(mode="python")
        data.update(
            stage=TravelContextStage.CONFIRMED,
            is_confirmed=True,
        )
        task = build_recommendation_tasks(
            TravelContext.model_validate(data)
        )[0]
        self.assertEqual(task.requested_count, 19)


if __name__ == "__main__":
    unittest.main()
