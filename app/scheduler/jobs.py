"""Background jobs. Each is safe to run concurrently or repeatedly: state lives in the database, not in memory."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.container import Services
from app.core.timeutil import next_allowed_time, utcnow
from app.models import Call, ScheduledTask
from app.models.enums import CallState, TaskKind, TaskStatus
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers
from app.repositories import task_repository as tasks
from app.schemas.transcript import CallAnalysis
from app.workflows import calling_workflow, meeting_workflow

log = logging.getLogger(__name__)
MAX_TASK_ATTEMPTS = 3


def exclusive(fn):
    """Skip (rather than queue) a job that is already running in this process, e.g. cron firing during a manual trigger."""
    async def wrapper(sv: Services) -> dict:
        lock = sv._locks.setdefault(("job", fn.__name__), asyncio.Lock())
        if lock.locked():
            log.info("job already running; skipped", extra={"job": fn.__name__})
            return {"skipped": "already_running"}
        async with lock:
            return await fn(sv)
    wrapper.__name__ = fn.__name__
    return wrapper


@exclusive
async def job_calling_run(sv: Services) -> dict:
    s = await calling_workflow.run_calling(sv)
    return {"run_id": s.run_id, "placed": s.placed, "failed": s.failed, "skipped": s.skipped}


@exclusive
async def job_due_tasks(sv: Services) -> dict:
    """Run callbacks, retries and reminders that are due. Also recovers tasks orphaned by a crash."""
    done = 0
    async with sv.sessions() as session:
        await tasks.requeue_stale(session, sv.policy.post_call.stale_task_minutes)
        for task in await tasks.claim_due(session):
            try:
                await _run_task(sv, session, task)
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("task failed", extra={"task_id": task.id})
                if task.attempts >= MAX_TASK_ATTEMPTS:
                    await tasks.finish(session, task, TaskStatus.FAILED, str(exc))
                else:  # retry shortly; call attempt keys keep this from double-dialling
                    task.status, task.run_at, task.last_error = TaskStatus.PENDING.value, utcnow() + timedelta(minutes=5), str(exc)[:500]
                    await session.commit()
    return {"processed": done}


async def _run_task(sv: Services, session, task: ScheduledTask) -> None:
    customer = await customers.get(session, task.customer_id)
    if task.kind == TaskKind.REMINDER.value:
        await meeting_workflow.send_reminder(sv, session, customer, task.payload)
        await tasks.finish(session, task, TaskStatus.DONE)
        return
    reason = task.payload.get("reason", "retry")
    if reason == "retry" and customer.call_count >= sv.policy.calls.max_attempts:
        await tasks.finish(session, task, TaskStatus.CANCELLED, "max attempts reached")
        return
    res = await calling_workflow.place_call(sv, session, customer, f"task:{task.id}", reason,
                                            tech_retry=task.payload.get("tech_retry", 0))
    if res.status == "outside_hours":  # slot drifted outside calling hours: move it, do not burn an attempt
        task.status, task.attempts = TaskStatus.PENDING.value, task.attempts - 1
        task.run_at, task.locked_at = next_allowed_time(utcnow(), sv.policy, sv.settings.tz), None
        await session.commit()
    elif res.status in ("placed", "duplicate"):
        await tasks.finish(session, task, TaskStatus.DONE)
    else:  # skipped (dnc / in progress) or failed/unknown: recorded on the call; do not retry the same task
        await tasks.finish(session, task, TaskStatus.CANCELLED if res.status == "skipped" else TaskStatus.FAILED, res.detail)


@exclusive
async def job_reconcile_calls(sv: Services) -> dict:
    """Safety net for lost webhooks and crashes: poll unfinished calls, settle unknown dials, re-sync the sheet."""
    pc = sv.policy.post_call
    out = {"processed": 0, "unknown": 0, "resynced": 0}
    async with sv.sessions() as session:
        for c in await calls.stuck_dialing(session, pc.dialing_unknown_after_minutes):
            c.state, c.error = CallState.UNKNOWN.value, (c.error or "interrupted while dialing; not retried automatically")
            out["unknown"] += 1
        await session.commit()
        # Nothing arrived for 24h: stop blocking the customer. Marked UNKNOWN (not a real outcome) and left for a human.
        stale_cut = utcnow() - timedelta(hours=24)
        q = select(Call).where(Call.processed_at.is_(None), Call.created_at <= stale_cut)
        for c in (await session.execute(q)).scalars():
            c.state, c.processed_at = CallState.UNKNOWN.value, utcnow()
            c.error = (c.error or "") + " | no result from provider after 24h; released"
        await session.commit()
        pending = await calls.awaiting_processing(session, pc.reconcile_after_minutes)
        recent = utcnow() - timedelta(hours=24)
        todo = [c.id for c in pending if c.dialed_at and c.dialed_at >= recent]
    for call_id in todo:
        if await calling_workflow.process_call(sv, call_id, poll=False) == "processed":
            out["processed"] += 1
    if sv.sheets:
        async with sv.sessions() as session:
            q = select(Call).where(Call.processed_at.is_not(None), Call.sheet_synced_at.is_(None)).limit(50)
            for c in (await session.execute(q)).scalars():
                customer = await customers.get(session, c.customer_id)
                analysis = CallAnalysis.model_validate(c.analysis) if c.analysis else None
                await calling_workflow.sync_sheet(sv, session, customer, c, analysis, None)
                out["resynced"] += 1
    return out
