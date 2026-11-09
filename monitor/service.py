"""Runs checks, records the results and raises alerts on state changes."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

import requests
from flask import current_app
from sqlalchemy import delete, select

from .alerts import AlertEvent, Notifier, build_notifiers, dispatch
from .checker import CheckResult, check_url
from .extensions import db
from .models import Check, Site, utcnow

log = logging.getLogger(__name__)

CheckFn = Callable[..., CheckResult]


def run_check(
    site: Site,
    notifiers: list[Notifier] | None = None,
    session: requests.Session | None = None,
    check_fn: CheckFn = check_url,
    now: datetime | None = None,
) -> Check:
    now = now or utcnow()
    result = check_fn(
        site.url,
        timeout=site.timeout_seconds,
        expected_status=site.expected_status,
        keyword=site.keyword,
        session=session,
        user_agent=current_app.config.get("USER_AGENT", "flask-url-monitor"),
    )

    check = Check(
        site=site,
        checked_at=now,
        is_up=result.is_up,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        error=result.error,
    )
    db.session.add(check)

    previous = site.is_up
    site.is_up = result.is_up
    site.last_checked_at = now
    changed = previous is not None and previous != result.is_up
    if previous is None or changed:
        site.last_change_at = now
    db.session.commit()

    # Alert on transitions only, and also when the very first check fails.
    if changed or (previous is None and not result.is_up):
        event = AlertEvent(
            site_name=site.name,
            url=site.url,
            is_up=result.is_up,
            occurred_at=now,
            status_code=result.status_code,
            error=result.error,
        )
        dispatch(event, notifiers if notifiers is not None else build_notifiers(current_app.config))
    return check


def due_sites(now: datetime | None = None) -> list[Site]:
    now = now or utcnow()
    sites = db.session.scalars(select(Site).where(Site.is_active.is_(True))).all()
    return [site for site in sites if site.is_due(now)]


def run_due_checks(now: datetime | None = None, **kwargs) -> list[Check]:
    """Check every active site whose interval has elapsed. Used by the scheduler."""
    now = now or utcnow()
    results = []
    with requests.Session() as session:
        for site in due_sites(now):
            try:
                results.append(run_check(site, session=session, now=now, **kwargs))
            except Exception:
                db.session.rollback()
                log.exception("check for %s crashed", site.name)
    return results


def prune_history(older_than_days: int, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=older_than_days)
    result = db.session.execute(delete(Check).where(Check.checked_at < cutoff))
    db.session.commit()
    return result.rowcount or 0
