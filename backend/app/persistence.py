from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .types import TrafficRecord

LOG = logging.getLogger(__name__)


class PersistenceStore:
    """Optional SQLite persistence via SQLAlchemy."""

    def __init__(self, enabled: bool, db_path: str):
        self.enabled = enabled
        self.db_path = db_path
        self._initialized = False
        self._Session = None
        self.StateSnapshot = None
        self.Traffic = None
        if self.enabled:
            self._init_sqlalchemy()

    def _init_sqlalchemy(self) -> None:
        try:
            from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
            from sqlalchemy.orm import declarative_base, sessionmaker
        except Exception as exc:  # pragma: no cover - import guard
            LOG.warning("SQLAlchemy unavailable, disabling persistence: %s", exc)
            self.enabled = False
            return

        Base = declarative_base()

        class StateSnapshot(Base):  # type: ignore[misc]
            __tablename__ = "state_snapshot"
            id = Column(Integer, primary_key=True)
            updated_at = Column(DateTime(timezone=True), nullable=False)
            state_json = Column(Text, nullable=False)

        class Traffic(Base):  # type: ignore[misc]
            __tablename__ = "traffic"
            id = Column(Integer, primary_key=True, autoincrement=True)
            timestamp = Column(DateTime(timezone=True), nullable=False)
            session_id = Column(String(128), nullable=False)
            role = Column(String(32), nullable=False)
            direction = Column(String(32), nullable=False)
            mid = Column(String(4), nullable=False)
            revision = Column(Integer, nullable=False)
            length = Column(Integer, nullable=False)
            raw_ascii = Column(Text, nullable=False)
            decoded_data = Column(Text, nullable=False)

        engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(engine)
        self._Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.StateSnapshot = StateSnapshot
        self.Traffic = Traffic
        self._initialized = True

    def load_state(self) -> dict[str, Any] | None:
        if not (self.enabled and self._initialized):
            return None
        assert self._Session is not None and self.StateSnapshot is not None
        with self._Session() as session:
            row = session.get(self.StateSnapshot, 1)
            if row is None:
                return None
            return json.loads(row.state_json)

    def save_state(self, state: dict[str, Any]) -> None:
        if not (self.enabled and self._initialized):
            return
        assert self._Session is not None and self.StateSnapshot is not None
        payload = json.dumps(state)
        now = datetime.now(timezone.utc)
        with self._Session() as session:
            row = session.get(self.StateSnapshot, 1)
            if row is None:
                row = self.StateSnapshot(id=1, updated_at=now, state_json=payload)
                session.add(row)
            else:
                row.updated_at = now
                row.state_json = payload
            session.commit()

    def append_traffic(self, record: TrafficRecord) -> None:
        if not (self.enabled and self._initialized):
            return
        assert self._Session is not None and self.Traffic is not None
        payload = asdict(record)
        with self._Session() as session:
            row = self.Traffic(
                timestamp=payload["timestamp"],
                session_id=payload["session_id"],
                role=payload["role"].value,
                direction=payload["direction"],
                mid=payload["mid"],
                revision=payload["revision"],
                length=payload["length"],
                raw_ascii=payload["raw_ascii"],
                decoded_data=payload["decoded_data"],
            )
            session.add(row)
            session.commit()

