"""Outbound calling: customer selection, safe dialing, and the post-call pipeline."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Services
from app.core.config import Policy
from app.core.timeutil import fmt_local, in_calling_hours, next_allowed_time, utcnow
from app.models import Call, Customer
from app.models.enums import CallOutcome, CallState, MeetingStatus, TaskKind
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers
from app.repositories import task_repository as tasks
from app.schemas.call import ProviderCall
from app.services.ai_analysis_service import AnalysisError
from app.services.voice_service import VoiceAPIError
from app.workflows import followup_workflow

log = logging.getLogger(__name__)

RETRYABLE_OUTCOMES = {CallOutcome.NOT_RECEIVED.value, CallOutcome.NOT_RESPONDED.value, CallOutcome.ENDED.value}
MAX_TECH_RETRIES = 2
MAX_PROCESS_ATTEMPTS = 6


SKIP_TEXT = {
    "do_not_call": "On the do-not-call list",
    "max_attempts": "Already used all allowed call attempts",
    "meeting_scheduled": "A meeting is already booked",
    "call_in_progress": "A call to them is already in progress",
    "followup_already_scheduled": "A retry or callback is already scheduled",
    "already_contacted": "Already spoke with them; waiting on a person or a scheduled follow-up",
    "called_recently": "Called too recently (minimum gap not passed)",
    "outside_calling_hours": "Outside calling hours right now",
    "batch_limit": "Over today's batch limit",
    "duplicate_in_run": "Same phone number appears twice in this run",
}


# --------------------------------------------------------------------------------------------- selection
@dataclass
class EligibilityContext:
    now: datetime
    policy: Policy
    tz: ZoneInfo
    dnc: set[str] = field(default_factory=set)
    in_flight: set[int] = field(default_factory=set)
    has_pending_call_task: set[int] = field(default_factory=set)


def skip_reason(c: Customer, ctx: EligibilityContext) -> str | None:
    """None if the customer may be dialled now, else why not. Pure function: easy to test."""
    p = ctx.policy
    if c.phone in ctx.dnc:
        return "do_not_call"
    if c.exhausted or c.call_count >= p.calls.max_attempts:
        return "max_attempts"
    if c.meeting_status == MeetingStatus.SCHEDULED.value:
        return "meeting_scheduled"
    if c.id in ctx.in_flight:
        return "call_in_progress"
    if c.id in ctx.has_pending_call_task:
        return "followup_already_scheduled"
    if c.last_outcome is not None and c.last_outcome not in RETRYABLE_OUTCOMES:
        return "already_contacted"  # connected/callback customers are driven by follow-up tasks or people, not the daily run
    if c.last_call_at and (ctx.now - c.last_call_at).total_seconds() < p.calls.min_gap_minutes * 60:
        return "called_recently"
    if not in_calling_hours(ctx.now, p, ctx.tz):
        return "outside_calling_hours"
    return None


def select_customers(candidates: list[Customer], ctx: EligibilityContext, limit: int) -> tuple[list[Customer], dict[int, str]]:
    selected: list[Customer] = []
    skipped: dict[int, str] = {}
    phones: set[str] = set()
    for c in candidates:
        reason = "batch_limit" if len(selected) >= limit else ("duplicate_in_run" if c.phone in phones else skip_reason(c, ctx))
        if reason:
            skipped[c.id] = reason
        else:
            selected.append(c)
            phones.add(c.phone)
    return selected, skipped


async def _context(sv: Services, session: AsyncSession, now: datetime) -> EligibilityContext:
    return EligibilityContext(
        now=now, policy=sv.policy, tz=sv.settings.tz, dnc=await customers.dnc_phones(session),
        in_flight=await calls.in_flight_customer_ids(session),
        has_pending_call_task=await tasks.customers_with_pending(session, TaskKind.CALL),
    )


eligibility_context = _context


# --------------------------------------------------------------------------------------------- dialing
@dataclass
class PlaceResult:
    status: str  # placed | duplicate | skipped | outside_hours | failed | unknown
    call_id: int | None = None
    detail: str = ""


async def place_call(sv: Services, session: AsyncSession, customer: Customer, attempt_key: str, reason: str,
                     run_id: str = "", now: datetime | None = None, tech_retry: int = 0) -> PlaceResult:
    async with sv._locks.setdefault(("customer", customer.id), asyncio.Lock()):
        return await _place_call_locked(sv, session, customer, attempt_key, reason, run_id, now or utcnow(), tech_retry)


async def _place_call_locked(sv: Services, session: AsyncSession, customer: Customer, attempt_key: str, reason: str,
                             run_id: str, now: datetime, tech_retry: int) -> PlaceResult:
    if await customers.is_dnc(session, customer.phone):
        return PlaceResult("skipped", detail="do_not_call")
    if not in_calling_hours(now, sv.policy, sv.settings.tz):
        return PlaceResult("outside_hours")
    if customer.id in await calls.in_flight_customer_ids(session):
        return PlaceResult("skipped", detail="call_in_progress")
    call = await calls.reserve_attempt(session, customer.id, attempt_key, run_id, reason)
    if call is None:
        return PlaceResult("duplicate", detail=attempt_key)

    call.state = CallState.DIALING.value
    await session.commit()
    s = sv.settings
    variables = {"customer_name": customer.name, "name": customer.name,
                 "current_date": now.astimezone(s.tz).strftime("%d/%m/%Y"),
                 **{k: v for k, v in (customer.sheet_data or {}).items() if k.isidentifier()}}
    callback = f"{s.public_base_url.rstrip('/')}/api/webhooks/voice?token={s.webhook_secret.get_secret_value()}" \
        if s.public_base_url and s.webhook_secret.get_secret_value() else None
    try:
        placed = await sv.voice.place_call(customer.phone, variables, {"call_row_id": call.id, "customer_id": customer.id}, callback)
    except VoiceAPIError as exc:
        call.error = str(exc)[:500]
        if exc.status is None:  # no HTTP answer: the call may or may not have gone out. NEVER redial automatically.
            call.state = CallState.UNKNOWN.value
            await session.commit()
            log.error("dial outcome unknown", extra={"call_id": call.id})
            return PlaceResult("unknown", call.id, call.error)
        call.state = CallState.FAILED.value
        await session.commit()
        log.error("dial rejected", extra={"call_id": call.id, "code": exc.code, "status": exc.status})
        if exc.retryable and tech_retry < MAX_TECH_RETRIES:  # technical failure: separate from customer outcomes
            run_at = next_allowed_time(now + timedelta(minutes=15), sv.policy, s.tz)
            await tasks.enqueue(session, TaskKind.CALL, customer.id, run_at, f"call:techretry:{call.id}",
                                {"reason": "retry", "tech_retry": tech_retry + 1})
        return PlaceResult("failed", call.id, call.error)

    call.provider_call_id, call.provider_sid = placed.call_id, placed.sid
    call.state, call.dialed_at = CallState.INITIATED.value, now
    customer.call_count += 1
    customer.last_call_at = now
    await session.commit()
    log.info("call placed", extra={"call_id": call.id, "customer_id": customer.id, "provider_call_id": placed.call_id})
    if getattr(sv.voice, "inline", False) or not s.enable_real_calls:  # dry run: no webhook will arrive, finish inline
        await process_call(sv, call.id, poll=False)
    return PlaceResult("placed", call.id)


@dataclass
class RunSummary:
    run_id: str
    considered: int = 0
    placed: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    failed: int = 0


async def run_calling(sv: Services, run_id: str | None = None, now: datetime | None = None) -> RunSummary:
    """One calling run. Deterministic run ids (daily-<date>) make a restarted/retried job unable to re-dial."""
    now = now or utcnow()
    run_id = run_id or f"daily-{now.astimezone(sv.settings.tz).date().isoformat()}"
    summary = RunSummary(run_id)
    async with sv.sessions() as session:
        if sv.sheets:
            await customers.upsert_from_sheet(session, await sv.sheets.fetch_customers())
        candidates = list(await customers.list_customers(session, limit=100000))
        ctx = await _context(sv, session, now)
        selected, skipped = select_customers(candidates, ctx, sv.policy.calls.batch_limit)
        summary.considered = len(candidates)
        for reason in skipped.values():
            summary.skipped[reason] = summary.skipped.get(reason, 0) + 1
        for c in selected:
            res = await place_call(sv, session, c, f"run:{run_id}:{c.id}", "scheduled", run_id, now)
            if res.status == "placed":
                summary.placed += 1
            elif res.status in ("failed", "unknown"):
                summary.failed += 1
            else:
                summary.skipped[res.status] = summary.skipped.get(res.status, 0) + 1
            if sv.policy.calls.pause_between_calls_seconds and res.status == "placed":
                await asyncio.sleep(sv.policy.calls.pause_between_calls_seconds)
    log.info("calling run finished", extra={"run_id": run_id, "placed": summary.placed, "skipped": summary.skipped})
    return summary


# --------------------------------------------------------------------------------------------- post-call
async def _fetch_finished(sv: Services, call: Call, poll: bool) -> ProviderCall | None:
    attempts = sv.policy.post_call.poll_attempts if poll else 1
    for i in range(attempts):
        pc = await sv.voice.get_call(call.provider_call_id)
        if pc.finished and (pc.transcript or pc.answered is False or pc.customer_spoke is False):
            return pc
        if i < attempts - 1:
            await asyncio.sleep(sv.policy.post_call.poll_interval_seconds)
    return None


async def process_call(sv: Services, call_id: int, poll: bool = True, now: datetime | None = None) -> str:
    """Fetch results, analyse, persist, follow up, update sheet. Idempotent and safe to call from webhook + reconciler."""
    lock = sv._locks.setdefault(call_id, asyncio.Lock())
    async with lock, sv.sessions() as session:
        call = await calls.get(session, call_id)
        if call is None or call.processed_at is not None or not call.provider_call_id:
            return "skipped"
        customer = await customers.get(session, call.customer_id)
        call.process_attempts += 1
        await session.commit()
        try:
            pc = await _fetch_finished(sv, call, poll)
        except VoiceAPIError as exc:
            log.warning("provider fetch failed", extra={"call_id": call_id, "error": str(exc)[:200]})
            return "pending"
        if pc is None:
            return "pending"  # not finished yet; the reconciler will look again

        call.transcript, call.summary, call.recording_url = pc.transcript or None, pc.summary or None, pc.recording_url or None
        call.duration_seconds, call.provider_raw = pc.duration_seconds, pc.raw
        now = now or utcnow()
        analysis = None
        try:
            analysis = await sv.analysis.analyze(pc, now)
        except (AnalysisError, Exception) as exc:  # noqa: BLE001 - LLM outage must not lose the transcript
            log.error("analysis failed", extra={"call_id": call_id, "error": str(exc)[:200]})
            call.error = f"analysis failed: {str(exc)[:300]}"
            if call.process_attempts < MAX_PROCESS_ATTEMPTS:
                await session.commit()
                return "pending"  # keep transcript, retry analysis on the next reconcile tick

        plan = followup_workflow.FollowUpPlan()
        if analysis is not None:
            call.analysis, call.outcome = analysis.model_dump(), analysis.outcome.value
            customer.last_outcome = analysis.outcome.value
            plan = followup_workflow.decide_followup(
                outcome=analysis.outcome, analysis=analysis, call_count=customer.call_count,
                policy=sv.policy, tz=sv.settings.tz, now=now)
        call.state, call.processed_at = CallState.COMPLETED.value, now
        await session.commit()  # durable before any side effect

        await followup_workflow.execute_plan(sv, session, customer, call, plan, now)
        await sync_sheet(sv, session, customer, call, analysis, plan)
        return "processed"


async def sync_sheet(sv: Services, session: AsyncSession, customer: Customer, call: Call, analysis, plan) -> None:
    if sv.sheets is None:
        return
    tz = sv.settings.tz
    from app.services.google_sheets_service import CLEAR

    values: dict = {
        "call_datetime": fmt_local(call.dialed_at, tz), "call_count": customer.call_count,
        "transcript": call.transcript, "summary": call.summary, "recording_url": call.recording_url,
    }
    if plan is not None:  # plan is None when re-syncing an old call: do not touch the next-attempt cell
        values["next_attempt_at"] = fmt_local(plan.next_call_at, tz) if plan.next_call_at else CLEAR
    if analysis is not None:
        values |= {
            "call_status": analysis.call_status, "meeting_status": analysis.meeting_status,
            "meeting_preference": analysis.meeting_preference, "meeting_availability": analysis.preferred_meeting_time,
            "callback_time": analysis.call_rescheduled_time if analysis.outcome == CallOutcome.RESCHEDULED else CLEAR,
        }
        values |= {f"req.{k}": v for k, v in analysis.requirements.items()}
    try:
        await sv.sheets.update_customer(customer.phone, values)
        call.sheet_synced_at = utcnow()
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - sheet failure is retried by the reconciler (sheet_synced_at stays null)
        log.error("sheet update failed", extra={"call_id": call.id, "error": str(exc)[:200]})
