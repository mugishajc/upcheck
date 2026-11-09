"""Creating and validating sites. Shared by the CLI and the JSON API."""

from urllib.parse import urlparse

from sqlalchemy import func, select

from .extensions import db
from .models import Site


class SiteError(ValueError):
    pass


def normalise_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SiteError(f"Not an http(s) URL: {url!r}")
    return url


def default_name(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc + parsed.path).rstrip("/")


def find_site(name_or_id: str) -> Site | None:
    if str(name_or_id).isdigit():
        site = db.session.get(Site, int(name_or_id))
        if site:
            return site
    return db.session.scalar(select(Site).where(func.lower(Site.name) == str(name_or_id).lower()))


def create_site(
    url: str,
    name: str | None = None,
    interval_seconds: int = 60,
    timeout_seconds: int = 10,
    expected_status: int | None = None,
    keyword: str | None = None,
) -> Site:
    url = normalise_url(url)
    name = (name or default_name(url)).strip()
    if not name:
        raise SiteError("Name cannot be empty")
    if not 10 <= interval_seconds <= 86400:
        raise SiteError("Interval must be between 10 seconds and 1 day")
    if not 1 <= timeout_seconds <= 60:
        raise SiteError("Timeout must be between 1 and 60 seconds")
    if timeout_seconds >= interval_seconds:
        raise SiteError("Timeout must be shorter than the interval")
    if expected_status is not None and not 100 <= expected_status <= 599:
        raise SiteError("Expected status must be a valid HTTP status code")
    if find_site(name) is not None:
        raise SiteError(f"A site called {name!r} already exists")

    site = Site(
        name=name,
        url=url,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        expected_status=expected_status,
        keyword=keyword or None,
    )
    db.session.add(site)
    db.session.commit()
    return site


def parse_site_list(text: str) -> list[tuple[str | None, str]]:
    """
    Parse a plain-text list of sites. Each line is either `URL` or `NAME URL`.
    Blank lines and lines starting with # are skipped.
    """
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 1:
            entries.append((None, parts[0]))
        else:
            entries.append((" ".join(parts[:-1]), parts[-1]))
    return entries
