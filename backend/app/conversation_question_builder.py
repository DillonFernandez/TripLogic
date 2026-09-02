from __future__ import annotations

from app.conversation_context_requirements import (
    MISSING_AVAILABLE_TIME,
    MISSING_DAILY_END_TIME,
    MISSING_DAILY_START_TIME,
    MISSING_FINAL_ENDING_LOCATION,
    MISSING_REQUEST_GROUPS,
    MISSING_SEARCH_LOCATION,
    MISSING_STARTING_LOCATION,
    MISSING_TRAVELLER_COUNT,
    MISSING_TRAVEL_MODE,
    MISSING_TRAVELLER_TYPE,
    MISSING_TRIP_END_DATE,
    MISSING_TRIP_START_DATE,
)
from app.conversation_models import TravelContext
from app.conversation_preference_rules import (
    build_request_preference_question,
)

QUESTION_BY_MISSING_FIELD: dict[str, str] = {
    MISSING_REQUEST_GROUPS: (
        "What would you like help planning, such as attractions, "
        "hotels, restaurants, a route, or an itinerary?"
    ),
    MISSING_STARTING_LOCATION: ("Where in Sri Lanka should your trip start?"),
    MISSING_SEARCH_LOCATION: (
        "Which Sri Lankan locality should I search for these places?"
    ),
    MISSING_FINAL_ENDING_LOCATION: (
        "Where in Sri Lanka must the complete trip end?"
    ),
    MISSING_TRIP_START_DATE: ("What date will your trip start?"),
    MISSING_TRIP_END_DATE: ("What date will your trip end?"),
    MISSING_AVAILABLE_TIME: ("How much time do you have for this trip?"),
    MISSING_DAILY_START_TIME: ("What time would you like to start?"),
    MISSING_DAILY_END_TIME: ("What time must you finish?"),
    MISSING_TRAVELLER_TYPE: ("Who are you travelling with?"),
    MISSING_TRAVELLER_COUNT: ("How many travellers will be staying?"),
    MISSING_TRAVEL_MODE: ("Will you be driving, walking, or cycling?"),
}


def build_next_question(
    context: TravelContext,
) -> str | None:
    preference_question = build_request_preference_question(context)

    if preference_question is not None:
        return preference_question

    for missing_field in context.missing_fields:
        question = QUESTION_BY_MISSING_FIELD.get(missing_field)

        if question is not None:
            return question

    return None
