from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException, status

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")
MAXIMUM_FORECAST_DAYS = 14


def _is_number(value: Any) -> bool:
    """Return true for integer and float values, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(
        value,
        bool,
    )


def _validate_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    if not _is_number(latitude):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Latitude must be a number.",
        )

    if not _is_number(longitude):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Longitude must be a number.",
        )

    if not -90 <= latitude <= 90:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Latitude must be between -90 and 90.",
        )

    if not -180 <= longitude <= 180:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Longitude must be between -180 and 180.",
        )


def _validate_visit_date(
    visit_date: date,
) -> None:
    today = datetime.now(
        SRI_LANKA_TIMEZONE,
    ).date()

    final_allowed_date = today + timedelta(
        days=MAXIMUM_FORECAST_DAYS - 1,
    )

    if visit_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The visit date cannot be in the past.",
        )

    if visit_date > final_allowed_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Recommendations are limited to the next "
                f"{MAXIMUM_FORECAST_DAYS} days."
            ),
        )


async def get_weather_forecast(
    *,
    latitude: float,
    longitude: float,
    visit_date: date,
) -> dict[str, Any]:
    """Fetch hourly weather for one supported visit date."""

    _validate_coordinates(
        latitude,
        longitude,
    )

    _validate_visit_date(
        visit_date,
    )

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "Asia/Colombo",
        "start_date": visit_date.isoformat(),
        "end_date": visit_date.isoformat(),
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "rain",
                "showers",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_gusts_10m",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "rain",
                "showers",
                "weather_code",
                "cloud_cover",
                "visibility",
                "wind_speed_10m",
                "wind_gusts_10m",
            ]
        ),
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout=15.0,
                connect=5.0,
            ),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                OPEN_METEO_FORECAST_URL,
                params=params,
            )

            response.raise_for_status()

    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=("The weather service took too long " "to respond."),
        ) from error

    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The weather service returned an error.",
        ) from error

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("The weather service is currently " "unavailable."),
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The weather service returned invalid data."),
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The weather service returned an " "unexpected response."),
        )

    hourly_data = payload.get("hourly")

    if not isinstance(hourly_data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Hourly weather data is unavailable.",
        )

    hourly_times = hourly_data.get("time")

    if not isinstance(hourly_times, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Hourly weather times are unavailable.",
        )

    hourly_fields = [
        "temperature_2m",
        "apparent_temperature",
        "precipitation_probability",
        "precipitation",
        "rain",
        "showers",
        "weather_code",
        "cloud_cover",
        "visibility",
        "wind_speed_10m",
        "wind_gusts_10m",
    ]

    hourly_forecast: list[dict[str, Any]] = []

    for index, time_value in enumerate(
        hourly_times,
    ):
        hour: dict[str, Any] = {
            "time": time_value,
        }

        for field in hourly_fields:
            values = hourly_data.get(field)

            if isinstance(values, list) and index < len(values):
                hour[field] = values[index]
            else:
                hour[field] = None

        hourly_forecast.append(hour)

    current_data = payload.get("current")

    if not isinstance(current_data, dict):
        current_data = {}

    returned_latitude = payload.get("latitude")
    returned_longitude = payload.get("longitude")

    returned_timezone = payload.get("timezone")

    if not isinstance(returned_timezone, str):
        returned_timezone = "Asia/Colombo"

    return {
        "latitude": (
            float(returned_latitude)
            if _is_number(returned_latitude)
            else float(latitude)
        ),
        "longitude": (
            float(returned_longitude)
            if _is_number(returned_longitude)
            else float(longitude)
        ),
        "timezone": returned_timezone,
        "visitDate": visit_date.isoformat(),
        "currentAtRequestTime": current_data,
        "hourly": hourly_forecast,
    }
