from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.security import require_webhook_secret
from app.db import get_session
from app.repositories import call_repository as calls
from app.workflows import calling_workflow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def extract_call_id(payload: dict) -> str | None:
    """The callback schema is not documented by the provider, so look in the usual places."""
    for scope in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else {}):
        for k in ("conversationId", "conversation_id", "callId", "call_id", "id"):
            if scope.get(k):
                return str(scope[k])
    return None


@router.post("/voice", dependencies=[Depends(require_webhook_secret)])
async def voice_webhook(request: Request, background: BackgroundTasks, sv: Services = Depends(get_services),
                        session: AsyncSession = Depends(get_session)):
    """'Call ended' notification. The payload is only a trigger: authoritative data is re-fetched from the provider API."""
    try:
        payload = await request.json()
    except ValueError:
        return {"status": "ignored", "reason": "invalid json"}
    if not isinstance(payload, dict):
        return {"status": "ignored", "reason": "unexpected payload"}
    provider_id = extract_call_id(payload)
    call = await calls.by_provider_id(session, provider_id) if provider_id else None
    if call is None:
        return {"status": "ignored", "reason": "unknown call"}
    call_id = call.id  # read before recording: a duplicate triggers a rollback that expires loaded objects
    is_new = await calls.record_webhook_event(session, f"voice:{provider_id}:{payload.get('event') or payload.get('type') or 'end'}", payload)
    # Processing is idempotent (processed_at), so a duplicate delivery may safely re-trigger an unfinished call.
    background.add_task(calling_workflow.process_call, sv, call_id)
    return {"status": "accepted" if is_new else "duplicate"}
