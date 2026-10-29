from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, UTCDateTime


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    sheet_data: Mapped[dict] = mapped_column(default=dict)  # other sheet columns, passed to the agent as context
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    last_outcome: Mapped[str | None] = mapped_column(String(30), default=None)
    last_call_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    meeting_status: Mapped[str] = mapped_column(String(30), default="Not Scheduled")
    exhausted: Mapped[bool] = mapped_column(Boolean, default=False)  # retries used up; no more automatic calls
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class DoNotCall(Base):
    __tablename__ = "do_not_call"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual | sheet | call
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
