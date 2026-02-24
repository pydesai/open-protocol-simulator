# Operations Guide

## Runtime Topology

- One Docker image.
- Two supervised processes:
  - `uvicorn` (FastAPI + TCP protocol service).
  - `nginx` (UI static hosting + API reverse proxy).

## Health Checks

- `GET /api/v1/health` verifies profile, MID count, and session counts.

## Persistence

- `SIM_PERSIST=1` enables SQLite persistence at `SIM_DB_PATH`.
- Persisted data:
  - Full simulator state snapshot.
  - Traffic log records.

## Session Modes

- `Classic` port 4545.
- `Actor` port 4546.
- `Viewer` port 4547.

Actor-mode restrictions:

- If an active Actor session exists, command requests from non-Actor sessions are rejected with MID `0004` error `92`.
- Additional Actor attempts can be rejected with MID `0004` error `35`.

## Keepalive / Timeout

- Inactivity timeout defaults to 15 seconds.
- Keepalive MID `9999` is mirrored as response.

## Logs

- `supervisord` routes application and nginx logs to stdout/stderr.

## Typical Event Flow

1. Client connects to one of `4545/4546/4547`.
2. Client sends `MID 0001`.
3. Server replies `MID 0002`.
4. Client subscribes (`0008` or dedicated subscribe MID).
5. Operator injects event via UI/API.
6. Simulator pushes subscribed result/event MIDs.

