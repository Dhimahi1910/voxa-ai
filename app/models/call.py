from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, UTCDateTime
from app.models.enums import CallState, NotificationStatus, TaskStatus


_INFLIGHT = "state IN ('pending','dialing','initiated') AND processed_at IS NULL"


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        # Database-level guarantee: at most one live call per customer, even across processes or racing jobs.
        Index("uq_calls_one_inflight_per_customer", "customer_id", unique=True,
              postgresql_where=text(_INFLIGHT), sqlite_where=text(_INFLIGHT)),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    # Unique per intended attempt (e.g. "run:<run_id>:<customer>" or "task:<id>"). Makes duplicate dialing impossible.
    attempt_key: Mapped[str] = mapped_column(String(120), unique=True)
    run_id: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(30), default="scheduled")  # scheduled | retry | callback | manual
    state: Mapped[str] = mapped_column(String(20), default=CallState.PENDING.value, index=True)
    outcome: Mapped[str | None] = mapped_column(String(30), default=None)
    provider_call_id: Mapped[str | None] = mapped_column(String(100), unique=True, default=None)
    provider_sid: Mapped[str | None] = mapped_column(String(100), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    dialed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    transcript: Mapped[str | None] = mapped_column(Text, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    recording_url: Mapped[str | None] = mapped_column(Text, default=None)
    provider_raw: Mapped[dict | None] = mapped_column(default=None)
    analysis: Mapped[dict | None] = mapped_column(default=None)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    process_attempts: Mapped[int] = mapped_column(Integer, default=0)
    sheet_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ScheduledTask(Base):
    """Durable job queue: survives restarts, so pending callbacks/retries/reminders are never lost."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    to_email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default=NotificationStatus.SENDING.value)
    provider_message_id: Mapped[str | None] = mapped_column(String(100), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
