from datetime import timedelta

from sqlalchemy import select

from app.models import Call, Customer, DoNotCall
from app.models.enums import CallState, TaskKind
from app.repositories import customer_repository as customers
from app.repositories import task_repository as tasks
from app.schemas.call import ProviderCall
from app.workflows import calling_workflow as cw
from tests.conftest import NOW, make_customer


def ctx(sv, **kw):
    return cw.EligibilityContext(now=kw.pop("now", NOW), policy=sv.policy, tz=sv.settings.tz, **kw)


async def test_skip_reasons(sv, sessions):
    c = await make_customer(sessions)
    assert cw.skip_reason(c, ctx(sv)) is None
    assert cw.skip_reason(c, ctx(sv, dnc={c.phone})) == "do_not_call"
    assert cw.skip_reason(c, ctx(sv, in_flight={c.id})) == "call_in_progress"
    assert cw.skip_reason(c, ctx(sv, has_pending_call_task={c.id})) == "followup_already_scheduled"
    c.call_count = 3
    assert cw.skip_reason(c, ctx(sv)) == "max_attempts"
    c.call_count, c.meeting_status = 0, "Scheduled"
    assert cw.skip_reason(c, ctx(sv)) == "meeting_scheduled"
    c.meeting_status, c.last_outcome = "Not Scheduled", "Connected"
    assert cw.skip_reason(c, ctx(sv)) == "already_contacted"
    c.last_outcome, c.last_call_at = "Not Received", NOW - timedelta(minutes=30)
    assert cw.skip_reason(c, ctx(sv)) == "called_recently"
    c.last_call_at = NOW - timedelta(hours=5)
    assert cw.skip_reason(c, ctx(sv)) is None


async def test_outside_calling_hours_and_sunday(sv, sessions):
    c = await make_customer(sessions)
    night = NOW.replace(hour=20)           # 01:30 IST
    sunday = NOW + timedelta(days=5)       # 2026-11-01 is a Sunday
    assert cw.skip_reason(c, ctx(sv, now=night)) == "outside_calling_hours"
    assert cw.skip_reason(c, ctx(sv, now=sunday)) == "outside_calling_hours"


async def test_select_dedupes_same_phone_and_respects_limit(sv, sessions):
    a = await make_customer(sessions)
    b = await make_customer(sessions, phone="+919876500000")
    from app.models import Customer
    dup = Customer(id=99, phone=a.phone, name="dup")
    sel, skipped = cw.select_customers([a, dup, b], ctx(sv), limit=10)
    assert [c.id for c in sel] == [a.id, b.id] and skipped == {99: "duplicate_in_run"}
    sel, skipped = cw.select_customers([a, b], ctx(sv), limit=1)
    assert [c.id for c in sel] == [a.id] and skipped[b.id] == "batch_limit"


async def test_run_never_dials_same_customer_twice_in_a_run(sv, sessions):
    await make_customer(sessions)
    s1 = await cw.run_calling(sv, run_id="r1", now=NOW)
    s2 = await cw.run_calling(sv, run_id="r1", now=NOW)  # job retry / restart with the same run id
    assert s1.placed == 1 and s2.placed == 0
    assert len(sv.voice.placed) == 1


async def test_unique_attempt_key_blocks_duplicate(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        r1 = await cw.place_call(sv, s, c, "k1", "manual", now=NOW)
        sv.voice.details["c1"] = ProviderCall(provider_call_id="c1", finished=True, answered=False, status="no-answer")
        await cw.process_call(sv, r1.call_id, poll=False)
        r2 = await cw.place_call(sv, s, c, "k1", "manual", now=NOW)
    assert r1.status == "placed" and r2.status == "duplicate" and len(sv.voice.placed) == 1


async def test_database_blocks_two_live_calls_for_one_customer(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        assert await cw.place_call(sv, s, c, "a", "manual", now=NOW) is not None
        from app.repositories import call_repository as calls
        assert await calls.reserve_attempt(s, c.id, "b", "", "manual") is None  # partial unique index


async def test_dnc_customer_never_dialled(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        await customers.add_dnc(s, c.phone, "asked")
        r = await cw.place_call(sv, s, c, "k", "manual", now=NOW)
    assert r.status == "skipped" and not sv.voice.placed


async def test_dial_outside_hours_refused(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        r = await cw.place_call(sv, s, c, "k", "manual", now=NOW.replace(hour=20))
    assert r.status == "outside_hours" and not sv.voice.placed


async def test_transport_error_marks_unknown_and_is_not_redialled(sv, sessions):
    from app.services.voice_service import VoiceAPIError
    c = await make_customer(sessions)
    sv.voice.error = VoiceAPIError("boom", retryable=True)  # no HTTP status -> outcome unknown
    async with sessions() as s:
        r = await cw.place_call(sv, s, c, "k", "manual", now=NOW)
        call = await s.get(Call, r.call_id)
        assert r.status == "unknown" and call.state == CallState.UNKNOWN.value
        sv.voice.error = None
        assert (await cw.place_call(sv, s, c, "k2", "manual", now=NOW)).detail == "call_in_progress"
    assert not sv.voice.placed


async def test_provider_rejection_is_technical_failure_with_bounded_retry(sv, sessions):
    from app.services.voice_service import VoiceAPIError
    c = await make_customer(sessions)
    sv.voice.error = VoiceAPIError("busy", status=503, retryable=True)
    async with sessions() as s:
        c = await s.get(Customer, c.id)
        r = await cw.place_call(sv, s, c, "k", "manual", now=NOW)
        call = await s.get(Call, r.call_id)
        assert r.status == "failed" and call.state == "failed" and call.outcome is None  # not a customer outcome
        assert c.call_count == 0
        assert c.id in await tasks.customers_with_pending(s, TaskKind.CALL)


async def test_task_claim_is_exclusive(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        await tasks.enqueue(s, TaskKind.CALL, c.id, NOW, "t1")
        assert await tasks.enqueue(s, TaskKind.CALL, c.id, NOW, "t1") is None  # idempotent enqueue
        first = await tasks.claim_due(s, NOW)
        second = await tasks.claim_due(s, NOW)
    assert len(first) == 1 and second == []


async def test_stale_running_tasks_recovered_after_restart(sv, sessions):
    c = await make_customer(sessions)
    async with sessions() as s:
        await tasks.enqueue(s, TaskKind.CALL, c.id, NOW, "t1")
        await tasks.claim_due(s, NOW)
        assert await tasks.requeue_stale(s, 15, NOW + timedelta(minutes=20)) == 1
        assert len(await tasks.claim_due(s, NOW + timedelta(minutes=20))) == 1


async def test_webhook_event_idempotent(sv, sessions):
    from app.repositories import call_repository as calls
    async with sessions() as s:
        assert await calls.record_webhook_event(s, "voice:c1:end", {}) is True
        assert await calls.record_webhook_event(s, "voice:c1:end", {}) is False
