import click
from flask import Flask
from sqlalchemy import select

from .extensions import db
from .models import Site
from .service import prune_history, run_check
from .sites import SiteError, create_site, find_site, parse_site_list
from .stats import overview


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create the database tables."""
        db.create_all()
        click.echo("Database ready.")

    @app.cli.command("add-site")
    @click.argument("url")
    @click.option("--name", help="Display name (defaults to host + path).")
    @click.option("--interval", default=60, show_default=True, help="Seconds between checks.")
    @click.option("--timeout", default=10, show_default=True, help="Request timeout in seconds.")
    @click.option("--expect", type=int, help="Exact HTTP status that counts as up.")
    @click.option("--keyword", help="Text that must appear in the response body.")
    def add_site(url, name, interval, timeout, expect, keyword):
        """Start monitoring URL."""
        try:
            site = create_site(url, name, interval, timeout, expect, keyword)
        except SiteError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Added {site.name} ({site.url}), every {site.interval_seconds}s.")

    @app.cli.command("remove-site")
    @click.argument("name")
    def remove_site(name):
        """Stop monitoring a site and delete its history."""
        site = find_site(name)
        if site is None:
            raise click.ClickException(f"No site named {name!r}")
        db.session.delete(site)
        db.session.commit()
        click.echo(f"Removed {site.name}.")

    @app.cli.command("import-sites")
    @click.argument("path", type=click.File("r"))
    def import_sites(path):
        """Add sites from a text file with one `URL` or `NAME URL` per line."""
        added = skipped = 0
        for name, url in parse_site_list(path.read()):
            try:
                create_site(url, name)
                added += 1
            except SiteError as exc:
                db.session.rollback()
                skipped += 1
                click.echo(f"skip: {exc}", err=True)
        click.echo(f"Imported {added} site(s), skipped {skipped}.")

    @app.cli.command("list-sites")
    def list_sites():
        """Show each site with its state and 24h uptime."""
        rows = overview()
        if not rows:
            click.echo("No sites yet. Add one with `flask add-site URL`.")
            return
        click.echo(f"{'NAME':<28} {'STATE':<8} {'UPTIME 24H':>10} {'AVG MS':>7}  URL")
        for row in rows:
            site, day = row["site"], row["day"]
            uptime = f"{day.uptime_percent:.2f}%" if day.uptime_percent is not None else "-"
            latency = str(day.avg_latency_ms) if day.avg_latency_ms is not None else "-"
            state = site.state if site.is_active else "paused"
            click.echo(f"{site.name[:28]:<28} {state:<8} {uptime:>10} {latency:>7}  {site.url}")

    @app.cli.command("check")
    @click.argument("name", required=False)
    def check(name):
        """Check one site (or all active sites) right now."""
        if name:
            site = find_site(name)
            if site is None:
                raise click.ClickException(f"No site named {name!r}")
            sites = [site]
        else:
            sites = list(db.session.scalars(select(Site).where(Site.is_active.is_(True))))
        for site in sites:
            result = run_check(site)
            detail = result.error or f"HTTP {result.status_code}"
            latency = f"{result.latency_ms} ms" if result.latency_ms is not None else "-"
            click.echo(f"{site.name}: {'UP' if result.is_up else 'DOWN'} ({detail}, {latency})")

    @app.cli.command("prune")
    @click.option("--days", default=30, show_default=True, help="Keep this many days of history.")
    def prune(days):
        """Delete check history older than --days."""
        removed = prune_history(days)
        click.echo(f"Deleted {removed} old check(s).")
