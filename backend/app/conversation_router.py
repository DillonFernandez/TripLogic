import re
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.auth import get_current_user
from app.conversation_context_patcher import (
    apply_conversation_interpretation,
)
from app.conversation_preference_rules import (
    apply_no_specific_preference_reply,
)
from app.conversation_confirmation_builder import (
    build_confirmation_summary,
)
from app.conversation_confirmation_handler import (
    confirm_travel_context,
)
from app.conversation_recommendation_adapter import (
    ConversationRecommendationAdapterError,
)
from app.conversation_recommendation_runner import (
    generate_conversation_recommendations,
)
from app.conversation_context_requirements import (
    refresh_missing_fields,
)
from app.conversation_extraction_models import (
    ConversationInterpretation,
    ConversationInterpretationAction,
)
from app.conversation_interpreter import (
    ConversationInterpreterOutputError,
    ConversationInterpreterTimeoutError,
    ConversationInterpreterUnavailableError,
    get_conversation_interpreter,
)
from app.conversation_itinerary_builder import (
    ConversationItineraryBuilderError,
    build_conversation_itinerary,
)
from app.conversation_location_verifier import (
    LocationResolution,
    LocationResolutionStatus,
    resolve_sri_lankan_location,
)
from app.conversation_models import (
    AssistantConversationMessage,
    ConversationMessageType,
    ConversationNextAction,
    ConversationTurnOperation,
    ConversationTurnRequest,
    ConversationTurnResponse,
    FixedTravelPlaceRole,
    MAXIMUM_REQUESTED_RECOMMENDATIONS,
    TravelContext,
    TravelContextStage,
    TravelLocationSource,
)
from app.conversation_question_builder import (
    build_next_question,
)
from app.conversation_store import (
    get_processed_response,
    load_conversation_state,
    persist_conversation_response,
    validate_traveller_message,
)

router = APIRouter(
    prefix="/conversation",
    tags=["Conversation"],
)


@dataclass(frozen=True, slots=True)
class PendingLocationVerification:
    role: str
    query: str
    resolution: LocationResolution
    request_kind: str | None = None


async def _verify_context_locations(
    context: TravelContext,
) -> tuple[TravelContext, PendingLocationVerification | None]:
    """Verify each semantic location role without substituting another role."""

    context_data = context.model_dump(mode="python")
    resolution_cache: dict[str, LocationResolution] = {}
    first_pending: PendingLocationVerification | None = None

    async def resolve(
        *,
        role: str,
        query: str,
        request_kind: str | None = None,
    ) -> LocationResolution:
        nonlocal first_pending

        cache_key = " ".join(query.casefold().split())

        if cache_key not in resolution_cache:
            resolution_cache[cache_key] = await resolve_sri_lankan_location(query)

        resolution = resolution_cache[cache_key]

        if (
            first_pending is None
            and resolution.status is not LocationResolutionStatus.VERIFIED
        ):
            first_pending = PendingLocationVerification(
                role=role,
                query=query,
                resolution=resolution,
                request_kind=request_kind,
            )

        return resolution

    starting_location = context.starting_location

    if (
        starting_location is not None
        and starting_location.source is TravelLocationSource.SEARCHED
        and not starting_location.is_route_ready
    ):
        resolution = await resolve(
            role="routeOrigin",
            query=starting_location.display_name,
        )

        if resolution.is_verified and resolution.location is not None:
            context_data["starting_location"] = resolution.location.model_dump(
                mode="python"
            )

    for place_index, place in enumerate(context.fixed_places):
        if (
            place.role is not FixedTravelPlaceRole.END_POINT
            or place.location.source is not TravelLocationSource.SEARCHED
            or place.location.is_route_ready
        ):
            continue

        resolution = await resolve(
            role="finalEndingLocation",
            query=place.location.display_name,
        )

        if resolution.is_verified and resolution.location is not None:
            verified_place = place.model_copy(
                update={
                    "name": resolution.location.display_name,
                    "location": resolution.location,
                }
            )
            context_data["fixed_places"][place_index] = verified_place.model_dump(
                mode="python"
            )

    for group_index, group in enumerate(context.request_groups):
        search_location = group.search_location

        if (
            search_location is None
            or search_location.source is not TravelLocationSource.SEARCHED
            or search_location.is_route_ready
        ):
            continue

        resolution = await resolve(
            role="searchLocation",
            query=search_location.display_name,
            request_kind=group.kind.value,
        )

        if resolution.is_verified and resolution.location is not None:
            verified_group = group.model_copy(
                update={"search_location": resolution.location}
            )
            context_data["request_groups"][group_index] = (
                verified_group.model_dump(mode="python")
            )

    return (
        refresh_missing_fields(TravelContext.model_validate(context_data)),
        first_pending,
    )


