import asyncio
from datetime import datetime, time, timedelta
from typing import Any

import httpx
from fastapi import HTTPException

from app.foursquare import (
    MAXIMUM_SEARCH_RESULTS as FOURSQUARE_MAXIMUM_SEARCH_RESULTS,
    create_search_client,
    search_places,
)
from app.openrouteservice import MAXIMUM_MATRIX_LOCATIONS, get_route_matrix
from app.recommendation_models import (
    FoursquareProviderFilter,
    RecommendationCategory,
    RecommendationRequest,
)
from app.weather import get_weather_forecast

DEFAULT_RECOMMENDATION_RESULTS = 6
TOP_RECOMMENDATION_RESULTS = 3

# One matrix location is the traveller's origin. The remaining locations are
# the largest candidate pool the unchanged ORS request can enrich safely.
MAXIMUM_ROUTE_MATRIX_CANDIDATES = MAXIMUM_MATRIX_LOCATIONS - 1

SEARCH_RADIUS_BY_TYPE = {
    "attraction": 25_000,
    "hotel": 20_000,
    "restaurant": 12_000,
}

DEFAULT_HOTEL_WEATHER_TIME = time(
    hour=15,
    minute=0,
)

OUTDOOR_KEYWORDS = {
    "adventure",
    "beach",
    "botanical",
    "camp",
    "garden",
    "hiking",
    "lake",
    "landmark",
    "mountain",
    "nature",
    "outdoor",
    "park",
    "river",
    "scenic",
    "trail",
    "viewpoint",
    "waterfall",
    "wildlife",
    "zoo",
}

INDOOR_KEYWORDS = {
    "aquarium",
    "art gallery",
    "cafe",
    "cinema",
    "gallery",
    "hotel",
    "library",
    "mall",
    "museum",
    "restaurant",
    "shopping",
    "spa",
    "theatre",
}

TRAVEL_PARTNER_KEYWORDS = {
    "soloTraveller": {
        "cafe",
        "gallery",
        "historic",
        "library",
        "museum",
        "park",
    },
    "couple": {
        "beach",
        "cafe",
        "garden",
        "restaurant",
        "scenic",
        "spa",
        "viewpoint",
    },
    "family": {
        "aquarium",
        "botanical",
        "family",
        "garden",
        "museum",
        "park",
        "wildlife",
        "zoo",
    },
    "friendsGroup": {
        "adventure",
        "bar",
        "beach",
        "cycling",
        "hiking",
        "nightlife",
        "park",
        "sports",
    },
    "seniorTravellers": set(),
}


def _is_number(
    value: Any,
) -> bool:
    return isinstance(
        value,
        (int, float),
    ) and not isinstance(
        value,
        bool,
    )


def _number_or_none(
    value: Any,
) -> float | None:
    if not _is_number(value):
        return None

    return float(value)


def _normalized_text(
    values: list[str],
) -> str:
    return " ".join(value.strip().lower() for value in values if value.strip())


def _candidate_category_text(
    candidate: dict[str, Any],
) -> str:
    category_names: list[str] = []

    raw_categories = candidate.get("categories")

    if isinstance(raw_categories, list):
        for category in raw_categories:
            if not isinstance(category, dict):
                continue

            category_name = category.get("name")

            if isinstance(category_name, str):
                category_names.append(category_name)

    raw_matched_categories = candidate.get("matchedCategories")

    if isinstance(
        raw_matched_categories,
        list,
    ):
        for category in raw_matched_categories:
            if not isinstance(category, dict):
                continue

            category_name = category.get("name")

            if isinstance(category_name, str):
                category_names.append(category_name)

    return _normalized_text(category_names)


def _classify_place_environment(
    candidate: dict[str, Any],
) -> str:
    category_text = _candidate_category_text(candidate)

    outdoor_match = any(keyword in category_text for keyword in OUTDOOR_KEYWORDS)

    indoor_match = any(keyword in category_text for keyword in INDOOR_KEYWORDS)

    if outdoor_match and not indoor_match:
        return "outdoor"

    if indoor_match and not outdoor_match:
        return "indoor"

    if outdoor_match:
        return "mixed"

    return "neutral"


def _selected_visit_datetime(
    request: RecommendationRequest,
) -> datetime:
    if request.recommendation_type in {
        "attraction",
        "restaurant",
    }:
        if request.visit_date is None or request.start_time is None:
            raise ValueError("Visit date and start time are unavailable.")

        return datetime.combine(
            request.visit_date,
            request.start_time,
        )

    if request.check_in_date is None:
        raise ValueError("Hotel check-in date is unavailable.")

    return datetime.combine(
        request.check_in_date,
        DEFAULT_HOTEL_WEATHER_TIME,
    )


