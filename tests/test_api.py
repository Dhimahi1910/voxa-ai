import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.models import Call
from tests.conftest import make_customer


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


async def test_dashboard_and_call_list(client, sv, sessions):
    from app.models import Customer
    from app.schemas.call import ProviderCall
    from app.workflows import calling_workflow as cw
    from tests.conftest import NOW
    from app.core import timeutil
    c = await make_customer(sessions)
    sv.voice.details["c1"] = ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False)
    async with sessions() as s:
        await cw.place_call(sv, s, await s.get(Customer, c.id), "k", "manual", now=NOW)
    h = {"x-api-key": "adminkey"}
    d = (await client.get("/api/dashboard", headers=h)).json()
    assert d["totals"]["customers"] == 1 and d["company"] == "voxai" and d["switches"]["real_calls"] is True
    lst = (await client.get(f"/api/calls?customer_id={c.id}", headers=h)).json()
    assert lst[0]["customer_name"] == "Asha" and lst[0]["customer_phone"] == c.phone
    assert (await client.get("/api/calls?outcome=Connected", headers=h)).json() == []
    assert (await client.get("/api/customers?q=asha", headers=h)).json()[0]["id"] == c.id
    assert (await client.get("/api/customers?q=zzz", headers=h)).json() == []
    assert (await client.get("/api/dashboard")).status_code == 401


async def test_create_customer_and_dnc_lifecycle(client):
    h = {"x-api-key": "adminkey"}
    assert (await client.post("/api/customers", json={"name": "Ravi", "phone": "98765 43210", "email": "r@x.com"}, headers=h)).status_code == 201
    dup = await client.post("/api/customers", json={"name": "Ravi2", "phone": "+919876543210"}, headers=h)
    assert dup.status_code == 409
    assert (await client.post("/api/customers", json={"name": "X", "phone": "12"}, headers=h)).status_code == 422
    assert (await client.post("/api/customers", json={"name": "X", "phone": "9876500000", "email": "bad"}, headers=h)).status_code == 422
    assert (await client.post("/api/customers", json={"name": "", "phone": "9876500000"}, headers=h)).status_code == 422

    assert (await client.post("/api/dnc", json={"phone": "9876543210", "reason": "asked"}, headers=h)).status_code == 204
    lst = (await client.get("/api/dnc", headers=h)).json()
    assert lst[0]["phone"] == "+919876543210" and lst[0]["reason"] == "asked"
    assert (await client.delete("/api/dnc?phone=9876543210", headers=h)).status_code == 204
    assert (await client.delete("/api/dnc?phone=9876543210", headers=h)).status_code == 404
    assert (await client.get("/api/dnc", headers=h)).json() == []
    assert (await client.get("/api/dnc")).status_code == 401
    assert (await client.delete("/api/dnc?phone=9876543210")).status_code == 401


async def test_settings_endpoint_has_no_secrets_and_requires_key(client, sv):
    assert (await client.get("/api/settings")).status_code == 401
    r = await client.get("/api/settings", headers={"x-api-key": "adminkey"})
    body = r.json()
    assert body["business"]["company"] == "voxai" and body["calling"]["max_attempts"] == 3
    assert set(body["integrations"]) == {"voice_provider", "google_sheets", "gmail", "llm", "webhook"}
    assert all(isinstance(v, bool) for v in body["integrations"].values())
    assert "adminkey" not in r.text and "whsecret" not in r.text
