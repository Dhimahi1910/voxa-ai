from datetime import timedelta

from sqlalchemy import select

from app.models import Call, Customer, DoNotCall, Meeting, Notification, ScheduledTask
from app.schemas.call import ProviderCall
from app.scheduler import jobs
from app.services.google_sheets_service import CLEAR, GoogleSheetsService, col_letter, merge_updates
from app.workflows import calling_workflow as cw
from tests.conftest import COLUMNS, NOW, FakeSheetsAPI, make_customer

HEADER = ["Name", "phone_number", "Email", "Call Count", "Call Status", "Summary", "Product Interest", "Scale",
          "Next Attempt", "Callback Time", "Transcript"]


def finished(text="Agent: hi\nCustomer: we need voice agents", **kw):
    return ProviderCall(provider_call_id="c1", status="completed", finished=True, answered=True, duration_seconds=30,
                        transcript=text, customer_spoke=True, summary="sum", recording_url="http://rec", **kw)


# ---- sheets -------------------------------------------------------------------------------------------------
def test_merge_never_blanks_existing_values():
    assert merge_updates({"summary": "old"}, {"summary": "", "transcript": "t", "x": None}) == {"transcript": "t"}


def test_merge_skips_unchanged_and_supports_explicit_clear():
    assert merge_updates({"a": "1", "b": "x"}, {"a": "1", "b": CLEAR, "c": CLEAR}) == {"b": ""}


def test_col_letter():
    assert [col_letter(i) for i in (0, 25, 26, 27)] == ["A", "Z", "AA", "AB"]


async def test_fetch_customers_maps_columns_and_skips_bad_phones(sv):
    api = FakeSheetsAPI([HEADER + ["Industry"],
                         ["Asha", "98765 43210", "a@x.com", "2", "", "", "", "", "", "", "", "Retail"],
                         ["Bad", "123", "b@x.com"], ["Dup", "+919876543210"]])
    svc = GoogleSheetsService(sv.settings, api, COLUMNS)
    rows = await svc.fetch_customers()
    assert [r.phone for r in rows] == ["+919876543210", "+919876543210"]
    assert rows[0].call_count == 2 and rows[0].extra == {"Industry": "Retail"} and rows[0].row_number == 2


async def test_update_writes_only_changes_in_right_cells(sv):
    api = FakeSheetsAPI([HEADER, ["Asha", "9876543210", "a@x.com", "1", "", "keep me"]])
    svc = GoogleSheetsService(sv.settings, api, COLUMNS)
    changed = await svc.update_customer("+919876543210", {"summary": "", "call_count": 2, "call_status": "Connected", "req.scale": "20 users"})
    assert changed == {"call_count": "2", "call_status": "Connected", "req.scale": "20 users"}
    assert api.writes == [{"D2": "2", "E2": "Connected", "H2": "20 users"}]


async def test_sheet_dry_run_does_not_write(sv):
    sv.settings.sheets_dry_run = True
    api = FakeSheetsAPI([HEADER, ["Asha", "9876543210"]])
    await GoogleSheetsService(sv.settings, api, COLUMNS).update_customer("+919876543210", {"call_status": "Connected"})
    assert api.writes == []


async def test_missing_sheet_column_is_skipped_not_fatal(sv):
    api = FakeSheetsAPI([["Name", "phone_number"], ["Asha", "9876543210"]])
    assert await GoogleSheetsService(sv.settings, api, COLUMNS).update_customer("+919876543210", {"summary": "x"}) == {}


# ---- email --------------------------------------------------------------------------------------------------
async def test_email_sent_once_per_dedupe_key(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        assert await sv.email.send(s, c, "missed_call", "k1") == "sent"
        assert await sv.email.send(s, c, "missed_call", "k1") == "duplicate"
    assert len(sv.email._backend.sent) == 1
    assert "voxai" in sv.email._backend.sent[0][1] and "Veesha" in sv.email._backend.sent[0][2]


async def test_email_dry_run_sends_nothing_but_is_recorded(sv, sessions):
    sv.settings.enable_email_sending = False
    c = await make_customer(sessions)
    async with sessions() as s:
        assert await sv.email.send(s, c, "missed_call", "k1") == "skipped"
        assert (await s.execute(select(Notification))).scalar_one().status == "skipped"
    assert sv.email._backend.sent == []


async def test_email_requires_valid_address_and_enabled_kind(sv, sessions):
    c = await make_customer(sessions, email="nope")
    async with sessions() as s:
        assert await sv.email.send(s, c, "missed_call", "k") == "no_email"
        sv.policy.notifications.enabled_kinds = ["callback_confirmation"]
        c.email = "a@x.com"
        assert await sv.email.send(s, c, "missed_call", "k") == "disabled"


async def test_email_failure_recorded_not_raised(sv, sessions):
    def boom(*a):
        raise RuntimeError("smtp down")
    sv.email._backend.send = boom
    c = await make_customer(sessions)
    async with sessions() as s:
        assert await sv.email.send(s, c, "missed_call", "k") == "failed"


# ---- full pipeline ------------------------------------------------------------------------------------------
async def dial(sv, sessions, details, **cust):
    c = await make_customer(sessions, **cust)
    sv.voice.details["c1"] = details
    async with sessions() as s:
        c = await s.get(Customer, c.id)
        r = await cw.place_call(sv, s, c, "k", "manual", now=NOW)
    assert r.status == "placed"
    return c.id, r.call_id


async def test_not_received_pipeline_records_retries_emails_and_updates_sheet(sv, sessions):
    sv.fake_sheet.rows = [HEADER, ["Asha", "9876543210", "asha@example.com", "0"]]
    cid, call_id = await dial(sv, sessions, ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False))
    assert await cw.process_call(sv, call_id, poll=False) == "processed"
    async with sessions() as s:
        call = await s.get(Call, call_id)
        cust = await s.get(Customer, cid)
        task = (await s.execute(select(ScheduledTask))).scalar_one()
    assert (call.state, call.outcome) == ("completed", "Not Received") and cust.call_count == 1
    assert task.kind == "call" and task.payload["reason"] == "retry"
    assert [e[1].split()[0] for e in sv.email._backend.sent] == ["missed_call"]
    assert sv.fake_llm.calls == 0
    written = {k: v for w in sv.fake_sheet.writes for k, v in w.items()}
    assert written["E2"] == "Not Received" and written["D2"] == "1"


