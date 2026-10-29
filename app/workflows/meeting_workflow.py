"""Meeting records and their reminders."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Services
from app.core.timeutil import fmt_local
from app.models import Call, Customer, Meeting
from app.models.enums import MeetingStatus, TaskKind
from app.repositories import customer_repository as customers
from app.repositories import task_repository as tasks

log = logging.getLogger(__name__)


async def schedule_meeting(sv: Services, session: AsyncSession, customer: Customer, call: Call, when: datetime,
                           mode: str, now: datetime) -> Meeting | None:
    meeting = Meeting(customer_id=customer.id, call_id=call.id, scheduled_for=when, mode=mode)
    session.add(meeting)
    try:
        await session.commit()
    except IntegrityError:  # same meeting already recorded (reprocessed call)
        await session.rollback()
        meeting = (await session.execute(select(Meeting).where(
            Meeting.customer_id == customer.id, Meeting.scheduled_for == when))).scalar_one()
    customer.meeting_status = MeetingStatus.SCHEDULED.value
    await session.commit()
    await tasks.cancel_pending(session, customer.id, TaskKind.CALL)  # a booked meeting replaces further outreach
    for offset in sv.policy.meeting.reminders_minutes_before:
        run_at = when - timedelta(minutes=offset)
        if run_at > now:
            await tasks.enqueue(session, TaskKind.REMINDER, customer.id, run_at, f"reminder:{meeting.id}:{offset}",
                                {"meeting_id": meeting.id, "offset": offset})
    return meeting


async def send_reminder(sv: Services, session: AsyncSession, customer: Customer, payload: dict) -> str:
    meeting = await session.get(Meeting, payload["meeting_id"])
    if meeting is None or meeting.status != "scheduled":
        return "meeting_inactive"
    if await customers.is_dnc(session, customer.phone):
        return "dnc"
    tz = sv.settings.tz
    result = await sv.email.send(
        session, customer, "meeting_reminder", f"meeting_reminder:{meeting.id}:{payload['offset']}",
        {"meeting_time": fmt_local(meeting.scheduled_for, tz), "meeting_mode": (meeting.mode or "scheduled").lower()},
    )
    if result == "sent" and sv.sheets:
        await sv.sheets.update_customer(customer.phone, {"reminder_email_date": fmt_local(meeting.scheduled_for, tz)})
    return result
