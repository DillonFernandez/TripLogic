from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from app.conversation_models import (
    FixedTravelPlaceRole,
    TravelContext,
)
from app.openrouteservice import get_route_matrix

MAXIMUM_ITINERARY_STOPS = 5
MAXIMUM_CANDIDATES = 8
MINIMUM_VISIT_MINUTES = 30

TARGET_VISIT_MINUTES = {
    "attraction": 75,
    "restaurant": 60,
}


class ConversationItineraryBuilderError(ValueError):
    """Raised when a trusted itinerary cannot be built."""


async def build_conversation_itinerary(
    *,
    context: TravelContext,
    recommendation_groups: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    if not context.is_confirmed:
        raise ConversationItineraryBuilderError(
            "The trip must be confirmed before building an itinerary."
        )

    if context.trip_start_date is None:
        raise ConversationItineraryBuilderError("A trip date is required.")

    if context.daily_start_time is None or context.daily_end_time is None:
        raise ConversationItineraryBuilderError(
            "A daily start and finish time are required."
        )

    if not context.travel_modes:
        raise ConversationItineraryBuilderError("A travel mode is required.")

    base_name, base_latitude, base_longitude = _route_anchor(context)

    candidates = _extract_candidates(recommendation_groups)

    if not candidates:
        raise ConversationItineraryBuilderError(
            "No suitable attraction or restaurant recommendations "
            "were available for the itinerary."
        )

    start_time = _parse_time(context.daily_start_time)
    end_time = _parse_time(context.daily_end_time)

    start_datetime = datetime.combine(
        context.trip_start_date,
        start_time,
    )
    end_datetime = datetime.combine(
        context.trip_start_date,
        end_time,
    )

    if end_datetime <= start_datetime:
        end_datetime += timedelta(days=1)

    total_available_seconds = (end_datetime - start_datetime).total_seconds()

    durations = _reuse_route_durations(
        recommendation_groups=recommendation_groups,
        candidates=candidates,
        base_latitude=base_latitude,
        base_longitude=base_longitude,
    )

    if durations is None:
        route_locations = [
            (base_latitude, base_longitude),
            *[
                (
                    candidate["latitude"],
                    candidate["longitude"],
                )
                for candidate in candidates
            ],
        ]

        matrix = await get_route_matrix(
            locations=route_locations,
            travel_mode=context.travel_modes[0],
        )

        durations = matrix.get("durationsSeconds")

        if not isinstance(durations, list):
            raise ConversationItineraryBuilderError("Route durations were unavailable.")

    selected_indices = _select_route(
        candidates=candidates,
        durations=durations,
        total_available_seconds=total_available_seconds,
    )

    if not selected_indices:
        raise ConversationItineraryBuilderError(
            "No recommended stop could fit safely inside " "the available time window."
        )

    visit_minutes, free_minutes = _allocate_visit_time(
        candidates=candidates,
        selected_indices=selected_indices,
        durations=durations,
        total_available_seconds=total_available_seconds,
    )

    travel_mode = context.travel_modes[0]

    text, stops = _build_schedule(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        base_name=base_name,
        travel_mode=travel_mode,
        candidates=candidates,
        selected_indices=selected_indices,
        visit_minutes=visit_minutes,
        free_minutes=free_minutes,
        durations=durations,
    )

    itinerary_data = {
        "date": context.trip_start_date.isoformat(),
        "startTime": context.daily_start_time,
        "endTime": context.daily_end_time,
        "travelMode": travel_mode,
        "base": {
            "name": base_name,
            "latitude": base_latitude,
            "longitude": base_longitude,
        },
        "stops": stops,
        "freeBufferMinutes": free_minutes,
    }

    return text, itinerary_data


def _route_anchor(
    context: TravelContext,
) -> tuple[str, float, float]:
    location = context.starting_location

    if (
        location is not None
        and location.is_route_ready
        and location.latitude is not None
        and location.longitude is not None
    ):
        return (
            location.display_name,
            float(location.latitude),
            float(location.longitude),
        )

    for place in context.fixed_places:
        if (
            place.role is FixedTravelPlaceRole.DAILY_BASE
            and place.confirmed
            and place.location.is_route_ready
            and place.location.latitude is not None
            and place.location.longitude is not None
        ):
            return (
                place.name,
                float(place.location.latitude),
                float(place.location.longitude),
            )

    raise ConversationItineraryBuilderError(
        "A verified route-ready starting location is required."
    )


def _extract_candidates(
    recommendation_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for group in recommendation_groups:
        recommendation_type = group.get("recommendationType")

        if recommendation_type not in {
            "attraction",
            "restaurant",
        }:
            continue

        result = group.get("result")

        if not isinstance(result, dict):
            continue

        places: list[Any] = []

        top = result.get("topRecommendations")
        more = result.get("moreRecommendations")

        if isinstance(top, list):
            places.extend(top)

        if isinstance(more, list):
            places.extend(more)

        for place in places:
            if not isinstance(place, dict):
                continue

            name = place.get("name")
            latitude = _number_or_none(place.get("latitude"))
            longitude = _number_or_none(place.get("longitude"))

            if (
                not isinstance(name, str)
                or not name.strip()
                or latitude is None
                or longitude is None
            ):
                continue

            raw_id = (
                place.get("fsqId")
                or place.get("id")
                or (f"{name.strip().casefold()}:" f"{latitude:.6f}:{longitude:.6f}")
            )

            unique_id = str(raw_id)

            if unique_id in seen:
                continue

            seen.add(unique_id)

            candidates.append(
                {
                    "id": unique_id,
                    "name": name.strip(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "recommendationType": recommendation_type,
                    "explanation": place.get("explanation"),
                }
            )

            if len(candidates) >= MAXIMUM_CANDIDATES:
                return candidates

    return candidates


def _reuse_route_durations(
    *,
    recommendation_groups: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    base_latitude: float,
    base_longitude: float,
) -> list[Any] | None:
    candidate_groups = [
        group
        for group in recommendation_groups
        if group.get("recommendationType")
        in {
            "attraction",
            "restaurant",
        }
    ]

    # A single recommendation group already has a complete
    # base + candidate all-to-all route matrix.
    #
    # Multiple attraction/restaurant groups have separate matrices,
    # so a fresh combined matrix is still required for the itinerary.
    if len(candidate_groups) != 1:
        return None

    result = candidate_groups[0].get("result")

    if not isinstance(result, dict):
        return None

    route_matrix = result.get("_internalRouteMatrix")

    if not isinstance(route_matrix, dict):
        return None

    locations = route_matrix.get("locations")
    source_durations = route_matrix.get("durationsSeconds")

    if (
        not isinstance(locations, list)
        or not isinstance(source_durations, list)
        or not locations
    ):
        return None

    base_location = locations[0]

    if not isinstance(base_location, dict):
        return None

    matrix_base_latitude = _number_or_none(base_location.get("latitude"))
    matrix_base_longitude = _number_or_none(base_location.get("longitude"))

    if (
        matrix_base_latitude is None
        or matrix_base_longitude is None
        or not _coordinates_match(
            base_latitude,
            base_longitude,
            matrix_base_latitude,
            matrix_base_longitude,
        )
    ):
        return None

    remapped_indices = [0]

    for candidate in candidates:
        candidate_latitude = _number_or_none(candidate.get("latitude"))
        candidate_longitude = _number_or_none(candidate.get("longitude"))

        if candidate_latitude is None or candidate_longitude is None:
            return None

        matching_index: int | None = None

        for index, location in enumerate(
            locations[1:],
            start=1,
        ):
            if not isinstance(location, dict):
                continue

            latitude = _number_or_none(location.get("latitude"))
            longitude = _number_or_none(location.get("longitude"))

            if (
                latitude is not None
                and longitude is not None
                and _coordinates_match(
                    candidate_latitude,
                    candidate_longitude,
                    latitude,
                    longitude,
                )
            ):
                matching_index = index
                break

        if matching_index is None:
            return None

        remapped_indices.append(matching_index)

    remapped_durations: list[list[Any]] = []

    for source_index in remapped_indices:
        if source_index >= len(source_durations):
            return None

        source_row = source_durations[source_index]

        if not isinstance(source_row, list):
            return None

        remapped_row: list[Any] = []

        for destination_index in remapped_indices:
            if destination_index >= len(source_row):
                return None

            remapped_row.append(source_row[destination_index])

        remapped_durations.append(remapped_row)

    return remapped_durations


def _coordinates_match(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> bool:
    tolerance = 0.000001

    return (
        abs(first_latitude - second_latitude) <= tolerance
        and abs(first_longitude - second_longitude) <= tolerance
    )


def _select_route(
    *,
    candidates: list[dict[str, Any]],
    durations: list[Any],
    total_available_seconds: float,
) -> list[int]:
    remaining = set(range(1, len(candidates) + 1))

    selected: list[int] = []
    current_index = 0
    elapsed_seconds = 0.0

    while remaining and len(selected) < MAXIMUM_ITINERARY_STOPS:
        ordered = sorted(
            remaining,
            key=lambda index: (
                _matrix_duration(
                    durations,
                    current_index,
                    index,
                )
                or float("inf")
            ),
        )

        chosen_index: int | None = None

        for index in ordered:
            outbound_seconds = _matrix_duration(
                durations,
                current_index,
                index,
            )
            return_seconds = _matrix_duration(
                durations,
                index,
                0,
            )

            if outbound_seconds is None or return_seconds is None:
                continue

            minimum_visit_seconds = MINIMUM_VISIT_MINUTES * 60

            projected_seconds = (
                elapsed_seconds
                + outbound_seconds
                + minimum_visit_seconds
                + return_seconds
            )

            if projected_seconds <= total_available_seconds:
                chosen_index = index
                break

        if chosen_index is None:
            break

        travel_seconds = _matrix_duration(
            durations,
            current_index,
            chosen_index,
        )

        if travel_seconds is None:
            break

        elapsed_seconds += travel_seconds + MINIMUM_VISIT_MINUTES * 60

        selected.append(chosen_index)
        remaining.remove(chosen_index)
        current_index = chosen_index

    return selected


def _allocate_visit_time(
    *,
    candidates: list[dict[str, Any]],
    selected_indices: list[int],
    durations: list[Any],
    total_available_seconds: float,
) -> tuple[list[int], int]:
    total_travel_seconds = 0.0
    current_index = 0

    for index in selected_indices:
        travel_seconds = _matrix_duration(
            durations,
            current_index,
            index,
        )

        if travel_seconds is None:
            raise ConversationItineraryBuilderError(
                "A route duration became unavailable."
            )

        total_travel_seconds += travel_seconds
        current_index = index

    return_seconds = _matrix_duration(
        durations,
        current_index,
        0,
    )

    if return_seconds is None:
        raise ConversationItineraryBuilderError(
            "The return route duration is unavailable."
        )

    total_travel_seconds += return_seconds

    available_visit_minutes = max(
        0,
        int((total_available_seconds - total_travel_seconds) // 60),
    )

    visit_minutes = [MINIMUM_VISIT_MINUTES for _ in selected_indices]

    remaining_minutes = max(
        0,
        available_visit_minutes - MINIMUM_VISIT_MINUTES * len(selected_indices),
    )

    for position, matrix_index in enumerate(selected_indices):
        candidate = candidates[matrix_index - 1]

        target = TARGET_VISIT_MINUTES.get(
            candidate["recommendationType"],
            MINIMUM_VISIT_MINUTES,
        )

        additional_capacity = max(
            0,
            target - visit_minutes[position],
        )

        additional = min(
            remaining_minutes,
            additional_capacity,
        )

        visit_minutes[position] += additional
        remaining_minutes -= additional

        if remaining_minutes <= 0:
            break

    return visit_minutes, remaining_minutes


def _build_schedule(
    *,
    start_datetime: datetime,
    end_datetime: datetime,
    base_name: str,
    travel_mode: str,
    candidates: list[dict[str, Any]],
    selected_indices: list[int],
    visit_minutes: list[int],
    free_minutes: int,
    durations: list[Any],
) -> tuple[str, list[dict[str, Any]]]:
    cursor = start_datetime
    current_index = 0

    lines = [f"Your itinerary for " f"{start_datetime.strftime('%d %b %Y')}"]

    stops: list[dict[str, Any]] = []

    for position, matrix_index in enumerate(selected_indices):
        candidate = candidates[matrix_index - 1]

        travel_seconds = _matrix_duration(
            durations,
            current_index,
            matrix_index,
        )

        if travel_seconds is None:
            raise ConversationItineraryBuilderError(
                "A route duration became unavailable."
            )

        departure = cursor
        arrival = cursor + timedelta(seconds=travel_seconds)

        lines.append(
            f"{_format_time(departure)} to {_format_time(arrival)} "
            f"{_travel_label(travel_mode)} to {candidate['name']}"
        )

        visit_start = arrival
        visit_end = visit_start + timedelta(minutes=visit_minutes[position])

        lines.append(
            f"{_format_time(visit_start)} to {_format_time(visit_end)} "
            f"{candidate['name']}"
        )

        stops.append(
            {
                "id": candidate["id"],
                "name": candidate["name"],
                "recommendationType": (candidate["recommendationType"]),
                "latitude": candidate["latitude"],
                "longitude": candidate["longitude"],
                "travelStart": departure.isoformat(),
                "arrivalTime": arrival.isoformat(),
                "visitStart": visit_start.isoformat(),
                "visitEnd": visit_end.isoformat(),
                "visitMinutes": visit_minutes[position],
                "travelMinutes": round(
                    travel_seconds / 60,
                ),
                "explanation": candidate.get("explanation"),
            }
        )

        cursor = visit_end
        current_index = matrix_index

    if free_minutes >= 10:
        buffer_end = cursor + timedelta(
            minutes=free_minutes,
        )

        lines.append(
            f"{_format_time(cursor)} to {_format_time(buffer_end)} "
            "Flexible break / spare time"
        )

        cursor = buffer_end

    return_seconds = _matrix_duration(
        durations,
        current_index,
        0,
    )

    if return_seconds is None:
        raise ConversationItineraryBuilderError(
            "The return route duration is unavailable."
        )

    return_end = cursor + timedelta(
        seconds=return_seconds,
    )

    lines.append(
        f"{_format_time(cursor)} to {_format_time(return_end)} "
        f"{_travel_label(travel_mode)} back to {base_name}"
    )

    if return_end > end_datetime + timedelta(minutes=2):
        raise ConversationItineraryBuilderError(
            "The itinerary exceeds the available time window."
        )

    lines.append(
        (
            f"Planned for {travel_mode} within your "
            f"{_format_time(start_datetime)} to "
            f"{_format_time(end_datetime)} time window."
        )
    )

    return "\n".join(lines), stops


def _matrix_duration(
    durations: list[Any],
    source: int,
    destination: int,
) -> float | None:
    if source >= len(durations):
        return None

    row = durations[source]

    if not isinstance(row, list) or destination >= len(row):
        return None

    return _number_or_none(row[destination])


def _number_or_none(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    return None


def _parse_time(
    value: str,
) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ConversationItineraryBuilderError(
            f"Invalid itinerary time: {value}."
        ) from error


def _format_time(
    value: datetime,
) -> str:
    return value.strftime("%H:%M")


def _travel_label(
    travel_mode: str,
) -> str:
    return {
        "driving": "Drive",
        "walking": "Walk",
        "cycling": "Cycle",
    }.get(
        travel_mode,
        "Travel",
    )
