# Copilot / AI Agent Instructions for Open-Protocol Simulator

Purpose
- Keep guidance short and actionable so an AI agent can be productive immediately.

Big picture (what to inspect first)
- Backend: `backend/app` — a FastAPI service that also launches TCP Open Protocol endpoints.
  - Key modules: `main.py`, `tcp_server.py`, `dispatcher.py`, `protocol.py`, `state.py`, `persistence.py`, `mid_catalog.py`, `profiles.py`.
  - Data: `backend/data/mid_catalog.json`, `backend/data/profiles/*.json`, `backend/data/scenarios.json`.
- Frontend: `frontend/src` — small React app; served via Docker/Nginx in production.
- Docker: top-level `Dockerfile` and `docker/` for integrated runs (ports mapped: 8080 UI, 4545/4546/4547 TCP).

Developer workflows (exact commands)
- Install backend deps and run locally (Windows):
  - `cd backend`
  - `python -m venv .venv`
  - `.venv\Scripts\activate`
  - `pip install -r requirements.txt`
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Run tests from repo root: `pytest -q` (ensure backend deps installed in the active environment).
- Run frontend dev server: `cd frontend && npm install && npm run dev`.

Project-specific patterns and conventions
- MID-driven behavior: business logic is driven by `mid_catalog.json` and per-profile deltas in `backend/data/profiles/*.json`.
- Dispatcher pattern: `dispatcher.py` maps incoming TCP messages (by MID) to handlers implemented across `protocol.py` and `dispatcher.py`.
- Profiles: `profiles.py` loads JSON profile overrides; when changing behavior for a vendor, update profile JSON first, then adjust dispatcher if necessary.
- Persistence is optional and toggled with environment variables (`SIM_PERSIST`, `SIM_DB_PATH`) configured in `backend/config.py`.
- Keep changes small and local: prefer adding a handler function and unit tests in `tests/` rather than broad refactors.

Integration points to watch
- TCP sockets: `tcp_server.py` — mutates session state and emits REST-visible traffic; be mindful of concurrency and async code.
- REST API: `app/main.py` exposes endpoints used by the UI; tests reference these routes in `tests/test_dispatcher.py` and `tests/test_protocol.py`.
- DB: `persistence.py` uses SQLAlchemy — schema and migrations are minimal; altering models affects tests and local SQLite files under `.simdata` in Docker runs.

What to change when adding behavior (example)
- To handle a new MID:
  1. Add/verify the MID in `backend/data/mid_catalog.json`.
  2. Add a handler in `backend/app/protocol.py` (or `dispatcher.py` if routing only).
  3. Add unit tests under `tests/` mirroring existing `test_protocol.py` patterns.
  4. Run `pytest -q` and manual local run via `uvicorn`.

Files to inspect for context
- [backend/app/main.py](backend/app/main.py)
- [backend/app/tcp_server.py](backend/app/tcp_server.py)
- [backend/app/dispatcher.py](backend/app/dispatcher.py)
- [backend/data/mid_catalog.json](backend/data/mid_catalog.json)
- [backend/data/profiles/atlas_pf.json](backend/data/profiles/atlas_pf.json)
- [tests/test_protocol.py](tests/test_protocol.py)

When unsure
- Run tests and reproduce behavior locally with the backend dev commands above; consult `README.md` quick-start examples.

Ask me for feedback
- If any section is unclear or you want the agent to perform a specific change (add MID, update profile, or add a test), tell me which area and I'll update this guidance and make the change.
