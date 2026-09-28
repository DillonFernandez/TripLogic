import re
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")
MAXIMUM_RECOMMENDATION_DAYS = 14
MAXIMUM_SELECTED_CATEGORIES = 3
MAXIMUM_CATEGORY_ID_LENGTH = 64

CATEGORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")

RecommendationType = Literal[
    "attraction",
    "hotel",
    "restaurant",
]

TravelMode = Literal[
    "driving",
    "walking",
    "cycling",
]

TravelPartner = Literal[
    "soloTraveller",
    "couple",
    "family",
    "friendsGroup",
    "seniorTravellers",
]

LocationSource = Literal[
    "current",
    "selected",
]


class RecommendationLocation(BaseModel):
    display_name: str = Field(
        alias="displayName",
        min_length=2,
        max_length=150,
        description=("Traveller-selected Sri Lankan location name."),
    )

    locality_name: str | None = Field(
        default=None,
        alias="localityName",
        min_length=2,
        max_length=150,
        description=("Verified canonical locality name used for place discovery."),
    )

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

    source: LocationSource = Field(
        description=("Whether the location came from GPS " "or manual selection."),
    )

    country_code: str | None = Field(
        default=None,
        alias="countryCode",
        min_length=2,
        max_length=2,
    )
    admin1: str | None = Field(default=None, max_length=200)
    admin2: str | None = Field(default=None, max_length=200)
    admin3: str | None = Field(default=None, max_length=200)
    admin4: str | None = Field(default=None, max_length=200)
    feature_code: str | None = Field(
        default=None,
        alias="featureCode",
        max_length=20,
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class RecommendationOpeningInterval(BaseModel):
    """One verified Foursquare regular-hours interval."""

    day: int = Field(
        ge=1,
        le=7,
        description="Provider weekday number where Monday is 1 and Sunday is 7.",
    )
    opening_time: str = Field(
        alias="openingTime",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    closing_time: str = Field(
        alias="closingTime",
        pattern=r"^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$",
    )
    overnight: bool = False
    all_day: bool = Field(
        default=False,
        alias="allDay",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


class RecommendationOpeningHours(BaseModel):
    """Verified provider hours without inferring future availability."""

    regular: tuple[RecommendationOpeningInterval, ...] = ()
    open_now: bool | None = Field(
        default=None,
        alias="openNow",
        description="Provider current-status value, not future opening proof.",
    )
    is_local_holiday: bool | None = Field(
        default=None,
        alias="isLocalHoliday",
    )
    display: str | None = Field(
        default=None,
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class RecommendationPlaceMetadata(BaseModel):
    """Optional Foursquare metadata exposed with a recommendation place."""

    rating: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Optional Foursquare rating on its native 0-to-10 scale.",
    )
    hours: RecommendationOpeningHours | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


class RecommendationCategory(BaseModel):
    id: str | None = Field(
        default=None,
        max_length=MAXIMUM_CATEGORY_ID_LENGTH,
        description=(
            "Legacy optional Foursquare category identifier. "
            "Backend provider filters are preferred."
        ),
    )

    name: str = Field(
        min_length=2,
        max_length=100,
        description="Traveller-facing category name.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @field_validator("id")
    @classmethod
    def validate_category_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip()

        if not normalized_value:
            return None

        if CATEGORY_ID_PATTERN.fullmatch(normalized_value) is None:
            raise ValueError("Category IDs must contain letters or numbers only.")

        return normalized_value


class FoursquareProviderFilter(BaseModel):
    """Backend-only query and verified Foursquare category group."""

    query: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        description=(
            "Optional human-readable text sent to Foursquare Place Search."
        ),
    )

    category_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        alias="categoryIds",
        description="Verified backend-owned Foursquare category identifiers.",
    )

    provenance_key: str | None = Field(
        default=None,
        alias="provenanceKey",
        min_length=1,
        max_length=100,
        description="Backend key identifying the group that produced a match.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        normalized_value = " ".join(value.split())

        return normalized_value or None

    @field_validator("category_ids")
    @classmethod
    def validate_category_ids(
        cls,
        category_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized_category_ids: list[str] = []

        for raw_category_id in category_ids:
            category_id = raw_category_id.strip()

            if (
                not category_id
                or len(category_id) > MAXIMUM_CATEGORY_ID_LENGTH
                or CATEGORY_ID_PATTERN.fullmatch(category_id) is None
            ):
                raise ValueError(
                    "Provider category IDs must contain letters or numbers only."
                )

            if category_id not in normalized_category_ids:
                normalized_category_ids.append(category_id)

        return tuple(normalized_category_ids)

    @model_validator(mode="after")
    def validate_provider_constraint(
        self,
    ) -> "FoursquareProviderFilter":
        if self.query is None and not self.category_ids:
            raise ValueError(
                "A provider query or at least one category ID is required."
            )

        return self


class RecommendationRequest(BaseModel):
    _provider_filters: tuple[FoursquareProviderFilter, ...] = PrivateAttr(
        default=(),
    )
    _route_origin: RecommendationLocation | None = PrivateAttr(
        default=None,
    )
    _route_origin_attached: bool = PrivateAttr(default=False)
    _restaurant_cuisine_preferences: tuple[str, ...] = PrivateAttr(default=())
    _restaurant_dietary_requirements: tuple[str, ...] = PrivateAttr(default=())
    _restaurant_food_avoidances: tuple[str, ...] = PrivateAttr(default=())
    _restaurant_meal_intents: tuple[str, ...] = PrivateAttr(default=())

    recommendation_type: RecommendationType = Field(
        alias="recommendationType",
        description=("Attraction, hotel, or restaurant."),
    )

    location: RecommendationLocation

    travel_mode: TravelMode | None = Field(
        default=None,
        alias="travelMode",
        description=("Transport mode used for route calculations."),
    )

    travel_partner: TravelPartner | None = Field(
        default=None,
        alias="travelPartner",
        description=("Who the traveller is travelling with."),
    )

    categories: list[RecommendationCategory] = Field(
        min_length=1,
        max_length=MAXIMUM_SELECTED_CATEGORIES,
        description=("One to three selected place categories."),
    )

    visit_date: date | None = Field(
        default=None,
        alias="visitDate",
        description=(
            "Required for attractions and optional restaurant planning metadata."
        ),
    )

    start_time: time | None = Field(
        default=None,
        alias="startTime",
        description=("Planned local start time for the visit."),
    )

    visit_duration_minutes: int | None = Field(
        default=None,
        alias="visitDurationMinutes",
        ge=30,
        le=720,
        description=(
            "Optional explicit duration for one planned place visit. "
            "A trip's daily available window is a separate concept."
        ),
    )

    check_in_date: date | None = Field(
        default=None,
        alias="checkInDate",
        description="Optional hotel-stay planning metadata.",
    )

    check_out_date: date | None = Field(
        default=None,
        alias="checkOutDate",
        description="Optional hotel-stay planning metadata.",
    )

    travellers: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional number of hotel guests for later planning.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        categories: list[RecommendationCategory],
    ) -> list[RecommendationCategory]:
        category_keys: set[str] = set()
        unique_categories: list[RecommendationCategory] = []

        for category in categories:
            category_key = (
                f"id:{category.id}"
                if category.id is not None
                else f"name:{category.name.casefold()}"
            )

            if category_key in category_keys:
                continue

            category_keys.add(category_key)

            unique_categories.append(category)

        if not unique_categories:
            raise ValueError("Select at least one category.")

        if len(unique_categories) > MAXIMUM_SELECTED_CATEGORIES:
            raise ValueError("A maximum of three categories " "can be selected.")

        return unique_categories

    @field_validator("start_time")
    @classmethod
    def validate_start_time(
        cls,
        value: time | None,
    ) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError(
                "startTime must be a local time " "without a timezone offset."
            )

        return value

    @staticmethod
    def _validate_supported_date(
        selected_date: date,
        *,
        field_name: str,
    ) -> None:
        today = datetime.now(
            SRI_LANKA_TIMEZONE,
        ).date()

        final_allowed_date = today + timedelta(
            days=MAXIMUM_RECOMMENDATION_DAYS - 1,
        )

        if selected_date < today:
            raise ValueError(f"{field_name} cannot be in the past.")

        if selected_date > final_allowed_date:
            raise ValueError(
                f"{field_name} must be within the "
                f"next {MAXIMUM_RECOMMENDATION_DAYS} days."
            )

    @staticmethod
    def _validate_future_visit_time(
        visit_date: date,
        start_time: time,
    ) -> None:
        current_datetime = datetime.now(
            SRI_LANKA_TIMEZONE,
        )

        if visit_date != current_datetime.date():
            return

        visit_datetime = datetime.combine(
            visit_date,
            start_time,
            tzinfo=SRI_LANKA_TIMEZONE,
        )

        if visit_datetime <= current_datetime:
            raise ValueError(
                "startTime must be in the future " "when visitDate is today."
            )

    @model_validator(mode="after")
    def validate_request_type(
        self,
    ) -> "RecommendationRequest":
        if self.recommendation_type == "attraction":
            if self.visit_date is not None:
                self._validate_supported_date(
                    self.visit_date,
                    field_name="visitDate",
                )

            if self.visit_date is not None and self.start_time is not None:
                self._validate_future_visit_time(
                    self.visit_date,
                    self.start_time,
                )

            if (
                self.check_in_date is not None
                or self.check_out_date is not None
                or self.travellers is not None
            ):
                raise ValueError(
                    "Hotel-only fields cannot be used "
                    "for attraction or restaurant requests."
                )

            return self

        if self.recommendation_type == "restaurant":
            if self.visit_date is not None:
                self._validate_supported_date(
                    self.visit_date,
                    field_name="visitDate",
                )

            if self.visit_date is not None and self.start_time is not None:
                self._validate_future_visit_time(
                    self.visit_date,
                    self.start_time,
                )

            if (
                self.check_in_date is not None
                or self.check_out_date is not None
                or self.travellers is not None
            ):
                raise ValueError(
                    "Hotel-only fields cannot be used for restaurant requests."
                )

            return self

        if self.check_in_date is not None:
            self._validate_supported_date(
                self.check_in_date,
                field_name="checkInDate",
            )

        if self.check_out_date is not None:
            self._validate_supported_date(
                self.check_out_date,
                field_name="checkOutDate",
            )

        if (
            self.check_in_date is not None
            and self.check_out_date is not None
            and self.check_out_date < self.check_in_date
        ):
            raise ValueError("checkOutDate cannot be before checkInDate.")

        if (
            self.visit_date is not None
            or self.start_time is not None
            or self.visit_duration_minutes is not None
        ):
            raise ValueError("Visit-time fields cannot be used " "for hotel requests.")

        return self

    @property
    def category_ids(
        self,
    ) -> list[str]:
        return [category.id for category in self.categories if category.id is not None]

    @property
    def category_names(
        self,
    ) -> list[str]:
        return [category.name for category in self.categories]

    @property
    def provider_filters(
        self,
    ) -> tuple[FoursquareProviderFilter, ...]:
        """Return backend-owned filters excluded from request serialization."""

        return self._provider_filters

    def attach_provider_filters(
        self,
        provider_filters: list[FoursquareProviderFilter]
        | tuple[FoursquareProviderFilter, ...],
    ) -> None:
        """Attach trusted backend filters after public request validation."""

        self._provider_filters = tuple(provider_filters)

    @property
    def route_origin(
        self,
    ) -> RecommendationLocation | None:
        """Return the trusted route origin, separate from place discovery."""

        if self._route_origin_attached:
            return self._route_origin

        # Preserve the legacy direct RecommendationRequest contract. The
        # conversation adapter always attaches an explicit origin or None.
        return self.location

    def attach_route_origin(
        self,
        route_origin: RecommendationLocation | None,
    ) -> None:
        """Attach a backend-owned route origin after public validation."""

        self._route_origin = route_origin
        self._route_origin_attached = True

    def attach_restaurant_preferences(
        self,
        *,
        cuisine_preferences: list[str] | tuple[str, ...] = (),
        dietary_requirements: list[str] | tuple[str, ...] = (),
        food_avoidances: list[str] | tuple[str, ...] = (),
        meal_intents: list[str] | tuple[str, ...] = (),
    ) -> None:
        """Attach structured traveller semantics outside the public payload."""

        self._restaurant_cuisine_preferences = tuple(cuisine_preferences)
        self._restaurant_dietary_requirements = tuple(dietary_requirements)
        self._restaurant_food_avoidances = tuple(food_avoidances)
        self._restaurant_meal_intents = tuple(meal_intents)

    @property
    def restaurant_cuisine_preferences(self) -> tuple[str, ...]:
        return self._restaurant_cuisine_preferences

    @property
    def restaurant_dietary_requirements(self) -> tuple[str, ...]:
        return self._restaurant_dietary_requirements

    @property
    def restaurant_food_avoidances(self) -> tuple[str, ...]:
        return self._restaurant_food_avoidances

    @property
    def restaurant_meal_intents(self) -> tuple[str, ...]:
        return self._restaurant_meal_intents

    @property
    def stay_duration_days(
        self,
    ) -> int | None:
        if self.check_in_date is None or self.check_out_date is None:
            return None

        return (self.check_out_date - self.check_in_date).days
