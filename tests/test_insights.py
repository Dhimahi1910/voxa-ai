from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Call, Customer, DoNotCall, ScheduledTask
from app.schemas.call import ProviderCall
from app.workflows import calling_workflow as cw
from app.workflows.analytics import build_analytics
from app.workflows.simulation import PERSONAS
from tests.conftest import NOW, make_customer

H = {"x-api-key": "adminkey"}


# ---- practice room ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("persona,outcome", [("interested", "Connected"), ("browsing", "Connected"), ("busy", "Rescheduled"),
                                             ("no_answer", "Not Received"), ("silent", "Not Responded"), ("dropped", "Ended"),
                                             ("stop", "Connected")])
async def test_every_persona_reaches_expected_outcome(client, persona, outcome):
    r = await client.post("/api/practice/run", json={"persona": persona}, headers=H)
    assert r.status_code == 200
    assert r.json()["analysis"]["call_status"] == outcome and r.json()["reasons"]


async def test_practice_interested_books_meeting_and_previews_email(client):
    d = (await client.post("/api/practice/run", json={"persona": "interested"}, headers=H)).json()
    assert d["plan"]["meeting_at"] and d["plan"]["emails"][0]["kind"] == "meeting_confirmation"
    assert "Alex (practice)" in d["plan"]["emails"][0]["body"] and d["analysis_source"] == "scripted"


async def test_practice_no_answer_uses_rules_and_retries_until_exhausted(client):
    first = (await client.post("/api/practice/run", json={"persona": "no_answer", "attempt": 1}, headers=H)).json()
    last = (await client.post("/api/practice/run", json={"persona": "no_answer", "attempt": 3}, headers=H)).json()
    assert first["analysis_source"] == "rules" and first["plan"]["next_call_at"] and first["plan"]["emails"]
    assert last["plan"]["next_call_at"] is None and last["plan"]["exhausted"] and last["plan"]["emails"] == []


async def test_practice_stop_marks_dnc_and_sends_nothing(client):
    d = (await client.post("/api/practice/run", json={"persona": "stop"}, headers=H)).json()
    assert d["plan"]["mark_dnc"] and d["plan"]["emails"] == [] and d["plan"]["next_call_at"] is None


async def test_practice_writes_nothing_and_validates(client, sv, sessions):
    await client.post("/api/practice/run", json={"persona": "interested"}, headers=H)
    async with sessions() as s:
        assert (await s.execute(select(Call))).scalars().all() == []
        assert (await s.execute(select(ScheduledTask))).scalars().all() == []
        assert (await s.execute(select(DoNotCall))).scalars().all() == []
    assert not sv.voice.placed and sv.email._backend.sent == []
    assert (await client.post("/api/practice/run", json={"persona": "nope"}, headers=H)).status_code == 404
    assert (await client.post("/api/practice/run", json={"persona": "busy", "attempt": 0}, headers=H)).status_code == 422
    assert (await client.post("/api/practice/run", json={"persona": "busy", "use_ai": True}, headers=H)).status_code == 422
    assert (await client.post("/api/practice/run", json={"persona": "busy"})).status_code == 401
    assert len((await client.get("/api/practice/personas", headers=H)).json()["personas"]) == len(PERSONAS)


# ---- timeline + today's plan ----------------------------------------------------------------------------------------
async def test_timeline_shows_call_followup_and_email_with_reasons(client, sv, sessions):
    c = await make_customer(sessions)
    sv.voice.details["c1"] = ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False)
    async with sessions() as s:
        r = await cw.place_call(sv, s, await s.get(Customer, c.id), "k", "manual", now=NOW)
    await cw.process_call(sv, r.call_id, poll=False, now=NOW)
    ev = (await client.get(f"/api/customers/{c.id}/timeline", headers=H)).json()
    kinds = [e["kind"] for e in ev]
    assert "call" in kinds and "task" in kinds and "email" in kinds
    retry = next(e for e in ev if e["kind"] == "task")
    assert "Not Received" in retry["why"] and "retry" in retry["why"]
    assert (await client.get("/api/customers/999/timeline", headers=H)).status_code == 404
    assert (await client.get(f"/api/customers/{c.id}/timeline")).status_code == 401


async def test_plan_today_explains_who_is_called_and_who_is_not(client, sv, sessions):
    ok = await make_customer(sessions, phone="+919876500001", name="Ok")
    dnc = await make_customer(sessions, phone="+919876500002", name="Stop")
    async with sessions() as s:
        s.add(DoNotCall(phone=dnc.phone, reason="asked"))
        await s.commit()
    import app.api.insights as ins
    real = ins.utcnow
    ins.utcnow = lambda: NOW
    try:
        d = (await client.get("/api/plan/today", headers=H)).json()
    finally:
        ins.utcnow = real
    assert [c["id"] for c in d["will_call"]] == [ok.id]
    assert d["skipped"][0]["reason"] == "do_not_call" and "do-not-call" in d["skipped"][0]["reason_text"]
    assert d["in_calling_hours"] is True


