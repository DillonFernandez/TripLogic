from __future__ import annotations

import re

from app.conversation_models import (
    TravelContext,
    TravelRequestGroup,
    TravelRequestKind,
)

NO_SPECIFIC_PREFERENCE = "no specific preference"


def _normalize_reply_text(text: str) -> str:
    normalized = text.casefold().replace("’", "'").replace("“", '"').replace("”", '"')
    normalized = normalized.replace("—", " ").replace("–", " ")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def is_no_specific_preference_reply(text: str) -> bool:
    normalized = _normalize_reply_text(text)
    if not normalized:
        return False

    exact_matches = {
        "no",
        "nope",
        "nah",
        "anything",
        "anything is fine",
        "anything is okay",
        "anything is ok",
        "no preference",
        "no preferences",
        "no specific preference",
        "whatever",
        "whatever you recommend",
        "surprise me",
        "i dont mind",
        "i do not mind",
    }

    if normalized in exact_matches:
        return True

    for phrase in (
        "no preference",
        "no specific preference",
        "whatever you recommend",
        "surprise me",
        "i do not mind",
        "i dont mind",
    ):
        if normalized == phrase or normalized.endswith(phrase):
            return True

    return False


def apply_no_specific_preference_reply(
    context: TravelContext,
    traveller_message: str,
) -> TravelContext:
    if not is_no_specific_preference_reply(traveller_message):
        return context

    unresolved_groups = [
        group
        for group in context.request_groups
        if group.kind in {TravelRequestKind.ATTRACTION, TravelRequestKind.RESTAURANT}
        and not group.preferences
    ]

    if not unresolved_groups:
        return context

    updated_context = context.model_copy()
    updated_context.request_groups = [
        (
            group.model_copy(update={"preferences": [NO_SPECIFIC_PREFERENCE]})
            if group in unresolved_groups
            else group
        )
        for group in updated_context.request_groups
    ]
    return updated_context


def build_request_preference_question(
    context: TravelContext,
) -> str | None:
    needs_restaurant_preference = any(
        group.kind is TravelRequestKind.RESTAURANT
        and not (
            group.preferences
            or group.cuisine_preferences
            or group.dietary_requirements
            or group.food_avoidances
            or group.meal_intents
        )
        for group in context.request_groups
    )

    needs_attraction_preference = any(
        group.kind is TravelRequestKind.ATTRACTION and not group.preferences
        for group in context.request_groups
    )

    if needs_restaurant_preference and needs_attraction_preference:
        return (
            "What would you like to eat, and what kinds of places "
            "would you like to see? You can tell me preferences for "
            "both, or say anything if you have no preference."
        )

    if needs_restaurant_preference:
        return (
            "What would you like to eat? You can mention a cuisine, "
            "type of food, dietary preference, or say anything if "
            "you have no preference."
        )

    if needs_attraction_preference:
        return (
            "What kinds of places would you like to see? You can "
            "mention things like nature, history, temples, culture, "
            "or adventure, or say anything if you have no preference."
        )

    return None


def provider_preferences(
    group: TravelRequestGroup,
) -> list[str]:
    return [
        preference
        for preference in group.preferences
        if preference.casefold() != NO_SPECIFIC_PREFERENCE.casefold()
    ]
