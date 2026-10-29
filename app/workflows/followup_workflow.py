"""What to do after a call. `decide_followup` is pure (no I/O) so every rule is unit-testable."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Services
from app.core.config import Policy
from app.core.timeutil import fmt_local, next_allowed_time, parse_when, slot_after
from app.models import Call, Customer
from app.models.enums import CallOutcome, MeetingStatus, TaskKind
from app.repositories import customer_repository as customers
from app.repositories import task_repository as tasks
from app.schemas.transcript import CallAnalysis
from app.workflows import meeting_workflow

log = logging.getLogger(__name__)

_RETRY_RULE = {CallOutcome.NOT_RECEIVED: "not_received", CallOutcome.NOT_RESPONDED: "not_responded", CallOutcome.ENDED: "ended"}
_RETRY_EMAIL = {CallOutcome.NOT_RECEIVED: "missed_call", CallOutcome.NOT_RESPONDED: "not_responded", CallOutcome.ENDED: "disconnected"}


@dataclass
class EmailAction:
    kind: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class FollowUpPlan:
    mark_dnc: bool = False
    next_call_at: datetime | None = None
    next_call_reason: str = ""          # retry | callback
    meeting_at: datetime | None = None
    meeting_mode: str = ""
    exhausted: bool = False
    emails: list[EmailAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def decide_followup(*, outcome: CallOutcome, analysis: CallAnalysis | None, call_count: int, policy: Policy,
                    tz: ZoneInfo, now: datetime) -> FollowUpPlan:
    plan = FollowUpPlan()
    if analysis is not None and analysis.do_not_contact:
        plan.mark_dnc = True
        plan.notes.append("customer asked not to be contacted")
        return plan

    if outcome in _RETRY_RULE:
        rule = getattr(policy.retry, _RETRY_RULE[outcome])
        if not rule.enabled:
            plan.notes.append("retry disabled for this outcome")
        elif call_count >= policy.calls.max_attempts:
            plan.exhausted = True
            plan.notes.append("max attempts reached")
        else:
            plan.next_call_at = slot_after(now, rule.delay_minutes, policy, tz, rule.window)
            plan.next_call_reason = "retry"
            plan.emails.append(EmailAction(_RETRY_EMAIL[outcome], {
                "next_attempt": f"We will try calling you again on {fmt_local(plan.next_call_at, tz)}."}))
        return plan

    if outcome == CallOutcome.RESCHEDULED:
        cb = parse_when(analysis.call_rescheduled_time if analysis else "", tz, now)
        lead = now + timedelta(minutes=policy.callback.min_lead_minutes)
        horizon = now + timedelta(days=policy.callback.max_days_ahead)
        if cb is None or cb < lead or cb > horizon:
            plan.notes.append("callback time missing/unusable; used default delay")
            cb = now + timedelta(minutes=policy.callback.default_delay_minutes)
        plan.next_call_at = next_allowed_time(cb, policy, tz)
        plan.next_call_reason = "callback"  # agreed callbacks are not limited by max_attempts
        plan.emails.append(EmailAction("callback_confirmation", {"callback_time": f"on {fmt_local(plan.next_call_at, tz)}"}))
        return plan

    if outcome == CallOutcome.CONNECTED and analysis is not None and analysis.meeting_status == MeetingStatus.SCHEDULED:
        when = parse_when(analysis.preferred_meeting_time, tz, now)
        if when and when > now:
            plan.meeting_at, plan.meeting_mode = when, analysis.meeting_preference
            plan.emails.append(EmailAction("meeting_confirmation", {
                "meeting_time": fmt_local(when, tz), "meeting_mode": (analysis.meeting_preference or "").lower() or "scheduled"}))
        else:
            plan.notes.append("meeting time missing or in the past; not scheduled")
    return plan


async def execute_plan(sv: Services, session: AsyncSession, customer: Customer, call: Call, plan: FollowUpPlan,
                       now: datetime) -> None:
    """Apply a plan. Every effect is idempotent (unique keys), so re-running after a crash or retry is safe."""
    if plan.mark_dnc:
        await customers.add_dnc(session, customer.phone, "customer request on call", source="call")
        await tasks.cancel_pending(session, customer.id)
        return  # no emails or calls for a do-not-contact customer

    if plan.meeting_at:
        await meeting_workflow.schedule_meeting(sv, session, customer, call, plan.meeting_at, plan.meeting_mode, now)
    if plan.next_call_at:
        await tasks.enqueue(session, TaskKind.CALL, customer.id, plan.next_call_at, f"call:followup:{call.id}",
                            {"reason": plan.next_call_reason})
    if plan.exhausted:
        customer.exhausted = True
        await session.commit()
    for e in plan.emails:
        await sv.email.send(session, customer, e.kind, f"{e.kind}:call:{call.id}", e.extra)
