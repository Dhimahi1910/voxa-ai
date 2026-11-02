"""Practice Room: run a scripted customer persona through the REAL analysis guardrails and follow-up rules.

Nothing is dialled, emailed or written to the database. It answers "what would the system do next?".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.container import Services
from app.models import Customer
from app.schemas.call import ProviderCall
from app.schemas.transcript import CallAnalysis
from app.services.ai_analysis_service import AnalysisError, apply_guardrails, decide_without_llm
from app.workflows.followup_workflow import FollowUpPlan, decide_followup
from app.core.timeutil import fmt_local


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    blurb: str
    transcript: str
    status: str
    answered: bool
    spoke: bool | None
    duration: int


def _local_iso(now: datetime, tz: ZoneInfo, days: int, hour: int, minute: int = 0) -> str:
    d = (now.astimezone(tz) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return d.strftime("%Y-%m-%dT%H:%M")


PERSONAS: dict[str, Persona] = {p.key: p for p in [
    Persona("interested", "Interested, books a meeting", "Engaged, shares needs and agrees a time for a virtual meeting.",
            "Agent: Hello, this is Veesha. Is this a good time?\nCustomer: Yes, go ahead.\nAgent: What are you hoping to achieve?\n"
            "Customer: We want AI voice agents for our sales team, about 20 users.\nAgent: Shall we set up a virtual meeting?\n"
            "Customer: Yes, tomorrow at 4 PM works.", "completed", True, True, 190),
    Persona("browsing", "Curious, no meeting", "Friendly and interested but not ready to commit to a time.",
            "Agent: Hello, this is Veesha. Is this a good time?\nCustomer: Sure.\nAgent: What are you looking for?\n"
            "Customer: Just exploring options for now.\nAgent: Happy to follow up whenever you like.\nCustomer: Maybe later, thanks.",
            "completed", True, True, 75),
    Persona("busy", "Busy, asks for a callback", "Picks up but is in a meeting and asks to be called back this evening.",
            "Agent: Hello, this is Veesha. Is this a good time?\nCustomer: I'm in a meeting, can you call me back at 5:30 this evening?\n"
            "Agent: Of course, I'll call you then.", "completed", True, True, 25),
    Persona("no_answer", "Does not pick up", "The phone rings out. No conversation happens.", "", "no-answer", False, None, 0),
    Persona("silent", "Answers but stays silent", "The line connects but the customer never speaks.",
            "Agent: Hello? Hello, can you hear me?\nAgent: I'll try again later. Goodbye.", "completed", True, False, 12),
    Persona("dropped", "Call drops mid-way", "The conversation starts and the line is cut before it finishes.",
            "Agent: Hello, this is Veesha. Is this a good time?\nCustomer: Yes, I wanted to ask about", "completed", True, True, 9),
    Persona("stop", "Asks not to be called again", "Polite but firm: please remove my number.",
            "Agent: Hello, this is Veesha. Is this a good time?\nCustomer: Please don't call me again, remove my number.\n"
            "Agent: Understood, I'm sorry to have bothered you.", "completed", True, True, 20),
]}


def _scripted(key: str, now: datetime, tz: ZoneInfo) -> dict:
    base = {"call_status": "Connected", "meeting_status": "Not Scheduled"}
    return {
        "interested": base | {"requirements": {"product_interest": "AI voice agents", "scale": "20 users"},
                              "meeting_preference": "Virtual", "meeting_status": "Scheduled",
                              "preferred_meeting_time": _local_iso(now, tz, 1, 16)},
        "browsing": base | {"requirements": {"product_interest": "exploring options"}},
        "busy": base | {"call_status": "Rescheduled", "call_rescheduled_time": _local_iso(now, tz, 0, 17, 30)},
        "dropped": base | {"call_status": "Ended"},
        "stop": base | {"do_not_contact": True},
    }.get(key, base)


def _explain(plan: FollowUpPlan, analysis: CallAnalysis, attempt: int, sv: Services, now: datetime) -> list[str]:
    p, tz, why = sv.policy, sv.settings.tz, []
    out = analysis.outcome.value
    why.append(f"The call was classed as “{out}”.")
    if plan.mark_dnc:
        why.append("The customer asked not to be contacted, so they are added to do-not-call and everything else is cancelled.")
    if plan.next_call_at and plan.next_call_reason == "retry":
        why.append(f"Attempt {attempt} of {p.calls.max_attempts} is used, so the policy schedules a retry for "
                   f"{fmt_local(plan.next_call_at, tz)} (inside the retry window).")
    if plan.next_call_at and plan.next_call_reason == "callback":
        why.append(f"They asked for a callback, so it is booked for {fmt_local(plan.next_call_at, tz)} "
                   "(callbacks are not limited by max attempts, but must fall inside calling hours).")
    if plan.exhausted:
        why.append(f"Attempt {attempt} reaches the limit of {p.calls.max_attempts}, so no more automatic calls and no further emails.")
    if plan.meeting_at:
        why.append(f"A meeting time was confirmed, so it is booked for {fmt_local(plan.meeting_at, tz)} with reminders "
                   f"{', '.join(f'{m // 60}h' if m >= 60 else f'{m}m' for m in p.meeting.reminders_minutes_before)} before.")
    why.extend(f"Note: {n}." for n in plan.notes if n not in ("max attempts reached", "customer asked not to be contacted"))
    if out == "Connected" and not plan.meeting_at and not plan.mark_dnc:
        why.append("Connected without a booked meeting, so no automatic follow-up: this one is for a person to pick up.")
    return why


async def run_practice(sv: Services, persona_key: str, attempt: int, use_ai: bool, now: datetime) -> dict:
    persona = PERSONAS[persona_key]
    tz = sv.settings.tz
    pc = ProviderCall(provider_call_id="practice", status=persona.status, finished=True, answered=persona.answered,
                      duration_seconds=persona.duration, transcript=persona.transcript, customer_spoke=persona.spoke)
    analysis = decide_without_llm(pc)
    source = "rules"  # decided from call facts without any model
    if analysis is None:
        if use_ai:
            try:
                analysis, source = await sv.analysis.analyze(pc, now), "ai"
            except AnalysisError as exc:
                raise ValueError(f"AI analysis failed: {exc}") from exc
        else:
            analysis, source = apply_guardrails(CallAnalysis.model_validate(_scripted(persona_key, now, tz)), pc, tz, now), "scripted"
    plan = decide_followup(outcome=analysis.outcome, analysis=analysis, call_count=attempt, policy=sv.policy, tz=tz, now=now)

    customer = Customer(name="Alex (practice)", phone="+910000000000", email="alex@example.com")
    emails = []
    for e in plan.emails:
        subject, body = sv.email.render(e.kind, customer, e.extra)
        emails.append({"kind": e.kind, "subject": subject, "body": body,
                       "would_send": e.kind in sv.policy.notifications.enabled_kinds})
    return {
        "persona": {"key": persona.key, "label": persona.label, "blurb": persona.blurb},
        "attempt": attempt, "max_attempts": sv.policy.calls.max_attempts, "analysis_source": source,
        "transcript": persona.transcript, "provider": {"status": persona.status, "answered": persona.answered, "duration": persona.duration},
        "analysis": analysis.model_dump(),
        "plan": {"mark_dnc": plan.mark_dnc, "exhausted": plan.exhausted,
                 "next_call_at": plan.next_call_at, "next_call_reason": plan.next_call_reason,
                 "meeting_at": plan.meeting_at, "meeting_mode": plan.meeting_mode, "emails": emails},
        "reasons": _explain(plan, analysis, attempt, sv, now),
    }
