"""APScheduler wiring. The scheduler only *triggers* jobs; durable state (tasks, calls) lives in PostgreSQL."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.container import Services
from app.scheduler import jobs

log = logging.getLogger(__name__)

JOBS = {"calling_run": jobs.job_calling_run, "due_tasks": jobs.job_due_tasks, "reconcile_calls": jobs.job_reconcile_calls}


def build_scheduler(sv: Services) -> AsyncIOScheduler:
    tz = sv.settings.tz
    sched = AsyncIOScheduler(timezone=tz)
    # max_instances=1 + coalesce: a slow run is never overlapped by itself; missed ticks collapse into one.
    common = dict(max_instances=1, coalesce=True, misfire_grace_time=300)
    d = sv.policy.daily_run
    sched.add_job(jobs.job_calling_run, CronTrigger(hour=d.hour, minute=d.minute, timezone=tz), args=[sv],
                  id="calling_run", **common)
    sched.add_job(jobs.job_due_tasks, "interval", seconds=30, args=[sv], id="due_tasks", **common)
    sched.add_job(jobs.job_reconcile_calls, "interval", minutes=2, args=[sv], id="reconcile_calls", **common)
    return sched
