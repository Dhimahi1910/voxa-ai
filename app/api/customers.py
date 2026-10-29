from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.phone import normalize_phone
from app.core.security import require_api_key
from app.db import get_session
from app.repositories import customer_repository as customers
from app.schemas.customer import CustomerOut, DncRequest

router = APIRouter(prefix="/api", tags=["customers"], dependencies=[Depends(require_api_key)])


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                         session: AsyncSession = Depends(get_session)):
    return await customers.list_customers(session, limit, offset)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: int, session: AsyncSession = Depends(get_session)):
    c = await customers.get(session, customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    return c


@router.post("/dnc", status_code=204)
async def add_dnc(body: DncRequest, sv: Services = Depends(get_services), session: AsyncSession = Depends(get_session)):
    phone = normalize_phone(body.phone, sv.policy.calls.default_country)
    if not phone:
        raise HTTPException(422, "invalid phone number")
    await customers.add_dnc(session, phone, body.reason, source="manual")
