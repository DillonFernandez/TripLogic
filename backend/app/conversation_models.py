from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[^/]+$",
    ),
]

NonEmptyText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=4000,
    ),
]

ShortText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]

# The current recommendation pipeline can enrich at most 19 candidates
# because one of 20 ORS matrix locations is reserved for the route origin.
# This is not a Foursquare provider limit.
MAXIMUM_REQUESTED_RECOMMENDATIONS = 19

LocalTimeText = Annotated[
    str,
    StringConstraints(
        pattern=r"^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$",
    ),
]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )


class ConversationTurnOperation(str, Enum):
    SEND_MESSAGE = "sendMessage"
    EDIT_MESSAGE = "editMessage"


class TravelContextStage(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaitingConfirmation"
    CONFIRMED = "confirmed"
    RECOMMENDING = "recommending"
    AWAITING_SELECTION = "awaitingSelection"
    PLANNING = "planning"
    COMPLETED = "completed"


class TravelRequestKind(str, Enum):
    ATTRACTION = "attraction"
    HOTEL = "hotel"
    RESTAURANT = "restaurant"


class TravellerType(str, Enum):
    SOLO_TRAVELLER = "soloTraveller"
    COUPLE = "couple"
    FAMILY = "family"
    FRIENDS_GROUP = "friendsGroup"
    SENIOR_TRAVELLERS = "seniorTravellers"


class TravelLocationSource(str, Enum):
    CURRENT = "current"
    SEARCHED = "searched"
    FIXED_PLACE = "fixedPlace"
    UNKNOWN = "unknown"


class FixedTravelPlaceRole(str, Enum):
    DAILY_BASE = "dailyBase"
    REQUIRED_STOP = "requiredStop"
    START_POINT = "startPoint"
    END_POINT = "endPoint"
    OVERNIGHT_STOP = "overnightStop"


class ConversationMessageType(str, Enum):
    TEXT = "text"
    CONFIRMATION = "confirmation"
    RECOMMENDATION_GROUP = "recommendationGroup"
    ITINERARY = "itinerary"
    WARNING = "warning"
    ERROR = "error"
    LOADING = "loading"


class ConversationNextAction(str, Enum):
    ASK_QUESTION = "askQuestion"
    REQUEST_CONFIRMATION = "requestConfirmation"
    REQUEST_PLACE_SELECTION = "requestPlaceSelection"
    RESOLVE_ROUTE_WARNING = "resolveRouteWarning"
    ASK_MODIFY_OR_NEW_TRIP = "askModifyOrNewTrip"
    NONE = "none"


class ConversationDeviceLocation(CamelModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    captured_at: AwareDatetime
    accuracy_metres: float | None = Field(
        default=None,
        ge=0,
    )


class ConversationTurnRequest(CamelModel):
    request_id: Identifier
    operation: ConversationTurnOperation
    chat_id: Identifier
    traveller_message_id: Identifier
    turn_id: Identifier
    traveller_message_sequence: int = Field(ge=0)
    text: NonEmptyText
    client_created_at: AwareDatetime
    expected_context_revision: int = Field(ge=0)
    device_location: ConversationDeviceLocation | None = None


class TravelLocation(CamelModel):
    display_name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=150,
        ),
    ]

    locality_name: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=2,
                max_length=150,
            ),
        ]
        | None
    ) = None

    source: TravelLocationSource

    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    provider_place_id: Identifier | None = None
    country_code: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=2,
                max_length=2,
                to_upper=True,
            ),
        ]
        | None
    ) = None
    admin1: ShortText | None = None
    admin2: ShortText | None = None
    admin3: ShortText | None = None
    admin4: ShortText | None = None
    feature_code: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=20,
                to_upper=True,
            ),
        ]
        | None
    ) = None
    population: int | None = Field(
        default=None,
        ge=0,
    )
    verified: bool = False

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> TravelLocation:
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None

        if has_latitude != has_longitude:
            raise ValueError(
                "latitude and longitude must either both be "
                "provided or both be omitted"
            )

        if self.verified and not (has_latitude and has_longitude):
            raise ValueError(
                "a verified location must include latitude " "and longitude"
            )

        return self

    @property
    def is_route_ready(self) -> bool:
        return (
            self.verified and self.latitude is not None and self.longitude is not None
        )