def _visit_window_minutes(
    request: RecommendationRequest,
) -> int:
    if (
        request.recommendation_type
        in {
            "attraction",
            "restaurant",
        }
        and request.visit_duration_minutes is not None
    ):
        return request.visit_duration_minutes

    return 60


def _parse_hourly_time(
    value: Any,
) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _closest_weather_hour(
    hourly_data: list[dict[str, Any]],
    target_datetime: datetime,
) -> dict[str, Any] | None:
    closest_entry: dict[str, Any] | None = None
    closest_difference: float | None = None

    for entry in hourly_data:
        entry_datetime = _parse_hourly_time(entry.get("time"))

        if entry_datetime is None:
            continue

        difference = abs((entry_datetime - target_datetime).total_seconds())

        if closest_difference is None or difference < closest_difference:
            closest_difference = difference
            closest_entry = entry

    return closest_entry


def _weather_entries_for_window(
    hourly_data: list[dict[str, Any]],
    *,
    start_datetime: datetime,
    duration_minutes: int,
) -> list[dict[str, Any]]:
    end_datetime = start_datetime + timedelta(
        minutes=duration_minutes,
    )

    selected_entries: list[dict[str, Any]] = []

    for entry in hourly_data:
        entry_datetime = _parse_hourly_time(entry.get("time"))

        if entry_datetime is None:
            continue

        if start_datetime <= entry_datetime <= end_datetime:
            selected_entries.append(entry)

    if selected_entries:
        return selected_entries

    closest_entry = _closest_weather_hour(
        hourly_data,
        start_datetime,
    )

    if closest_entry is None:
        return []

    return [
        closest_entry,
    ]


def _maximum_value(
    entries: list[dict[str, Any]],
    field_name: str,
) -> float | None:
    values = [
        float(value) for entry in entries if _is_number(value := entry.get(field_name))
    ]

    if not values:
        return None

    return max(values)


def _minimum_value(
    entries: list[dict[str, Any]],
    field_name: str,
) -> float | None:
    values = [
        float(value) for entry in entries if _is_number(value := entry.get(field_name))
    ]

    if not values:
        return None

    return min(values)


def _average_value(
    entries: list[dict[str, Any]],
    field_name: str,
) -> float | None:
    values = [
        float(value) for entry in entries if _is_number(value := entry.get(field_name))
    ]

    if not values:
        return None

    return sum(values) / len(values)


def _sum_values(
    entries: list[dict[str, Any]],
    field_name: str,
) -> float | None:
    values = [
        float(value) for entry in entries if _is_number(value := entry.get(field_name))
    ]

    if not values:
        return None

    return sum(values)


def _build_weather_summary(
    forecast: dict[str, Any] | None,
    request: RecommendationRequest,
) -> dict[str, Any] | None:
    if not isinstance(forecast, dict):
        return None

    raw_hourly = forecast.get("hourly")

    if not isinstance(raw_hourly, list):
        return None

    hourly_data = [entry for entry in raw_hourly if isinstance(entry, dict)]

    if not hourly_data:
        return None

    start_datetime = _selected_visit_datetime(request)

    duration_minutes = _visit_window_minutes(request)

    selected_entries = _weather_entries_for_window(
        hourly_data,
        start_datetime=start_datetime,
        duration_minutes=duration_minutes,
    )

    if not selected_entries:
        return None

    weather_codes = sorted(
        {
            int(weather_code)
            for entry in selected_entries
            if _is_number(weather_code := entry.get("weather_code"))
        }
    )

    return {
        "available": True,
        "startDateTime": (start_datetime.isoformat()),
        "durationMinutes": duration_minutes,
        "temperatureAverageC": (
            _average_value(
                selected_entries,
                "temperature_2m",
            )
        ),
        "apparentTemperatureAverageC": (
            _average_value(
                selected_entries,
                "apparent_temperature",
            )
        ),
        "precipitationProbabilityMax": (
            _maximum_value(
                selected_entries,
                "precipitation_probability",
            )
        ),
        "precipitationTotalMm": (
            _sum_values(
                selected_entries,
                "precipitation",
            )
        ),
        "rainTotalMm": _sum_values(
            selected_entries,
            "rain",
        ),
        "showersTotalMm": _sum_values(
            selected_entries,
            "showers",
        ),
        "windSpeedMaxKmh": (
            _maximum_value(
                selected_entries,
                "wind_speed_10m",
            )
        ),
        "windGustsMaxKmh": (
            _maximum_value(
                selected_entries,
                "wind_gusts_10m",
            )
        ),
        "visibilityMinMeters": (
            _minimum_value(
                selected_entries,
                "visibility",
            )
        ),
        "weatherCodes": weather_codes,
    }


