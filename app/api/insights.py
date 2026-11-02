"""Read-mostly endpoints behind the console's richer screens: timeline, today's plan, analytics, practice, CSV import."""
from __future__ import annotations

import csv
import io
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.phone import normalize_phone
from app.core.security import require_api_key
from app.core.timeutil import in_calling_hours, utcnow
from app.db import get_session
from app.models import Call, Customer, DoNotCall, Meeting, Notification, ScheduledTask
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers
from app.schemas.customer import ImportRequest, PracticeRequest
from app.workflows import calling_workflow
from app.workflows.analytics import build_analytics
from app.workflows.simulation import PERSONAS, run_practice

router = APIRouter(prefix="/api", tags=["insights"], dependencies=[Depends(require_api_key)])
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ALIASES = {
    "name": {"name", "full name", "fullname", "customer", "customer name"},
    "phone": {"phone", "phone_number", "phone number", "mobile", "mobile number", "number", "contact"},
    "email": {"email", "e-mail", "mail", "email address"},
}


# ---------------------------------------------------------------------------------------------------- timeline
@router.get("/customers/{customer_id}/timeline")
async def timeline(customer_id: int, session: AsyncSession = Depends(get_session)):
    c = await customers.get(session, customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    ev: list[dict] = []
    their_calls = (await session.execute(select(Call).where(Call.customer_id == customer_id))).scalars().all()
    by_id = {k.id: k for k in their_calls}
    why_call = {"scheduled": "Part of the daily calling run.", "retry": "A scheduled retry after the previous attempt.",
                "callback": "The callback the customer asked for.", "manual": "Started by hand from the console."}
    for k in their_calls:
        tone = {"Connected": "good", "Rescheduled": "info", "Not Received": "warn", "Not Responded": "warn", "Ended": "warn"}.get(k.outcome or "", "muted")
        if k.state in ("failed", "unknown"):
            tone, title = "bad", f"Call {k.state} (technical)"
        else:
            title = f"Call: {k.outcome or 'in progress'}"
        ev.append({"at": k.dialed_at or k.created_at, "kind": "call", "title": title, "tone": tone, "call_id": k.id,
                   "detail": (k.summary or k.error or "")[:200], "why": why_call.get(k.reason, "")})
    tasks = (await session.execute(select(ScheduledTask).where(ScheduledTask.customer_id == customer_id))).scalars().all()
    for t in tasks:
        src = by_id.get(int(t.dedupe_key.split(":")[2])) if t.dedupe_key.startswith("call:followup:") else None
        if t.kind == "reminder":
            title, why = "Meeting reminder", "Sent before the meeting, as set in the reminder schedule."
        else:
            kind = t.payload.get("reason", "retry")
            title = "Callback" if kind == "callback" else "Retry call"
            why = (f"Call #{src.id} ended as “{src.outcome}”, so the policy scheduled this {kind}." if src else
                   "Scheduled by the follow-up policy.")
        ev.append({"at": t.run_at, "kind": "task", "title": f"{title} ({t.status})", "tone": "info" if t.status == "pending" else "muted",
                   "detail": t.last_error or "", "why": why})
    for n in (await session.execute(select(Notification).where(Notification.customer_id == customer_id))).scalars():
        ev.append({"at": n.sent_at or n.created_at, "kind": "email", "title": f"Email: {n.kind.replace('_', ' ')} ({n.status})",
                   "tone": "good" if n.status == "sent" else "bad" if n.status == "failed" else "muted",
                   "detail": n.error or "", "why": "Sent automatically for that call outcome." if n.status == "sent" else
                   "Email sending is off or this was a dry run." if n.status == "skipped" else ""})
    for m in (await session.execute(select(Meeting).where(Meeting.customer_id == customer_id))).scalars():
        ev.append({"at": m.scheduled_for, "kind": "meeting", "title": f"Meeting {m.status}", "tone": "good",
                   "detail": m.mode, "why": "Agreed during the call."})
    d = await session.get(DoNotCall, c.phone)
    if d:
        ev.append({"at": d.created_at, "kind": "dnc", "title": "Added to do-not-call", "tone": "bad", "detail": d.reason,
                   "why": "No further calls or emails will be sent."})
    ev.sort(key=lambda e: e["at"])
    return ev


# ---------------------------------------------------------------------------------------------------- today's plan
@router.get("/plan/today")
async def plan_today(sv: Services = Depends(get_services), session: AsyncSession = Depends(get_session)):
    """Who the next calling run would dial, and why everyone else is skipped. Read-only."""
    now = utcnow()
    ctx = await calling_workflow.eligibility_context(sv, session, now)
    everyone = list(await customers.list_customers(session, limit=100000))
    selected, skipped = calling_workflow.select_customers(everyone, ctx, sv.policy.calls.batch_limit)
    by_id = {c.id: c for c in everyone}
    ch = sv.policy.calling_hours
    return {
        "in_calling_hours": in_calling_hours(now, sv.policy, sv.settings.tz),
        "window": f"{ch.start}–{ch.end}", "days": [d.capitalize() for d in ch.days], "batch_limit": sv.policy.calls.batch_limit,
        "will_call": [{"id": c.id, "name": c.name, "phone": c.phone} for c in selected],
        "skipped": [{"id": i, "name": by_id[i].name, "phone": by_id[i].phone, "reason": r,
                     "reason_text": calling_workflow.SKIP_TEXT.get(r, r)} for i, r in skipped.items()],
    }


# ---------------------------------------------------------------------------------------------------- analytics
@router.get("/analytics")
async def analytics(days: int = Query(14, ge=1, le=90), sv: Services = Depends(get_services),
                    session: AsyncSession = Depends(get_session)):
    now = utcnow()
    since = now - timedelta(days=days)
    rows = (await session.execute(select(Call).where(Call.created_at >= since))).scalars().all()
    return build_analytics(list(rows), sv.settings.tz, days, now)


# ---------------------------------------------------------------------------------------------------- practice room
@router.get("/practice/personas")
async def personas(sv: Services = Depends(get_services)):
    return {"max_attempts": sv.policy.calls.max_attempts, "ai_available": bool(sv.settings.llm_api_key.get_secret_value()),
            "personas": [{"key": p.key, "label": p.label, "blurb": p.blurb} for p in PERSONAS.values()]}


@router.post("/practice/run")
async def practice(body: PracticeRequest, sv: Services = Depends(get_services)):
    """Simulation only: nothing is dialled, emailed or stored."""
    if body.persona not in PERSONAS:
        raise HTTPException(404, "unknown persona")
    if body.use_ai and not sv.settings.llm_api_key.get_secret_value():
        raise HTTPException(422, "AI analysis is not configured (no LLM_API_KEY)")
    try:
        return await run_practice(sv, body.persona, body.attempt, body.use_ai, utcnow())
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc


# ---------------------------------------------------------------------------------------------------- CSV import
def _column(header: list[str], logical: str) -> int | None:
    for i, h in enumerate(header):
        if h.strip().lower() in _ALIASES[logical]:
            return i
    return None


@router.post("/customers/import")
async def import_customers(body: ImportRequest, sv: Services = Depends(get_services),
                           session: AsyncSession = Depends(get_session)):
    """Validate (dry_run=true) or create customers from CSV text. Invalid, duplicate and existing rows are reported, never fatal."""
    rows = list(csv.reader(io.StringIO(body.csv)))
    if len(rows) < 2:
        raise HTTPException(422, "The CSV needs a header row and at least one data row")
    if len(rows) - 1 > 5000:
        raise HTTPException(422, "Too many rows (max 5000 per import)")
    header = rows[0]
    ip, i_name, i_mail = _column(header, "phone"), _column(header, "name"), _column(header, "email")
    if ip is None:
        raise HTTPException(422, "No phone column found. Name it phone, mobile or phone_number")
    country = sv.policy.calls.default_country
    valid, invalid, seen = [], [], set()
    existing = duplicates = 0
    for n, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        get = lambda i: row[i].strip() if i is not None and i < len(row) else ""  # noqa: E731
        phone = normalize_phone(get(ip), country)
        email = get(i_mail)
        if not phone:
            invalid.append({"row": n, "reason": "invalid phone number", "value": get(ip)[:30]})
        elif email and not _EMAIL.match(email):
            invalid.append({"row": n, "reason": "invalid email", "value": email[:50]})
        elif phone in seen:
            duplicates += 1
        elif await customers.get_by_phone(session, phone):
            existing += 1
        else:
            seen.add(phone)
            valid.append({"name": get(i_name)[:200], "phone": phone, "email": email})
    created = 0
    if not body.dry_run and valid:
        for v in valid:
            session.add(Customer(name=v["name"], phone=v["phone"], email=v["email"]))
        await session.commit()
        created = len(valid)
    return {"dry_run": body.dry_run, "total": len(rows) - 1, "valid": len(valid), "invalid": invalid[:50], "invalid_count": len(invalid),
            "duplicates": duplicates, "existing": existing, "created": created, "preview": valid[:5]}
