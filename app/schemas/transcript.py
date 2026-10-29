"""Structured result of the LLM transcript analysis (validated; never trusts raw model output)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import CallOutcome, MeetingStatus

_OUTCOMES = {o.value.lower(): o.value for o in CallOutcome}
_MEETING = {m.value.lower(): m.value for m in MeetingStatus}


class CallAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Business-specific facts, keyed by the `requirements` list in config/business.yaml.
    requirements: dict[str, str] = {}
    meeting_preference: str = ""       # Virtual | Face-to-Face | ""
    preferred_meeting_time: str = ""   # ISO 8601 (local) when a concrete time was agreed, else the customer's words
    call_rescheduled_time: str = ""    # same convention
    call_status: Literal["Connected", "Not Received", "Not Responded", "Rescheduled", "Ended"]
    meeting_status: Literal["Scheduled", "Not Scheduled"] = "Not Scheduled"
    do_not_contact: bool = False       # customer explicitly asked not to be called again

    @field_validator("meeting_preference", "preferred_meeting_time", "call_rescheduled_time", mode="before")
    @classmethod
    def _text(cls, v):
        return "" if v is None else str(v).strip()

    @field_validator("requirements", mode="before")
    @classmethod
    def _reqs(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k): ("" if x is None else str(x).strip()) for k, x in v.items()}

    @field_validator("call_status", mode="before")
    @classmethod
    def _outcome(cls, v):
        return _OUTCOMES.get(str(v).strip().lower(), v)

    @field_validator("meeting_status", mode="before")
    @classmethod
    def _meeting(cls, v):
        return _MEETING.get(str(v or "Not Scheduled").strip().lower(), v)

    @property
    def outcome(self) -> CallOutcome:
        return CallOutcome(self.call_status)
