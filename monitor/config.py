import os


class Config:
    # Dev-only fallback. Set MONITOR_SECRET_KEY for anything public.
    SECRET_KEY = os.environ.get("MONITOR_SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("MONITOR_DATABASE_URL", "sqlite:///monitor.db")

    # Write endpoints of the JSON API require this bearer token when it is set.
    API_TOKEN = os.environ.get("MONITOR_API_TOKEN", "")

    # How often the scheduler wakes up to look for sites that are due.
    SCHEDULER_TICK_SECONDS = int(os.environ.get("MONITOR_TICK_SECONDS", "15"))
    # Run the scheduler inside the web process. Only safe with a single worker.
    RUN_SCHEDULER = os.environ.get("MONITOR_RUN_SCHEDULER", "0") == "1"
    USER_AGENT = os.environ.get("MONITOR_USER_AGENT", "flask-url-monitor/0.1")

    # Alerting. Leave blank to disable a channel.
    ALERT_WEBHOOK_URL = os.environ.get("MONITOR_WEBHOOK_URL", "")
    ALERT_EMAIL_TO = os.environ.get("MONITOR_ALERT_EMAIL", "")
    SMTP_HOST = os.environ.get("MONITOR_SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("MONITOR_SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("MONITOR_SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("MONITOR_SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("MONITOR_SMTP_FROM", "monitor@localhost")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    API_TOKEN = ""
    RUN_SCHEDULER = False
    ALERT_WEBHOOK_URL = ""
    ALERT_EMAIL_TO = ""
