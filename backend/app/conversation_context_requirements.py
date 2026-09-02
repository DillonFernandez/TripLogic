from __future__ import annotations

from app.conversation_models import (
    FixedTravelPlaceRole,
    TravelContext,
    TravelRequestKind,
)

MISSING_REQUEST_GROUPS = "requestGroups"
MISSING_STARTING_LOCATION = "startingLocation"
MISSING_SEARCH_LOCATION = "searchLocation"
MISSING_FINAL_ENDING_LOCATION = "finalEndingLocation"
MISSING_TRIP_START_DATE = "tripStartDate"
MISSING_TRIP_END_DATE = "tripEndDate"
MISSING_AVAILABLE_TIME = "availableTime"
MISSING_DAILY_START_TIME = "dailyStartTime"
MISSING_DAILY_END_TIME = "dailyEndTime"
MISSING_TRAVELLER_TYPE = "travellerType"
MISSING_TRAVELLER_COUNT = "travellerCount"
MISSING_TRAVEL_MODE = "travelMode"


def compute_missing_fields(
    context: TravelContext,
) -> list[str]:
    missing_fields: list[str] = []

    if not context.request_groups:
        missing_fields.append(MISSING_REQUEST_GROUPS)

    if context.requires_complete_itinerary:
        if not _has_supplied_route_anchor(context):
            missing_fields.append(MISSING_STARTING_LOCATION)

        if not _has_supplied_final_ending_location(context):
            missing_fields.append(MISSING_FINAL_ENDING_LOCATION)

    elif not _has_supplied_search_location(context):
        missing_fields.append(MISSING_SEARCH_LOCATION)

    if context.requires_trip_period:
        if context.trip_start_date is None:
            missing_fields.append(MISSING_TRIP_START_DATE)

        if context.trip_end_date is None:
            missing_fields.append(MISSING_TRIP_END_DATE)

    has_start_time = context.daily_start_time is not None
    has_end_time = context.daily_end_time is not None
    has_time_description = bool(context.available_time_description)

    if context.requires_complete_itinerary:
        if not has_start_time:
            missing_fields.append(MISSING_DAILY_START_TIME)

        if not has_end_time:
            missing_fields.append(MISSING_DAILY_END_TIME)

    simple_route_independent_discovery = (
        _is_simple_route_independent_discovery(context)
    )

    if (
        context.traveller_type is None
        and not simple_route_independent_discovery
    ):
        missing_fields.append(MISSING_TRAVELLER_TYPE)

    requests_hotel = any(
        group.kind is TravelRequestKind.HOTEL for group in context.request_groups
    )

    if requests_hotel and context.requires_complete_itinerary:
        if context.traveller_count is None:
            missing_fields.append(MISSING_TRAVELLER_COUNT)

    if not context.travel_modes and not simple_route_independent_discovery:
        missing_fields.append(MISSING_TRAVEL_MODE)

    return missing_fields


def _is_simple_route_independent_discovery(
    context: TravelContext,
) -> bool:
    return (
        not context.requires_complete_itinerary
        and bool(context.request_groups)
        and all(
            group.kind
            in {
                TravelRequestKind.ATTRACTION,
                TravelRequestKind.HOTEL,
                TravelRequestKind.RESTAURANT,
            }
            for group in context.request_groups
        )
    )


def refresh_missing_fields(
    context: TravelContext,
) -> TravelContext:
    context_data = context.model_dump(mode="python")

    context_data["missing_fields"] = compute_missing_fields(context)

    return TravelContext.model_validate(context_data)


def _has_supplied_route_anchor(
    context: TravelContext,
) -> bool:
    if context.starting_location is not None:
        return True

    return any(
        place.role is FixedTravelPlaceRole.DAILY_BASE and place.confirmed
        for place in context.fixed_places
    )


def _has_supplied_search_location(
    context: TravelContext,
) -> bool:
    if not context.request_groups:
        return False

    has_fallback_location = _has_supplied_route_anchor(context)

    return all(
        group.search_location is not None or has_fallback_location
        for group in context.request_groups
    )


def _has_supplied_final_ending_location(
    context: TravelContext,
) -> bool:
    return any(
        place.role is FixedTravelPlaceRole.END_POINT and place.confirmed
        for place in context.fixed_places
    )
