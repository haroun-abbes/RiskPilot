"""Runtime configuration from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

ENGINE_VERSION = "0.1.0"
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RISKPILOT_DATA_DIR", BACKEND_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "datasets").mkdir(exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'riskpilot.db'}")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
ENABLE_ECB = os.environ.get("ENABLE_ECB_PROVIDER", "true").lower() == "true"
