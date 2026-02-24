from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .mid_catalog import MidCatalog
from .profiles import ProfileStore
from .protocol import ascii_payload, build_message, format_mid_ack_payload, format_mid_error_payload
from .state import SimulatorState
from .types import OpenProtocolMessage, SessionContext


REQUEST_TO_REPLY_MAP: dict[str, str] = {
    "0010": "0011",
    "0012": "0013",
    "0030": "0031",
    "0032": "0033",
    "0040": "0041",
    "0050": "0052",
    "0064": "0065",
    "0080": "0081",
    "0214": "0215",
    "0260": "0262",
    "0300": "0301",
    "0410": "0411",
    "2600": "2601",
    "2602": "2603",
}


def _extract_first_int(data: str, digits: int, default: str) -> str:
    m = re.search(rf"(\d{{{digits}}})", data)
    if not m:
        return default
    return m.group(1)


class OpenProtocolDispatcher:
    def __init__(self, settings: Settings, catalog: MidCatalog, profiles: ProfileStore, state: SimulatorState):
        self.settings = settings
        self.catalog = catalog
        self.profiles = profiles
        self.state = state

    def _is_mid_supported(self, mid: str) -> bool:
        return mid in self.profiles.active.supported_mids

    def _supported_revisions(self, mid: str) -> list[int]:
        override = self.profiles.active.revision_overrides.get(mid)
        if override:
            return override
        definition = self.catalog.get(mid)
        return definition.supported_revisions if definition else [1]

    def _build_0002(self, session: SessionContext) -> OpenProtocolMessage:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d:%H:%M:%S")
        controller_name = "OpenProtocolSim".ljust(25)[:25]
        op_version = "2.16.0".ljust(19)
        controller_sw = "sim-0.1.0".ljust(19)
        tool_sw = "sim-tool-0.1".ljust(19)
        rbu_type = "SIM-RBU".ljust(24)
        serial = "SIM0000001".ljust(10)
        system_type = "003"
        system_subtype = "001"
        seq_support = "1"
        linking_support = "1"
        station_id_10 = "0000000001"
        station_name = "Simulator Station".ljust(25)[:25]
        client_id = "1"
        optional_keepalive = "0"

        data = ascii_payload(
            "01",
            "0001",
            "02",
            "01",
            "03",
            controller_name,
            "04",
            "ACT",
            "05",
            op_version,
            "06",
            controller_sw,
            "07",
            tool_sw,
            "08",
            rbu_type,
            "09",
            serial,
            "10",
            system_type,
            "11",
            system_subtype,
            "12",
            seq_support,
            "13",
            linking_support,
            "14",
            station_id_10,
            "15",
            station_name,
            "16",
            client_id,
            "17",
            optional_keepalive,
            "18",
            now.ljust(19)[:19],
        )
        return build_message(mid="0002", data=data, revision=7)

    async def _apply_simple_command_side_effects(self, msg: OpenProtocolMessage) -> None:
        data = msg.data_ascii()
        if msg.mid == "0018":
            domain = await self.state.get_state_domain("pset")
            domain["selected"] = _extract_first_int(data, 3, domain.get("selected", "001"))
            await self.state.update_state_domain("pset", domain)
        elif msg.mid == "0038":
            domain = await self.state.get_state_domain("job")
            domain["selected"] = _extract_first_int(data, 4, domain.get("selected", "0001"))
            await self.state.update_state_domain("job", domain)
        elif msg.mid == "0019":
            domain = await self.state.get_state_domain("pset")
            try:
                domain["batch_size"] = int(_extract_first_int(data, 4, "0001"))
            except ValueError:
                pass
            await self.state.update_state_domain("pset", domain)
        elif msg.mid == "0020":
            domain = await self.state.get_state_domain("pset")
            domain["batch_counter"] = 0
            await self.state.update_state_domain("pset", domain)
        elif msg.mid == "0042":
            domain = await self.state.get_state_domain("tool")
            domain["enabled"] = False
            await self.state.update_state_domain("tool", domain)
        elif msg.mid == "0043":
            domain = await self.state.get_state_domain("tool")
            domain["enabled"] = True
            await self.state.update_state_domain("tool", domain)
        elif msg.mid == "0046":
            domain = await self.state.get_state_domain("tool")
            domain["primary_tool"] = _extract_first_int(data, 2, "01")
            await self.state.update_state_domain("tool", domain)
        elif msg.mid == "0156":
            domain = await self.state.get_state_domain("identifiers")
            domain["latest"] = None
            await self.state.update_state_domain("identifiers", domain)
        elif msg.mid == "0157":
            domain = await self.state.get_state_domain("identifiers")
            domain["latest"] = None
            domain["all"] = []
            await self.state.update_state_domain("identifiers", domain)
        elif msg.mid == "0240":
            domain = await self.state.get_state_domain("user_data")
            domain["records"]["last_download"] = data
            await self.state.update_state_domain("user_data", domain)
        elif msg.mid == "0270":
            await self.state.reset()
        elif msg.mid == "2606":
            domain = await self.state.get_state_domain("mode")
            domain["selected"] = _extract_first_int(data, 4, domain.get("selected", "0001"))
            await self.state.update_state_domain("mode", domain)

    async def dispatch(self, session: SessionContext, msg: OpenProtocolMessage) -> list[OpenProtocolMessage]:
        session.touch()
        mid = msg.mid
        definition = self.catalog.get(mid)

        if definition is None:
            return [build_message(mid="0004", data=format_mid_error_payload(mid, 99), revision=1)]

        if not self._is_mid_supported(mid):
            if definition.category == "subscription_start":
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 73), revision=1)]
            if definition.category == "request":
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 75), revision=1)]
            return [build_message(mid="0004", data=format_mid_error_payload(mid, 79), revision=1)]

        supported_revisions = self._supported_revisions(mid)
        if msg.revision not in supported_revisions and msg.revision != 0:
            error = 74 if definition.category == "subscription_start" else 98
            return [build_message(mid="0004", data=format_mid_error_payload(mid, error), revision=1)]

        # Communication must start with MID 0001.
        if mid != "0001" and not session.communication_started:
            return [build_message(mid="0004", data=format_mid_error_payload(mid, 97), revision=1)]

        if mid == "0001":
            if session.communication_started:
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 97), revision=1)]
            if session.role.value == "actor":
                actor_exists = await self.state.actor_active(exclude_session=session.session_id)
                if actor_exists:
                    return [build_message(mid="0004", data=format_mid_error_payload(mid, 35), revision=1)]
            session.communication_started = True
            return [self._build_0002(session)]

        if mid == "0003":
            session.communication_started = False
            session.subscriptions.clear()
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if mid == "9999":
            # Keep alive mirror.
            return [build_message(mid="9999", data=msg.data, revision=msg.header.revision)]

        if mid == "0008":
            target = _extract_first_int(msg.data_ascii(), 4, "")
            if not target or not self.catalog.contains(target):
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 73), revision=1)]
            await self.state.add_subscription(session, target)
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if mid == "0009":
            target = _extract_first_int(msg.data_ascii(), 4, "")
            if target:
                await self.state.remove_subscription(session, target)
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if definition.category == "subscription_start":
            await self.state.add_subscription(session, mid)
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if definition.category == "subscription_stop":
            await self.state.remove_subscription(session, mid)
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if mid == "0006":
            target = _extract_first_int(msg.data_ascii(), 4, "")
            if not target or not self.catalog.contains(target):
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 75), revision=1)]
            if not self._is_mid_supported(target):
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 75), revision=1)]
            data = await self.state.build_data_for_mid(target)
            return [build_message(mid=target, data=data, revision=1, append_nul=(target != "0900"), binary=(target == "0900"))]

        if definition.category == "request":
            reply_mid = REQUEST_TO_REPLY_MAP.get(mid)
            if not reply_mid:
                plus_one = f"{int(mid) + 1:04d}"
                candidate = self.catalog.get(plus_one)
                if candidate and candidate.category in {"reply", "event_or_data"}:
                    reply_mid = plus_one
            if not reply_mid:
                return [build_message(mid="0004", data=format_mid_error_payload(mid, 75), revision=1)]
            data = await self.state.build_data_for_mid(reply_mid)
            return [
                build_message(
                    mid=reply_mid,
                    data=data,
                    revision=1,
                    append_nul=(reply_mid != "0900"),
                    binary=(reply_mid == "0900"),
                )
            ]

        if definition.category == "command":
            allowed, err = await self.state.ensure_command_allowed(session)
            if not allowed:
                return [build_message(mid="0004", data=format_mid_error_payload(mid, err), revision=1)]
            await self._apply_simple_command_side_effects(msg)
            return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

        if definition.category == "ack":
            # No app-level reply for ack messages.
            return []

        # Event/data message coming from integrator side: accept command-style for compatibility.
        return [build_message(mid="0005", data=format_mid_ack_payload(mid), revision=1)]

