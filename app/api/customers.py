from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.phone import normalize_phone
from app.core.security import require_api_key
from app.db import get_session
from app.repositories import customer_repository as customers
from app.models import Customer
from app.schemas.customer import CustomerCreate, CustomerOut, DncOut, DncRequest

router = APIRouter(prefix="/api", tags=["customers"], dependencies=[Depends(require_api_key)])


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                         q: str | None = Query(None, max_length=100), session: AsyncSession = Depends(get_session)):
    return await customers.list_customers(session, limit, offset, q)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: int, session: AsyncSession = Depends(get_session)):
    c = await customers.get(session, customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    return c


@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(body: CustomerCreate, sv: Services = Depends(get_services),
                          session: AsyncSession = Depends(get_session)):
    """Add one customer by hand (customers normally come from the spreadsheet)."""
    phone = normalize_phone(body.phone, sv.policy.calls.default_country)
    if not phone:
        raise HTTPException(422, "invalid phone number")
    if await customers.get_by_phone(session, phone):
        raise HTTPException(409, "a customer with this phone number already exists")
    c = Customer(phone=phone, name=body.name.strip(), email=body.email.strip())
    session.add(c)
    await session.commit()
    return c


@router.get("/dnc", response_model=list[DncOut])
async def list_dnc(session: AsyncSession = Depends(get_session)):
    return await customers.list_dnc(session)


@router.delete("/dnc", status_code=204)
async def remove_dnc(phone: str = Query(max_length=20), sv: Services = Depends(get_services),
                     session: AsyncSession = Depends(get_session)):
    """Remove a number from the do-not-call list. Use only when the customer has asked to be contacted again."""
    normalized = normalize_phone(phone, sv.policy.calls.default_country)
    if not normalized or not await customers.remove_dnc(session, normalized):
        raise HTTPException(404, "number is not on the do-not-call list")


@router.post("/dnc", status_code=204)
async def add_dnc(body: DncRequest, sv: Services = Depends(get_services), session: AsyncSession = Depends(get_session)):
    phone = normalize_phone(body.phone, sv.policy.calls.default_country)
    if not phone:
        raise HTTPException(422, "invalid phone number")
    await customers.add_dnc(session, phone, body.reason, source="manual")
