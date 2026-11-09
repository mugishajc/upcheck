"""
Alert channels. A notifier receives an AlertEvent when a site goes down or
comes back up. Add a channel by implementing `notify`.
"""

import logging
import smtplib
from dataclasses import asdict, dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertEvent:
    site_name: str
    url: str
    is_up: bool
    occurred_at: datetime
    status_code: int | None = None
    error: str | None = None

    @property
    def kind(self) -> str:
        return "recovered" if self.is_up else "down"

    @property
    def summary(self) -> str:
        if self.is_up:
            return f"{self.site_name} is back up"
        detail = self.error or f"HTTP {self.status_code}"
        return f"{self.site_name} is DOWN: {detail}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat() + "Z"
        data["kind"] = self.kind
        data["summary"] = self.summary
        return data


class Notifier(Protocol):
    def notify(self, event: AlertEvent) -> None: ...


class LogNotifier:
    def notify(self, event: AlertEvent) -> None:
        level = logging.INFO if event.is_up else logging.WARNING
        log.log(level, "alert: %s (%s)", event.summary, event.url)


class WebhookNotifier:
    """POSTs the event as JSON. Works with most chat webhooks that accept a `text` field."""

    def __init__(self, url: str, timeout: float = 5, session: requests.Session | None = None):
        self.url = url
        self.timeout = timeout
        self.http = session or requests

    def notify(self, event: AlertEvent) -> None:
        payload = {"text": event.summary, "event": event.to_dict()}
        response = self.http.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()


class EmailNotifier:
    """
    Sends a plain-text email. Without an SMTP host it only logs the message,
    which keeps local setups and tests free of real mail.
    """

    def __init__(
        self,
        to: str,
        sender: str,
        host: str = "",
        port: int = 587,
        username: str = "",
        password: str = "",
    ):
        self.to = to
        self.sender = sender
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    def build_message(self, event: AlertEvent) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = f"[monitor] {event.summary}"
        message["From"] = self.sender
        message["To"] = self.to
        lines = [
            event.summary,
            "",
            f"URL:    {event.url}",
            f"When:   {event.occurred_at:%Y-%m-%d %H:%M:%S} UTC",
        ]
        if event.status_code is not None:
            lines.append(f"Status: {event.status_code}")
        if event.error:
            lines.append(f"Error:  {event.error}")
        message.set_content("\n".join(lines))
        return message

    def notify(self, event: AlertEvent) -> None:
        message = self.build_message(event)
        if not self.host:
            log.info("email (not sent, no SMTP host): %s -> %s", message["Subject"], self.to)
            return
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


def build_notifiers(config) -> list[Notifier]:
    notifiers: list[Notifier] = [LogNotifier()]
    if config.get("ALERT_WEBHOOK_URL"):
        notifiers.append(WebhookNotifier(config["ALERT_WEBHOOK_URL"]))
    if config.get("ALERT_EMAIL_TO"):
        notifiers.append(
            EmailNotifier(
                to=config["ALERT_EMAIL_TO"],
                sender=config.get("SMTP_FROM", "monitor@localhost"),
                host=config.get("SMTP_HOST", ""),
                port=config.get("SMTP_PORT", 587),
                username=config.get("SMTP_USER", ""),
                password=config.get("SMTP_PASSWORD", ""),
            )
        )
    return notifiers


def dispatch(event: AlertEvent, notifiers: list[Notifier]) -> None:
    """Send to every channel. One failing channel must not block the others."""
    for notifier in notifiers:
        try:
            notifier.notify(event)
        except Exception:
            log.exception("alert channel %s failed", type(notifier).__name__)
