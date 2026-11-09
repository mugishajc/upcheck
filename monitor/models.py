from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow() -> datetime:
    """Naive UTC timestamp. SQLite has no timezone type, so everything is stored as UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


class Site(db.Model):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    # When set, only this status code counts as up. Otherwise any status below 400 does.
    expected_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional text that must appear in the response body.
    keyword: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Latest known state, kept here so the dashboard doesn't have to scan history.
    is_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    checks: Mapped[list["Check"]] = relationship(
        back_populates="site", cascade="all, delete-orphan", passive_deletes=True
    )

    def is_due(self, now: datetime) -> bool:
        if not self.is_active:
            return False
        if self.last_checked_at is None:
            return True
        return (now - self.last_checked_at).total_seconds() >= self.interval_seconds

    @property
    def state(self) -> str:
        if self.is_up is None:
            return "unknown"
        return "up" if self.is_up else "down"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "expected_status": self.expected_status,
            "keyword": self.keyword,
            "is_active": self.is_active,
            "state": self.state,
            "last_checked_at": _iso(self.last_checked_at),
            "last_change_at": _iso(self.last_change_at),
        }


class Check(db.Model):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    is_up: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    site: Mapped[Site] = relationship(back_populates="checks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "checked_at": _iso(self.checked_at),
            "is_up": self.is_up,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
