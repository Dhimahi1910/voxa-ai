import json

import pytest
from pydantic import ValidationError

from app.core.config import Business, Requirement
from app.schemas.call import ProviderCall
from app.schemas.transcript import CallAnalysis
from app.services.ai_analysis_service import AIAnalysisService, AnalysisError, decide_without_llm
from app.services.voice_service import normalize_call
from tests.conftest import BUSINESS, NOW, FakeLLM


def svc(settings, reply):
    llm = FakeLLM(reply)
    return AIAnalysisService(llm, settings, BUSINESS), llm


def good(**kw):
    return json.dumps({"requirements": {"product_interest": "voice agents", "scale": "20 users", "invented": "x"},
                       "call_status": "Connected", "meeting_status": "Not Scheduled"} | kw)


CONNECTED = ProviderCall(provider_call_id="c", status="completed", finished=True, answered=True, duration_seconds=60,
                         transcript="Agent: hi\nCustomer: we want voice agents for 20 users", customer_spoke=True)


def test_unanswered_is_not_received_without_llm():
    r = decide_without_llm(ProviderCall(provider_call_id="c", status="no-answer", finished=True, answered=False))
    assert r.call_status == "Not Received"


def test_answered_but_silent_is_not_responded_without_llm():
    r = decide_without_llm(ProviderCall(provider_call_id="c", status="completed", finished=True, answered=True,
                                        transcript="Agent: hello?", customer_spoke=False))
    assert r.call_status == "Not Responded"


def test_normal_conversation_needs_llm():
    assert decide_without_llm(CONNECTED) is None


async def test_llm_extraction_validated_and_unknown_keys_dropped(sv):
    s, llm = svc(sv.settings, good())
    r = await s.analyze(CONNECTED, NOW)
    assert r.call_status == "Connected"
    assert r.requirements == {"product_interest": "voice agents", "scale": "20 users"}  # "invented" key removed


async def test_missing_details_stay_empty_not_invented(sv):
    s, _ = svc(sv.settings, '{"call_status": "connected"}')
    r = await s.analyze(CONNECTED, NOW)
    assert r.requirements == {} and r.preferred_meeting_time == "" and r.call_status == "Connected"


async def test_meeting_scheduled_without_usable_time_is_downgraded(sv):
    s, _ = svc(sv.settings, good(meeting_status="Scheduled", preferred_meeting_time=""))
    assert (await s.analyze(CONNECTED, NOW)).meeting_status == "Not Scheduled"


async def test_meeting_scheduled_with_time_kept(sv):
    s, _ = svc(sv.settings, good(meeting_status="Scheduled", preferred_meeting_time="2026-10-28T16:00"))
    assert (await s.analyze(CONNECTED, NOW)).meeting_status == "Scheduled"


async def test_llm_cannot_claim_connected_when_provider_says_customer_silent(sv):
    call = CONNECTED.model_copy(update={"customer_spoke": None, "transcript": "x"})
    call2 = call.model_copy(update={"customer_spoke": False})
    # decide_without_llm already handles answered+silent; guardrail covers answered=None
    call2 = call2.model_copy(update={"answered": None})
    s, _ = svc(sv.settings, good())
    assert (await s.analyze(call2, NOW)).call_status == "Not Responded"


async def test_invalid_json_is_repaired_once_then_fails(sv):
    s, llm = svc(sv.settings, "not json")
    with pytest.raises(AnalysisError):
        await s.analyze(CONNECTED, NOW)
    assert llm.calls == 2


async def test_markdown_fenced_json_accepted(sv):
    s, _ = svc(sv.settings, "```json\n" + good() + "\n```")
    assert (await s.analyze(CONNECTED, NOW)).call_status == "Connected"


def test_unknown_call_status_rejected():
    with pytest.raises(ValidationError):
        CallAnalysis.model_validate({"call_status": "Maybe"})


@pytest.mark.parametrize("status", ["Connected", "Not Received", "Not Responded", "Rescheduled", "Ended"])
def test_all_five_outcomes_accepted(status):
    assert CallAnalysis.model_validate({"call_status": status.upper()}).call_status == status


def test_normalize_turns_and_customer_spoke():
    raw = {"success": True, "data": {"conversationId": "z", "status": "completed", "duration": 12,
           "transcript": [{"role": "assistant", "text": "hello"}, {"role": "user", "text": "hi there"}],
           "summary": "s", "recordingUrl": "http://r"}}
    pc = normalize_call(raw, "z")
    assert pc.customer_spoke is True and pc.answered is True and pc.recording_url == "http://r" and "Customer: hi there" in pc.transcript


def test_normalize_no_answer_status():
    pc = normalize_call({"data": {"status": "no-answer"}}, "z")
    assert pc.answered is False and pc.finished
