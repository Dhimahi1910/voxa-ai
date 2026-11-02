"""Pure analytics over a list of calls (small data: computed in Python, so it is portable across databases)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.timeutil import ensure_utc
from app.models import Call
from app.models.enums import CallState

ANSWERED = {"Connected", "Rescheduled", "Ended", "Not Responded"}


def build_analytics(calls: list[Call], tz: ZoneInfo, days: int, now: datetime) -> dict:
    dialed = [c for c in calls if c.state != CallState.FAILED.value]
    outcomes = Counter((c.outcome or "Pending") for c in dialed)
    answered = sum(1 for c in dialed if c.outcome in ANSWERED)
    connected = outcomes.get("Connected", 0)
    meetings = sum(1 for c in dialed if (c.analysis or {}).get("meeting_status") == "Scheduled")
    durations = [c.duration_seconds for c in dialed if c.duration_seconds]

    by_hour = [{"hour": h, "calls": 0, "connected": 0} for h in range(24)]
    start_day = (now.astimezone(tz) - timedelta(days=days - 1)).date()
    daily = {(start_day + timedelta(days=i)).isoformat(): {"calls": 0, "connected": 0} for i in range(days)}
    for c in dialed:
        local = ensure_utc(c.dialed_at or c.created_at).astimezone(tz)
        by_hour[local.hour]["calls"] += 1
        by_hour[local.hour]["connected"] += c.outcome == "Connected"
        slot = daily.get(local.date().isoformat())
        if slot is not None:
            slot["calls"] += 1
            slot["connected"] += c.outcome == "Connected"
    return {
        "days": days,
        "totals": {"calls": len(dialed), "failed": len(calls) - len(dialed),
                   "connect_rate": round(100 * connected / len(dialed)) if dialed else 0,
                   "avg_duration": round(sum(durations) / len(durations)) if durations else 0},
        "outcomes": dict(outcomes),
        "funnel": [{"label": "Dialed", "value": len(dialed)}, {"label": "Answered", "value": answered},
                   {"label": "Connected", "value": connected}, {"label": "Meeting booked", "value": meetings}],
        "by_hour": by_hour,
        "daily": [{"date": d, **v} for d, v in daily.items()],
    }
