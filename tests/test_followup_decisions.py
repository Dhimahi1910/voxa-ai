from datetime import timedelta
from zoneinfo import ZoneInfo

from app.core.config import load_policy, Policy, Settings
from app.core.timeutil import next_allowed_time, parse_when
from app.models.enums import CallOutcome as O
from app.schemas.transcript import CallAnalysis
from app.workflows.followup_workflow import decide_followup
from tests.conftest import NOW

TZ = ZoneInfo("Asia/Kolkata")
POLICY = load_policy(Settings(_env_file=None))  # the shipped config/policy.yaml


def plan(outcome, count=1, policy=None, **analysis):
    a = CallAnalysis.model_validate({"call_status": outcome.value, **analysis})
    return decide_followup(outcome=outcome, analysis=a, call_count=count, policy=policy or POLICY, tz=TZ, now=NOW)


def test_not_received_schedules_retry_next_day_in_window_and_emails():
    p = plan(O.NOT_RECEIVED)
    local = p.next_call_at.astimezone(TZ)
    assert (local.day, local.hour) == (28, 10) and p.next_call_reason == "retry"
    assert [e.kind for e in p.emails] == ["missed_call"]


def test_each_outcome_maps_to_its_email():
    assert plan(O.NOT_RESPONDED).emails[0].kind == "not_responded"
    assert plan(O.ENDED).emails[0].kind == "disconnected"


def test_max_attempts_stops_retries_and_emails():
    p = plan(O.NOT_RECEIVED, count=3)
    assert p.next_call_at is None and p.exhausted and not p.emails


def test_retry_can_be_disabled_by_config():
    pol = POLICY.model_copy(deep=True)
    pol.retry.ended.enabled = False
    assert plan(O.ENDED, policy=pol).next_call_at is None


def test_callback_at_requested_time():
    p = plan(O.RESCHEDULED, call_rescheduled_time="2026-10-27T17:30")
    assert p.next_call_at.astimezone(TZ).strftime("%H:%M") == "17:30" and p.next_call_reason == "callback"
    assert p.emails[0].kind == "callback_confirmation"


def test_callback_ignores_max_attempts():
    assert plan(O.RESCHEDULED, count=9, call_rescheduled_time="2026-10-27T17:30").next_call_at is not None


def test_callback_unparseable_uses_default_delay():
    p = plan(O.RESCHEDULED, call_rescheduled_time="whenever")
    assert p.next_call_at == NOW + timedelta(minutes=60) and any("default" in n for n in p.notes)


def test_callback_outside_hours_moved_to_next_window():
    p = plan(O.RESCHEDULED, call_rescheduled_time="2026-10-27T22:00")
    assert p.next_call_at.astimezone(TZ).strftime("%d %H") == "28 09"


def test_confirmed_meeting_creates_plan_and_confirmation_email():
    p = plan(O.CONNECTED, meeting_status="Scheduled", preferred_meeting_time="2026-10-28T16:00", meeting_preference="Virtual")
    assert p.meeting_at is not None and p.emails[0].kind == "meeting_confirmation"


def test_meeting_in_past_not_scheduled():
    p = plan(O.CONNECTED, meeting_status="Scheduled", preferred_meeting_time="2026-10-20T16:00")
    assert p.meeting_at is None and not p.emails


def test_connected_without_meeting_has_no_followup():
    p = plan(O.CONNECTED)
    assert not p.next_call_at and not p.emails


def test_do_not_contact_overrides_everything():
    p = plan(O.RESCHEDULED, do_not_contact=True, call_rescheduled_time="2026-10-27T17:30")
    assert p.mark_dnc and not p.next_call_at and not p.emails


def test_next_allowed_time_skips_sunday():
    sat_evening = parse_when("2026-10-31T20:00", TZ)
    assert next_allowed_time(sat_evening, Policy(), TZ).astimezone(TZ).strftime("%a %H") == "Mon 09"
