from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import Settings
from .dispatcher import OpenProtocolDispatcher
from .mid_catalog import MidCatalog
from .persistence import PersistenceStore
from .profiles import ProfileStore
from .state import SimulatorState
from .tcp_server import TcpService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOG = logging.getLogger(__name__)

settings = Settings.from_env()
catalog = MidCatalog.from_file(settings.data_dir / "mid_catalog.json")
profiles = ProfileStore.from_directory(settings.data_dir / "profiles", active=settings.sim_profile)
persistence = PersistenceStore(enabled=settings.sim_persist, db_path=settings.sim_db_path)
state = SimulatorState(
    catalog=catalog,
    profiles=profiles,
    persistence=persistence,
    keepalive_timeout_sec=settings.sim_keepalive_timeout_sec,
    inactivity_hint_sec=settings.sim_inactivity_keepalive_hint_sec,
    max_sessions=settings.sim_max_sessions,
)
dispatcher = OpenProtocolDispatcher(settings=settings, catalog=catalog, profiles=profiles, state=state)
tcp_service = TcpService(settings=settings, state=state, dispatcher=dispatcher)


class ProfileSwitchRequest(BaseModel):
    profile: str = Field(..., description="Profile name, e.g. atlas_pf or cleco")


class DomainUpdateRequest(BaseModel):
    payload: dict[str, Any]


class EventPayloadRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioRunRequest(BaseModel):
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _load_scenarios(path: Path) -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = raw.get("scenarios", [])
    return {s["name"]: s.get("steps", []) for s in scenarios}


SCENARIOS = _load_scenarios(settings.data_dir / "scenarios.json")

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await tcp_service.start()
    LOG.info("API started on %s:%d", settings.host, settings.api_port)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await tcp_service.stop()


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    sessions = await state.sessions()
    return {
        "status": "ok",
        "version": settings.app_version,
        "profile": profiles.active_name,
        "mid_count": catalog.len(),
        "sessions": len(sessions),
        "ports": {
            "classic": settings.classic_port,
            "actor": settings.actor_port,
            "viewer": settings.viewer_port,
        },
    }


@app.get("/api/v1/profiles")
async def get_profiles() -> dict[str, Any]:
    return state.profile_payload()


@app.put("/api/v1/profiles/active")
async def set_active_profile(req: ProfileSwitchRequest) -> dict[str, Any]:
    try:
        await state.set_profile(req.profile)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown profile {req.profile}") from None
    return state.profile_payload()


@app.get("/api/v1/sessions")
async def get_sessions() -> list[dict[str, Any]]:
    return await state.sessions()


@app.get("/api/v1/traffic")
async def get_traffic(
    limit: int = Query(default=100, ge=1, le=500),
    mid: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return await state.list_traffic(limit=limit, mid=mid, session_id=session_id)


@app.get("/api/v1/state")
async def get_full_state() -> dict[str, Any]:
    return await state.list_domains()


@app.get("/api/v1/state/{domain}")
async def get_state_domain(domain: str) -> dict[str, Any]:
    try:
        return await state.get_state_domain(domain)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown domain {domain}") from None


@app.put("/api/v1/state/{domain}")
async def put_state_domain(domain: str, req: DomainUpdateRequest) -> dict[str, Any]:
    try:
        updated = await state.update_state_domain(domain, req.payload)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown domain {domain}") from None
    return {"domain": domain, "state": updated}


@app.post("/api/v1/events/{event_name}")
async def post_event(event_name: str, req: EventPayloadRequest) -> dict[str, Any]:
    result = await tcp_service.publish_event(event_name, req.payload)
    return result


@app.get("/api/v1/scenarios")
async def list_scenarios() -> dict[str, Any]:
    return {"scenarios": sorted(SCENARIOS.keys())}


@app.post("/api/v1/scenarios/run")
async def run_scenario(req: ScenarioRunRequest) -> dict[str, Any]:
    steps = SCENARIOS.get(req.name)
    if steps is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario {req.name}")

    results: list[dict[str, Any]] = []
    for step in steps:
        delay = float(step.get("delay_sec", 0))
        if delay > 0:
            await asyncio.sleep(delay)
        event_name = step["event"]
        payload = dict(step.get("payload", {}))
        payload.update(req.payload)
        result = await tcp_service.publish_event(event_name, payload)
        results.append(result)
    return {"scenario": req.name, "steps_executed": len(steps), "results": results}


@app.post("/api/v1/reset")
async def reset_simulator() -> dict[str, Any]:
    await state.reset()
    return {"status": "reset"}


@app.get("/api/v1/capabilities")
async def capabilities() -> dict[str, Any]:
    matrix = await state.list_capability_matrix()
    return {"count": len(matrix), "items": matrix}

