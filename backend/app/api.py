from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import load_settings
from app.db import (
    authenticate_auth_user,
    ensure_db,
    read_raw_events,
    register_auth_user,
    write_batch,
)
from app.leaderboard import build_leaderboard

REQUIRED_EVENT_FIELDS = ("event_id", "event_type", "event_ts", "user_id", "session_id", "payload")

settings = load_settings()
app = FastAPI(title="Neurogame Events API", version="0.1.0")


def _require_api_key(body: dict[str, Any]) -> None:
    api_key = str(body.get("api_key", ""))
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")


@app.on_event("startup")
def _startup() -> None:
    ensure_db(settings.db_path)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/events")
def ingest_events(body: dict[str, Any]) -> JSONResponse:
    _require_api_key(body)
    api_key = str(body.get("api_key", ""))

    events = body.get("events")
    if not isinstance(events, list) or not events:
        raise HTTPException(status_code=400, detail="events_must_be_nonempty_list")
    if len(events) > 500:
        raise HTTPException(status_code=400, detail="batch_too_large")

    normalized_events: list[dict[str, Any]] = []
    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            raise HTTPException(status_code=400, detail=f"event_{idx}_must_be_object")
        missing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"event_{idx}_missing_fields:{','.join(missing)}",
            )
        normalized_events.append(event)

    client_version = str(body.get("client_version", "unknown"))
    write_batch(
        db_path=settings.db_path,
        api_key=api_key,
        client_version=client_version,
        events=normalized_events,
    )
    return JSONResponse(content={"ok": True}, status_code=200)


@app.post("/v1/auth/register")
def register_user(body: dict[str, Any]) -> JSONResponse:
    _require_api_key(body)
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    ok, code, user_id = register_auth_user(settings.db_path, username, password)
    if not ok:
        if code in ("username_required", "username_invalid_length", "username_invalid_chars", "password_too_short"):
            raise HTTPException(status_code=400, detail=code)
        if code == "user_exists":
            raise HTTPException(status_code=409, detail=code)
        raise HTTPException(status_code=500, detail="auth_register_failed")
    return JSONResponse(content={"ok": True, "user_id": user_id}, status_code=200)


@app.post("/v1/auth/login")
def login_user(body: dict[str, Any]) -> JSONResponse:
    _require_api_key(body)
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    ok, code, user_id = authenticate_auth_user(settings.db_path, username, password)
    if not ok:
        if code == "username_required":
            raise HTTPException(status_code=400, detail=code)
        if code in ("user_not_found", "invalid_password"):
            raise HTTPException(status_code=401, detail=code)
        raise HTTPException(status_code=500, detail="auth_login_failed")
    return JSONResponse(content={"ok": True, "user_id": user_id}, status_code=200)


@app.get("/v1/leaderboard")
def leaderboard(limit: int = 100, min_tasks: int = 30) -> dict[str, Any]:
    safe_limit = max(1, min(500, int(limit)))
    safe_min_tasks = max(0, int(min_tasks))
    rows = build_leaderboard(settings.db_path, limit=safe_limit, min_tasks=safe_min_tasks)
    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
        "limit": safe_limit,
        "min_tasks": safe_min_tasks,
    }


@app.get("/v1/export/raw")
def export_raw_events(api_key: str, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    rows = read_raw_events(
        db_path=settings.db_path,
        limit=limit,
        offset=offset,
    )
    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
        "limit": max(1, min(5000, int(limit))),
        "offset": max(0, int(offset)),
    }
