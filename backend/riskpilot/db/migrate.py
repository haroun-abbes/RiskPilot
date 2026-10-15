"""Apply Alembic migrations programmatically (used at API start-up)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from ..config import BACKEND_DIR, DATABASE_URL


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def upgrade() -> None:
    command.upgrade(alembic_config(), "head")
