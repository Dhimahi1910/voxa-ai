from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.container import Services
from app.core.config import Business, Policy, Requirement, Settings
from app.models import Base, Customer
from app.schemas.call import ProviderCall
from app.services.ai_analysis_service import AIAnalysisService
from app.services.email_service import EmailService
from app.services.google_sheets_service import GoogleSheetsService
from app.services.voice_service import PlacedCall

# Tue 2026-10-27 06:00 UTC = 11:30 IST: inside calling hours
NOW = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)

BUSINESS = Business(company_name="voxai", agent_name="Veesha", company_phone="123", company_website="voxai.test",
                    business_description="voice agents",
                    requirements=[Requirement(key="product_interest"), Requirement(key="scale")])
TEMPLATES = {"signature": "$agent_name | $company_name", "templates": {
    k: {"subject": f"{k} $company_name", "body": "Hi $name $next_attempt $callback_time $meeting_time"}
    for k in ("missed_call", "not_responded", "disconnected", "callback_confirmation", "meeting_confirmation", "meeting_reminder")}}
COLUMNS = {"name": "Name", "phone": "phone_number", "email": "Email", "do_not_call": "Do Not Call", "call_status": "Call Status",
           "call_datetime": "Call Datetime", "call_count": "Call Count", "transcript": "Transcript", "summary": "Summary",
           "recording_url": "Call Recording", "meeting_status": "Meeting Status", "meeting_availability": "Meeting Availability",
           "meeting_preference": "Meeting Preference", "callback_time": "Callback Time", "next_attempt_at": "Next Attempt",
           "reminder_email_date": "reminder_email_date", "req.product_interest": "Product Interest", "req.scale": "Scale"}


class FakeVoice:
    def __init__(self):
        self.placed: list[dict] = []
        self.details: dict[str, ProviderCall] = {}
        self.error: Exception | None = None
        self.n = 0

    async def place_call(self, phone, variables, metadata, callback_url):
        if self.error:
            raise self.error
        self.n += 1
        self.placed.append({"phone": phone, "variables": variables, "metadata": metadata})
        return PlacedCall(call_id=f"c{self.n}")

    async def get_call(self, call_id):
        return self.details[call_id]

    async def update_agent(self, fields): ...


class FakeLLM:
    def __init__(self, reply: str = '{"call_status": "Connected"}'):
        self.reply, self.calls = reply, 0

    async def complete_json(self, system, user):
        self.calls += 1
        return self.reply


class FakeSheetsAPI:
    def __init__(self, rows):
        self.rows, self.writes = rows, []

    def read_all(self):
        return self.rows

    def write_cells(self, cells):
        self.writes.append(cells)


class FakeEmailBackend:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))
        return f"m{len(self.sent)}"


@pytest.fixture
def policy():
    p = Policy()
    p.calls.pause_between_calls_seconds = 0
    p.post_call.poll_interval_seconds = 0
    p.notifications.enabled_kinds = list(TEMPLATES["templates"])
    return p


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def sv(sessions, policy):
    settings = Settings(_env_file=None, enable_email_sending=True, sheets_dry_run=False, enable_real_calls=True)
    llm = FakeLLM()
    sheets_api = FakeSheetsAPI([["Name", "phone_number", "Email", "Call Count"]])
    s = Services(
        settings=settings, policy=policy, business=BUSINESS, sessions=sessions, voice=FakeVoice(),
        analysis=AIAnalysisService(llm, settings, BUSINESS),
        email=EmailService(settings, policy, BUSINESS, FakeEmailBackend(), TEMPLATES),
        sheets=GoogleSheetsService(settings, sheets_api, COLUMNS),
    )
    s.fake_llm, s.fake_sheet = llm, sheets_api  # type: ignore[attr-defined]
    return s


async def make_customer(sessions, **kw) -> Customer:
    defaults = dict(phone="+919876543210", name="Asha", email="asha@example.com")
    async with sessions() as s:
        c = Customer(**(defaults | kw))
        s.add(c)
        await s.commit()
        return c


@pytest.fixture
async def client(sv, sessions):
    import httpx
    from pydantic import SecretStr
    from app.core.config import get_settings
    from app.main import app
    sv.settings.api_keys = SecretStr("adminkey")
    sv.settings.webhook_secret = SecretStr("whsecret")
    app.state.services = sv
    app.dependency_overrides[get_settings] = lambda: sv.settings
    from app.db import get_session

    async def _session():
        async with sessions() as s:
            yield s
    app.dependency_overrides[get_session] = _session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


