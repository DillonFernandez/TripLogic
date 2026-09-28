from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    Field,
    StringConstraints,
    model_validator,
)

from app.conversation_models import (
    CamelModel,
    MAXIMUM_REQUESTED_RECOMMENDATIONS,
    TravelRequestKind,
    TravellerType,
)

PatchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=500,
    ),
]

ChatTitleText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=80,
    ),
]

AssistantReplyText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=1200,
    ),
]

LocalTimeText = Annotated[
    str,
    StringConstraints(
        pattern=r"^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$",
    ),
]


class ConversationInterpretationAction(str, Enum):
    CONTINUE_CURRENT_REQUEST = "continueCurrentRequest"
    START_NEW_TRIP = "startNewTrip"
    MODIFY_CURRENT_TRIP = "modifyCurrentTrip"
    CONFIRM_SUMMARY = "confirmSummary"
    CORRECT_INFORMATION = "correctInformation"
    SELECT_RECOMMENDATION = "selectRecommendation"
    REMOVE_RECOMMENDATION = "removeRecommendation"
    REPLACE_RECOMMENDATION = "replaceRecommendation"
    SHOW_MORE = "showMore"
    REJECT_RESULTS = "rejectResults"
    USE_CURRENT_LOCATION = "useCurrentLocation"
    SEARCH_LOCATION = "searchLocation"
    CONTINUE_DESPITE_ROUTE_WARNING = "continueDespiteRouteWarning"
    INCREASE_AVAILABLE_TIME = "increaseAvailableTime"
    REQUEST_ITINERARY = "requestItinerary"
    UNKNOWN = "unknown"


class ConversationResponseIntent(str, Enum):
    PROVIDE_TRIP_DETAILS = "provideTripDetails"
    REQUEST_ADVICE = "requestAdvice"
    ASK_TRAVEL_QUESTION = "askTravelQuestion"
    SOCIAL_CHAT = "socialChat"
    CONFIRM_OR_REJECT = "confirmOrReject"
    CORRECT_TRIP_DETAILS = "correctTripDetails"
    UNKNOWN = "unknown"


class PatchOperation(str, Enum):
    SET = "set"
    REPLACE = "replace"
    ADD = "add"
    REMOVE = "remove"
    CLEAR = "clear"


ScalarPatchOperation = Literal[
    PatchOperation.SET,
    PatchOperation.REPLACE,
    PatchOperation.CLEAR,
]

CollectionPatchOperation = Literal[
    PatchOperation.ADD,
    PatchOperation.REMOVE,
    PatchOperation.REPLACE,
    PatchOperation.CLEAR,
]


class ExtractedTravelMode(str, Enum):
    DRIVING = "driving"
    WALKING = "walking"
    CYCLING = "cycling"


class ExtractedLocationSource(str, Enum):
    CURRENT = "current"
    SEARCHED = "searched"


class RecommendationActionKind(str, Enum):
    SELECT = "select"
    REMOVE = "remove"
    REPLACE = "replace"
    SHOW_MORE = "showMore"
    REJECT = "reject"
    KEEP = "keep"


