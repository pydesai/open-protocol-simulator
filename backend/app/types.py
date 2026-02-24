from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SessionRole(str, Enum):
    CLASSIC = "classic"
    ACTOR = "actor"
    VIEWER = "viewer"


class AckMode(str, Enum):
    APPLICATION = "application"
    LINK_LEVEL = "link_level"


@dataclass
class OpenProtocolHeader:
    length: int
    mid: str
    revision: str = "001"
    no_ack_flag: str = " "
    station_id: str = "  "
    spindle_id: str = "  "
    sequence_number: str = "00"
    message_parts: str = " "
    message_part_number: str = " "

    @property
    def sequence_int(self) -> int:
        try:
            return int(self.sequence_number)
        except ValueError:
            return 0

    @property
    def revision_int(self) -> int:
        try:
            return int(self.revision.strip() or "0")
        except ValueError:
            return 0

    @property
    def has_sequence(self) -> bool:
        return 1 <= self.sequence_int <= 99

    @property
    def linked_message(self) -> bool:
        return self.message_parts.strip() not in {"", "0"}

    @property
    def message_parts_int(self) -> int:
        if self.message_parts.strip() == "":
            return 0
        try:
            return int(self.message_parts)
        except ValueError:
            return 0

    @property
    def message_part_number_int(self) -> int:
        if self.message_part_number.strip() == "":
            return 0
        try:
            return int(self.message_part_number)
        except ValueError:
            return 0


@dataclass
class OpenProtocolMessage:
    header: OpenProtocolHeader
    data: bytes = b""
    raw: bytes = b""
    binary: bool = False

    @property
    def mid(self) -> str:
        return self.header.mid

    @property
    def revision(self) -> int:
        return self.header.revision_int

    def data_ascii(self) -> str:
        return self.data.decode("ascii", errors="ignore")


@dataclass
class MidDefinition:
    mid: str
    name: str
    category: str
    direction: str
    supported_revisions: list[int]
    payload_schema: dict[str, Any]
    ack_strategy: str
    error_rules: list[str]
    profile_overrides: dict[str, Any]


@dataclass
class SessionContext:
    session_id: str
    role: SessionRole
    remote: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ack_mode: AckMode = AckMode.APPLICATION
    next_tx_seq: int = 1
    next_rx_seq: int = 1
    last_rx_seq: int = 0
    communication_started: bool = False
    station_id: str = "01"
    spindle_id: str = "01"
    subscriptions: set[str] = field(default_factory=set)
    pending_replies: dict[str, Any] = field(default_factory=dict)
    last_link_ack: OpenProtocolMessage | None = None
    writer: Any | None = None

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)


@dataclass
class SimulationEvent:
    event_id: str
    timestamp: datetime
    source: str
    event_type: str
    payload: dict[str, Any]
    affected_mids: list[str]


@dataclass
class ScenarioDefinition:
    name: str
    steps: list[dict[str, Any]]


@dataclass
class TrafficRecord:
    timestamp: datetime
    session_id: str
    role: SessionRole
    direction: str
    mid: str
    revision: int
    length: int
    raw_ascii: str
    decoded_data: str

