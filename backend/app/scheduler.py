"""APScheduler wiring for the periodic control + forecast loops."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .orchestrator import Orchestrator

log = logging.getLogger("scheduler")


def build_scheduler(orch: Orchestrator) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        orch.control_cycle,
        IntervalTrigger(seconds=orch.cfg.control.loop_interval_seconds),
        id="control_cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        orch.forecast_cycle,
        IntervalTrigger(minutes=orch.cfg.control.forecast_interval_minutes),
        id="forecast_cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        orch.maintenance_cycle,
        IntervalTrigger(hours=24),
        id="maintenance_cycle",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def reschedule_jobs(scheduler: AsyncIOScheduler, orch: Orchestrator) -> None:
    """Apply updated control intervals after a UI config reload."""
    scheduler.reschedule_job(
        "control_cycle",
        trigger=IntervalTrigger(seconds=orch.cfg.control.loop_interval_seconds),
    )
    scheduler.reschedule_job(
        "forecast_cycle",
        trigger=IntervalTrigger(minutes=orch.cfg.control.forecast_interval_minutes),
    )
    log.info(
        "Scheduler rescheduled: control=%ss forecast=%sm",
        orch.cfg.control.loop_interval_seconds,
        orch.cfg.control.forecast_interval_minutes,
    )
