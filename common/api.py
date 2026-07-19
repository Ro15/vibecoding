"""Shared FastAPI app-factory helpers.

Gives every app the same error envelope, a /health endpoint, static-dir mount,
and an optional two-tier (viewer/operator) API-key auth dependency factory.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def make_app(title: str, description: str, version: str = "1.0.0") -> FastAPI:
    app = FastAPI(title=title, description=description, version=version)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500,
                            content={"error": {"message": str(exc), "details": None}})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def mount_dashboard(app: FastAPI, static_dir: Path):
    """Serve index.html at / and static assets under /static."""
    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def api_key_auth(viewer_key: str | None, operator_key: str | None):
    """Build a role checker. If no keys are set, auth is disabled (local mode)."""
    viewer_key = viewer_key or os.environ.get("APP_VIEWER_KEY")
    operator_key = operator_key or os.environ.get("APP_OPERATOR_KEY")

    def check(role: str, x_api_key: str | None) -> str:
        if not viewer_key and not operator_key:
            return "anonymous"
        if x_api_key is None:
            raise HTTPException(401, detail="missing X-API-Key header")
        if role == "operator":
            if x_api_key == operator_key:
                return "operator"
            raise HTTPException(403, detail="operator key required")
        if x_api_key in {viewer_key, operator_key}:
            return "operator" if x_api_key == operator_key else "viewer"
        raise HTTPException(403, detail="invalid API key")

    return check
