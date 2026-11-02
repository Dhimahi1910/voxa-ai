from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, DoNotCall
from app.schemas.customer import SheetCustomer


async def get(session: AsyncSession, customer_id: int) -> Customer | None:
    return await session.get(Customer, customer_id)


async def get_by_phone(session: AsyncSession, phone: str) -> Customer | None:
    return (await session.execute(select(Customer).where(Customer.phone == phone))).scalar_one_or_none()


async def list_customers(session: AsyncSession, limit: int = 50, offset: int = 0, search: str | None = None) -> Sequence[Customer]:
    q = select(Customer)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    q = q.order_by(Customer.id).limit(limit).offset(offset)
    return (await session.execute(q)).scalars().all()


async def dnc_phones(session: AsyncSession) -> set[str]:
    return set((await session.execute(select(DoNotCall.phone))).scalars().all())


async def is_dnc(session: AsyncSession, phone: str) -> bool:
    return await session.get(DoNotCall, phone) is not None


async def add_dnc(session: AsyncSession, phone: str, reason: str = "", source: str = "manual") -> None:
    if await session.get(DoNotCall, phone) is None:
        session.add(DoNotCall(phone=phone, reason=reason[:500], source=source))
        try:
            await session.commit()
        except IntegrityError:  # concurrent insert of the same number is fine
            await session.rollback()


async def remove_dnc(session: AsyncSession, phone: str) -> bool:
    row = await session.get(DoNotCall, phone)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def upsert_from_sheet(session: AsyncSession, rows: Sequence[SheetCustomer]) -> list[Customer]:
    """Create/refresh customers from sheet rows. The DB owns call_count once a customer exists (never lowered)."""
    out: list[Customer] = []
    seen: set[str] = set()
    for r in rows:
        if r.phone in seen:  # same number twice in the sheet: first row wins
            continue
        seen.add(r.phone)
        c = await get_by_phone(session, r.phone)
        if c is None:
            c = Customer(phone=r.phone, call_count=r.call_count, meeting_status=r.meeting_status or "Not Scheduled")
            session.add(c)
        c.name = r.name or c.name
        c.email = r.email or c.email
        c.sheet_data = r.extra
        c.call_count = max(c.call_count or 0, r.call_count)
        if r.do_not_call:
            await add_dnc(session, r.phone, "marked in spreadsheet", source="sheet")
        out.append(c)
    await session.commit()
    return out


async def count_customers(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Customer))).scalar_one()


async def count_dnc(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(DoNotCall))).scalar_one()