class TravelRequestGroup(CamelModel):
    id: Identifier
    kind: TravelRequestKind

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=500,
        ),
    ]

    preferences: list[ShortText] = Field(
        default_factory=list,
        max_length=50,
    )

    cuisine_preferences: list[ShortText] = Field(
        default_factory=list,
        max_length=30,
    )

    dietary_requirements: list[ShortText] = Field(
        default_factory=list,
        max_length=30,
    )

    food_avoidances: list[ShortText] = Field(
        default_factory=list,
        max_length=30,
    )

    meal_intents: list[ShortText] = Field(
        default_factory=list,
        max_length=30,
    )

    requested_count: int | None = Field(
        default=None,
        ge=1,
        le=MAXIMUM_REQUESTED_RECOMMENDATIONS,
        strict=True,
    )

    search_location: TravelLocation | None = None

    required: bool = True

    selected_place_ids: list[Identifier] = Field(
        default_factory=list,
        max_length=50,
    )

    @field_validator(
        "preferences",
        "cuisine_preferences",
        "dietary_requirements",
        "food_avoidances",
        "meal_intents",
        "selected_place_ids",
    )
    @classmethod
    def normalize_unique_string_list(
        cls,
        values: list[str],
    ) -> list[str]:
        return _unique_strings(values)


class FixedTravelPlace(CamelModel):
    id: Identifier

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ]

    role: FixedTravelPlaceRole
    location: TravelLocation

    notes: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=500,
            ),
        ]
        | None
    ) = None

    confirmed: bool = True


class TravelContext(CamelModel):
    @model_validator(mode="before")
    @classmethod
    def ignore_obsolete_room_count(
        cls,
        data: Any,
    ) -> Any:
        """Ignore the removed room-count field in historical stored contexts."""

        if not isinstance(data, dict):
            return data

        cleaned_data = dict(data)
        cleaned_data.pop("roomCount", None)
        cleaned_data.pop("room_count", None)

        for missing_fields_key in ("missingFields", "missing_fields"):
            raw_missing_fields = cleaned_data.get(missing_fields_key)

            if not isinstance(raw_missing_fields, list):
                continue

            cleaned_data[missing_fields_key] = [
                value
                for value in raw_missing_fields
                if not (
                    isinstance(value, str)
                    and value.casefold()
                    .replace("_", "")
                    .replace("-", "")
                    .replace(" ", "")
                    == "roomcount"
                )
            ]

        return cleaned_data

    schema_version: int = Field(
        default=1,
        ge=1,
    )

    revision: int = Field(
        default=0,
        ge=0,
    )

    stage: TravelContextStage = TravelContextStage.COLLECTING

    starting_location: TravelLocation | None = None

    trip_start_date: date | None = None
    trip_end_date: date | None = None

    daily_start_time: LocalTimeText | None = None
    daily_end_time: LocalTimeText | None = None

    available_time_description: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=500,
            ),
        ]
        | None
    ) = None

    traveller_type: TravellerType | None = None

    travel_party_description: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=300,
            ),
        ]
        | None
    ) = None

    traveller_count: int | None = Field(
        default=None,
        ge=1,
        le=50,
    )

    travel_modes: list[ShortText] = Field(
        default_factory=list,
        max_length=10,
    )

    request_groups: list[TravelRequestGroup] = Field(
        default_factory=list,
        max_length=20,
    )

    preferences: list[ShortText] = Field(
        default_factory=list,
        max_length=100,
    )

    accessibility_needs: list[ShortText] = Field(
        default_factory=list,
        max_length=50,
    )

    avoidances: list[ShortText] = Field(
        default_factory=list,
        max_length=50,
    )

    fixed_places: list[FixedTravelPlace] = Field(
        default_factory=list,
        max_length=30,
    )

    selected_place_ids: list[Identifier] = Field(
        default_factory=list,
        max_length=100,
    )

    missing_fields: list[ShortText] = Field(
        default_factory=list,
        max_length=50,
    )

    uncertainties: list[ShortText] = Field(
        default_factory=list,
        max_length=50,
    )

    confirmation_summary: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=4000,
            ),
        ]
        | None
    ) = None

    is_confirmed: bool = False
    allow_overlong_route: bool = False
    requires_complete_itinerary: bool = False

    @field_validator(
        "travel_modes",
        "preferences",
        "accessibility_needs",
        "avoidances",
        "selected_place_ids",
        "missing_fields",
        "uncertainties",
    )
    @classmethod
    def normalize_unique_string_list(
        cls,
        values: list[str],
    ) -> list[str]:
        return _unique_strings(values)

    @model_validator(mode="after")
    def validate_context_consistency(
        self,
    ) -> TravelContext:
        if (
            self.trip_start_date is not None
            and self.trip_end_date is not None
            and self.trip_end_date < self.trip_start_date
        ):
            raise ValueError("tripEndDate cannot be before tripStartDate")

        _require_unique_ids(
            self.request_groups,
            "requestGroups",
        )

        _require_unique_ids(
            self.fixed_places,
            "fixedPlaces",
        )

        if self.is_confirmed and not self.is_ready_for_confirmation:
            raise ValueError(
                "a confirmed context must be complete, "
                "verified, and free of uncertainties"
            )

        return self

    @property
    def has_route_ready_daily_base(self) -> bool:
        return any(
            place.role is FixedTravelPlaceRole.DAILY_BASE
            and place.confirmed
            and place.location.is_route_ready
            for place in self.fixed_places
        )

    @property
    def has_route_ready_final_ending_location(self) -> bool:
        return any(
            place.role is FixedTravelPlaceRole.END_POINT
            and place.confirmed
            and place.location.is_route_ready
            for place in self.fixed_places
        )

    @property
    def has_route_ready_search_locations(self) -> bool:
        if not self.request_groups:
            return False

        has_fallback_search_location = (
            self.starting_location is not None
            and self.starting_location.is_route_ready
        ) or self.has_route_ready_daily_base

        return all(
            (
                group.search_location.is_route_ready
                if group.search_location is not None
                else has_fallback_search_location
            )
            for group in self.request_groups
        )

    @property
    def has_valid_trip_period(self) -> bool:
        return (
            self.trip_start_date is not None
            and self.trip_end_date is not None
            and self.trip_end_date >= self.trip_start_date
        )

    @property
    def requires_trip_period(self) -> bool:
        """Whether the current request needs dated visit or itinerary planning."""

        return (
            self.requires_complete_itinerary
            or not self.request_groups
        )

    @property
    def is_ready_for_confirmation(self) -> bool:
        if self.requires_complete_itinerary:
            location_roles_ready = (
                self.starting_location is not None
                and self.starting_location.is_route_ready
                and self.has_route_ready_final_ending_location
            )
        else:
            location_roles_ready = self.has_route_ready_search_locations

        trip_period_ready = (
            self.has_valid_trip_period
            if self.requires_trip_period
            else True
        )

        return (
            bool(self.request_groups)
            and location_roles_ready
            and trip_period_ready
            and not self.missing_fields
            and not self.uncertainties
        )


