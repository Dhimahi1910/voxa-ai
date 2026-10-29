from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, UTCDateTime


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("customer_id", "scheduled_for"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"), default=None)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime)
    mode: Mapped[str] = mapped_column(String(30), default="")  # Virtual | Face-to-Face | ""
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled | cancelled | completed
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
