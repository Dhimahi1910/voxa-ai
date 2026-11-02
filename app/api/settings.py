from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_services
from app.container import Services
from app.core.security import require_api_key

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(require_api_key)])


@router.get("/settings")
async def read_settings(sv: Services = Depends(get_services)):
    """Read-only summary for the console. Contains no secrets: integrations are reported as configured yes/no only."""
    s, p, b = sv.settings, sv.policy, sv.business
    return {
        "business": {"company": b.company_name, "agent": b.agent_name, "requirements": [r.label or r.key for r in b.requirements]},
        "switches": {"real_calls": s.enable_real_calls, "email_sending": s.enable_email_sending,
                     "sheets_dry_run": s.sheets_dry_run, "scheduler": s.scheduler_enabled},
        "calling": {
            "timezone": s.timezone,
            "hours": f"{p.calling_hours.start}–{p.calling_hours.end}",
            "days": [d.capitalize() for d in p.calling_hours.days],
            "daily_run": f"{p.daily_run.hour:02d}:{p.daily_run.minute:02d}",
            "max_attempts": p.calls.max_attempts,
            "min_gap_minutes": p.calls.min_gap_minutes,
            "batch_limit": p.calls.batch_limit,
        },
        "retry": {
            name: {"enabled": rule.enabled, "delay_minutes": rule.delay_minutes,
                   "window": f"{rule.window.start}–{rule.window.end}" if rule.window else ""}
            for name, rule in (("not_received", p.retry.not_received), ("not_responded", p.retry.not_responded), ("ended", p.retry.ended))
        },
        "meeting_reminders_minutes_before": p.meeting.reminders_minutes_before,
        "integrations": {
            "voice_provider": bool(s.voice_api_key.get_secret_value() and s.voice_agent_id is not None),
            "google_sheets": sv.sheets is not None,
            "gmail": bool(s.gmail_sender and s.google_application_credentials),
            "llm": bool(s.llm_api_key.get_secret_value()),
            "webhook": bool(s.public_base_url and s.webhook_secret.get_secret_value()),
        },
    }
