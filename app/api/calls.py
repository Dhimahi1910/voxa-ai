from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.phone import normalize_phone
from app.core.security import require_api_key
from app.core.timeutil import fmt_local, utcnow
from app.db import get_session
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers
from app.schemas.call import CallDetailOut, CallListItem, CallOut, StartCallRequest
from app.workflows import calling_workflow

router = APIRouter(prefix="/api/calls", tags=["calls"], dependencies=[Depends(require_api_key)])


@router.post("/start", response_model=CallOut)
async def start_call(body: StartCallRequest, sv: Services = Depends(get_services),
                     session: AsyncSession = Depends(get_session)):
    """Manually call one existing customer. DNC, calling hours and one-live-call-per-customer all still apply."""
    if not body.has_target():
        raise HTTPException(422, "customer_id or phone is required")
    customer = await customers.get(session, body.customer_id) if body.customer_id else None
    if customer is None and body.phone:
        phone = normalize_phone(body.phone, sv.policy.calls.default_country)
        if not phone:
            raise HTTPException(422, "invalid phone number")
        customer = await customers.get_by_phone(session, phone)
    if customer is None:
        raise HTTPException(404, "customer not found")
    res = await calling_workflow.place_call(sv, session, customer, f"manual:{uuid.uuid4().hex}", "manual")
    if res.status == "placed":
        return await calls.get(session, res.call_id)
    code = {"skipped": 422, "outside_hours": 409, "duplicate": 409, "failed": 502, "unknown": 502}[res.status]
    raise HTTPException(code, res.detail or res.status)


def _since(days: int | None):
    return utcnow() - timedelta(days=days) if days else None


@router.get("", response_model=list[CallListItem])
async def list_calls(customer_id: int | None = None, outcome: str | None = Query(None, max_length=30),
                     q: str | None = Query(None, max_length=100), days: int | None = Query(None, ge=1, le=365),
                     limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     session: AsyncSession = Depends(get_session)):
    rows = await calls.list_calls(session, customer_id, outcome, limit, offset, q, _since(days))
    return [CallListItem.model_validate(c).model_copy(update={"customer_name": cu.name, "customer_phone": cu.phone})
            for c, cu in rows]


def _safe_cell(value) -> str:
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ would run as a formula in Excel/Sheets."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/export")
async def export_calls(outcome: str | None = Query(None, max_length=30), q: str | None = Query(None, max_length=100),
                       days: int | None = Query(None, ge=1, le=365), sv: Services = Depends(get_services),
                       session: AsyncSession = Depends(get_session)):
    rows = await calls.list_calls(session, None, outcome, 5000, 0, q, _since(days))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["call_id", "customer", "phone", "dialed_at", "outcome", "state", "reason", "duration_seconds", "meeting_status", "summary"])
    for c, cu in rows:
        w.writerow([_safe_cell(v) for v in (c.id, cu.name, cu.phone, fmt_local(c.dialed_at or c.created_at, sv.settings.tz),
                    c.outcome or "", c.state, c.reason, c.duration_seconds or "",
                    (c.analysis or {}).get("meeting_status", ""), c.summary or "")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="calls.csv"'})


@router.get("/{call_id}", response_model=CallDetailOut)
async def get_call(call_id: int, session: AsyncSession = Depends(get_session)):
    call = await calls.get(session, call_id)
    if call is None:
        raise HTTPException(404, "call not found")
    return call
