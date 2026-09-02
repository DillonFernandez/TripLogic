from __future__ import annotations

from app.conversation_models import (
    TravelContext,
    TravelContextStage,
)


def confirm_travel_context(
    context: TravelContext,
) -> TravelContext:
    if context.stage is not TravelContextStage.AWAITING_CONFIRMATION:
        raise ValueError("The travel context is not awaiting confirmation.")

    if not context.is_ready_for_confirmation:
        raise ValueError("The travel context is not ready for confirmation.")

    context_data = context.model_dump(
        mode="python",
    )

    context_data["stage"] = TravelContextStage.CONFIRMED
    context_data["is_confirmed"] = True

    return TravelContext.model_validate(context_data)