def _weather_risk_level(
    weather_summary: dict[str, Any] | None,
) -> str:
    if weather_summary is None:
        return "unknown"

    precipitation_probability = _number_or_none(
        weather_summary.get("precipitationProbabilityMax")
    )

    precipitation_total = _number_or_none(weather_summary.get("precipitationTotalMm"))

    wind_speed = _number_or_none(weather_summary.get("windSpeedMaxKmh"))

    wind_gusts = _number_or_none(weather_summary.get("windGustsMaxKmh"))

    visibility = _number_or_none(weather_summary.get("visibilityMinMeters"))

    raw_codes = weather_summary.get("weatherCodes")

    weather_codes = raw_codes if isinstance(raw_codes, list) else []

    severe_weather_code = any(
        _is_number(code) and int(code) >= 95 for code in weather_codes
    )

    heavy_rain_code = any(
        _is_number(code)
        and int(code)
        in {
            65,
            67,
            75,
            77,
            82,
            86,
        }
        for code in weather_codes
    )

    if (
        severe_weather_code
        or heavy_rain_code
        or (precipitation_probability is not None and precipitation_probability >= 75)
        or (precipitation_total is not None and precipitation_total >= 3)
        or (wind_gusts is not None and wind_gusts >= 50)
        or (visibility is not None and visibility < 2500)
    ):
        return "high"

    rainy_weather_code = any(
        _is_number(code)
        and int(code)
        in {
            51,
            53,
            55,
            56,
            57,
            61,
            63,
            66,
            71,
            73,
            80,
            81,
            85,
        }
        for code in weather_codes
    )

    if (
        rainy_weather_code
        or (precipitation_probability is not None and precipitation_probability >= 45)
        or (precipitation_total is not None and precipitation_total >= 0.5)
        or (wind_speed is not None and wind_speed >= 30)
        or (wind_gusts is not None and wind_gusts >= 40)
        or (visibility is not None and visibility < 7000)
    ):
        return "moderate"

    return "low"


