from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    email: str
    call_count: int
    last_outcome: str | None
    last_call_at: datetime | None
    meeting_status: str
    exhausted: bool


class SheetCustomer(BaseModel):
    """A customer row as read from the spreadsheet."""

    row_number: int
    name: str = ""
    phone: str
    email: str = ""
    do_not_call: bool = False
    call_count: int = 0
    call_status: str = ""
    meeting_status: str = ""
    extra: dict[str, str] = {}


class DncRequest(BaseModel):
    phone: str
    reason: str = ""
