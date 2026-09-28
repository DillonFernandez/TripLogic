from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from google.api_core.exceptions import (
    Aborted,
    GoogleAPICallError,
)
from google.cloud import firestore
from pydantic import ValidationError

from app.conversation_models import (
    ConversationTurnOperation,
    ConversationTurnRequest,
    ConversationTurnResponse,
    TravelContext,
)
from app.firebase import firestore_db


@dataclass(frozen=True, slots=True)
class ConversationState:
    uid: str
    chat_id: str
    chat_reference: Any
    chat_data: dict[str, Any]
    context_revision: int
    context: TravelContext
    recent_messages: tuple[str, ...]


def get_processed_response(
    *,
    uid: str,
    request: ConversationTurnRequest,
) -> ConversationTurnResponse | None:
    """
    Return the stored response when the same requestId was already completed.

    This check allows a Flutter retry to succeed even though the chat context
    revision has already advanced after the original request.
    """

    chat_reference = (
        firestore_db.collection("users")
        .document(uid)
        .collection("chats")
        .document(request.chat_id)
    )

    request_reference = chat_reference.collection("requests").document(
        request.request_id
    )

    try:
        chat_snapshot = chat_reference.get()
        request_snapshot = request_reference.get()
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to read the conversation at this time.",
        ) from error

    if not chat_snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The conversation was not found.",
        )

    _validate_chat_owner(
        chat_data=chat_snapshot.to_dict() or {},
        uid=uid,
    )

    if not request_snapshot.exists:
        return None

    return _read_stored_response(
        request_data=request_snapshot.to_dict() or {},
        request=request,
    )


def load_conversation_state(
    *,
    uid: str,
    request: ConversationTurnRequest,
) -> ConversationState:
    """
    Load and validate the authenticated traveller's chat state.

    The request is rejected when the chat does not exist, belongs to another
    user, contains invalid stored context, or has moved to a newer revision.
    """

    chat_reference = (
        firestore_db.collection("users")
        .document(uid)
        .collection("chats")
        .document(request.chat_id)
    )

    try:
        chat_snapshot = chat_reference.get()
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to read the conversation at this time.",
        ) from error

    if not chat_snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The conversation was not found.",
        )

    chat_data = chat_snapshot.to_dict() or {}

    _validate_chat_owner(
        chat_data=chat_data,
        uid=uid,
    )

    context_revision = _read_context_revision(chat_data)

    if request.expected_context_revision != context_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The conversation changed before this message was processed. "
                "Reload the latest chat and try again."
            ),
        )

    context = _read_travel_context(
        chat_data,
        context_revision=context_revision,
    )

    recent_messages = _load_recent_messages(
        chat_reference=chat_reference,
        current_sequence=request.traveller_message_sequence,
    )

    return ConversationState(
        uid=uid,
        chat_id=request.chat_id,
        chat_reference=chat_reference,
        chat_data=chat_data,
        context_revision=context_revision,
        context=context,
        recent_messages=recent_messages,
    )


def _load_recent_messages(
    *,
    chat_reference: Any,
    current_sequence: int,
) -> tuple[str, ...]:
    try:
        snapshots = (
            chat_reference.collection("messages")
            .order_by(
                "sequence",
                direction=firestore.Query.DESCENDING,
            )
            .limit(12)
            .stream()
        )
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to load recent conversation messages.",
        ) from error

    collected_messages: list[tuple[int, str]] = []

    try:
        for snapshot in snapshots:
            message_data = snapshot.to_dict() or {}

            sequence = message_data.get("sequence")
            text = message_data.get("text")
            author = message_data.get("author")

            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence >= current_sequence
            ):
                continue

            if not isinstance(text, str) or not text.strip():
                continue

            speaker = "Traveller" if author == "traveller" else "Assistant"

            collected_messages.append(
                (
                    sequence,
                    f"{speaker}: {text.strip()}",
                )
            )
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to load recent conversation messages.",
        ) from error

    collected_messages.sort(key=lambda item: item[0])

    return tuple(text for _, text in collected_messages[-6:])


def validate_traveller_message(
    *,
    state: ConversationState,
    request: ConversationTurnRequest,
) -> dict[str, Any]:
    """
    Confirm that the referenced traveller message exists in Firestore.

    New messages must match the client-written text and turn identifier.
    Edit requests intentionally contain replacement text and a fresh turn
    identifier, so only the existing document and stable sequence are checked
    at this stage.
    """

    message_reference = state.chat_reference.collection("messages").document(
        request.traveller_message_id
    )

    try:
        message_snapshot = message_reference.get()
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to read the traveller message at this time.",
        ) from error

    if not message_snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The traveller message was not found.",
        )

    message_data = message_snapshot.to_dict() or {}

    _validate_traveller_message_data(
        message_data=message_data,
        request=request,
    )

    return message_data


