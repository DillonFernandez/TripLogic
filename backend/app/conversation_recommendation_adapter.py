from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from typing import Literal

from app.conversation_models import (
    FixedTravelPlaceRole,
    TravelContext,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
)
from app.conversation_preference_rules import (
    provider_preferences,
)
from app.foursquare_categories import (
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
    resolve_attraction_intent_presets,
    strip_generic_attraction_signals,
)
from app.recommendation_models import (
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationLocation,
    RecommendationRequest,
)

SUPPORTED_TRAVEL_MODES = {
    "driving",
    "walking",
    "cycling",
}

MAXIMUM_CATEGORY_NAME_LENGTH = 100

GENERIC_RESTAURANT_QUERIES = {
    "dining",
    "food",
    "food places",
    "place to eat",
    "places to eat",
    "restaurant",
    "restaurants",
}

SEARCHABLE_DIETARY_TERMS = {
    "halal",
    "vegan",
    "vegetarian",
}

NEGATIVE_PREFERENCE_PATTERN = re.compile(
    r"\b(?:avoid|avoiding|do\s+not|don['’]?t|no|not|without)\b",
    re.IGNORECASE,
)

FOURSQUARE_CATEGORY_GROUPS_BY_TRAVEL_REQUEST_KIND: dict[
    TravelRequestKind,
    tuple[tuple[str, ...], ...],
] = {
    TravelRequestKind.HOTEL: ((HOTEL_CATEGORY_ID,),),
    TravelRequestKind.RESTAURANT: ((RESTAURANT_CATEGORY_ID,),),
    TravelRequestKind.ATTRACTION: tuple(GENERIC_ATTRACTION_GROUPS.values()),
}

FOURSQUARE_CATEGORY_IDS_BY_TRAVEL_REQUEST_KIND: dict[
    TravelRequestKind,
    tuple[str, ...],
] = {
    kind: tuple(
        category_id
        for category_group in category_groups
        for category_id in category_group
    )
    for kind, category_groups in (
        FOURSQUARE_CATEGORY_GROUPS_BY_TRAVEL_REQUEST_KIND.items()
    )
}


class ConversationRecommendationAdapterError(ValueError):
    """Raised when trusted context cannot form a request."""


@dataclass(
    frozen=True,
    slots=True,
)
class ConversationRecommendationTask:
    request_group_id: str
    requested_count: int | None
    required: bool
    request: RecommendationRequest
    traveller_query: str | None = None


