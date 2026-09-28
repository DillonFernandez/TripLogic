from __future__ import annotations

import asyncio
from typing import Any

from app.conversation_models import TravelContext
from app.conversation_recommendation_adapter import (
    build_recommendation_tasks,
)
from app.recommendation_engine import (
    generate_recommendations,
)


async def generate_conversation_recommendations(
    context: TravelContext,
    *,
    include_internal_route_matrix: bool = False,
) -> list[dict[str, Any]]:
    """
    Generate recommendations for every confirmed request group.

    OpenAI is not involved here. The trusted context is converted
    into validated RecommendationRequest models before provider
    services are called.
    """

    tasks = build_recommendation_tasks(context)

    results = await asyncio.gather(
        *[
            generate_recommendations(
                task.request,
                requested_count=task.requested_count,
                include_internal_route_matrix=(include_internal_route_matrix),
            )
            for task in tasks
        ]
    )

    grouped_results: list[dict[str, Any]] = []

    for task, result in zip(
        tasks,
        results,
        strict=True,
    ):
        limited_result = _limit_recommendation_result(
            result=result,
            requested_count=task.requested_count,
        )

        grouped_results.append(
            {
                "requestGroupId": task.request_group_id,
                "recommendationType": (task.request.recommendation_type),
                "travellerQuery": task.traveller_query,
                "requestedCount": task.requested_count,
                "required": task.required,
                "result": limited_result,
            }
        )

    return grouped_results


def _limit_recommendation_result(
    *,
    result: dict[str, Any],
    requested_count: int | None,
) -> dict[str, Any]:
    if requested_count is None:
        return result

    top_recommendations = result.get(
        "topRecommendations",
        [],
    )
    more_recommendations = result.get(
        "moreRecommendations",
        [],
    )

    if not isinstance(top_recommendations, list):
        top_recommendations = []

    if not isinstance(more_recommendations, list):
        more_recommendations = []

    remaining_count = requested_count

    limited_top = top_recommendations[:remaining_count]
    remaining_count -= len(limited_top)

    limited_more = more_recommendations[:remaining_count]

    limited_result = dict(result)
    limited_result["topRecommendations"] = limited_top
    limited_result["moreRecommendations"] = limited_more
    limited_result["count"] = len(limited_top) + len(limited_more)

    return limited_result