# ---- analytics ------------------------------------------------------------------------------------------------------
def _call(outcome, hour, dur=30, meeting=False, state="completed"):
    return Call(customer_id=1, attempt_key=f"{outcome}{hour}", outcome=outcome, state=state, duration_seconds=dur,
                dialed_at=NOW.replace(hour=hour), created_at=NOW.replace(hour=hour),
                analysis={"meeting_status": "Scheduled" if meeting else "Not Scheduled"})


def test_build_analytics_funnel_hours_and_rates(sv):
    calls = [_call("Connected", 5, 60, True), _call("Connected", 5, 40), _call("Not Received", 6, 0), _call("Rescheduled", 7, 20),
             _call(None, 7, 0, state="failed")]
    a = build_analytics(calls, sv.settings.tz, 7, NOW)
    assert a["totals"] == {"calls": 4, "failed": 1, "connect_rate": 50, "avg_duration": 40}
    assert [f["value"] for f in a["funnel"]] == [4, 3, 2, 1]
    assert a["by_hour"][10]["calls"] == 2 and a["by_hour"][10]["connected"] == 2   # 05 UTC = 10:30 IST
    assert len(a["daily"]) == 7 and sum(d["calls"] for d in a["daily"]) == 4


async def test_analytics_endpoint(client):
    d = (await client.get("/api/analytics?days=7", headers=H)).json()
    assert d["days"] == 7 and len(d["by_hour"]) == 24
    assert (await client.get("/api/analytics?days=500", headers=H)).status_code == 422
    assert (await client.get("/api/analytics")).status_code == 401


# ---- calls filters + export -------------------------------------------------------------------------------------------
async def test_call_filters_and_csv_export_neutralises_formulas(client, sv, sessions):
    c = await make_customer(sessions, name='=HYPERLINK("http://evil")')
    sv.voice.details["c1"] = ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False)
    async with sessions() as s:
        r = await cw.place_call(sv, s, await s.get(Customer, c.id), "k", "manual", now=NOW)
    await cw.process_call(sv, r.call_id, poll=False, now=NOW)
    assert len((await client.get("/api/calls?q=HYPERLINK", headers=H)).json()) == 1
    assert (await client.get("/api/calls?q=zzz", headers=H)).json() == []
    assert (await client.get("/api/calls?outcome=Not%20Received&days=30", headers=H)).json()[0]["outcome"] == "Not Received"
    resp = await client.get("/api/calls/export", headers=H)
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in resp.text and ",=HYPERLINK" not in resp.text and '"=HYPERLINK' not in resp.text
    assert (await client.get("/api/calls/export")).status_code == 401


# ---- csv import ---------------------------------------------------------------------------------------------------------
CSV = "Name,Mobile,Email\nAsha,98765 43210,a@x.com\nBad,123,b@x.com\nRavi,9876500000,not-an-email\nDup,+919876543210,\nNeha,9876500001,\n,,\n"


async def test_import_dry_run_reports_without_writing(client, sessions):
    d = (await client.post("/api/customers/import", json={"csv": CSV, "dry_run": True}, headers=H)).json()
    assert d["valid"] == 2 and d["invalid_count"] == 2 and d["duplicates"] == 1 and d["created"] == 0
    assert {i["reason"] for i in d["invalid"]} == {"invalid phone number", "invalid email"}
    async with sessions() as s:
        assert (await s.execute(select(Customer))).scalars().all() == []


async def test_import_commit_creates_new_and_skips_existing(client, sessions):
    await make_customer(sessions, phone="+919876500001")
    d = (await client.post("/api/customers/import", json={"csv": CSV, "dry_run": False}, headers=H)).json()
    assert d["created"] == 1 and d["existing"] == 1
    async with sessions() as s:
        assert len((await s.execute(select(Customer))).scalars().all()) == 2


async def test_import_validation_and_auth(client):
    assert (await client.post("/api/customers/import", json={"csv": "Name\nA"}, headers=H)).status_code == 422
    assert (await client.post("/api/customers/import", json={"csv": "only header"}, headers=H)).status_code == 422
    assert (await client.post("/api/customers/import", json={"csv": "phone\n9876543210"})).status_code == 401


async def test_dashboard_has_milestones(client):
    m = (await client.get("/api/dashboard", headers=H)).json()["milestones"]
    assert set(m) == {"calls", "connected", "callbacks", "meetings", "emails"}