class TextFieldPatch(CamelModel):
    operation: ScalarPatchOperation
    value: PatchText | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> TextFieldPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("text fields support only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.value is not None:
                raise ValueError("clear operations cannot include a value")
        elif self.value is None:
            raise ValueError("set and replace operations require a value")

        return self


class IntegerFieldPatch(CamelModel):
    operation: ScalarPatchOperation
    value: int | None = Field(
        default=None,
        ge=1,
        le=50,
    )

    @model_validator(mode="after")
    def validate_patch(self) -> IntegerFieldPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("integer fields support only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.value is not None:
                raise ValueError("clear operations cannot include a value")
        elif self.value is None:
            raise ValueError("set and replace operations require a value")

        return self


class DateFieldPatch(CamelModel):
    operation: ScalarPatchOperation
    value: date | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> DateFieldPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("date fields support only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.value is not None:
                raise ValueError("clear operations cannot include a value")
        elif self.value is None:
            raise ValueError("set and replace operations require a value")

        return self


class TimeFieldPatch(CamelModel):
    operation: ScalarPatchOperation
    value: LocalTimeText | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> TimeFieldPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("time fields support only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.value is not None:
                raise ValueError("clear operations cannot include a value")
        elif self.value is None:
            raise ValueError("set and replace operations require a value")

        return self


class TravellerTypeFieldPatch(CamelModel):
    operation: ScalarPatchOperation
    value: TravellerType | None = None

    @model_validator(mode="after")
    def validate_patch(
        self,
    ) -> TravellerTypeFieldPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("traveller type supports only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.value is not None:
                raise ValueError("clear operations cannot include a value")
        elif self.value is None:
            raise ValueError("set and replace operations require a value")

        return self


class TextListPatch(CamelModel):
    operation: CollectionPatchOperation

    values: list[PatchText] = Field(
        default_factory=list,
        max_length=50,
    )

    @model_validator(mode="after")
    def validate_patch(self) -> TextListPatch:
        allowed_operations = {
            PatchOperation.ADD,
            PatchOperation.REMOVE,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("list fields support add, remove, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.values:
                raise ValueError("clear operations cannot include values")
        elif not self.values:
            raise ValueError("add, remove, and replace operations require values")

        return self


class TravelModeListPatch(CamelModel):
    operation: CollectionPatchOperation

    values: list[ExtractedTravelMode] = Field(
        default_factory=list,
        max_length=3,
    )

    @model_validator(mode="after")
    def validate_patch(self) -> TravelModeListPatch:
        allowed_operations = {
            PatchOperation.ADD,
            PatchOperation.REMOVE,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("travel modes support add, remove, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.values:
                raise ValueError("clear operations cannot include values")
        elif not self.values:
            raise ValueError("add, remove, and replace operations require values")

        return self


class StartingLocationPatch(CamelModel):
    operation: PatchOperation

    source: ExtractedLocationSource | None = None
    search_text: PatchText | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> StartingLocationPatch:
        allowed_operations = {
            PatchOperation.SET,
            PatchOperation.REPLACE,
            PatchOperation.CLEAR,
        }

        if self.operation not in allowed_operations:
            raise ValueError("starting location supports only set, replace, or clear")

        if self.operation is PatchOperation.CLEAR:
            if self.source is not None or self.search_text is not None:
                raise ValueError("clear operations cannot include location data")

            return self

        if self.source is None:
            raise ValueError("set and replace operations require a source")

        if self.source is ExtractedLocationSource.CURRENT:
            if self.search_text is not None:
                raise ValueError("current location cannot include search text")

        if self.source is ExtractedLocationSource.SEARCHED:
            if self.search_text is None:
                raise ValueError("searched locations require search text")

        return self


class ExtractedRequestGroup(CamelModel):
    kind: TravelRequestKind
    query: PatchText

    search_location_text: PatchText | None = Field(
        default=None,
        description=(
            "Traveller-supplied locality where this recommendation group "
            "should discover places. This is not the route origin."
        ),
    )

    preferences: list[PatchText] = Field(
        default_factory=list,
        max_length=30,
    )

    cuisine_preferences: list[PatchText] = Field(
        default_factory=list,
        max_length=30,
        description="Positive restaurant cuisine or food-style preferences.",
    )

    dietary_requirements: list[PatchText] = Field(
        default_factory=list,
        max_length=30,
        description="Restaurant dietary requirements kept separate from cuisine.",
    )

    food_avoidances: list[PatchText] = Field(
        default_factory=list,
        max_length=30,
        description="Restaurant foods or cuisines the traveller wants to avoid.",
    )

    meal_intents: list[PatchText] = Field(
        default_factory=list,
        max_length=30,
        description="Restaurant meal or dining intent such as breakfast or cafe.",
    )

    requested_count: int | None = Field(
        default=None,
        ge=1,
        le=MAXIMUM_REQUESTED_RECOMMENDATIONS,
        strict=True,
    )

    required: Literal[True] = True


class RequestGroupReference(CamelModel):
    kind: TravelRequestKind | None = None
    query: PatchText | None = None
    search_location_text: PatchText | None = Field(
        default=None,
        description=(
            "Optional traveller-supplied locality that identifies one "
            "request group when several groups have the same kind."
        ),
    )

    ordinal: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )

    @model_validator(mode="after")
    def require_reference(
        self,
    ) -> RequestGroupReference:
        if (
            self.kind is None
            and self.query is None
            and self.search_location_text is None
            and self.ordinal is None
        ):
            raise ValueError(
                "a request group reference requires a kind, query, "
                "search location, or ordinal"
            )

        return self


class RequestGroupsPatch(CamelModel):
    operation: CollectionPatchOperation

    groups: list[ExtractedRequestGroup] = Field(
        default_factory=list,
        max_length=20,
    )

    targets: list[RequestGroupReference] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_patch(self) -> RequestGroupsPatch:
        if self.operation is PatchOperation.CLEAR:
            if self.groups or self.targets:
                raise ValueError("clear operations cannot include groups or targets")

        elif self.operation is PatchOperation.ADD:
            if not self.groups or self.targets:
                raise ValueError("add operations require groups and no targets")

        elif self.operation is PatchOperation.REMOVE:
            if not self.targets or self.groups:
                raise ValueError("remove operations require targets and no groups")

        elif self.operation is PatchOperation.REPLACE:
            if not self.groups or not self.targets:
                raise ValueError("replace operations require groups and targets")

        else:
            raise ValueError("request groups support add, remove, replace, or clear")

        return self


class RecommendationGroupReference(CamelModel):
    kind: TravelRequestKind | None = None
    query: PatchText | None = None

    @model_validator(mode="after")
    def require_reference(
        self,
    ) -> RecommendationGroupReference:
        if self.kind is None and self.query is None:
            raise ValueError(
                "a recommendation group reference requires " "a kind or query"
            )

        return self


class ExtractedRecommendationAction(CamelModel):
    action: RecommendationActionKind

    group: RecommendationGroupReference | None = None

    selection_numbers: list[int] = Field(
        default_factory=list,
        max_length=20,
    )

    place_names: list[PatchText] = Field(
        default_factory=list,
        max_length=20,
    )

    requested_count: int | None = Field(
        default=None,
        ge=1,
        le=MAXIMUM_REQUESTED_RECOMMENDATIONS,
        strict=True,
    )

    replacement_preferences: list[PatchText] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_action(
        self,
    ) -> ExtractedRecommendationAction:
        selection_actions = {
            RecommendationActionKind.SELECT,
            RecommendationActionKind.REMOVE,
            RecommendationActionKind.KEEP,
        }

        if self.action in selection_actions:
            if not self.selection_numbers and not self.place_names:
                raise ValueError(
                    "selection actions require selection numbers " "or place names"
                )

        if self.action is RecommendationActionKind.SHOW_MORE:
            if self.group is None:
                raise ValueError("show-more actions require a recommendation group")

        if self.action is RecommendationActionKind.REPLACE:
            has_target = bool(
                self.selection_numbers or self.place_names or self.group is not None
            )

            if not has_target:
                raise ValueError("replace actions require a target")

        return self


class TravelContextPatch(CamelModel):
    starting_location: StartingLocationPatch | None = None
    final_ending_location: StartingLocationPatch | None = None

    trip_start_date: DateFieldPatch | None = None
    trip_end_date: DateFieldPatch | None = None

    daily_start_time: TimeFieldPatch | None = None
    daily_end_time: TimeFieldPatch | None = None

    available_time_description: TextFieldPatch | None = None

    traveller_type: TravellerTypeFieldPatch | None = None
    travel_party_description: TextFieldPatch | None = None
    traveller_count: IntegerFieldPatch | None = None

    travel_modes: TravelModeListPatch | None = None
    request_groups: RequestGroupsPatch | None = None

    preferences: TextListPatch | None = None
    accessibility_needs: TextListPatch | None = None
    avoidances: TextListPatch | None = None


class ConversationInterpretation(CamelModel):
    action: ConversationInterpretationAction

    response_intent: ConversationResponseIntent = ConversationResponseIntent.UNKNOWN

    context_patch: TravelContextPatch = Field(
        default_factory=TravelContextPatch,
    )

    recommendation_actions: list[ExtractedRecommendationAction] = Field(
        default_factory=list,
        max_length=20,
    )

    uncertainties: list[PatchText] = Field(
        default_factory=list,
        max_length=20,
    )

    requires_clarification: bool = False

    proposed_next_question: PatchText | None = None

    suggested_chat_title: ChatTitleText | None = None

    assistant_reply: AssistantReplyText | None = None

    suggested_travel_mode: ExtractedTravelMode | None = None

    requires_user_confirmation: bool = False

    @model_validator(mode="after")
    def validate_conversational_output(
        self,
    ) -> ConversationInterpretation:
        if self.suggested_chat_title is not None:
            title_word_count = len(self.suggested_chat_title.split())

            if not 3 <= title_word_count <= 5:
                raise ValueError("suggested chat title must contain 3 to 5 words")

        if self.suggested_travel_mode is not None and not self.assistant_reply:
            raise ValueError("a suggested travel mode requires an assistant reply")

        return self
