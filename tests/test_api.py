import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.models import Call
from tests.conftest import make_customer


@pytest.fixture
async def client(sv, sessions, monkeypatch):
    from pydantic import SecretStr
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


async def test_health_is_open(client):
    assert (await client.get("/health")).status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/api/customers"), ("get", "/api/calls/1"),
                                         ("post", "/api/calls/start"), ("post", "/api/jobs/trigger")])
async def test_protected_routes_reject_missing_or_wrong_key(client, method, path):
    assert (await getattr(client, method)(path)).status_code == 401
    assert (await getattr(client, method)(path, headers={"x-api-key": "wrong"})).status_code == 401


async def test_fails_closed_when_no_keys_configured(client, sv):
    from pydantic import SecretStr
    sv.settings.api_keys = SecretStr("")
    assert (await client.get("/api/customers", headers={"x-api-key": ""})).status_code == 503


async def test_customers_list_and_get(client, sessions):
    c = await make_customer(sessions)
    h = {"x-api-key": "adminkey"}
    assert (await client.get("/api/customers", headers=h)).json()[0]["phone"] == c.phone
    assert (await client.get(f"/api/customers/{c.id}", headers=h)).json()["name"] == "Asha"
    assert (await client.get("/api/customers/999", headers=h)).status_code == 404


async def test_start_call_validates_input(client):
    h = {"x-api-key": "adminkey"}
    assert (await client.post("/api/calls/start", json={}, headers=h)).status_code == 422
    assert (await client.post("/api/calls/start", json={"phone": "12"}, headers=h)).status_code == 422
    assert (await client.post("/api/jobs/trigger", json={"job": "rm -rf"}, headers=h)).status_code == 422


async def test_webhook_requires_secret(client):
    assert (await client.post("/api/webhooks/voice", json={})).status_code == 401
    assert (await client.post("/api/webhooks/voice?token=bad", json={})).status_code == 401


async def test_webhook_unknown_call_ignored_and_known_call_idempotent(client, sv, sessions):
    from app.schemas.call import ProviderCall
    from app.workflows import calling_workflow as cw
    from app.models import Customer
    from tests.conftest import NOW
    r = await client.post("/api/webhooks/voice?token=whsecret", json={"conversationId": "nope"})
    assert r.json()["status"] == "ignored"
    c = await make_customer(sessions)
    sv.voice.details["c1"] = ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False)
    async with sessions() as s:
        await cw.place_call(sv, s, await s.get(Customer, c.id), "k", "manual", now=NOW)
    h = {"x-webhook-secret": "whsecret"}
    first = await client.post("/api/webhooks/voice", json={"data": {"conversationId": "c1"}}, headers=h)
    second = await client.post("/api/webhooks/voice", json={"data": {"conversationId": "c1"}}, headers=h)
    assert (first.json()["status"], second.json()["status"]) == ("accepted", "duplicate")
    assert len(sv.email._backend.sent) == 1   # processed once despite two deliveries


async def test_trigger_job_runs_and_is_authenticated(client, sv):
    r = await client.post("/api/jobs/trigger", json={"job": "due_tasks"}, headers={"x-api-key": "adminkey"})
    assert r.status_code == 200 and r.json()["job"] == "due_tasks"
