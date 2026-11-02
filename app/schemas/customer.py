from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class DncOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone: str
    reason: str
    source: str
    created_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=5, max_length=20)
    email: str = Field(default="", max_length=320, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ImportRequest(BaseModel):
    csv: str = Field(max_length=1_000_000)
    dry_run: bool = True


class PracticeRequest(BaseModel):
    persona: str = Field(max_length=40)
    attempt: int = Field(default=1, ge=1, le=10)
    use_ai: bool = False
