from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.phone import normalize_phone
from app.core.security import require_api_key
from app.db import get_session
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers
from app.schemas.call import CallDetailOut, CallOut, StartCallRequest
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


@router.get("/{call_id}", response_model=CallDetailOut)
async def get_call(call_id: int, session: AsyncSession = Depends(get_session)):
    call = await calls.get(session, call_id)
    if call is None:
        raise HTTPException(404, "call not found")
    return call