def build_recommendation_tasks(
    context: TravelContext,
) -> list[ConversationRecommendationTask]:
    if not context.is_confirmed:
        raise ConversationRecommendationAdapterError(
            "The travel context must be confirmed first."
        )

    route_location = _resolve_route_origin(context)
    route_origin = (
        _build_location(route_location)
        if route_location is not None
        else None
    )
    simple_route_independent_discovery = (
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
    travel_mode = _resolve_travel_mode(
        context,
        required=not simple_route_independent_discovery,
    )

    if (
        context.traveller_type is None
        and not simple_route_independent_discovery
    ):
        raise ConversationRecommendationAdapterError("Traveller type is required.")

    tasks: list[ConversationRecommendationTask] = []

    for group in context.request_groups:
        search_location = _resolve_search_location(
            context=context,
            group=group,
            route_location=route_location,
        )
        request = _build_group_request(
            context=context,
            group=group,
            location=_build_location(search_location),
            route_origin=route_origin,
            travel_mode=travel_mode,
        )

        tasks.append(
            ConversationRecommendationTask(
                request_group_id=group.id,
                requested_count=group.requested_count,
                required=group.required,
                request=request,
                traveller_query=group.query,
            )
        )

    if not tasks:
        raise ConversationRecommendationAdapterError(
            "At least one recommendation group is required."
        )

    return tasks


def _build_group_request(
    *,
    context: TravelContext,
    group: TravelRequestGroup,
    location: RecommendationLocation,
    route_origin: RecommendationLocation | None,
    travel_mode: Literal[
        "driving",
        "walking",
        "cycling",
    ]
    | None,
) -> RecommendationRequest:
    search_query = _provider_search_query(group)
    semantic_category_name = (
        group.query
        if group.kind is TravelRequestKind.RESTAURANT
        else (
            search_query
            or (
                "attractions"
                if group.kind is TravelRequestKind.ATTRACTION
                else group.query
            )
        )
    )

    provider_filters = tuple(
        FoursquareProviderFilter(
            query=search_query,
            categoryIds=category_ids,
            provenanceKey=provenance_key,
        )
        for provenance_key, category_ids in _provider_category_groups(group)
    )

    common_fields = {
        "recommendationType": group.kind.value,
        "location": location,
        "travelMode": travel_mode,
        "travelPartner": (
            context.traveller_type.value
            if context.traveller_type is not None
            else None
        ),
        "categories": [RecommendationCategory(name=semantic_category_name)],
    }

    if group.kind is TravelRequestKind.HOTEL:
        check_in_date = context.trip_start_date
        check_out_date = context.trip_end_date

        if (
            check_in_date is not None
            and check_out_date is not None
            and check_out_date <= check_in_date
        ):
            check_in_date = None
            check_out_date = None

        request = RecommendationRequest(
            **common_fields,
            checkInDate=check_in_date,
            checkOutDate=check_out_date,
            travellers=context.traveller_count,
        )

        request.attach_provider_filters(provider_filters)
        request.attach_route_origin(route_origin)
        return request

    start_time = _parse_local_time(context.daily_start_time)

    if group.kind is TravelRequestKind.RESTAURANT:
        request = RecommendationRequest(
            **common_fields,
            visitDate=context.trip_start_date,
            startTime=start_time,
        )

        request.attach_restaurant_preferences(
            cuisine_preferences=group.cuisine_preferences,
            dietary_requirements=group.dietary_requirements,
            food_avoidances=group.food_avoidances,
            meal_intents=group.meal_intents,
        )
        request.attach_provider_filters(provider_filters)
        request.attach_route_origin(route_origin)
        return request

    request = RecommendationRequest(
        **common_fields,
        visitDate=context.trip_start_date,
        startTime=start_time,
    )

    request.attach_provider_filters(provider_filters)
    request.attach_route_origin(route_origin)
    return request


def _resolve_route_origin(
    context: TravelContext,
) -> TravelLocation | None:
    if (
        context.starting_location is not None
        and context.starting_location.is_route_ready
    ):
        return context.starting_location

    for place in context.fixed_places:
        if (
            place.role is FixedTravelPlaceRole.DAILY_BASE
            and place.confirmed
            and place.location.is_route_ready
        ):
            return place.location

    return None


def _resolve_search_location(
    *,
    context: TravelContext,
    group: TravelRequestGroup,
    route_location: TravelLocation | None,
) -> TravelLocation:
    if group.search_location is not None:
        if not group.search_location.is_route_ready:
            raise ConversationRecommendationAdapterError(
                "The recommendation search location must be verified first."
            )

        return group.search_location

    if route_location is not None:
        return route_location

    raise ConversationRecommendationAdapterError(
        "A verified recommendation search location is required."
    )


def _build_location(
    location: TravelLocation,
) -> RecommendationLocation:
    if location.latitude is None or location.longitude is None:
        raise ConversationRecommendationAdapterError(
            "The selected location has no coordinates."
        )

    source: Literal[
        "current",
        "selected",
    ] = (
        "current" if location.source is TravelLocationSource.CURRENT else "selected"
    )

    return RecommendationLocation(
        displayName=location.display_name,
        localityName=location.locality_name,
        latitude=location.latitude,
        longitude=location.longitude,
        source=source,
        countryCode=location.country_code,
        admin1=location.admin1,
        admin2=location.admin2,
        admin3=location.admin3,
        admin4=location.admin4,
        featureCode=location.feature_code,
    )


def _resolve_travel_mode(
    context: TravelContext,
    *,
    required: bool = True,
) -> Literal[
    "driving",
    "walking",
    "cycling",
] | None:
    if not context.travel_modes:
        if required:
            raise ConversationRecommendationAdapterError("A travel mode is required.")

        return None

    travel_mode = context.travel_modes[0]

    if travel_mode not in SUPPORTED_TRAVEL_MODES:
        raise ConversationRecommendationAdapterError(
            f"Unsupported travel mode: {travel_mode}."
        )

    return travel_mode  # type: ignore[return-value]


def _parse_local_time(
    value: str | None,
) -> time | None:
    if value is None:
        return None

    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ConversationRecommendationAdapterError(
            f"Invalid local time: {value}."
        ) from error


def _normalize_category_name(
    query: str,
) -> str:
    normalized_query = " ".join(query.strip().split())

    if len(normalized_query) < 2:
        raise ConversationRecommendationAdapterError(
            "The recommendation query is too short."
        )

    if len(normalized_query) > MAXIMUM_CATEGORY_NAME_LENGTH:
        raise ConversationRecommendationAdapterError(
            "The recommendation query cannot exceed "
            f"{MAXIMUM_CATEGORY_NAME_LENGTH} characters."
        )

    return normalized_query


def _provider_search_query(
    group: TravelRequestGroup,
) -> str | None:
    if group.kind is TravelRequestKind.HOTEL:
        return "hotel"

    if group.kind is TravelRequestKind.RESTAURANT:
        return _restaurant_provider_search_query(group)

    preferences = provider_preferences(group)

    group_query = group.query

    if group.kind is TravelRequestKind.ATTRACTION:
        if not resolve_attraction_intent_presets(
            (group.query, *group.preferences)
        ):
            return None

        preferences = [
            cleaned_preference
            for preference in preferences
            if (
                cleaned_preference := strip_generic_attraction_signals(
                    preference
                )
            )
        ]
        group_query = strip_generic_attraction_signals(group.query)

        if group_query.casefold() in {
            "attraction",
            "attractions",
        }:
            group_query = ""

    useful_preferences = [
        preference
        for preference in preferences
        if preference.casefold() not in group_query.casefold()
    ]

    search_parts = [
        *useful_preferences,
        group_query,
    ]

    search_query = " ".join(part.strip() for part in search_parts if part.strip())

    return _normalize_category_name(search_query)


def _restaurant_provider_search_query(
    group: TravelRequestGroup,
) -> str | None:
    """Build positive discovery text without turning avoidances into matches."""

    avoidances = {
        " ".join(value.split()).casefold()
        for value in group.food_avoidances
        if value.strip()
    }

    def is_avoided(value: str) -> bool:
        normalized_value = " ".join(value.split()).casefold()

        return any(
            normalized_value == avoidance
            or normalized_value in avoidance
            or avoidance in normalized_value
            for avoidance in avoidances
        )

    primary_positive_values = [
        *group.cuisine_preferences,
        *group.meal_intents,
        *provider_preferences(group),
    ]
    searchable_dietary_requirements = [
        requirement
        for requirement in group.dietary_requirements
        if any(
            re.search(rf"\b{re.escape(term)}\b", requirement, re.IGNORECASE)
            for term in SEARCHABLE_DIETARY_TERMS
        )
    ]
    positive_values = (
        primary_positive_values
        if primary_positive_values
        else searchable_dietary_requirements
    )

    group_query = " ".join(group.query.split())
    normalized_group_query = group_query.casefold()

    if (
        normalized_group_query in GENERIC_RESTAURANT_QUERIES
        or NEGATIVE_PREFERENCE_PATTERN.search(group_query)
    ):
        group_query = ""

    search_parts: list[str] = []
    seen_parts: set[str] = set()

    for value in positive_values:
        normalized_value = " ".join(value.split())
        comparison_value = normalized_value.casefold()

        if (
            not normalized_value
            or comparison_value in seen_parts
            or NEGATIVE_PREFERENCE_PATTERN.search(normalized_value)
            or is_avoided(normalized_value)
            or comparison_value in group_query.casefold()
        ):
            continue

        seen_parts.add(comparison_value)
        search_parts.append(normalized_value)

    if group_query:
        search_parts.append(group_query)

    search_query = " ".join(search_parts)

    return _normalize_category_name(search_query) if search_query else None


def _provider_category_groups(
    group: TravelRequestGroup,
) -> tuple[tuple[str | None, tuple[str, ...]], ...]:
    if group.kind is not TravelRequestKind.ATTRACTION:
        return tuple(
            (None, category_ids)
            for category_ids in FOURSQUARE_CATEGORY_GROUPS_BY_TRAVEL_REQUEST_KIND[
                group.kind
            ]
        )

    matched_presets = resolve_attraction_intent_presets(
        (group.query, *group.preferences)
    )

    if matched_presets:
        named_groups = tuple(
            (
                f"intent:{preset_name}",
                INTENT_CATEGORY_PRESETS[preset_name],
            )
            for preset_name in matched_presets
        )
    else:
        named_groups = tuple(
            (f"generic:{group_name}", category_ids)
            for group_name, category_ids in GENERIC_ATTRACTION_GROUPS.items()
        )

    deduplicated_groups: list[tuple[str, tuple[str, ...]]] = []
    seen_category_ids: set[str] = set()

    for provenance_key, category_ids in named_groups:
        unique_category_ids = tuple(
            category_id
            for category_id in category_ids
            if category_id not in seen_category_ids
        )

        if not unique_category_ids:
            continue

        seen_category_ids.update(unique_category_ids)
        deduplicated_groups.append((provenance_key, unique_category_ids))

    return tuple(deduplicated_groups)