async def test_processing_twice_is_idempotent(sv, sessions):
    cid, call_id = await dial(sv, sessions, ProviderCall(provider_call_id="c1", status="no-answer", finished=True, answered=False))
    assert await cw.process_call(sv, call_id, poll=False) == "processed"
    assert await cw.process_call(sv, call_id, poll=False) == "skipped"
    async with sessions() as s:
        assert len((await s.execute(select(ScheduledTask))).scalars().all()) == 1
    assert len(sv.email._backend.sent) == 1


async def test_meeting_scheduled_creates_meeting_reminders_and_cancels_calls(sv, sessions):
    sv.fake_llm.reply = ('{"call_status":"Connected","meeting_status":"Scheduled","preferred_meeting_time":"2026-10-29T16:00",'
                         '"meeting_preference":"Virtual","requirements":{"scale":"20 users"}}')
    cid, call_id = await dial(sv, sessions, finished())
    sv.policy.post_call.poll_attempts = 1
    assert await cw.process_call(sv, call_id, poll=False, now=NOW) == "processed"
    async with sessions() as s:
        meeting = (await s.execute(select(Meeting))).scalar_one()
        reminders = (await s.execute(select(ScheduledTask).where(ScheduledTask.kind == "reminder"))).scalars().all()
        cust = await s.get(Customer, cid)
    assert meeting.mode == "Virtual" and cust.meeting_status == "Scheduled" and len(reminders) == 2
    assert [e[1].split()[0] for e in sv.email._backend.sent] == ["meeting_confirmation"]


async def test_due_reminder_sends_once_even_if_job_runs_twice(sv, sessions):
    sv.fake_llm.reply = '{"call_status":"Connected","meeting_status":"Scheduled","preferred_meeting_time":"2026-10-27T18:00"}'
    cid, call_id = await dial(sv, sessions, finished())
    await cw.process_call(sv, call_id, poll=False, now=NOW)
    import app.repositories.task_repository as tr
    real = tr.utcnow
    tr.utcnow = lambda: NOW + timedelta(hours=8)   # after 1h-before reminder time (meeting 12:30 UTC)
    try:
        await jobs.job_due_tasks(sv)
        await jobs.job_due_tasks(sv)
    finally:
        tr.utcnow = real
    kinds = [e[1].split()[0] for e in sv.email._backend.sent]
    # the 24h reminder is already in the past so it is never created; the 1h one is sent exactly once
    assert kinds.count("meeting_reminder") == 1 and kinds.count("meeting_confirmation") == 1


async def test_do_not_contact_adds_dnc_cancels_tasks_and_sends_nothing(sv, sessions):
    sv.fake_llm.reply = '{"call_status":"Connected","do_not_contact":true}'
    cid, call_id = await dial(sv, sessions, finished("Agent: hi\nCustomer: stop calling me"))
    await cw.process_call(sv, call_id, poll=False)
    async with sessions() as s:
        assert (await s.execute(select(DoNotCall))).scalar_one().source == "call"
        assert (await s.execute(select(ScheduledTask))).scalars().all() == []
    assert sv.email._backend.sent == []
    sv.voice.placed.clear()
    async with sessions() as s:
        c = await s.get(Customer, cid)
        assert (await cw.place_call(sv, s, c, "again", "manual", now=NOW + timedelta(days=1))).status == "skipped"


async def test_analysis_failure_keeps_transcript_and_retries_later(sv, sessions):
    sv.fake_llm.reply = "garbage"
    cid, call_id = await dial(sv, sessions, finished())
    assert await cw.process_call(sv, call_id, poll=False) == "pending"
    async with sessions() as s:
        call = await s.get(Call, call_id)
        assert call.transcript and call.processed_at is None
    sv.fake_llm.reply = '{"call_status":"Connected"}'
    assert await cw.process_call(sv, call_id, poll=False) == "processed"


async def test_provider_not_finished_stays_pending(sv, sessions):
    cid, call_id = await dial(sv, sessions, ProviderCall(provider_call_id="c1", status="in-progress", finished=False))
    assert await cw.process_call(sv, call_id, poll=False) == "pending"


async def test_reconciler_releases_interrupted_dials_as_unknown(sv, sessions):
    c = await make_customer(sessions)
    from app.repositories import call_repository as calls
    async with sessions() as s:
        call = await calls.reserve_attempt(s, c.id, "k", "", "manual")
        call.state, call.created_at = "dialing", NOW - timedelta(hours=1)
        await s.commit()
    import app.scheduler.jobs as j
    real = j.utcnow
    j.utcnow = lambda: NOW
    try:
        out = await jobs.job_reconcile_calls(sv)
    finally:
        j.utcnow = real
    assert out["unknown"] == 1 and not sv.voice.placed
