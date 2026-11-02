from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services
from app.container import Services
from app.core.security import require_api_key
from app.core.timeutil import utcnow
from app.db import get_session
from app.models import Call, Customer, Meeting, Notification, ScheduledTask
from app.models.enums import TaskStatus
from app.repositories import call_repository as calls
from app.repositories import customer_repository as customers

router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(require_api_key)])


@router.get("/dashboard")
async def dashboard(sv: Services = Depends(get_services), session: AsyncSession = Depends(get_session)):
    tz = sv.settings.tz
    start_local = utcnow().astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    since = start_local.astimezone(timezone.utc)
    by_outcome = await calls.outcome_counts_since(session, since)

    q = (select(ScheduledTask, Customer).join(Customer, Customer.id == ScheduledTask.customer_id)
         .where(ScheduledTask.status == TaskStatus.PENDING.value).order_by(ScheduledTask.run_at).limit(20))
    upcoming = [{"id": t.id, "kind": t.kind, "reason": (t.payload or {}).get("reason", ""), "run_at": t.run_at,
                 "customer_id": c.id, "customer_name": c.name, "customer_phone": c.phone}
                for t, c in (await session.execute(q)).all()]

    mq = (select(Meeting, Customer).join(Customer, Customer.id == Meeting.customer_id)
          .where(Meeting.status == "scheduled", Meeting.scheduled_for >= utcnow()).order_by(Meeting.scheduled_for).limit(20))
    meetings = [{"id": m.id, "scheduled_for": m.scheduled_for, "mode": m.mode, "customer_id": c.id,
                 "customer_name": c.name, "customer_phone": c.phone} for m, c in (await session.execute(mq)).all()]

    async def count(model, *where) -> int:
        return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()

    milestones = {
        "calls": await count(Call, Call.state != "failed"),
        "connected": await count(Call, Call.outcome == "Connected"),
        "callbacks": await count(Call, Call.outcome == "Rescheduled"),
        "meetings": await count(Meeting),
        "emails": await count(Notification, Notification.status == "sent"),
    }

    return {
        "milestones": milestones,
        "today": {"calls": sum(by_outcome.values()), "by_outcome": by_outcome, "technical_failures": await calls.failed_since(session, since)},
        "totals": {"customers": await customers.count_customers(session), "do_not_call": await customers.count_dnc(session)},
        "upcoming_tasks": upcoming,
        "upcoming_meetings": meetings,
        "switches": {"real_calls": sv.settings.enable_real_calls, "email_sending": sv.settings.enable_email_sending,
                     "sheets_dry_run": sv.settings.sheets_dry_run, "scheduler": sv.settings.scheduler_enabled},
        "company": sv.business.company_name,
    }