def _location_clarification_message(
    pending: PendingLocationVerification,
) -> str:
    candidate_text = ", ".join(pending.resolution.candidates[:5])

    if pending.role == "searchLocation":
        subject = (
            f"the {pending.request_kind} search"
            if pending.request_kind is not None
            else "the place search"
        )
        question = f"Which Sri Lankan location should I use for {subject}?"
    elif pending.role == "finalEndingLocation":
        question = "Which Sri Lankan location must the complete trip end at?"
    else:
        question = "Which Sri Lankan location should the trip start from?"

    return f"{question} {candidate_text}" if candidate_text else question


def _has_unverified_context_location(
    context: TravelContext,
) -> bool:
    if (
        context.starting_location is not None
        and not context.starting_location.is_route_ready
    ):
        return True

    if any(
        group.search_location is not None
        and not group.search_location.is_route_ready
        for group in context.request_groups
    ):
        return True

    return any(
        place.role is FixedTravelPlaceRole.END_POINT
        and not place.location.is_route_ready
        for place in context.fixed_places
    )


def _assistant_reply_contains_question(
    text: str,
) -> bool:
    return "?" in text.strip()


def _is_simple_confirmation(text: str) -> bool:
    normalized = text.casefold().replace("’", "'")
    normalized = normalized.replace("—", " ").replace("–", " ").replace("-", " ")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return False

    polite_suffix = r"(?:\s+(?:please|pls|thanks|thank you|thx))*"
    confirmation_patterns = (
        rf"(?:yes|yes correct|correct|confirm|i confirm|confirmed|okay|ok|proceed){polite_suffix}",
        rf"(?:yes\s+)?(?:go ahead|looks good|sounds good|thats correct|that is correct|do it|give it(?:\s+to me)?){polite_suffix}",
        rf"(?:(?:yes|okay|ok)\s+)?go ahead(?:\s+and\s+(?:give|show|send)\s+(?:it|them)(?:\s+to\s+me)?(?:\s+so)?)?{polite_suffix}",
    )

    return any(
        re.fullmatch(pattern, normalized) is not None
        for pattern in confirmation_patterns
    )


def _confirmation_fact_snapshot(
    context: TravelContext,
) -> dict[str, Any]:
    """Return only traveller facts relevant to confirmation review."""

    snapshot = context.model_dump(
        mode="json",
    )

    for state_field in (
        "revision",
        "stage",
        "missing_fields",
        "confirmation_summary",
        "is_confirmed",
        "allow_overlong_route",
    ):
        snapshot.pop(state_field, None)

    return snapshot


def _apply_conversation_punctuation_style(
    text: str,
) -> str:
    time_colon_token = "\ue000"

    styled = re.sub(
        r"(?<=\d):(?=\d)",
        time_colon_token,
        text,
    )

    styled = styled.replace("—", " ")
    styled = styled.replace("–", " ")
    styled = styled.replace("-", " ")
    styled = styled.replace(";", ",")
    styled = styled.replace(":", " ")

    styled = styled.replace(
        time_colon_token,
        ":",
    )

    styled = re.sub(
        r"[ \t]{2,}",
        " ",
        styled,
    )

    styled = re.sub(
        r" *\n *",
        "\n",
        styled,
    )

    return styled.strip()