class AssistantConversationMessage(CamelModel):
    id: Identifier
    sequence: int = Field(ge=0)
    type: ConversationMessageType
    text: NonEmptyText
    created_at: AwareDatetime | None = None

    data: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def reject_client_only_message_types(
        self,
    ) -> AssistantConversationMessage:
        if self.type is ConversationMessageType.LOADING:
            raise ValueError("the backend cannot return a loading message")

        return self


class ConversationTurnResponse(CamelModel):
    request_id: Identifier
    chat_id: Identifier
    turn_id: Identifier

    accepted_traveller_message_id: Identifier

    context_revision: int = Field(ge=0)

    next_action: ConversationNextAction
    context: TravelContext

    assistant_messages: list[AssistantConversationMessage] = Field(
        min_length=1,
        max_length=50,
    )

    suggested_chat_title: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=100,
            ),
        ]
        | None
    ) = None

    created_at: AwareDatetime

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_response_consistency(
        self,
    ) -> ConversationTurnResponse:
        if self.context.revision != self.context_revision:
            raise ValueError("context.revision must match " "contextRevision")

        _require_unique_ids(
            self.assistant_messages,
            "assistantMessages",
        )

        sequences = [message.sequence for message in self.assistant_messages]

        if len(sequences) != len(set(sequences)):
            raise ValueError("assistantMessages must use unique " "sequence values")

        self.assistant_messages.sort(key=lambda message: message.sequence)

        return self


def _unique_strings(
    values: list[str],
) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.strip()
        comparison_value = normalized.casefold()

        if not normalized or comparison_value in seen:
            continue

        seen.add(comparison_value)
        unique_values.append(normalized)

    return unique_values


def _require_unique_ids(
    items: list[Any],
    field_name: str,
) -> None:
    identifiers = [item.id for item in items]

    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field_name} must use unique identifiers")