def _assess_weather_suitability(
    candidate: dict[str, Any],
    weather_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    environment = _classify_place_environment(candidate)

    risk_level = _weather_risk_level(weather_summary)

    if risk_level == "unknown":
        return {
            "status": "unknown",
            "environment": environment,
            "riskLevel": risk_level,
            "score": 10.0,
            "message": ("Weather information is currently " "unavailable."),
        }

    if environment == "outdoor":
        if risk_level == "high":
            return {
                "status": "unsuitable",
                "environment": environment,
                "riskLevel": risk_level,
                "score": 0.0,
                "message": (
                    "Poor weather may significantly " "affect this outdoor visit."
                ),
            }

        if risk_level == "moderate":
            return {
                "status": "warning",
                "environment": environment,
                "riskLevel": risk_level,
                "score": 9.0,
                "message": (
                    "Rain, wind, or reduced visibility "
                    "may affect this outdoor visit."
                ),
            }

        return {
            "status": "suitable",
            "environment": environment,
            "riskLevel": risk_level,
            "score": 20.0,
            "message": ("The forecast is suitable for this " "outdoor visit."),
        }

    if environment == "indoor":
        if risk_level == "high":
            return {
                "status": "warning",
                "environment": environment,
                "riskLevel": risk_level,
                "score": 14.0,
                "message": (
                    "The place is mainly indoors, "
                    "but travelling conditions may be poor."
                ),
            }

        return {
            "status": "suitable",
            "environment": environment,
            "riskLevel": risk_level,
            "score": (20.0 if risk_level == "low" else 18.0),
            "message": (
                "The indoor setting reduces the " "effect of the forecast conditions."
            ),
        }

    if risk_level == "high":
        return {
            "status": "warning",
            "environment": environment,
            "riskLevel": risk_level,
            "score": 8.0,
            "message": ("Weather may affect travel or parts " "of the visit."),
        }

    if risk_level == "moderate":
        return {
            "status": "warning",
            "environment": environment,
            "riskLevel": risk_level,
            "score": 14.0,
            "message": ("Some rain or wind is possible " "during the visit."),
        }

    return {
        "status": "suitable",
        "environment": environment,
        "riskLevel": risk_level,
        "score": 18.0,
        "message": ("No major weather issue is expected " "for the visit."),
    }


def _partner_score(
    candidate: dict[str, Any],
    travel_partner: str | None,
) -> tuple[float, bool]:
    if travel_partner is None:
        return 0.0, False

    category_text = _candidate_category_text(candidate)

    partner_keywords = TRAVEL_PARTNER_KEYWORDS.get(
        travel_partner,
        set(),
    )

    matched = any(keyword in category_text for keyword in partner_keywords)

    if matched:
        return 10.0, True

    return 6.0, False


def _route_score(
    *,
    route: dict[str, Any],
) -> float:
    duration_seconds = _number_or_none(route.get("durationSeconds"))

    distance_meters = _number_or_none(route.get("distanceMeters"))

    if duration_seconds is not None:
        duration_minutes = duration_seconds / 60

        return max(
            0.0,
            30.0
            * (
                1.0
                - min(
                    duration_minutes,
                    180.0,
                )
                / 180.0
            ),
        )

    if distance_meters is not None:
        distance_kilometres = distance_meters / 1000

        return max(
            0.0,
            20.0
            * (
                1.0
                - min(
                    distance_kilometres,
                    80.0,
                )
                / 80.0
            ),
        )

    return 5.0


def _category_score(
    candidate: dict[str, Any],
) -> float:
    raw_matched_categories = candidate.get("matchedCategories")

    if not isinstance(
        raw_matched_categories,
        list,
    ):
        return 25.0

    match_count = len(raw_matched_categories)

    return min(
        35.0,
        25.0 + match_count * 5.0,
    )


def _search_rank_score(
    candidate: dict[str, Any],
) -> float:
    raw_search_position = candidate.get("bestSearchPosition")

    if not isinstance(
        raw_search_position,
        int,
    ):
        return 1.0

    denominator = max(
        1,
        DEFAULT_RECOMMENDATION_RESULTS - 1,
    )

    return max(
        0.0,
        5.0
        * (
            1.0
            - min(
                raw_search_position,
                denominator,
            )
            / denominator
        ),
    )


def _matched_category_names(
    candidate: dict[str, Any],
) -> list[str]:
    names: list[str] = []

    raw_categories = candidate.get("matchedCategories")

    if not isinstance(raw_categories, list):
        return names

    for category in raw_categories:
        if not isinstance(category, dict):
            continue

        name = category.get("name")

        if isinstance(name, str) and name.strip() and name.strip() not in names:
            names.append(name.strip())

    return names


def _travel_mode_label(
    travel_mode: str,
) -> str:
    labels = {
        "driving": "car",
        "walking": "walking",
        "cycling": "cycling",
    }

    return labels.get(
        travel_mode,
        travel_mode,
    )


def _build_explanation(
    *,
    candidate: dict[str, Any],
    request: RecommendationRequest,
    route: dict[str, Any],
    weather_assessment: dict[str, Any],
    partner_match: bool,
) -> str:
    explanation_parts: list[str] = []

    matched_names = _matched_category_names(candidate)

    if matched_names:
        explanation_parts.append(
            "it matches your " + ", ".join(matched_names) + " preference"
        )

    duration_seconds = _number_or_none(route.get("durationSeconds"))

    if duration_seconds is not None:
        duration_minutes = duration_seconds / 60

        if request.recommendation_type == "hotel":
            explanation_parts.append(
                (
                    f"it is about {duration_minutes:.0f} "
                    f"minutes away by "
                    f"{_travel_mode_label(request.travel_mode)}"
                )
            )
        else:
            explanation_parts.append(
                "the estimated round trip is about "
                f"{duration_minutes:.0f} minutes "
                f"by {_travel_mode_label(request.travel_mode)}"
            )

    remaining_visit_minutes = _number_or_none(route.get("remainingVisitMinutes"))

    if (
        request.recommendation_type
        in {
            "attraction",
            "restaurant",
        }
        and remaining_visit_minutes is not None
    ):
        explanation_parts.append(
            "after the estimated round trip, "
            f"about {remaining_visit_minutes:.0f} "
            "minutes remain for the visit"
        )

    weather_status = weather_assessment.get("status")

    if weather_status == "suitable":
        explanation_parts.append("the forecast is suitable for this type of visit")

    elif weather_status == "warning":
        explanation_parts.append(
            "the forecast may affect the visit, " "so some preparation is recommended"
        )

    elif weather_status == "unsuitable":
        explanation_parts.append(
            "the forecast may make this visit " "unsuitable at the selected time"
        )

    if partner_match:
        explanation_parts.append(
            "its categories also align with the " "selected traveller type"
        )

    if not explanation_parts:
        return "This place matches the available " "recommendation information."

    return "Recommended because " + ", ".join(explanation_parts) + "."


def _provider_searches(
    request: RecommendationRequest,
) -> tuple[tuple[FoursquareProviderFilter, RecommendationCategory], ...]:
    if request.provider_filters:
        return tuple(
            (
                provider_filter,
                RecommendationCategory(
                    name=(
                        request.categories[0].name
                        if request.recommendation_type == "restaurant"
                        else (
                            provider_filter.query
                            or request.categories[0].name
                        )
                    )
                ),
            )
            for provider_filter in request.provider_filters
        )

    return tuple(
        (
            FoursquareProviderFilter(
                query=category.name,
                categoryIds=((category.id,) if category.id is not None else ()),
            ),
            category,
        )
        for category in request.categories
    )


def _provider_match(
    provider_filter: FoursquareProviderFilter,
    category: RecommendationCategory,
) -> dict[str, Any]:
    match: dict[str, Any] = {
        "id": category.id,
        "name": category.name,
    }

    if provider_filter.provenance_key is not None:
        match["providerFilterKey"] = provider_filter.provenance_key

    return match


def _provider_search_result_limit(provider_search_count: int) -> int:
    """Allocate the routable candidate capacity fairly across searches."""

    if provider_search_count < 1:
        return 1

    fair_share = (
        MAXIMUM_ROUTE_MATRIX_CANDIDATES + provider_search_count - 1
    ) // provider_search_count

    return min(
        fair_share,
        FOURSQUARE_MAXIMUM_SEARCH_RESULTS,
    )


def _uses_generic_attraction_discovery(
    provider_searches: tuple[
        tuple[FoursquareProviderFilter, RecommendationCategory],
        ...,
    ],
) -> bool:
    return bool(provider_searches) and all(
        provider_filter.provenance_key is not None
        and provider_filter.provenance_key.startswith("generic:")
        for provider_filter, _ in provider_searches
    )


def _provider_search_identity(
    provider_filter: FoursquareProviderFilter,
    *,
    latitude: float,
    longitude: float,
    near: str | None,
    radius: int,
    limit: int,
) -> tuple[Any, ...]:
    """Identify requests that are equivalent at the Foursquare boundary."""

    return (
        provider_filter.query,
        tuple(sorted(provider_filter.category_ids)),
        latitude,
        longitude,
        near,
        radius,
        limit,
        "RELEVANCE",
    )


def _fair_candidate_ids(
    search_place_ids: list[list[str]],
) -> list[str]:
    """Round-robin provider results while preserving each search's rank."""

    candidate_ids: list[str] = []
    selected_ids: set[str] = set()
    maximum_search_size = max(
        (len(place_ids) for place_ids in search_place_ids),
        default=0,
    )

    for position in range(maximum_search_size):
        for place_ids in search_place_ids:
            if position >= len(place_ids):
                continue

            place_id = place_ids[position]

            if place_id in selected_ids:
                continue

            selected_ids.add(place_id)
            candidate_ids.append(place_id)

    return candidate_ids


async def _collect_candidates(
    request: RecommendationRequest,
) -> list[dict[str, Any]]:
    radius = SEARCH_RADIUS_BY_TYPE[request.recommendation_type]
    provider_searches = _provider_searches(request)
    provider_result_limit = _provider_search_result_limit(len(provider_searches))
    locality_name = request.location.locality_name
    near = None

    if locality_name is not None:
        near = (
            f"{locality_name}, Sri Lanka"
            if request.location.country_code == "LK"
            else locality_name
        )

    unique_provider_filters: list[FoursquareProviderFilter] = []
    unique_search_index_by_identity: dict[tuple[Any, ...], int] = {}
    logical_to_unique_search_indexes: list[int] = []

    for provider_filter, _ in provider_searches:
        search_identity = _provider_search_identity(
            provider_filter,
            latitude=request.location.latitude,
            longitude=request.location.longitude,
            near=near,
            radius=radius,
            limit=provider_result_limit,
        )
        unique_search_index = unique_search_index_by_identity.get(search_identity)

        if unique_search_index is None:
            unique_search_index = len(unique_provider_filters)
            unique_search_index_by_identity[search_identity] = unique_search_index
            unique_provider_filters.append(provider_filter)

        logical_to_unique_search_indexes.append(unique_search_index)

    async with create_search_client() as client:
        unique_search_results = await asyncio.gather(
            *(
                search_places(
                    query=provider_filter.query,
                    latitude=request.location.latitude,
                    longitude=request.location.longitude,
                    category_ids=(
                        list(provider_filter.category_ids)
                        if provider_filter.category_ids
                        else None
                    ),
                    radius=radius,
                    limit=provider_result_limit,
                    sort="RELEVANCE",
                    client=client,
                    **({"near": near} if near is not None else {}),
                )
                for provider_filter in unique_provider_filters
            ),
            return_exceptions=True,
        )

    search_results = [
        unique_search_results[unique_search_index]
        for unique_search_index in logical_to_unique_search_indexes
    ]

    candidates_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    matched_search_indexes_by_place_id: dict[str, set[int]] = {}

    search_place_ids: list[list[str]] = [
        [] for _ in provider_searches
    ]

    search_errors: list[Exception] = []

    for search_index, ((provider_filter, category), result) in enumerate(
        zip(
            provider_searches,
            search_results,
            strict=True,
        )
    ):
        if isinstance(result, HTTPException):
            search_errors.append(result)
            continue

        if isinstance(result, BaseException):
            raise result

        for position, raw_place in enumerate(result):
            if not isinstance(raw_place, dict):
                continue

            place_id = raw_place.get("id")

            if not isinstance(place_id, str) or not place_id.strip():
                continue

            if place_id not in search_place_ids[search_index]:
                search_place_ids[search_index].append(place_id)

            existing_candidate = candidates_by_id.get(place_id)

            if existing_candidate is None:
                candidate = dict(raw_place)

                candidate["matchedCategories"] = [
                    _provider_match(provider_filter, category)
                ]

                candidate["bestSearchPosition"] = position

                candidates_by_id[place_id] = candidate
                matched_search_indexes_by_place_id[place_id] = {search_index}

                continue

            raw_matched_categories = existing_candidate.get("matchedCategories")

            if not isinstance(
                raw_matched_categories,
                list,
            ):
                raw_matched_categories = []

                existing_candidate["matchedCategories"] = raw_matched_categories

            matched_search_indexes = matched_search_indexes_by_place_id.setdefault(
                place_id,
                set(),
            )

            if search_index not in matched_search_indexes:
                provider_match = _provider_match(provider_filter, category)

                if provider_match not in raw_matched_categories:
                    raw_matched_categories.append(provider_match)

                matched_search_indexes.add(search_index)

            current_position = existing_candidate.get("bestSearchPosition")

            if (
                not isinstance(
                    current_position,
                    int,
                )
                or position < current_position
            ):
                existing_candidate["bestSearchPosition"] = position

    if _uses_generic_attraction_discovery(provider_searches):
        candidates = [
            candidates_by_id[place_id]
            for place_id in _fair_candidate_ids(search_place_ids)
        ]
    else:
        candidates = list(candidates_by_id.values())

        candidates.sort(
            key=lambda candidate: (
                candidate.get(
                    "bestSearchPosition",
                    FOURSQUARE_MAXIMUM_SEARCH_RESULTS,
                ),
                candidate.get("name", ""),
            )
        )

    if candidates:
        return candidates[:MAXIMUM_ROUTE_MATRIX_CANDIDATES]

    if search_errors:
        first_error = search_errors[0]

        if isinstance(
            first_error,
            HTTPException,
        ):
            raise first_error

    return []


async def _load_route_information(
    request: RecommendationRequest,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    route_origin = request.route_origin

    if route_origin is None or request.travel_mode is None:
        for candidate in candidates:
            candidate["route"] = {
                "available": False,
                "travelMode": request.travel_mode,
                "outboundDurationSeconds": None,
                "returnDurationSeconds": None,
                "roundTripDurationSeconds": None,
                "durationSeconds": None,
                "durationMinutes": None,
                "outboundDistanceMeters": None,
                "returnDistanceMeters": None,
                "roundTripDistanceMeters": None,
                "distanceMeters": None,
                "distanceKilometres": None,
                "availableTimeMinutes": None,
                "remainingVisitMinutes": None,
                "timeFeasible": None,
                "totalPlannedMinutes": None,
            }

        return None

    route_locations = [
        (
            route_origin.latitude,
            route_origin.longitude,
        )
    ]

    routable_candidates: list[tuple[dict[str, Any], int]] = []

    for candidate in candidates:
        latitude = candidate.get("latitude")
        longitude = candidate.get("longitude")

        if not _is_number(latitude) or not _is_number(longitude):
            candidate["route"] = {
                "available": False,
                "travelMode": request.travel_mode,
                "outboundDurationSeconds": None,
                "returnDurationSeconds": None,
                "roundTripDurationSeconds": None,
                "durationSeconds": None,
                "durationMinutes": None,
                "outboundDistanceMeters": None,
                "returnDistanceMeters": None,
                "roundTripDistanceMeters": None,
                "distanceMeters": None,
                "distanceKilometres": None,
                "totalPlannedMinutes": None,
            }
            continue

        route_locations.append(
            (
                float(latitude),
                float(longitude),
            )
        )

        routable_candidates.append(
            (
                candidate,
                len(route_locations) - 1,
            )
        )

    if not routable_candidates:
        return None

    try:
        matrix = await get_route_matrix(
            locations=route_locations,
            travel_mode=request.travel_mode,
        )
    except HTTPException:
        for candidate in candidates:
            fallback_distance = _number_or_none(candidate.get("distanceMeters"))

            if request.recommendation_type == "hotel":
                journey_distance = fallback_distance
            else:
                journey_distance = (
                    fallback_distance * 2 if fallback_distance is not None else None
                )

            candidate["route"] = {
                "available": False,
                "travelMode": request.travel_mode,
                "outboundDurationSeconds": None,
                "returnDurationSeconds": None,
                "roundTripDurationSeconds": None,
                "durationSeconds": None,
                "durationMinutes": None,
                "outboundDistanceMeters": fallback_distance,
                "returnDistanceMeters": (
                    fallback_distance
                    if request.recommendation_type != "hotel"
                    else None
                ),
                "roundTripDistanceMeters": (
                    journey_distance if request.recommendation_type != "hotel" else None
                ),
                "distanceMeters": journey_distance,
                "distanceKilometres": (
                    journey_distance / 1000 if journey_distance is not None else None
                ),
                "totalPlannedMinutes": None,
            }

        return None

    raw_durations = matrix.get("durationsSeconds")
    raw_distances = matrix.get("distancesMeters")

    durations = raw_durations if isinstance(raw_durations, list) else []
    distances = raw_distances if isinstance(raw_distances, list) else []

    for candidate, matrix_index in routable_candidates:
        outbound_duration = None
        return_duration = None
        outbound_distance = None
        return_distance = None

        if (
            durations
            and isinstance(durations[0], list)
            and matrix_index < len(durations[0])
        ):
            outbound_duration = _number_or_none(durations[0][matrix_index])

        if (
            matrix_index < len(durations)
            and isinstance(durations[matrix_index], list)
            and durations[matrix_index]
        ):
            return_duration = _number_or_none(durations[matrix_index][0])

        if (
            distances
            and isinstance(distances[0], list)
            and matrix_index < len(distances[0])
        ):
            outbound_distance = _number_or_none(distances[0][matrix_index])

        if (
            matrix_index < len(distances)
            and isinstance(distances[matrix_index], list)
            and distances[matrix_index]
        ):
            return_distance = _number_or_none(distances[matrix_index][0])

        round_trip_duration = (
            outbound_duration + return_duration
            if outbound_duration is not None and return_duration is not None
            else None
        )

        round_trip_distance = (
            outbound_distance + return_distance
            if outbound_distance is not None and return_distance is not None
            else None
        )

        if request.recommendation_type == "hotel":
            journey_duration = outbound_duration
            journey_distance = outbound_distance
        else:
            journey_duration = round_trip_duration
            journey_distance = round_trip_distance

        available_time_minutes = None
        remaining_visit_minutes = None
        time_feasible = None
        total_planned_minutes = None

        if (
            request.recommendation_type
            in {
                "attraction",
                "restaurant",
            }
            and request.visit_duration_minutes is not None
        ):
            available_time_minutes = float(request.visit_duration_minutes)
            total_planned_minutes = available_time_minutes

            if journey_duration is not None:
                journey_minutes = journey_duration / 60

                remaining_visit_minutes = max(
                    0.0,
                    available_time_minutes - journey_minutes,
                )

                time_feasible = remaining_visit_minutes > 0

        candidate["route"] = {
            "available": (
                journey_duration is not None and journey_distance is not None
            ),
            "travelMode": request.travel_mode,
            "outboundDurationSeconds": outbound_duration,
            "returnDurationSeconds": return_duration,
            "roundTripDurationSeconds": round_trip_duration,
            "durationSeconds": journey_duration,
            "durationMinutes": (
                journey_duration / 60 if journey_duration is not None else None
            ),
            "outboundDistanceMeters": outbound_distance,
            "returnDistanceMeters": return_distance,
            "roundTripDistanceMeters": round_trip_distance,
            "distanceMeters": journey_distance,
            "distanceKilometres": (
                journey_distance / 1000 if journey_distance is not None else None
            ),
            "availableTimeMinutes": (available_time_minutes),
            "remainingVisitMinutes": (remaining_visit_minutes),
            "timeFeasible": time_feasible,
            "totalPlannedMinutes": total_planned_minutes,
        }

    return {
        "locations": [
            {
                "latitude": latitude,
                "longitude": longitude,
            }
            for latitude, longitude in route_locations
        ],
        "durationsSeconds": durations,
    }


async def _load_weather_summary_for_coordinates(
    request: RecommendationRequest,
    *,
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    if (
        request.recommendation_type == "hotel"
        and request.check_in_date is None
    ):
        return None

    if (
        request.recommendation_type in {"attraction", "restaurant"}
        and (request.visit_date is None or request.start_time is None)
    ):
        return None

    selected_datetime = _selected_visit_datetime(request)

    try:
        forecast = await get_weather_forecast(
            latitude=latitude,
            longitude=longitude,
            visit_date=selected_datetime.date(),
        )
    except HTTPException:
        return None

    return _build_weather_summary(
        forecast,
        request,
    )


async def _load_location_weather_summary(
    request: RecommendationRequest,
) -> dict[str, Any] | None:
    return await _load_weather_summary_for_coordinates(
        request,
        latitude=request.location.latitude,
        longitude=request.location.longitude,
    )


async def _load_candidate_weather_information(
    request: RecommendationRequest,
    candidates: list[dict[str, Any]],
) -> None:
    weather_tasks = []
    weather_candidates = []

    for candidate in candidates:
        latitude = candidate.get("latitude")
        longitude = candidate.get("longitude")

        if not _is_number(latitude) or not _is_number(longitude):
            candidate["weather"] = None
            continue

        weather_candidates.append(candidate)
        weather_tasks.append(
            _load_weather_summary_for_coordinates(
                request,
                latitude=float(latitude),
                longitude=float(longitude),
            )
        )

    if not weather_tasks:
        return

    weather_results = await asyncio.gather(
        *weather_tasks,
        return_exceptions=True,
    )

    for candidate, result in zip(
        weather_candidates,
        weather_results,
        strict=True,
    ):
        candidate["weather"] = result if isinstance(result, dict) else None


def _score_candidates(
    request: RecommendationRequest,
    candidates: list[dict[str, Any]],
) -> None:
    for candidate in candidates:
        route = candidate.get("route")

        if not isinstance(route, dict):
            route = {}

        candidate_weather = candidate.get("weather")

        weather_summary = (
            candidate_weather if isinstance(candidate_weather, dict) else None
        )

        weather_assessment = _assess_weather_suitability(
            candidate,
            weather_summary,
        )

        partner_score, partner_match = _partner_score(
            candidate,
            request.travel_partner,
        )

        category_score = _category_score(candidate)
        route_score = _route_score(route=route)

        weather_score = _number_or_none(weather_assessment.get("score"))

        if weather_score is None:
            weather_score = 0.0

        search_score = _search_rank_score(candidate)

        total_score = (
            category_score + route_score + weather_score + partner_score + search_score
        )

        candidate["weatherSuitability"] = weather_assessment
        candidate["score"] = round(total_score, 2)

        candidate["scoreBreakdown"] = {
            "category": round(category_score, 2),
            "route": round(route_score, 2),
            "weather": round(weather_score, 2),
            "travelPartner": round(partner_score, 2),
            "searchRelevance": round(search_score, 2),
        }

        candidate["explanation"] = _build_explanation(
            candidate=candidate,
            request=request,
            route=route,
            weather_assessment=weather_assessment,
            partner_match=partner_match,
        )

    def sort_duration(candidate: dict[str, Any]) -> float:
        route = candidate.get("route")

        if not isinstance(route, dict):
            return float("inf")

        duration = _number_or_none(route.get("durationSeconds"))

        return duration if duration is not None else float("inf")

    candidates.sort(
        key=lambda candidate: (
            -float(candidate.get("score", 0)),
            sort_duration(candidate),
            str(candidate.get("name", "")),
        )
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        candidate["rank"] = index


async def generate_recommendations(
    request: RecommendationRequest,
    *,
    requested_count: int | None = None,
    include_internal_route_matrix: bool = False,
) -> dict[str, Any]:
    """Generate ranked and explainable travel recommendations."""

    if requested_count is not None and not (
        1 <= requested_count <= MAXIMUM_ROUTE_MATRIX_CANDIDATES
    ):
        raise ValueError(
            "requested_count must be between 1 and "
            f"{MAXIMUM_ROUTE_MATRIX_CANDIDATES}."
        )

    output_count = (
        DEFAULT_RECOMMENDATION_RESULTS
        if requested_count is None
        else requested_count
    )

    candidates = await _collect_candidates(request)

    if not candidates:
        return {
            "recommendationType": request.recommendation_type,
            "location": request.location.model_dump(by_alias=True),
            "weather": None,
            "count": 0,
            "topRecommendations": [],
            "moreRecommendations": [],
            "message": (
                "No matching places were found " "for the selected categories."
            ),
        }

    route_task = _load_route_information(
        request,
        candidates,
    )

    location_weather_task = _load_location_weather_summary(request)

    candidate_weather_task = _load_candidate_weather_information(
        request,
        candidates,
    )

    route_matrix, location_weather, _ = await asyncio.gather(
        route_task,
        location_weather_task,
        candidate_weather_task,
    )

    _score_candidates(
        request,
        candidates,
    )

    selected_candidates = candidates[:output_count]

    top_recommendations = selected_candidates[:TOP_RECOMMENDATION_RESULTS]

    more_recommendations = selected_candidates[TOP_RECOMMENDATION_RESULTS:]

    result = {
        "recommendationType": request.recommendation_type,
        "location": request.location.model_dump(by_alias=True),
        "travelMode": request.travel_mode,
        "travelPartner": request.travel_partner,
        "selectedCategories": [
            category.model_dump() for category in request.categories
        ],
        "weather": location_weather,
        "count": len(selected_candidates),
        "topRecommendations": top_recommendations,
        "moreRecommendations": more_recommendations,
    }

    if include_internal_route_matrix and route_matrix is not None:
        result["_internalRouteMatrix"] = route_matrix

    return result
