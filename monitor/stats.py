"""Uptime and latency figures computed from the check history."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Integer, cast, func, select

from .extensions import db
from .models import Check, Site, utcnow

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


@dataclass
class SiteStats:
    checks: int
    up_checks: int
    avg_latency_ms: int | None
    max_latency_ms: int | None

    @property
    def uptime_percent(self) -> float | None:
        if self.checks == 0:
            return None
        return round(self.up_checks * 100 / self.checks, 2)

    def to_dict(self) -> dict:
        return {
            "checks": self.checks,
            "uptime_percent": self.uptime_percent,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
        }


def site_stats(site_id: int, since: datetime) -> SiteStats:
    row = db.session.execute(
        select(
            func.count(Check.id),
            func.coalesce(func.sum(cast(Check.is_up, Integer)), 0),
            func.avg(Check.latency_ms),
            func.max(Check.latency_ms),
        ).where(Check.site_id == site_id, Check.checked_at >= since)
    ).one()
    checks, up, avg, peak = row
    return SiteStats(
        checks=checks,
        up_checks=int(up),
        avg_latency_ms=round(avg) if avg is not None else None,
        max_latency_ms=peak,
    )


def stats_by_window(site_id: int, now: datetime | None = None) -> dict[str, dict]:
    now = now or utcnow()
    return {name: site_stats(site_id, now - span).to_dict() for name, span in WINDOWS.items()}


def recent_checks(site_id: int, limit: int = 50) -> list[Check]:
    return list(
        db.session.scalars(
            select(Check)
            .where(Check.site_id == site_id)
            .order_by(Check.checked_at.desc(), Check.id.desc())
            .limit(limit)
        )
    )


def overview(now: datetime | None = None) -> list[dict]:
    """One row per site for the dashboard and /api/summary."""
    now = now or utcnow()
    since = now - WINDOWS["24h"]
    rows = []
    for site in db.session.scalars(select(Site).order_by(Site.name)):
        rows.append({"site": site, "day": site_stats(site.id, since)})
    return rows
