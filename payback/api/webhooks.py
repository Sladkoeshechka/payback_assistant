"""PlanFix webhook intake (stage 9B/9C)."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.applications import Starlette

from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.webhook import WebhookService

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
            app=request.app,
        )
        return {"result": "ok"}

    return router


async def process_planfix_webhook(
    *,
    task_id: int,
    status_name: str,
    app: Starlette | None = None,
    events: list[tuple[int, str]] | None = None,
) -> None:
    """Handle a verified webhook in the background (re-fetch task, apply status)."""
    sink = events
    if sink is None and app is not None:
        sink = getattr(app.state, "webhook_events", None)
    if sink is not None:
        sink.append((task_id, status_name))
    logger.info(
        "planfix webhook queued",
        extra={"planfix_task_id": task_id, "planfix_status_name": status_name},
    )
    if app is None:
        return

    session_factory = getattr(app.state, "session_factory", None)
    planfix = getattr(app.state, "planfix", None)
    notifier = getattr(app.state, "notifier", None)
    status_ids = getattr(app.state, "status_ids", None)
    if session_factory is None or planfix is None or notifier is None or status_ids is None:
        logger.info(
            "planfix webhook apply skipped (dependencies not configured)",
            extra={"planfix_task_id": task_id},
        )
        return

    async with session_factory() as session:
        service = WebhookService(
            ExpensesRepo(session),
            UsersRepo(session),
            planfix,
            notifier,
            status_ids,
        )
        await service.apply(task_id, webhook_status_name=status_name)
        await session.commit()


__all__ = ["PlanfixWebhookBody", "create_router", "process_planfix_webhook"]
