"""PlanFix webhook intake (stage 9B)."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PlanfixWebhookBody(BaseModel):
    """JSON body sent by PlanFix HTTP actions (spec §7 / planfix-notes §5)."""

    task: int
    secret: str
    status: str = Field(min_length=1)


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/planfix")
    async def planfix_webhook(
        body: PlanfixWebhookBody,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        expected = request.app.state.webhook_secret
        if not hmac.compare_digest(body.secret, expected):
            raise HTTPException(status_code=403, detail="Forbidden")
        # Respond first; PlanFix retries on slow/non-200 responses (spec §8).
        background_tasks.add_task(
            process_planfix_webhook,
            task_id=body.task,
            status_name=body.status,
            events=request.app.state.webhook_events,
        )
        return {"result": "ok"}

    return router


async def process_planfix_webhook(
    *,
    task_id: int,
    status_name: str,
    events: list[tuple[int, str]] | None = None,
) -> None:
    """Handle a verified webhook in the background.

    Stage 9B only records the event. Stage 9C will re-fetch the task and apply status.
    """
    if events is not None:
        events.append((task_id, status_name))
    logger.info(
        "planfix webhook queued",
        extra={"planfix_task_id": task_id, "planfix_status_name": status_name},
    )


__all__ = ["PlanfixWebhookBody", "create_router", "process_planfix_webhook"]
