from __future__ import annotations

from datetime import date, time

from app.conversation_models import (
    FixedTravelPlaceRole,
    TravelContext,
    TravelRequestGroup,
    TravelRequestKind,
    TravellerType,
)
from app.conversation_preference_rules import (
    NO_SPECIFIC_PREFERENCE,
)

TRAVELLER_TYPE_LABELS: dict[TravellerType, str] = {
    TravellerType.SOLO_TRAVELLER: "Solo traveller",
    TravellerType.COUPLE: "Couple",
    TravellerType.FAMILY: "Family",
    TravellerType.FRIENDS_GROUP: "Friends group",
    TravellerType.SENIOR_TRAVELLERS: "Senior travellers",
}

GROUP_SINGULAR_LABELS: dict[TravelRequestKind, str] = {
    TravelRequestKind.ATTRACTION: "Attraction",
    TravelRequestKind.RESTAURANT: "Restaurant",
    TravelRequestKind.HOTEL: "Hotel",
}

GROUP_PLURAL_LABELS: dict[TravelRequestKind, str] = {
    TravelRequestKind.ATTRACTION: "Attractions",
    TravelRequestKind.RESTAURANT: "Restaurants",
    TravelRequestKind.HOTEL: "Hotels",
}

FIXED_PLACE_LABELS: dict[FixedTravelPlaceRole, str] = {
    FixedTravelPlaceRole.DAILY_BASE: "Daily base",
    FixedTravelPlaceRole.REQUIRED_STOP: "Required stop",
    FixedTravelPlaceRole.START_POINT: "Fixed start point",
    FixedTravelPlaceRole.OVERNIGHT_STOP: "Overnight stop",
}

MAXIMUM_CONFIRMATION_LENGTH = 4000


def build_confirmation_summary(
    context: TravelContext,
) -> str:
    if not context.is_ready_for_confirmation:
        raise ValueError("The travel context is not ready for confirmation.")

    sections = ["Please confirm these trip details:"]

    if context.request_groups:
        sections.append(_recommendation_section(context.request_groups))

    trip_lines = _trip_detail_lines(context)

    if trip_lines:
        sections.append("\n".join(["Trip details", "", *trip_lines]))

    sections.append(
        "Please confirm these details or tell me what you would like to change."
    )

    summary = "\n\n".join(sections)

    if len(summary) > MAXIMUM_CONFIRMATION_LENGTH:
        raise ValueError(
            "The confirmation summary exceeds "
            f"{MAXIMUM_CONFIRMATION_LENGTH} characters."
        )

    return summary


def _recommendation_section(
    groups: list[TravelRequestGroup],
) -> str:
    if len(groups) == 1:
        group = groups[0]
        title = f"{GROUP_SINGULAR_LABELS[group.kind]} recommendations"
        details = _request_group_detail_lines(group)

        return "\n".join(
            [
                title,
                "",
                *[f"• {detail}" for detail in details],
            ]
        )

    lines = ["Recommendations"]

    for group in groups:
        lines.extend(
            [
                "",
                f"• {GROUP_PLURAL_LABELS[group.kind]}",
                *[
                    f"  {detail}"
                    for detail in _request_group_detail_lines(group)
                ],
            ]
        )

    return "\n".join(lines)


def _request_group_detail_lines(
    group: TravelRequestGroup,
) -> list[str]:
    lines: list[str] = []

    if group.search_location is not None:
        lines.append(f"Location: {group.search_location.display_name}")

    if group.requested_count is not None:
        lines.append(f"Number requested: {group.requested_count}")

    generic_preference = any(
        value.casefold() == NO_SPECIFIC_PREFERENCE.casefold()
        for value in group.preferences
    )
    specific_preferences = [
        value
        for value in group.preferences
        if value.casefold() != NO_SPECIFIC_PREFERENCE.casefold()
    ]

    if group.kind is TravelRequestKind.RESTAURANT:
        if group.cuisine_preferences:
            lines.append(
                "Cuisine: "
                f"{_format_values(group.cuisine_preferences)}"
            )
        elif generic_preference:
            lines.append("Cuisine: No preference — Trip Logic chooses")

        if group.meal_intents:
            lines.append(f"Meal: {_format_values(group.meal_intents)}")

        if group.dietary_requirements:
            lines.append(
                "Dietary requirements: "
                f"{_format_values(group.dietary_requirements)}"
            )

        if group.food_avoidances:
            lines.append(
                "Food avoidances: "
                f"{_format_values(group.food_avoidances)}"
            )

    elif generic_preference:
        lines.append("Preferences: No preference — Trip Logic chooses")

    if specific_preferences:
        lines.append(f"Preferences: {_format_values(specific_preferences)}")

    return lines


