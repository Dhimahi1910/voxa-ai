from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models import Call, Customer, WebhookEvent
from app.models.enums import CallState

IN_FLIGHT = (CallState.PENDING.value, CallState.DIALING.value, CallState.INITIATED.value)


async def reserve_attempt(session: AsyncSession, customer_id: int, attempt_key: str, run_id: str, reason: str) -> Call | None:
    """Insert the attempt row BEFORE contacting the provider. The unique key makes a second dial impossible."""
    call = Call(customer_id=customer_id, attempt_key=attempt_key, run_id=run_id, reason=reason)
    session.add(call)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    return call


async def get(session: AsyncSession, call_id: int) -> Call | None:
    return await session.get(Call, call_id)


async def by_provider_id(session: AsyncSession, provider_call_id: str) -> Call | None:
    return (await session.execute(select(Call).where(Call.provider_call_id == provider_call_id))).scalar_one_or_none()


async def in_flight_customer_ids(session: AsyncSession) -> set[int]:
    """Customers with an unfinished call, including 'unknown' ones (we cannot tell if those rang)."""
    states = IN_FLIGHT + (CallState.UNKNOWN.value,)
    q = select(Call.customer_id).where(Call.state.in_(states), Call.processed_at.is_(None))
    return set((await session.execute(q)).scalars().all())


async def awaiting_processing(session: AsyncSession, older_than_minutes: int, now: datetime | None = None) -> list[Call]:
    cutoff = (now or utcnow()) - timedelta(minutes=older_than_minutes)
    q = select(Call).where(Call.state == CallState.INITIATED.value, Call.processed_at.is_(None), Call.dialed_at <= cutoff)
    return list((await session.execute(q)).scalars().all())


async def stuck_dialing(session: AsyncSession, older_than_minutes: int, now: datetime | None = None) -> list[Call]:
    cutoff = (now or utcnow()) - timedelta(minutes=older_than_minutes)
    q = select(Call).where(Call.state.in_((CallState.PENDING.value, CallState.DIALING.value)), Call.created_at <= cutoff)
    return list((await session.execute(q)).scalars().all())


async def record_webhook_event(session: AsyncSession, event_key: str, payload: dict) -> bool:
    """True if this event is new; False if it was already received (idempotent webhooks)."""
    session.add(WebhookEvent(event_key=event_key, payload=payload))
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def list_calls(session: AsyncSession, customer_id: int | None = None, outcome: str | None = None,
                     limit: int = 50, offset: int = 0, q: str | None = None,
                     since: datetime | None = None) -> list[tuple[Call, Customer]]:
    stmt = select(Call, Customer).join(Customer, Customer.id == Call.customer_id)
    if customer_id is not None:
        stmt = stmt.where(Call.customer_id == customer_id)
    if outcome:
        stmt = stmt.where(Call.outcome == outcome)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    if since is not None:
        stmt = stmt.where(Call.created_at >= since)
    stmt = stmt.order_by(Call.created_at.desc(), Call.id.desc()).limit(limit).offset(offset)
    return [(c, cu) for c, cu in (await session.execute(stmt)).all()]


async def outcome_counts_since(session: AsyncSession, since: datetime) -> dict[str, int]:
    q = select(Call.outcome, func.count()).where(Call.created_at >= since).group_by(Call.outcome)
    return {(o or "Pending"): n for o, n in (await session.execute(q)).all()}


async def failed_since(session: AsyncSession, since: datetime) -> int:
    q = select(func.count()).where(Call.created_at >= since, Call.state.in_((CallState.FAILED.value, CallState.UNKNOWN.value)))
    return (await session.execute(q)).scalar_one()
