"""Timezone-aware helpers: calling windows, slot clamping and tolerant datetime parsing."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser

from app.core.config import Policy, Window

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def next_allowed_time(dt: datetime, policy: Policy, tz: ZoneInfo, window: Window | None = None) -> datetime:
    """Earliest instant >= dt (UTC) inside the calling days and the given window (default: calling hours)."""
    start = _hm(window.start if window else policy.calling_hours.start)
    end = _hm(window.end if window else policy.calling_hours.end)
    days = set(policy.calling_hours.days)
    local = ensure_utc(dt).astimezone(tz)
    for offset in range(0, 15):
        day = (local + timedelta(days=offset)).date()
        if _DAYS[day.weekday()] not in days:
            continue
        w_start = datetime.combine(day, start, tz)
        w_end = datetime.combine(day, end, tz)
        candidate = max(local, w_start)
        if candidate < w_end:
            return candidate.astimezone(timezone.utc)
    return ensure_utc(dt)  # misconfigured days; do not loop forever


def in_calling_hours(dt: datetime, policy: Policy, tz: ZoneInfo) -> bool:
    return abs((next_allowed_time(dt, policy, tz) - ensure_utc(dt)).total_seconds()) < 1


def parse_when(text: str | None, tz: ZoneInfo, now: datetime | None = None) -> datetime | None:
    """Parse an ISO-ish or natural date/time string (as produced by the LLM) into UTC; None if unusable."""
    if not text or not text.strip():
        return None
    now_local = ensure_utc(now or utcnow()).astimezone(tz)
    try:
        dt = dtparser.parse(text, default=now_local.replace(hour=0, minute=0, second=0, microsecond=0), fuzzy=True)
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def fmt_local(dt: datetime | None, tz: ZoneInfo) -> str:
    return ensure_utc(dt).astimezone(tz).strftime("%d %b %Y, %I:%M %p IST" if tz.key == "Asia/Kolkata" else "%d %b %Y, %I:%M %p %Z") if dt else ""


def slot_after(now: datetime, delay_minutes: int, policy: Policy, tz: ZoneInfo, window: Window | None = None) -> datetime:
    """now + delay, preferring the start of `window` on the target day (so "tomorrow 10-11" means 10:00 tomorrow)."""
    target = ensure_utc(now) + timedelta(minutes=delay_minutes)
    if window:
        local = target.astimezone(tz)
        anchor = datetime.combine(local.date(), _hm(window.start), tz).astimezone(timezone.utc)
        if anchor > ensure_utc(now):
            target = anchor
    return next_allowed_time(target, policy, tz, window)
