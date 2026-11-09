from flask import Flask

from .config import Config
from .extensions import db


def create_app(config: type[Config] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config or Config)

    db.init_app(app)

    from . import models  # noqa: F401  (register tables)

    with app.app_context():
        db.create_all()

    from .cli import register_cli

    register_cli(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
