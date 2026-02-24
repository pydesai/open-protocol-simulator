from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "OpenProtocol Torque Tool Simulator"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    api_port: int = 8000

    classic_port: int = 4545
    actor_port: int = 4546
    viewer_port: int = 4547

    sim_profile: str = "atlas_pf"
    sim_persist: bool = False
    sim_db_path: str = "/data/openprotocol.db"
    sim_max_sessions: int = 10
    sim_keepalive_timeout_sec: int = 15
    sim_inactivity_keepalive_hint_sec: int = 10

    data_dir: Path = Path(__file__).resolve().parent.parent / "data"

    @staticmethod
    def from_env() -> "Settings":
        def _int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return Settings(
            host=os.getenv("HOST", "0.0.0.0"),
            api_port=_int("API_PORT", 8000),
            classic_port=_int("SIM_CLASSIC_PORT", 4545),
            actor_port=_int("SIM_ACTOR_PORT", 4546),
            viewer_port=_int("SIM_VIEWER_PORT", 4547),
            sim_profile=os.getenv("SIM_PROFILE", "atlas_pf"),
            sim_persist=_bool("SIM_PERSIST", False),
            sim_db_path=os.getenv("SIM_DB_PATH", "/data/openprotocol.db"),
            sim_max_sessions=_int("SIM_MAX_SESSIONS", 10),
            sim_keepalive_timeout_sec=_int("SIM_KEEPALIVE_TIMEOUT_SEC", 15),
            sim_inactivity_keepalive_hint_sec=_int("SIM_INACTIVITY_KEEPALIVE_HINT_SEC", 10),
        )