def _trip_detail_lines(
    context: TravelContext,
) -> list[str]:
    lines: list[str] = []

    if context.starting_location is not None:
        lines.append(
            f"• Starting location: {context.starting_location.display_name}"
        )

    for place in context.fixed_places:
        if place.role is FixedTravelPlaceRole.END_POINT:
            lines.append(f"• Final ending location: {place.name}")
            continue

        label = FIXED_PLACE_LABELS.get(place.role)

        if label is not None:
            lines.append(f"• {label}: {place.name}")

    if context.trip_start_date is not None and context.trip_end_date is not None:
        if context.trip_start_date == context.trip_end_date:
            lines.append(f"• Date: {_format_date(context.trip_start_date)}")
        else:
            lines.append(
                "• Dates: "
                f"{_format_date(context.trip_start_date)} to "
                f"{_format_date(context.trip_end_date)}"
            )
    elif context.trip_start_date is not None:
        lines.append(f"• Start date: {_format_date(context.trip_start_date)}")
    elif context.trip_end_date is not None:
        lines.append(f"• End date: {_format_date(context.trip_end_date)}")

    if context.daily_start_time is not None:
        lines.append(
            "• Daily start time: "
            f"{_format_time(context.daily_start_time)}"
        )

    if context.daily_end_time is not None:
        lines.append(
            "• Final arrival deadline: "
            f"{_format_time(context.daily_end_time)}"
        )

    if (
        context.available_time_description is not None
        and not (
            context.daily_start_time is not None
            and context.daily_end_time is not None
        )
    ):
        lines.append(
            "• Available time: "
            f"{_humanize_value(context.available_time_description)}"
        )

    traveller_description = _traveller_description(context)

    if traveller_description is not None:
        lines.append(f"• Travellers: {traveller_description}")

    if context.travel_modes:
        lines.append(
            f"• Travel mode: {_format_values(context.travel_modes)}"
        )

    if context.preferences:
        lines.append(f"• General preferences: {_format_values(context.preferences)}")

    if context.accessibility_needs:
        lines.append(
            "• Accessibility needs: "
            f"{_format_values(context.accessibility_needs)}"
        )

    if context.avoidances:
        lines.append(f"• General avoidances: {_format_values(context.avoidances)}")

    return lines


def _traveller_description(
    context: TravelContext,
) -> str | None:
    values: list[str] = []

    if context.traveller_count is not None:
        noun = "traveller" if context.traveller_count == 1 else "travellers"
        values.append(f"{context.traveller_count} {noun}")

    if context.traveller_type is not None:
        values.append(TRAVELLER_TYPE_LABELS[context.traveller_type])

    if context.travel_party_description is not None:
        values.append(_humanize_value(context.travel_party_description))

    return ", ".join(values) if values else None


def _format_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _format_time(value: str) -> str:
    parsed = time.fromisoformat(value)
    hour = parsed.hour
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12

    return f"{display_hour}:{parsed.minute:02d} {suffix}"


def _humanize_value(value: str) -> str:
    normalized = " ".join(value.replace("_", " ").strip().split())

    if not normalized:
        return normalized

    return normalized[:1].upper() + normalized[1:]


def _format_values(values: list[str]) -> str:
    return ", ".join(
        humanized
        for value in values
        if (humanized := _humanize_value(value))
    )