def _uncertainty_clarification_message(uncertainty: str) -> str:
    normalized = " ".join(uncertainty.casefold().split())
    requested_numbers = [
        int(value)
        for value in re.findall(r"\b\d+\b", normalized)
    ]
    count_uncertainty = (
        "requestedcount" in normalized
        or "requested count" in normalized
        or ("request" in normalized and "capacity" in normalized)
    )

    over_capacity = any(
        value > MAXIMUM_REQUESTED_RECOMMENDATIONS
        for value in requested_numbers
    ) or (
        any(
            marker in normalized
            for marker in ("greater than", "exceeds", "above", "over")
        )
        and MAXIMUM_REQUESTED_RECOMMENDATIONS in requested_numbers
    )

    if count_uncertainty and over_capacity:
        return (
            "Trip Logic can currently return up to "
            f"{MAXIMUM_REQUESTED_RECOMMENDATIONS} verified recommendations "
            "for this request. Would you like me to use "
            f"{MAXIMUM_REQUESTED_RECOMMENDATIONS}?"
        )

    return f"Could you clarify this detail? {uncertainty}"


def _first_name_from_user(
    current_user: dict[str, Any],
) -> str | None:
    raw_name = (
        current_user.get("name")
        or current_user.get("displayName")
        or current_user.get("display_name")
    )

    if not isinstance(raw_name, str):
        return None

    normalized_name = " ".join(raw_name.strip().split())

    if not normalized_name:
        return None

    return normalized_name.split(" ", 1)[0]


def _address_traveller(
    text: str,
    first_name: str | None,
) -> str:
    if first_name is None:
        return text

    normalized_name = first_name.strip()

    if not normalized_name:
        return text

    if normalized_name.casefold() in text.casefold():
        return text

    return f"{normalized_name}, {text}"


