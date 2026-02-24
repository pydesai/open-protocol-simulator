from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .mid_catalog import MidCatalog
from .persistence import PersistenceStore
from .profiles import ProfileStore
from .protocol import ascii_payload, build_message
from .types import OpenProtocolMessage, SessionContext, SessionRole, SimulationEvent, TrafficRecord


SUBSCRIPTION_TARGETS: dict[str, list[str]] = {
    "0014": ["0015"],
    "0021": ["0022"],
    "0034": ["0035"],
    "0051": ["0052"],
    "0060": ["0061"],
    "0070": ["0071"],
    "0090": ["0091"],
    "0100": ["0101"],
    "0105": ["0106", "0107"],
    "0120": ["0121", "0122", "0123", "0124"],
    "0151": ["0152"],
    "0210": ["0211"],
    "0216": ["0217"],
    "0220": ["0221"],
    "0241": ["0242"],
    "0250": ["0251"],
    "0261": ["0262"],
    "0400": ["0401"],
    "0420": ["0421"],
    "0500": ["0501"],
    "0901": ["0900"],
    "8000": ["8001"],
}

EVENT_DEFAULT_MIDS: dict[str, list[str]] = {
    "tightening": ["0061", "1201", "1202"],
    "alarm": ["0071", "1000"],
    "io_change": ["0211", "0217", "0221"],
    "trace": ["0900"],
}


