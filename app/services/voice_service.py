"""Voice provider integration (Edesy Voice Agent API) plus a dry-run stand-in.

Documented at https://edesy.in/docs/voice-agent/api (POST /api/v1/calls, GET /api/v1/calls/{id}).
The docs do not specify the call-detail response fields or the webhook payload, so responses are
normalised tolerantly in `normalize_call`; verify against a real call before relying on any single field.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.schemas.call import ProviderCall

log = logging.getLogger(__name__)

_NOT_ANSWERED = {"no-answer", "no_answer", "noanswer", "busy", "not_connected", "not-connected", "unanswered",
                 "canceled", "cancelled", "rejected", "failed", "unreachable"}
_FINISHED = _NOT_ANSWERED | {"completed", "ended", "complete", "hangup", "disconnected", "done"}
_USER_ROLES = {"user", "customer", "caller", "human", "client"}
_LABEL = re.compile(r"^\s*(user|customer|caller|human|client|agent|assistant|bot|ai)\s*[:\-]\s*(.*)$", re.I)


class VoiceAPIError(Exception):
    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.status, self.code, self.retryable = status, code, retryable


@dataclass
class PlacedCall:
    call_id: str
    sid: str | None = None
    status: str = "initiated"


class VoiceClient(Protocol):
    async def place_call(self, phone: str, variables: dict, metadata: dict, callback_url: str | None) -> PlacedCall: ...
    async def get_call(self, call_id: str) -> ProviderCall: ...
    async def update_agent(self, fields: dict) -> None: ...


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def _transcript_from_turns(turns: list) -> tuple[str, bool | None]:
    lines, spoke = [], False
    for t in turns:
        if not isinstance(t, dict):
            continue
        role = str(_first(t, "role", "speaker", "from") or "").lower()
        text = str(_first(t, "text", "content", "message", "transcript") or "").strip()
        if not text:
            continue
        is_user = role in _USER_ROLES
        spoke = spoke or is_user
        lines.append(f"{'Customer' if is_user else 'Agent'}: {text}")
    return "\n".join(lines), (spoke if lines else None)


def _spoke_from_text(text: str) -> bool | None:
    """Only conclusive when the text carries speaker labels."""
    user = agent = False
    for line in text.splitlines():
        m = _LABEL.match(line)
        if not m:
            continue
        is_user = m.group(1).lower() in _USER_ROLES
        if is_user and m.group(2).strip():
            user = True
        elif not is_user:
            agent = True
    if user:
        return True
    return False if agent else None


def normalize_call(raw: dict, call_id: str) -> ProviderCall:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    status = str(_first(data, "status", "callStatus", "call_status", "disposition") or "").lower()
    transcript_raw = _first(data, "fullText", "full_text", "transcript", "transcriptText", "turns", "messages")
    spoke: bool | None = None
    if isinstance(transcript_raw, list):
        transcript, spoke = _transcript_from_turns(transcript_raw)
    else:
        transcript = str(transcript_raw or "").strip()
        spoke = _spoke_from_text(transcript) if transcript else None
    analysis = data.get("call_analysis") if isinstance(data.get("call_analysis"), dict) else {}
    summary = _first(data, "summary", "callSummary", "call_summary") or analysis.get("call_summary") or ""
    duration = _first(data, "duration", "durationSeconds", "duration_seconds", "callDuration")
    try:
        duration = int(float(duration)) if duration is not None else None
    except (TypeError, ValueError):
        duration = None
    answered: bool | None = None
    if status in _NOT_ANSWERED:
        answered = False
    elif status in {"completed", "answered", "in-progress", "in_progress", "ended", "complete"}:
        answered = True
    finished = status in _FINISHED or bool(_first(data, "endedAt", "ended_at"))
    return ProviderCall(
        provider_call_id=str(_first(data, "conversationId", "conversation_id", "call_id", "id") or call_id),
        status=status, finished=finished, answered=answered, duration_seconds=duration,
        transcript=transcript, customer_spoke=spoke, summary=str(summary).strip(),
        recording_url=str(_first(data, "recordingUrl", "recording_url", "recording") or ""), raw=data,
    )


class EdesyVoiceClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._s = settings
        self._http = client or httpx.AsyncClient(
            base_url=settings.voice_api_base_url.rstrip("/"), timeout=settings.http_timeout_seconds
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._s.voice_api_key.get_secret_value()}", "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, *, retries: int = 0, **kw) -> dict:
        """`retries` > 0 only for idempotent reads. Dialing is never retried: a retry could ring the customer twice."""
        for attempt in range(retries + 1):
            try:
                resp = await self._http.request(method, path, headers=self._headers(), **kw)
            except httpx.TransportError as exc:
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise VoiceAPIError(f"transport error: {type(exc).__name__}", retryable=True) from exc
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(2 ** attempt)
                continue
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if resp.status_code >= 400 or body.get("success") is False:
                raise VoiceAPIError(
                    str(body.get("error") or f"HTTP {resp.status_code}"), status=resp.status_code,
                    code=body.get("code"), retryable=resp.status_code >= 500 or resp.status_code == 429,
                )
            return body
        raise AssertionError("unreachable")

    async def place_call(self, phone: str, variables: dict, metadata: dict, callback_url: str | None) -> PlacedCall:
        if self._s.voice_agent_id is None:
            raise VoiceAPIError("VOICE_AGENT_ID is not configured")
        body: dict[str, Any] = {"agentId": self._s.voice_agent_id, "phoneNumber": phone,
                                "variables": variables, "metadata": metadata}
        if self._s.voice_from_number:
            body["fromNumber"] = self._s.voice_from_number
        if self._s.voice_provider:
            body["provider"] = self._s.voice_provider
        if callback_url:
            body["callbackUrl"] = callback_url
        data = (await self._request("POST", "/api/v1/calls", json=body)).get("data", {})
        call_id = data.get("conversationId")
        if not call_id:
            raise VoiceAPIError("provider response had no conversationId")
        return PlacedCall(call_id=str(call_id), sid=data.get("callSid"), status=data.get("status", "initiated"))

    async def get_call(self, call_id: str) -> ProviderCall:
        body = await self._request("GET", f"/api/v1/calls/{call_id}", retries=3)
        call = normalize_call(body, call_id)
        if not call.transcript:  # a dedicated transcript endpoint exists in the OpenAPI spec
            try:
                tr = await self._request("GET", f"/api/v1/calls/{call_id}/transcript", retries=2)
                t = normalize_call(tr, call_id)
                call.transcript, call.customer_spoke = t.transcript, t.customer_spoke
            except VoiceAPIError as exc:
                log.info("transcript endpoint unavailable", extra={"call_id": call_id, "error": str(exc)})
        return call

    async def update_agent(self, fields: dict) -> None:
        if self._s.voice_agent_id is None:
            raise VoiceAPIError("VOICE_AGENT_ID is not configured")
        await self._request("PATCH", f"/api/v1/agents/{self._s.voice_agent_id}", json=fields)

    async def aclose(self) -> None:
        await self._http.aclose()


class DryRunVoiceClient:
    """Never touches the network. `scenario` picks the canned post-call result."""

    TRANSCRIPTS = {
        "connected": (
            "Agent: Hello, this is Veesha from voxai. Is this a good time?\n"
            "Customer: Yes, tell me.\n"
            "Agent: You enquired about our services. What are you looking for?\n"
            "Customer: We want voice agents for our sales team, around 20 users.\n"
            "Agent: Great. Can we set up a virtual meeting with our team?\n"
            "Customer: Yes, tomorrow at 4 PM works."
        ),
        "not_responded": "Agent: Hello? Hello, can you hear me?\nAgent: I will call again later. Goodbye.",
    }

    def __init__(self, scenario: str = "connected"):
        self.scenario = scenario
        self.placed: list[dict] = []

    async def place_call(self, phone: str, variables: dict, metadata: dict, callback_url: str | None) -> PlacedCall:
        self.placed.append({"phone": phone, "variables": variables, "metadata": metadata})
        log.info("DRY-RUN: call not placed", extra={"phone_tail": phone[-4:]})
        return PlacedCall(call_id=f"dryrun-{uuid.uuid4().hex[:12]}", sid=None, status="initiated")

    async def get_call(self, call_id: str) -> ProviderCall:
        if self.scenario == "not_received":
            return ProviderCall(provider_call_id=call_id, status="no-answer", finished=True, answered=False)
        text = self.TRANSCRIPTS.get(self.scenario, self.TRANSCRIPTS["connected"])
        return ProviderCall(
            provider_call_id=call_id, status="completed", finished=True, answered=True, duration_seconds=42,
            transcript=text, customer_spoke=_spoke_from_text(text), summary="Dry-run call summary.",
            recording_url="https://example.invalid/recording.wav",
        )

    async def update_agent(self, fields: dict) -> None:
        log.info("DRY-RUN: agent not updated", extra={"fields": sorted(fields)})


def build_voice_client(settings: Settings) -> VoiceClient:
    return EdesyVoiceClient(settings) if settings.enable_real_calls else DryRunVoiceClient()