@router.post(
    "/turn",
    response_model=ConversationTurnResponse,
    response_model_by_alias=True,
)
async def process_conversation_turn(
    request: ConversationTurnRequest,
    current_user: Annotated[
        dict[str, Any],
        Depends(get_current_user),
    ],
) -> ConversationTurnResponse:
    """
    Interpret, validate, update, and persist one conversation turn.

    OpenAI interprets natural language into a restricted schema.
    Deterministic backend logic applies the context patch, calculates
    missing fields, chooses the next question, and persists the trusted
    result.
    """

    request_started_at = perf_counter()

    load_state_seconds = 0.0
    interpret_seconds = 0.0
    recommendation_seconds = 0.0
    itinerary_seconds = 0.0

    uid = current_user["uid"]
    traveller_first_name = _first_name_from_user(current_user)

    stored_response = get_processed_response(
        uid=uid,
        request=request,
    )

    if stored_response is not None:
        return stored_response

    if request.operation is ConversationTurnOperation.EDIT_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Message editing is not connected yet. "
                "No conversation data was changed."
            ),
        )

    load_state_started_at = perf_counter()

    state = load_conversation_state(
        uid=uid,
        request=request,
    )

    load_state_seconds = perf_counter() - load_state_started_at

    validate_traveller_message(
        state=state,
        request=request,
    )

    confirmation_fast_path = (
        state.context.stage is TravelContextStage.AWAITING_CONFIRMATION
        and _is_simple_confirmation(request.text)
    )
    confirmation_review_fast_path = (
        state.context.stage is not TravelContextStage.AWAITING_CONFIRMATION
        and not state.context.is_confirmed
        and state.context.is_ready_for_confirmation
        and _is_simple_confirmation(request.text)
    )

    interpreter = get_conversation_interpreter()

    interpret_started_at = perf_counter()

    try:
        if confirmation_fast_path:
            interpretation = ConversationInterpretation(
                action=ConversationInterpretationAction.CONFIRM_SUMMARY,
            )
        elif confirmation_review_fast_path:
            # Q5 requires the complete summary to be shown before a clean
            # acceptance can dispatch any external recommendation work.
            interpretation = ConversationInterpretation(
                action=(
                    ConversationInterpretationAction.CONTINUE_CURRENT_REQUEST
                ),
            )
        else:
            interpretation = await interpreter.interpret(
                traveller_message=request.text,
                current_context=state.context,
                recent_messages=state.recent_messages,
                traveller_name=traveller_first_name,
            )

        interpret_seconds = perf_counter() - interpret_started_at
    except ConversationInterpreterTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Trip Logic could not interpret the message "
                "before the request timed out. Please try again."
            ),
        ) from error
    except ConversationInterpreterUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Trip Logic language understanding is temporarily "
                "unavailable. Please try again."
            ),
        ) from error
    except ConversationInterpreterOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Trip Logic received an invalid language "
                "interpretation. No conversation data was changed."
            ),
        ) from error

    try:
        patched_context = apply_conversation_interpretation(
            current_context=state.context,
            interpretation=interpretation,
            traveller_message=request.text,
            device_location=request.device_location,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The interpreted travel information could not " "be applied safely."
            ),
        ) from error

    patched_context, pending_location = await _verify_context_locations(
        patched_context
    )

    patched_context = apply_no_specific_preference_reply(
        patched_context,
        request.text,
    )

    confirmation_facts_changed = (
        state.context.stage is TravelContextStage.AWAITING_CONFIRMATION
        and _confirmation_fact_snapshot(state.context)
        != _confirmation_fact_snapshot(patched_context)
    )

    if (
        state.context.stage is TravelContextStage.AWAITING_CONFIRMATION
        and not confirmation_facts_changed
        and patched_context.stage is not TravelContextStage.AWAITING_CONFIRMATION
    ):
        # A redundant extraction patch must not lose the authoritative
        # confirmation state when no traveller fact actually changed.
        restored_context_data = patched_context.model_dump(mode="python")
        restored_context_data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        restored_context_data["is_confirmed"] = False
        restored_context_data["confirmation_summary"] = (
            state.context.confirmation_summary
        )
        patched_context = TravelContext.model_validate(restored_context_data)

    created_at = datetime.now(timezone.utc)
    next_context_revision = state.context_revision + 1

    context_data = patched_context.model_dump(
        mode="python",
    )
    context_data["revision"] = next_context_revision

    updated_context = TravelContext.model_validate(context_data)

    next_question = build_next_question(updated_context)

    confirmation_accepted = False
    recommendation_groups: list[dict[str, Any]] = []
    external_apis_called = False

    itinerary_text: str | None = None
    itinerary_data: dict[str, Any] | None = None

    stored_chat_title = state.chat_data.get("title")

    normalized_stored_title = (
        stored_chat_title.strip() if isinstance(stored_chat_title, str) else ""
    )

    temporary_chat_title = (
        not normalized_stored_title
        or normalized_stored_title.lower()
        in {
            "new chat",
            "new trip",
        }
        or normalized_stored_title.lower().startswith("new chat ")
    )

    suggested_chat_title = (
        interpretation.suggested_chat_title if temporary_chat_title else None
    )

    if (
        interpretation.action is ConversationInterpretationAction.REQUEST_ITINERARY
        and updated_context.is_ready_for_confirmation
        and not confirmation_facts_changed
    ):
        # An explicit itinerary request is enough confirmation to proceed
        # once every required trip detail has already been collected.
        if not updated_context.is_confirmed:
            try:
                confirmation_summary = build_confirmation_summary(updated_context)

                context_data = updated_context.model_dump(
                    mode="python",
                )
                context_data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
                context_data["confirmation_summary"] = confirmation_summary

                updated_context = TravelContext.model_validate(context_data)

                updated_context = confirm_travel_context(updated_context)

            except ValueError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "The trip details are not complete enough "
                        "to build an itinerary."
                    ),
                ) from error

        try:
            recommendation_started_at = perf_counter()

            itinerary_source_groups = await generate_conversation_recommendations(
                updated_context,
                include_internal_route_matrix=(
                    updated_context.requires_complete_itinerary
                ),
            )

            recommendation_seconds += perf_counter() - recommendation_started_at

            itinerary_started_at = perf_counter()

            if updated_context.requires_complete_itinerary:
                itinerary_text, itinerary_data = await build_conversation_itinerary(
                    context=updated_context,
                    recommendation_groups=itinerary_source_groups,
                )

                itinerary_seconds += perf_counter() - itinerary_started_at

                for group in itinerary_source_groups:
                    result = group.get("result")

                    if isinstance(result, dict):
                        result.pop("_internalRouteMatrix", None)

        except ConversationRecommendationAdapterError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "The trip details could not be converted "
                    "into itinerary recommendations."
                ),
            ) from error

        except ConversationItineraryBuilderError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

        external_apis_called = True
        recommendation_groups = itinerary_source_groups

    elif (
        interpretation.action is ConversationInterpretationAction.CONFIRM_SUMMARY
        and not confirmation_facts_changed
    ):
        try:
            updated_context = confirm_travel_context(updated_context)
        except ValueError as error:
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
                detail=(
                    "The trip details cannot be confirmed "
                    "at the current conversation stage."
                ),
            ) from error

        try:
            recommendation_started_at = perf_counter()

            itinerary_source_groups = await generate_conversation_recommendations(
                updated_context,
                include_internal_route_matrix=(
                    updated_context.requires_complete_itinerary
                ),
            )

            recommendation_seconds += perf_counter() - recommendation_started_at

            itinerary_started_at = perf_counter()

            if updated_context.requires_complete_itinerary:
                itinerary_text, itinerary_data = await build_conversation_itinerary(
                    context=updated_context,
                    recommendation_groups=itinerary_source_groups,
                )

                itinerary_seconds += perf_counter() - itinerary_started_at

                for group in itinerary_source_groups:
                    result = group.get("result")

                    if isinstance(result, dict):
                        result.pop("_internalRouteMatrix", None)
        except ConversationRecommendationAdapterError as error:
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
                detail=(
                    "The confirmed trip details could not "
                    "be converted into recommendation "
                    "requests."
                ),
            ) from error
        except ConversationItineraryBuilderError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

        external_apis_called = True
        confirmation_accepted = True
        recommendation_groups = itinerary_source_groups

    if itinerary_text is not None:
        assistant_text = itinerary_text
        message_type = ConversationMessageType.ITINERARY
        next_action = ConversationNextAction.NONE

    elif confirmation_accepted:
        assistant_text = (
            "Your trip details are confirmed. " "Your recommendations are ready."
        )
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.NONE

    elif (
        pending_location is not None
        and pending_location.resolution.status
        is LocationResolutionStatus.AMBIGUOUS
    ):
        assistant_text = _location_clarification_message(pending_location)
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.ASK_QUESTION

    elif (
        pending_location is not None
        and pending_location.resolution.status
        is LocationResolutionStatus.NOT_FOUND
    ):
        assistant_text = (
            f"I could not verify {pending_location.query} as a "
            "Sri Lankan location. Which Sri Lankan city "
            "or region should I use?"
        )
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.ASK_QUESTION

    elif updated_context.uncertainties:
        assistant_text = _uncertainty_clarification_message(
            updated_context.uncertainties[0]
        )
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.ASK_QUESTION

    elif (
        confirmation_facts_changed
        and updated_context.is_ready_for_confirmation
    ):
        confirmation_summary = build_confirmation_summary(updated_context)

        context_data = updated_context.model_dump(
            mode="python",
        )
        context_data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        context_data["is_confirmed"] = False
        context_data["confirmation_summary"] = confirmation_summary

        updated_context = TravelContext.model_validate(context_data)

        assistant_text = confirmation_summary
        message_type = ConversationMessageType.CONFIRMATION
        next_action = ConversationNextAction.REQUEST_CONFIRMATION

    elif confirmation_facts_changed and next_question is not None:
        assistant_text = next_question
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.ASK_QUESTION

    elif (
        updated_context.is_ready_for_confirmation
        and next_question is None
        and not updated_context.is_confirmed
    ):
        # The deterministic backend owns required-information decisions.
        # Once a request is complete and there is no canonical next question,
        # an optional GPT question must not delay the required Q5 summary.
        confirmation_summary = build_confirmation_summary(updated_context)

        context_data = updated_context.model_dump(
            mode="python",
        )
        context_data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        context_data["confirmation_summary"] = confirmation_summary

        updated_context = TravelContext.model_validate(context_data)

        assistant_text = confirmation_summary
        message_type = ConversationMessageType.CONFIRMATION
        next_action = ConversationNextAction.REQUEST_CONFIRMATION

    elif next_question is not None:
        # The backend owns which fact is relevant next. A fluent GPT reply
        # must not replace that deterministic question with an unrelated one.
        assistant_text = next_question
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.ASK_QUESTION

    elif interpretation.assistant_reply is not None:
        assistant_text = interpretation.assistant_reply
        message_type = ConversationMessageType.TEXT
        next_action = (
            ConversationNextAction.ASK_QUESTION
            if interpretation.requires_user_confirmation
            else ConversationNextAction.NONE
        )

    elif (
        updated_context.is_ready_for_confirmation
        and not updated_context.is_confirmed
    ):
        confirmation_summary = build_confirmation_summary(updated_context)

        context_data = updated_context.model_dump(
            mode="python",
        )
        context_data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
        context_data["confirmation_summary"] = confirmation_summary

        updated_context = TravelContext.model_validate(context_data)

        assistant_text = confirmation_summary
        message_type = ConversationMessageType.CONFIRMATION
        next_action = ConversationNextAction.REQUEST_CONFIRMATION

    else:
        assistant_text = (
            "I understood your trip details, but I still need "
            "one required detail before preparing the "
            "confirmation summary."
        )
        message_type = ConversationMessageType.TEXT
        next_action = ConversationNextAction.NONE

    location_verification_pending = _has_unverified_context_location(
        updated_context
    )

    if message_type is not ConversationMessageType.CONFIRMATION:
        assistant_text = _apply_conversation_punctuation_style(assistant_text)

    assistant_message = AssistantConversationMessage(
        id=f"assistant_{uuid4().hex}",
        sequence=request.traveller_message_sequence + 1,
        type=message_type,
        text=assistant_text,
        created_at=created_at,
        data={
            "openAiConnected": True,
            "structuredInterpretation": True,
            "interpretationAction": interpretation.action.value,
            "responseIntent": interpretation.response_intent.value,
            "suggestedTravelMode": (
                interpretation.suggested_travel_mode.value
                if interpretation.suggested_travel_mode is not None
                else None
            ),
            "requiresUserConfirmation": (interpretation.requires_user_confirmation),
            "trustedContextPatched": True,
            "requiresClarification": interpretation.requires_clarification,
            "locationVerificationPending": location_verification_pending,
            "externalApisCalled": external_apis_called,
            "recommendationGroups": recommendation_groups,
            "itinerary": itinerary_data,
            "firestoreMessageValidated": True,
        },
    )

    response = ConversationTurnResponse(
        request_id=request.request_id,
        chat_id=request.chat_id,
        turn_id=request.turn_id,
        accepted_traveller_message_id=request.traveller_message_id,
        context_revision=next_context_revision,
        next_action=next_action,
        context=updated_context,
        assistant_messages=[assistant_message],
        suggested_chat_title=suggested_chat_title,
        created_at=created_at,
        metadata={
            "operation": request.operation.value,
            "interpretationAction": interpretation.action.value,
            "openAiStructuredOutput": True,
            "externalApisCalled": external_apis_called,
            "recommendationGroupCount": len(recommendation_groups),
        },
    )

    persistence_started_at = perf_counter()

    persisted_response = persist_conversation_response(
        state=state,
        request=request,
        response=response,
    )

    persistence_seconds = perf_counter() - persistence_started_at

    total_seconds = perf_counter() - request_started_at

    other_seconds = max(
        0.0,
        total_seconds
        - load_state_seconds
        - interpret_seconds
        - recommendation_seconds
        - itinerary_seconds
        - persistence_seconds,
    )

    print(
        "TRIP_LOGIC_TIMING "
        f"load_state={load_state_seconds:.3f}s "
        f"interpret={interpret_seconds:.3f}s "
        f"recommendations={recommendation_seconds:.3f}s "
        f"itinerary={itinerary_seconds:.3f}s "
        f"persistence={persistence_seconds:.3f}s "
        f"other={other_seconds:.3f}s "
        f"total={total_seconds:.3f}s"
    )

    return persisted_response