def persist_conversation_response(
    *,
    state: ConversationState,
    request: ConversationTurnRequest,
    response: ConversationTurnResponse,
) -> ConversationTurnResponse:
    """
    Atomically persist one trusted backend response.

    The transaction rechecks the chat revision and traveller message before
    updating the travel context, creating assistant messages, and recording an
    idempotency document for the request. A repeated requestId returns the
    response stored by the original successful transaction.
    """

    _validate_response_matches_request(
        request=request,
        response=response,
    )

    transaction = firestore_db.transaction()

    try:
        return _persist_response_transaction(
            transaction,
            state,
            request,
            response,
        )
    except HTTPException:
        raise
    except Aborted as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The conversation changed while the response was being saved. "
                "Reload the latest chat and try again."
            ),
        ) from error
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to save the conversation at this time.",
        ) from error


@firestore.transactional
def _persist_response_transaction(
    transaction: Any,
    state: ConversationState,
    request: ConversationTurnRequest,
    response: ConversationTurnResponse,
) -> ConversationTurnResponse:
    chat_reference = state.chat_reference

    message_reference = chat_reference.collection("messages").document(
        request.traveller_message_id
    )

    request_reference = chat_reference.collection("requests").document(
        request.request_id
    )

    # Firestore requires every transaction read before the first write.
    chat_snapshot = chat_reference.get(
        transaction=transaction,
    )

    message_snapshot = message_reference.get(
        transaction=transaction,
    )

    request_snapshot = request_reference.get(
        transaction=transaction,
    )

    if not chat_snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The conversation was not found.",
        )

    chat_data = chat_snapshot.to_dict() or {}

    _validate_chat_owner(
        chat_data=chat_data,
        uid=state.uid,
    )

    # Check idempotency before comparing revisions. A successful earlier
    # request has already advanced the revision.
    if request_snapshot.exists:
        return _read_stored_response(
            request_data=request_snapshot.to_dict() or {},
            request=request,
        )

    current_revision = _read_context_revision(chat_data)

    if current_revision != request.expected_context_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The conversation changed before this response was saved. "
                "Reload the latest chat and try again."
            ),
        )

    if not message_snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The traveller message was not found.",
        )

    message_data = message_snapshot.to_dict() or {}

    _validate_traveller_message_data(
        message_data=message_data,
        request=request,
    )

    expected_response_revision = current_revision + 1

    if response.context_revision != expected_response_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The response context revision must be exactly one greater "
                "than the stored conversation revision."
            ),
        )

    response_payload = response.model_dump(
        by_alias=True,
        mode="json",
    )

    # The client creates the traveller message as pending.
    # Once the backend has successfully processed the turn,
    # persist the delivered state as part of the same transaction.
    transaction.update(
        message_reference,
        {
            "deliveryStatus": "delivered",
            "contextRevision": response.context_revision,
        },
    )

    assistant_message_ids: list[str] = []

    for assistant_message in response.assistant_messages:
        assistant_message_ids.append(assistant_message.id)

        assistant_reference = chat_reference.collection("messages").document(
            assistant_message.id
        )

        transaction.create(
            assistant_reference,
            {
                "turnId": response.turn_id,
                "sequence": assistant_message.sequence,
                "author": "assistant",
                "type": assistant_message.type.value,
                "origin": "backend",
                "text": assistant_message.text,
                "createdAt": (assistant_message.created_at or response.created_at),
                "editedAt": None,
                "deliveryStatus": "delivered",
                "data": assistant_message.data,
                "requestId": request.request_id,
                "contextRevision": (response.context_revision),
            },
        )

    final_assistant_message = response.assistant_messages[-1]

    chat_updates: dict[str, Any] = {
        "contextRevision": response.context_revision,
        "travelContext": response.context.model_dump(
            by_alias=True,
            mode="json",
        ),
        "nextAction": response.next_action.value,
        "lastTurnId": response.turn_id,
        "lastProcessedRequestId": request.request_id,
        "lastMessageText": final_assistant_message.text,
        "lastMessageAt": response.created_at,
        "lastSequence": final_assistant_message.sequence,
        "updatedAt": response.created_at,
    }

    if response.suggested_chat_title is not None:
        chat_updates["title"] = response.suggested_chat_title

    transaction.update(
        chat_reference,
        chat_updates,
    )

    transaction.create(
        request_reference,
        {
            "uid": state.uid,
            "chatId": request.chat_id,
            "requestId": request.request_id,
            "operation": request.operation.value,
            "turnId": request.turn_id,
            "travellerMessageId": (request.traveller_message_id),
            "travellerMessageSequence": (request.traveller_message_sequence),
            "contextRevision": response.context_revision,
            "assistantMessageIds": assistant_message_ids,
            "createdAt": response.created_at,
            "response": response_payload,
        },
    )

    return response


