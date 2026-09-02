from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth import get_current_user
from app.config import get_settings
from app.foursquare import (
    DEFAULT_SEARCH_RADIUS_METERS,
    MAXIMUM_SEARCH_RADIUS_METERS,
    MAXIMUM_SEARCH_RESULTS,
    search_places,
)
from app.open_meteo import search_sri_lankan_locations
from app.openrouteservice import (
    MAXIMUM_MATRIX_LOCATIONS,
    get_route_matrix,
)
from app.recommendation_engine import (
    generate_recommendations,
)
from app.recommendation_models import (
    RecommendationRequest,
)
from app.weather import get_weather_forecast
from app.conversation_router import router as conversation_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=("Context-aware travel recommendation API " "for Trip Logic."),
)

app.include_router(conversation_router)


class RouteLocation(BaseModel):
    latitude: float = Field(
        ge=-90,
        le=90,
        description="Location latitude.",
    )

    longitude: float = Field(
        ge=-180,
        le=180,
        description="Location longitude.",
    )


class RouteMatrixRequest(BaseModel):
    locations: list[RouteLocation] = Field(
        min_length=2,
        max_length=MAXIMUM_MATRIX_LOCATIONS,
        description=("Locations used to calculate the route matrix."),
    )

    travel_mode: str = Field(
        alias="travelMode",
        min_length=1,
        max_length=30,
        description=("Driving, walking, or cycling."),
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/auth/me", tags=["Authentication"])
async def get_authenticated_user(
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> dict[str, Any]:
    return {
        "uid": current_user["uid"],
        "email": current_user.get("email"),
        "emailVerified": current_user.get(
            "email_verified",
            False,
        ),
    }


@app.get("/locations/search", tags=["Locations"])
async def search_locations(
    query: Annotated[
        str,
        Query(
            min_length=2,
            max_length=80,
            description=("Sri Lankan city or region name."),
        ),
    ],
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> dict[str, Any]:
    normalized_query = query.strip()

    locations = await search_sri_lankan_locations(
        normalized_query,
    )

    return {
        "query": normalized_query,
        "count": len(locations),
        "locations": locations,
    }


@app.get("/weather/forecast", tags=["Weather"])
async def weather_forecast(
    latitude: Annotated[
        float,
        Query(
            ge=-90,
            le=90,
            description="Destination latitude.",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180,
            le=180,
            description="Destination longitude.",
        ),
    ],
    visit_date: Annotated[
        date,
        Query(
            description=("Visit date in YYYY-MM-DD format."),
        ),
    ],
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> dict[str, Any]:
    return await get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        visit_date=visit_date,
    )


@app.get("/places/search", tags=["Places"])
async def search_foursquare_places(
    query: Annotated[
        str,
        Query(
            min_length=2,
            max_length=80,
            description=("Place name, category, or search term."),
        ),
    ],
    latitude: Annotated[
        float,
        Query(
            ge=-90,
            le=90,
            description="Search-centre latitude.",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180,
            le=180,
            description="Search-centre longitude.",
        ),
    ],
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
    category_ids: Annotated[
        list[str] | None,
        Query(
            description=(
                "Optional Foursquare category IDs. "
                "Repeat this parameter for multiple "
                "categories."
            ),
        ),
    ] = None,
    radius: Annotated[
        int,
        Query(
            ge=1,
            le=MAXIMUM_SEARCH_RADIUS_METERS,
            description="Search radius in metres.",
        ),
    ] = DEFAULT_SEARCH_RADIUS_METERS,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAXIMUM_SEARCH_RESULTS,
            description="Maximum number of places.",
        ),
    ] = 6,
    sort: Annotated[
        str,
        Query(
            min_length=1,
            max_length=20,
            description=("RELEVANCE, RATING, DISTANCE, " "or POPULARITY."),
        ),
    ] = "RELEVANCE",
) -> dict[str, Any]:
    normalized_query = query.strip()

    places = await search_places(
        query=normalized_query,
        latitude=latitude,
        longitude=longitude,
        category_ids=category_ids,
        radius=radius,
        limit=limit,
        sort=sort,
    )

    return {
        "query": normalized_query,
        "count": len(places),
        "categoryIds": category_ids or [],
        "radiusMeters": radius,
        "sort": sort.strip().upper(),
        "places": places,
    }


@app.post("/routes/matrix", tags=["Routes"])
async def calculate_route_matrix(
    request: RouteMatrixRequest,
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> dict[str, Any]:
    locations = [
        (
            location.latitude,
            location.longitude,
        )
        for location in request.locations
    ]

    return await get_route_matrix(
        locations=locations,
        travel_mode=request.travel_mode,
    )


@app.post(
    "/recommendations/generate",
    tags=["Recommendations"],
)
async def create_recommendations(
    request: RecommendationRequest,
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> dict[str, Any]:
    return await generate_recommendations(
        request,
    )
