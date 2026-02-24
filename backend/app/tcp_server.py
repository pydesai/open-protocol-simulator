from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from .config import Settings
from .dispatcher import OpenProtocolDispatcher
from .protocol import NUL, build_message, format_mid_error_payload, next_sequence, parse_stream_buffer
from .state import SimulatorState
from .types import AckMode, OpenProtocolMessage, SessionContext, SessionRole

LOG = logging.getLogger(__name__)


class TcpService:
    def __init__(self, settings: Settings, state: SimulatorState, dispatcher: OpenProtocolDispatcher):
        self.settings = settings
        self.state = state
        self.dispatcher = dispatcher
        self._servers: list[asyncio.AbstractServer] = []
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    async def start(self) -> None:
        for role, port in (
            (SessionRole.CLASSIC, self.settings.classic_port),
            (SessionRole.ACTOR, self.settings.actor_port),
            (SessionRole.VIEWER, self.settings.viewer_port),
        ):
            server = await asyncio.start_server(
                lambda r, w, role=role: self._handle_client(r, w, role),
                host=self.settings.host,
                port=port,
            )
            self._servers.append(server)
            LOG.info("Listening for %s sessions on %s:%d", role.value, self.settings.host, port)

        self._tasks.append(asyncio.create_task(self._keepalive_watchdog()))

    async def stop(self) -> None:
        self._stopping = True
        for server in self._servers:
            server.close()
            await server.wait_closed()
        self._servers.clear()

        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(Exception):
                await task
        self._tasks.clear()

    async def _keepalive_watchdog(self) -> None:
        while not self._stopping:
            await asyncio.sleep(1)
            sessions = await self.state.sessions()
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.settings.sim_keepalive_timeout_sec)
            for session_info in sessions:
                last_activity = datetime.fromisoformat(session_info["last_activity"])
                if last_activity < cutoff:
                    context = await self.state.get_session(session_info["session_id"])
                    if context and context.writer:
                        LOG.info("Closing session %s due to keepalive timeout", context.session_id)
                        context.writer.close()
                        with contextlib.suppress(Exception):
                            await context.writer.wait_closed()

    async def _send(self, session: SessionContext, message: OpenProtocolMessage, *, direction: str = "tx") -> None:
        writer = session.writer
        if writer is None or writer.is_closing():
            return
        writer.write(message.raw)
        await writer.drain()
        await self.state.record_traffic(session, direction, message)

    def _with_sequence_if_needed(self, session: SessionContext, msg: OpenProtocolMessage) -> OpenProtocolMessage:
        if session.ack_mode != AckMode.LINK_LEVEL:
            return msg
        if msg.mid in {"9997", "9998"}:
            return msg
        seq = session.next_tx_seq
        session.next_tx_seq = next_sequence(session.next_tx_seq)
        append_nul = msg.raw.endswith(NUL)
        return build_message(
            mid=msg.mid,
            data=msg.data,
            revision=msg.header.revision,
            no_ack_flag=msg.header.no_ack_flag,
            station_id=msg.header.station_id,
            spindle_id=msg.header.spindle_id,
            sequence_number=seq,
            message_parts=msg.header.message_parts,
            message_part_number=msg.header.message_part_number,
            append_nul=append_nul,
            binary=msg.binary,
        )

    async def _handle_link_ack(self, session: SessionContext, msg: OpenProtocolMessage) -> tuple[bool, OpenProtocolMessage | None]:
        """Returns (continue_processing, outbound_ack)."""
        if not msg.header.has_sequence:
            session.ack_mode = AckMode.APPLICATION
            return True, None

        session.ack_mode = AckMode.LINK_LEVEL
        seq = msg.header.sequence_int
        expected = session.next_rx_seq

        if seq == expected:
            next_expected = next_sequence(expected)
            session.next_rx_seq = next_expected
            session.last_rx_seq = seq
            ack = build_message(
                mid="9997",
                data=f"{msg.mid}".encode("ascii"),
                revision=1,
                sequence_number=next_expected,
            )
            session.last_link_ack = ack
            return True, ack

        if seq == session.last_rx_seq and session.last_link_ack is not None:
            return False, session.last_link_ack

        nack = build_message(
            mid="9998",
            data=format_mid_error_payload(msg.mid, 3),
            revision=1,
            sequence_number=expected,
        )
        session.last_link_ack = nack
        return False, nack

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        role: SessionRole,
    ) -> None:
        peer = writer.get_extra_info("peername")
        remote = f"{peer[0]}:{peer[1]}" if peer else "unknown"
        session = SessionContext(
            session_id=uuid.uuid4().hex[:12],
            role=role,
            remote=remote,
            writer=writer,
        )
        ok, reason = await self.state.register_session(session)
        if not ok:
            # Best-effort reject with error 16.
            reject = build_message(mid="0004", data=format_mid_error_payload("0001", 16), revision=1)
            writer.write(reject.raw)
            await writer.drain()
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            LOG.warning("Rejected %s session (%s): %s", role.value, remote, reason)
            return

        LOG.info("Session connected %s (%s, %s)", session.session_id, role.value, remote)
        buffer = bytearray()
        try:
            while not reader.at_eof():
                chunk = await reader.read(4096)
                if not chunk:
                    break
                session.touch()
                buffer.extend(chunk)
                incoming = parse_stream_buffer(buffer)
                for msg in incoming:
                    await self.state.record_traffic(session, "rx", msg)

                    process, link_ack = await self._handle_link_ack(session, msg)
                    if link_ack:
                        await self._send(session, link_ack)
                    if not process:
                        continue

                    responses = await self.dispatcher.dispatch(session, msg)
                    for response in responses:
                        out = self._with_sequence_if_needed(session, response)
                        await self._send(session, out)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive.
            LOG.exception("Session failed %s", session.session_id)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            await self.state.unregister_session(session.session_id)
            LOG.info("Session closed %s", session.session_id)

    async def publish_event(self, event_type: str, payload: dict | None = None) -> dict:
        event = await self.state.inject_event(event_type, payload or {})
        session_list = await self.state.sessions()
        pushed = 0

        for info in session_list:
            session = await self.state.get_session(info["session_id"])
            if not session or not session.communication_started:
                continue
            messages = await self.state.generate_push_messages(session, event)
            for msg in messages:
                out = self._with_sequence_if_needed(session, msg)
                await self._send(session, out)
                pushed += 1

        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "affected_mids": event.affected_mids,
            "pushed_messages": pushed,
        }

