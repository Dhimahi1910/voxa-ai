from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderCall(BaseModel):
    """Provider-neutral view of a finished (or in-progress) call, normalised by the voice client."""

    provider_call_id: str
    status: str = ""                     # raw provider status, lower-cased
    finished: bool = False
    answered: bool | None = None         # None = provider did not say
    duration_seconds: int | None = None
    transcript: str = ""
    customer_spoke: bool | None = None   # None = cannot tell from the data we have
    summary: str = ""
    recording_url: str = ""
    raw: dict = Field(default_factory=dict)


class StartCallRequest(BaseModel):
    customer_id: int | None = None
    phone: str | None = Field(default=None, max_length=20)

    def has_target(self) -> bool:
        return bool(self.customer_id or self.phone)


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    reason: str
    state: str
    outcome: str | None
    provider_call_id: str | None
    error: str | None
    dialed_at: datetime | None
    duration_seconds: int | None
    summary: str | None
    recording_url: str | None
    analysis: dict | None
    processed_at: datetime | None
    created_at: datetime


class CallDetailOut(CallOut):
    transcript: str | None


class JobTriggerRequest(BaseModel):
    job: str = Field(pattern="^(calling_run|due_tasks|reconcile_calls)$")
