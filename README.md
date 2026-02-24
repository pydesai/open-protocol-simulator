# OpenProtocol Torque Tool Simulator

Dockerized Open Protocol (2.16.0) simulator with:

- TCP Open Protocol endpoints for `Classic`, `Actor`, and `Viewer` sessions.
- Full MID catalog coverage (191 MID IDs from the provided spec).
- Both reliability modes:
  - Application-level ACK (`0004/0005` and MID-specific behavior).
  - Link-level ACK with sequence numbers (`9997/9998`).
- REST control API and React operator console.
- Optional SQLite persistence.
- Dual vendor profiles:
  - `atlas_pf`
  - `cleco` (generic OP parity profile).

## Ports

- `8080`: UI + REST API (via Nginx proxy)
- `4545`: Open Protocol `Classic`
- `4546`: Open Protocol `Actor`
- `4547`: Open Protocol `Viewer`

## Quick Start (Docker)

```bash
docker build -t openprotocol-simulator .
docker run --rm -p 8080:8080 -p 4545:4545 -p 4546:4546 -p 4547:4547 \
  -e SIM_PROFILE=atlas_pf \
  -e SIM_PERSIST=1 \
  -v "$(pwd)/.simdata:/data" \
  openprotocol-simulator
```

Open UI at `http://localhost:8080`.

## Local Backend Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Local Frontend Run

```bash
cd frontend
npm install
npm run dev
```

Set frontend proxy to backend or use Docker/Nginx for integrated serving.

## Environment Variables

- `SIM_PROFILE=atlas_pf|cleco`
- `SIM_PERSIST=0|1`
- `SIM_DB_PATH=/data/openprotocol.db`
- `SIM_MAX_SESSIONS=10`
- `SIM_KEEPALIVE_TIMEOUT_SEC=15`
- `SIM_INACTIVITY_KEEPALIVE_HINT_SEC=10`
- `SIM_CLASSIC_PORT=4545`
- `SIM_ACTOR_PORT=4546`
- `SIM_VIEWER_PORT=4547`

## REST API

- `GET /api/v1/health`
- `GET /api/v1/profiles`
- `PUT /api/v1/profiles/active`
- `GET /api/v1/sessions`
- `GET /api/v1/traffic?limit=&mid=&session_id=`
- `GET /api/v1/state`
- `GET /api/v1/state/{domain}`
- `PUT /api/v1/state/{domain}`
- `POST /api/v1/events/{event_name}`
- `GET /api/v1/scenarios`
- `POST /api/v1/scenarios/run`
- `POST /api/v1/reset`
- `GET /api/v1/capabilities`

## Notes

- MID IDs are loaded from `backend/data/mid_catalog.json`, generated from your provided PDF spec.
- Atlas appendix and profile-specific notes are in `backend/data/profiles/atlas_pf.json`.
- For Cleco-specific behavior deltas, extend `backend/data/profiles/cleco.json` and dispatcher logic.