class SimulatorState:
    def __init__(
        self,
        *,
        catalog: MidCatalog,
        profiles: ProfileStore,
        persistence: PersistenceStore,
        keepalive_timeout_sec: int,
        inactivity_hint_sec: int,
        max_sessions: int,
    ):
        self.catalog = catalog
        self.profiles = profiles
        self.persistence = persistence
        self.keepalive_timeout_sec = keepalive_timeout_sec
        self.inactivity_hint_sec = inactivity_hint_sec
        self.max_sessions = max_sessions

        self._lock = asyncio.Lock()
        self._sessions: dict[str, SessionContext] = {}
        self._traffic: list[TrafficRecord] = []
        self._events: list[SimulationEvent] = []
        self._state = self._initial_state()

        loaded = self.persistence.load_state()
        if loaded:
            self._state = loaded

    def _initial_state(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "metadata": {"created_at": now, "profile": self.profiles.active_name},
            "tool": {
                "enabled": True,
                "primary_tool": "01",
                "calibration_value": "0.00",
                "paired": False,
            },
            "job": {"selected": "0001", "running": False, "batch_counter": 0, "batch_size": 1},
            "pset": {"selected": "001", "running": False, "batch_counter": 0, "batch_size": 1},
            "vin": {"current": "SIMVIN00000000001", "history": []},
            "results": {"last_tightening_id": 1, "history": []},
            "alarms": {"active": [], "history": []},
            "io": {"relays": {}, "inputs": {}, "relay_functions": {}, "digin_functions": {}},
            "selector": {"socket": "1", "green": [], "red": []},
            "traces": {"latest": None},
            "programs": {"last_download": None, "catalog": {}},
            "mode": {"selected": "0001", "list": [{"id": "0001", "name": "Default"}]},
            "user_data": {"records": {}},
            "identifiers": {"latest": None, "all": []},
        }

    async def register_session(self, session: SessionContext) -> tuple[bool, str]:
        async with self._lock:
            if len(self._sessions) >= self.max_sessions:
                return False, "max sessions reached"
            self._sessions[session.session_id] = session
            return True, ""

    async def unregister_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def sessions(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [self._session_to_dict(s) for s in self._sessions.values()]

    async def get_session(self, session_id: str) -> SessionContext | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def actor_active(self, exclude_session: str | None = None) -> bool:
        async with self._lock:
            for sid, session in self._sessions.items():
                if exclude_session and sid == exclude_session:
                    continue
                if session.role == SessionRole.ACTOR and session.communication_started:
                    return True
            return False

    async def ensure_command_allowed(self, session: SessionContext) -> tuple[bool, int]:
        # Error 92 if commands disabled by actor.
        if session.role == SessionRole.ACTOR:
            return True, 0
        active = await self.actor_active(exclude_session=session.session_id)
        if active:
            return False, 92
        return True, 0

    def _session_to_dict(self, s: SessionContext) -> dict[str, Any]:
        return {
            "session_id": s.session_id,
            "role": s.role.value,
            "remote": s.remote,
            "created_at": s.created_at.isoformat(),
            "last_activity": s.last_activity.isoformat(),
            "ack_mode": s.ack_mode.value,
            "next_tx_seq": s.next_tx_seq,
            "next_rx_seq": s.next_rx_seq,
            "communication_started": s.communication_started,
            "subscriptions": sorted(s.subscriptions),
        }

    async def list_traffic(self, *, limit: int = 100, mid: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            items = self._traffic
            if mid:
                mid = f"{mid:0>4}"[-4:]
                items = [t for t in items if t.mid == mid]
            if session_id:
                items = [t for t in items if t.session_id == session_id]
            out = items[-max(1, min(limit, 500)) :]
            return [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "session_id": t.session_id,
                    "role": t.role.value,
                    "direction": t.direction,
                    "mid": t.mid,
                    "revision": t.revision,
                    "length": t.length,
                    "raw_ascii": t.raw_ascii,
                    "decoded_data": t.decoded_data,
                }
                for t in out
            ]

    async def record_traffic(self, session: SessionContext, direction: str, msg: OpenProtocolMessage) -> None:
        decoded = msg.data.decode("ascii", errors="replace")
        raw_ascii = msg.raw.decode("ascii", errors="replace")
        record = TrafficRecord(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            role=session.role,
            direction=direction,
            mid=msg.mid,
            revision=msg.revision,
            length=msg.header.length,
            raw_ascii=raw_ascii,
            decoded_data=decoded,
        )
        async with self._lock:
            self._traffic.append(record)
            if len(self._traffic) > 5000:
                self._traffic = self._traffic[-5000:]
        self.persistence.append_traffic(record)

    async def get_state_domain(self, domain: str) -> dict[str, Any]:
        async with self._lock:
            if domain not in self._state:
                raise KeyError(domain)
            return json.loads(json.dumps(self._state[domain]))

    async def list_domains(self) -> dict[str, Any]:
        async with self._lock:
            return json.loads(json.dumps(self._state))

    async def update_state_domain(self, domain: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if domain not in self._state:
                raise KeyError(domain)
            self._state[domain] = payload
            self._state["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.persistence.save_state(self._state)
            return json.loads(json.dumps(self._state[domain]))

    async def reset(self) -> None:
        async with self._lock:
            self._state = self._initial_state()
            for session in self._sessions.values():
                session.subscriptions.clear()
                session.pending_replies.clear()
                session.communication_started = False
                session.next_rx_seq = 1
                session.next_tx_seq = 1
            self._events.clear()
            self.persistence.save_state(self._state)

    async def set_profile(self, name: str) -> None:
        self.profiles.set_active(name)
        async with self._lock:
            self._state["metadata"]["profile"] = name
            self._state["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.persistence.save_state(self._state)

    def profile_payload(self) -> dict[str, Any]:
        active = self.profiles.active
        return {
            "active": self.profiles.active_name,
            "profiles": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "supported_mid_count": len(p.supported_mids),
                }
                for p in self.profiles.all()
            ],
            "active_details": {
                "name": active.name,
                "description": active.description,
                "supported_mids": active.supported_mids,
                "revision_overrides": active.revision_overrides,
                "notes": active.notes,
            },
        }

    async def add_subscription(self, session: SessionContext, mid: str) -> None:
        session.subscriptions.add(f"{mid:0>4}"[-4:])

    async def remove_subscription(self, session: SessionContext, mid: str) -> None:
        session.subscriptions.discard(f"{mid:0>4}"[-4:])

    async def list_capability_matrix(self) -> list[dict[str, Any]]:
        active = self.profiles.active
        matrix = []
        for entry in self.catalog.as_list():
            supported = entry["mid"] in active.supported_mids
            revs = active.revision_overrides.get(entry["mid"], entry["supported_revisions"])
            matrix.append(
                {
                    "mid": entry["mid"],
                    "name": entry["name"],
                    "category": entry["category"],
                    "supported": supported,
                    "revisions": revs,
                }
            )
        return matrix

    def _event_record(self, event_type: str, payload: dict[str, Any], mids: list[str]) -> SimulationEvent:
        event = SimulationEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            source="rest_api",
            event_type=event_type,
            payload=payload,
            affected_mids=mids,
        )
        self._events.append(event)
        if len(self._events) > 2000:
            self._events = self._events[-2000:]
        return event

    async def inject_event(self, event_type: str, payload: dict[str, Any] | None = None) -> SimulationEvent:
        payload = payload or {}
        mids = payload.get("mids")
        if not isinstance(mids, list):
            mids = EVENT_DEFAULT_MIDS.get(event_type, [])
        event = self._event_record(event_type, payload, mids)

        if event_type == "tightening":
            await self._update_tightening_state(payload)
        elif event_type == "alarm":
            await self._update_alarm_state(payload)
        elif event_type == "io_change":
            await self._update_io_state(payload)

        return event

    async def _update_tightening_state(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            tightening_id = int(self._state["results"]["last_tightening_id"]) + 1
            torque = payload.get("torque_nm", 12.34)
            angle = payload.get("angle_deg", 123.0)
            ok = payload.get("ok", True)
            result = {
                "tightening_id": tightening_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "torque_nm": torque,
                "angle_deg": angle,
                "status": "OK" if ok else "NOK",
            }
            self._state["results"]["last_tightening_id"] = tightening_id
            self._state["results"]["history"].append(result)
            self._state["results"]["history"] = self._state["results"]["history"][-1000:]
            self._state["traces"]["latest"] = {
                "tightening_id": tightening_id,
                "points": payload.get("trace_points", [10, 12, 14, 15, 14, 12]),
            }
            self.persistence.save_state(self._state)

    async def _update_alarm_state(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            alarm = {
                "code": payload.get("code", "0001"),
                "text": payload.get("text", "Simulated alarm"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._state["alarms"]["active"] = [alarm]
            self._state["alarms"]["history"].append(alarm)
            self._state["alarms"]["history"] = self._state["alarms"]["history"][-1000:]
            self.persistence.save_state(self._state)

    async def _update_io_state(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            key = payload.get("key", "input_01")
            value = payload.get("value", True)
            self._state["io"]["inputs"][key] = value
            self.persistence.save_state(self._state)

    async def generate_push_messages(self, session: SessionContext, event: SimulationEvent) -> list[OpenProtocolMessage]:
        """Build push messages for an event based on subscriptions."""
        messages: list[OpenProtocolMessage] = []
        target_mids = {f"{m:0>4}"[-4:] for m in event.affected_mids}

        # Subscribed pushes from dedicated subscription MIDs.
        subscribed_targets: set[str] = set()
        for sub_mid in session.subscriptions:
            subscribed_targets.update(SUBSCRIPTION_TARGETS.get(sub_mid, []))
            # Generic subscription where subscribed MID itself is the target.
            subscribed_targets.add(sub_mid)

        for mid in sorted(target_mids):
            if mid not in subscribed_targets:
                continue
            data = await self.build_data_for_mid(mid)
            messages.append(
                build_message(
                    mid=mid,
                    data=data,
                    revision=1,
                    sequence_number=session.next_tx_seq if session.ack_mode.value == "link_level" else 0,
                )
            )
        return messages

    async def build_data_for_mid(self, mid: str) -> bytes:
        async with self._lock:
            if mid == "0015":
                return ascii_payload("01", str(self._state["pset"]["selected"]).rjust(3, "0"))
            if mid == "0022":
                return ascii_payload("01", "1")
            if mid == "0035":
                return ascii_payload("01", str(self._state["job"]["selected"]).rjust(4, "0"))
            if mid == "0052":
                return ascii_payload("01", str(self._state["vin"]["current"]).ljust(25)[:25])
            if mid == "0061":
                latest = self._state["results"]["history"][-1] if self._state["results"]["history"] else {}
                tid = str(latest.get("tightening_id", self._state["results"]["last_tightening_id"])).rjust(10, "0")
                status = latest.get("status", "OK")
                return ascii_payload("01", tid, "02", status.ljust(3)[:3])
            if mid == "0071":
                alarm = self._state["alarms"]["active"][-1] if self._state["alarms"]["active"] else {"code": "0000", "text": "No alarm"}
                return ascii_payload("01", str(alarm["code"]).rjust(4, "0"), "02", str(alarm["text"]).ljust(25)[:25])
            if mid == "0211":
                return ascii_payload("01", "1")
            if mid == "0217":
                return ascii_payload("01", "1")
            if mid == "0221":
                return ascii_payload("01", "1")
            if mid == "0401":
                return ascii_payload("01", "AUTO")
            if mid == "0421":
                return ascii_payload("01", "0")
            if mid == "0501":
                return ascii_payload("01", "OK")
            if mid == "0900":
                points = self._state["traces"]["latest"]["points"] if self._state["traces"]["latest"] else [10, 12, 14, 15]
                binary = bytes(int(p) & 0xFF for p in points)
                return ascii_payload("01", "TRACE", "02", f"{len(binary):04d}") + b"\x00" + binary
            if mid == "1000":
                alarm = self._state["alarms"]["active"][-1] if self._state["alarms"]["active"] else {"code": "0000", "text": "No alarm"}
                return ascii_payload("01", str(alarm["code"]).rjust(4, "0"), "02", str(alarm["text"]).ljust(25)[:25])
            if mid == "1201":
                latest = self._state["results"]["history"][-1] if self._state["results"]["history"] else {}
                torque = f"{float(latest.get('torque_nm', 12.34)):07.2f}"
                angle = f"{float(latest.get('angle_deg', 123.0)):07.2f}"
                return ascii_payload("01", torque, "02", angle)
            if mid == "1202":
                latest = self._state["results"]["history"][-1] if self._state["results"]["history"] else {}
                return ascii_payload("01", str(latest.get("status", "OK")).ljust(3)[:3])
            if mid == "0262":
                return ascii_payload("01", "TAG1234567890")
            if mid == "0101":
                return ascii_payload("01", "MS_RESULT")
            if mid == "0106":
                return ascii_payload("01", "STATION_RESULT")
            if mid == "0107":
                return ascii_payload("01", "BOLT_RESULT")
            if mid == "0242":
                return ascii_payload("01", "USER_DATA")
            if mid == "0251":
                return ascii_payload("01", str(self._state["selector"]["socket"]).rjust(2, "0"))
            if mid == "2601":
                return ascii_payload("01", "0001")
            if mid == "2603":
                return ascii_payload("01", "MODE_DEFAULT")
            return ascii_payload("01", "SIM")
