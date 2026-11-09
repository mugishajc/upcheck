"""
Periodic checks with APScheduler.

A single job wakes up every SCHEDULER_TICK_SECONDS and checks whichever sites
are due. That way new sites and changed intervals take effect without
re-registering jobs.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask

from .service import run_due_checks

log = logging.getLogger(__name__)

JOB_ID = "check-due-sites"


def tick(app: Flask) -> int:
    with app.app_context():
        checks = run_due_checks()
        # Read results before the app context closes and the session goes away.
        down = sum(1 for c in checks if not c.is_up)
    if checks:
        log.info("ran %d check(s), %d down", len(checks), down)
    return len(checks)


def configure(scheduler: BaseScheduler, app: Flask) -> BaseScheduler:
    scheduler.add_job(
        tick,
        "interval",
        seconds=app.config["SCHEDULER_TICK_SECONDS"],
        args=[app],
        id=JOB_ID,
        max_instances=1,  # never overlap a slow round of checks
        coalesce=True,
        replace_existing=True,
    )
    return scheduler


def start_background(app: Flask) -> BackgroundScheduler:
    """Run checks in a thread next to the web server (single process only)."""
    scheduler = configure(BackgroundScheduler(timezone="UTC"), app)
    scheduler.start()
    return scheduler


def run_blocking(app: Flask) -> None:
    """Run checks in the foreground. Used by `flask watch`."""
    scheduler = configure(BlockingScheduler(timezone="UTC"), app)
    tick(app)  # don't wait a full tick for the first round
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
