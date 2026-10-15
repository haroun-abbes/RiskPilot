"""FastAPI application entry point: `uvicorn riskpilot.main:app`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import CORS_ORIGINS, ENGINE_VERSION
from .db.migrate import upgrade
from .db.session import SessionLocal
from .services.store import bootstrap

log = logging.getLogger("riskpilot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade()
    with SessionLocal() as db:
        bootstrap(db)
    yield


app = FastAPI(title="RiskPilot API", version=ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Internal error ({type(exc).__name__}). The calculation was not completed."})


app.include_router(router)