def _read_stored_response(
    *,
    request_data: dict[str, Any],
    request: ConversationTurnRequest,
) -> ConversationTurnResponse:
    if (
        request_data.get("chatId") != request.chat_id
        or request_data.get("turnId") != request.turn_id
        or request_data.get("travellerMessageId") != request.traveller_message_id
        or request_data.get("operation") != request.operation.value
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The request ID has already been used for a different "
                "conversation operation."
            ),
        )

    raw_response = request_data.get("response")

    if not isinstance(raw_response, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored conversation response is invalid.",
        )

    try:
        return ConversationTurnResponse.model_validate(raw_response)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=("The stored conversation response could not be validated."),
        ) from error


def _validate_response_matches_request(
    *,
    request: ConversationTurnRequest,
    response: ConversationTurnResponse,
) -> None:
    if response.request_id != request.request_id:
        raise ValueError("response.requestId must match request.requestId")

    if response.chat_id != request.chat_id:
        raise ValueError("response.chatId must match request.chatId")

    if response.turn_id != request.turn_id:
        raise ValueError("response.turnId must match request.turnId")

    if response.accepted_traveller_message_id != request.traveller_message_id:
        raise ValueError(
            "response.acceptedTravellerMessageId must match "
            "request.travellerMessageId"
        )

    expected_sequences = list(
        range(
            request.traveller_message_sequence + 1,
            request.traveller_message_sequence + 1 + len(response.assistant_messages),
        )
    )

    actual_sequences = [message.sequence for message in response.assistant_messages]

    if actual_sequences != expected_sequences:
        raise ValueError(
            "assistant message sequences must be contiguous and begin "
            "immediately after the traveller message"
        )


def _validate_chat_owner(
    *,
    chat_data: dict[str, Any],
    uid: str,
) -> None:
    stored_uid = chat_data.get("uid")

    if stored_uid is not None and stored_uid != uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation.",
        )


def _validate_traveller_message_data(
    *,
    message_data: dict[str, Any],
    request: ConversationTurnRequest,
) -> None:
    if message_data.get("author") != "traveller":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The referenced message is not a traveller message.",
        )

    stored_sequence = message_data.get("sequence")

    if (
        isinstance(stored_sequence, bool)
        or not isinstance(stored_sequence, int)
        or stored_sequence < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored traveller message sequence is invalid.",
        )

    if stored_sequence != request.traveller_message_sequence:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The traveller message sequence no longer matches.",
        )

    if request.operation is ConversationTurnOperation.SEND_MESSAGE:
        stored_turn_id = message_data.get("turnId")
        stored_text = message_data.get("text")

        if stored_turn_id != request.turn_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The traveller message turn no longer matches.",
            )

        if not isinstance(stored_text, str):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The stored traveller message text is invalid.",
            )

        if stored_text.strip() != request.text.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The traveller message text no longer matches.",
            )


def _read_context_revision(
    chat_data: dict[str, Any],
) -> int:
    raw_revision = chat_data.get("contextRevision", 0)

    if (
        isinstance(raw_revision, bool)
        or not isinstance(raw_revision, int)
        or raw_revision < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored conversation revision is invalid.",
        )

    return raw_revision


def _read_travel_context(
    chat_data: dict[str, Any],
    *,
    context_revision: int,
) -> TravelContext:
    raw_context = chat_data.get("travelContext")

    if raw_context is None:
        return TravelContext(
            revision=context_revision,
            missing_fields=[
                "requestedPlaces",
                "startingLocation",
                "tripPeriod",
            ],
        )

    if not isinstance(raw_context, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored travel context is invalid.",
        )

    try:
        context = TravelContext.model_validate(raw_context)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored travel context could not be validated.",
        ) from error

    if context.revision != context_revision:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The stored travel context revision does not match "
                "the conversation revision."
            ),
        )

    return context
