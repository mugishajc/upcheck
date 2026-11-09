import hmac
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from .extensions import db
from .models import Site
from .service import run_check
from .sites import SiteError, create_site
from .stats import overview, recent_checks, stats_by_window

bp = Blueprint("api", __name__, url_prefix="/api")

EDITABLE_INT_FIELDS = {"interval_seconds", "timeout_seconds", "expected_status"}


def require_token(view):
    """Write endpoints need `Authorization: Bearer <MONITOR_API_TOKEN>` when a token is set."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("API_TOKEN")
        if expected:
            header = request.headers.get("Authorization", "")
            given = header.removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given.encode(), expected.encode()):
                abort(401, description="Missing or invalid API token")
        return view(*args, **kwargs)

    return wrapper


def get_site_or_404(site_id: int) -> Site:
    site = db.session.get(Site, site_id)
    if site is None:
        abort(404, description="Site not found")
    return site


@bp.errorhandler(HTTPException)
def json_error(exc: HTTPException):
    return jsonify(error=exc.description), exc.code


@bp.get("/sites")
def list_sites():
    rows = overview()
    return jsonify(
        [{**row["site"].to_dict(), "uptime_24h": row["day"].uptime_percent} for row in rows]
    )


@bp.post("/sites")
@require_token
def add_site():
    data = request.get_json(silent=True) or {}
    try:
        site = create_site(
            url=data.get("url", ""),
            name=data.get("name"),
            interval_seconds=int(data.get("interval_seconds", 60)),
            timeout_seconds=int(data.get("timeout_seconds", 10)),
            expected_status=_optional_int(data.get("expected_status")),
            keyword=data.get("keyword"),
        )
    except (SiteError, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    return jsonify(site.to_dict()), 201


@bp.get("/sites/<int:site_id>")
def site_detail(site_id: int):
    site = get_site_or_404(site_id)
    return jsonify({**site.to_dict(), "stats": stats_by_window(site.id)})


@bp.patch("/sites/<int:site_id>")
@require_token
def update_site(site_id: int):
    """Pause/resume a site or change its check settings."""
    site = get_site_or_404(site_id)
    data = request.get_json(silent=True) or {}
    try:
        for field in EDITABLE_INT_FIELDS & data.keys():
            setattr(site, field, _optional_int(data[field]))
        if "keyword" in data:
            site.keyword = data["keyword"] or None
        if "is_active" in data:
            site.is_active = bool(data["is_active"])
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    if not site.interval_seconds or not 10 <= site.interval_seconds <= 86400:
        db.session.rollback()
        return jsonify(error="Interval must be between 10 seconds and 1 day"), 400
    if not site.timeout_seconds or not 1 <= site.timeout_seconds < site.interval_seconds:
        db.session.rollback()
        return jsonify(error="Timeout must be at least 1s and shorter than the interval"), 400
    db.session.commit()
    return jsonify(site.to_dict())


@bp.delete("/sites/<int:site_id>")
@require_token
def delete_site(site_id: int):
    db.session.delete(get_site_or_404(site_id))
    db.session.commit()
    return "", 204


@bp.get("/sites/<int:site_id>/checks")
def site_checks(site_id: int):
    site = get_site_or_404(site_id)
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    return jsonify([check.to_dict() for check in recent_checks(site.id, limit)])


@bp.post("/sites/<int:site_id>/check")
@require_token
def check_now(site_id: int):
    site = get_site_or_404(site_id)
    return jsonify(run_check(site).to_dict()), 201


@bp.get("/summary")
def summary():
    rows = overview()
    states = [row["site"].state for row in rows if row["site"].is_active]
    return jsonify(
        sites=len(rows),
        up=states.count("up"),
        down=states.count("down"),
        unknown=states.count("unknown"),
        paused=sum(1 for row in rows if not row["site"].is_active),
    )


def _optional_int(value):
    if value is None or value == "":
        return None
    return int(value)
