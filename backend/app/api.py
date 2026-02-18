from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import load_settings
from app.db import ensure_db, write_batch
from app.leaderboard import build_leaderboard

REQUIRED_EVENT_FIELDS = ("event_id", "event_type", "event_ts", "user_id", "session_id", "payload")

settings = load_settings()
app = FastAPI(title="Neurogame Events API", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    ensure_db(settings.db_path)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/events")
def ingest_events(body: dict[str, Any]) -> JSONResponse:
    api_key = str(body.get("api_key", ""))
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")

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
