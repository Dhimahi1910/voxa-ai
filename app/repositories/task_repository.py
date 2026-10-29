from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models import ScheduledTask
from app.models.enums import TaskKind, TaskStatus


async def enqueue(session: AsyncSession, kind: TaskKind, customer_id: int, run_at: datetime, dedupe_key: str,
                  payload: dict | None = None) -> ScheduledTask | None:
    """Idempotent: re-enqueueing the same dedupe_key (job retry, restart) returns None and changes nothing."""
    task = ScheduledTask(kind=kind.value, customer_id=customer_id, run_at=run_at, dedupe_key=dedupe_key, payload=payload or {})
    session.add(task)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    return task


async def claim_due(session: AsyncSession, now: datetime | None = None, limit: int = 20) -> list[ScheduledTask]:
    """Atomically move due tasks pending -> running. Each task is claimed by exactly one worker."""
    now = now or utcnow()
    q = select(ScheduledTask.id).where(ScheduledTask.status == TaskStatus.PENDING.value, ScheduledTask.run_at <= now) \
        .order_by(ScheduledTask.run_at).limit(limit)
    claimed: list[ScheduledTask] = []
    for task_id in (await session.execute(q)).scalars().all():
        res = await session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id, ScheduledTask.status == TaskStatus.PENDING.value)
            .values(status=TaskStatus.RUNNING.value, locked_at=now, attempts=ScheduledTask.attempts + 1)
        )
        if res.rowcount == 1:
            await session.commit()
            task = await session.get(ScheduledTask, task_id)
            await session.refresh(task)
            claimed.append(task)
        else:
            await session.rollback()
    return claimed


async def finish(session: AsyncSession, task: ScheduledTask, status: TaskStatus, error: str | None = None) -> None:
    task.status, task.last_error, task.locked_at = status.value, (error or None), None
    await session.commit()


async def requeue_stale(session: AsyncSession, stale_minutes: int, now: datetime | None = None) -> int:
    """Recovery after a crash: tasks left 'running' go back to pending. Calls stay safe via their attempt_key."""
    cutoff = (now or utcnow()) - timedelta(minutes=stale_minutes)
    res = await session.execute(
        update(ScheduledTask)
        .where(ScheduledTask.status == TaskStatus.RUNNING.value, ScheduledTask.locked_at <= cutoff)
        .values(status=TaskStatus.PENDING.value, locked_at=None)
    )
    await session.commit()
    return res.rowcount or 0


async def cancel_pending(session: AsyncSession, customer_id: int, kind: TaskKind | None = None) -> int:
    q = update(ScheduledTask).where(ScheduledTask.customer_id == customer_id, ScheduledTask.status == TaskStatus.PENDING.value)
    if kind:
        q = q.where(ScheduledTask.kind == kind.value)
    res = await session.execute(q.values(status=TaskStatus.CANCELLED.value))
    await session.commit()
    return res.rowcount or 0


async def customers_with_pending(session: AsyncSession, kind: TaskKind) -> set[int]:
    q = select(ScheduledTask.customer_id).where(
        ScheduledTask.kind == kind.value, ScheduledTask.status.in_((TaskStatus.PENDING.value, TaskStatus.RUNNING.value))
    )
    return set((await session.execute(q)).scalars().all())
