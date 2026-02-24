from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.config import Settings
from app.dispatcher import OpenProtocolDispatcher
from app.mid_catalog import MidCatalog
from app.persistence import PersistenceStore
from app.profiles import ProfileStore
from app.protocol import build_message
from app.state import SimulatorState
from app.types import SessionContext, SessionRole


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        root = Path(__file__).resolve().parent.parent
        settings = Settings.from_env()
        catalog = MidCatalog.from_file(root / "data" / "mid_catalog.json")
        profiles = ProfileStore.from_directory(root / "data" / "profiles", active="atlas_pf")
        state = SimulatorState(
            catalog=catalog,
            profiles=profiles,
            persistence=PersistenceStore(enabled=False, db_path="/tmp/openprotocol_sim_test.db"),
            keepalive_timeout_sec=15,
            inactivity_hint_sec=10,
            max_sessions=10,
        )
        self.dispatcher = OpenProtocolDispatcher(settings, catalog, profiles, state)
        self.state = state
        self.session = SessionContext(session_id="s1", role=SessionRole.CLASSIC, remote="127.0.0.1:9999")

    async def test_handshake_then_keepalive(self) -> None:
        r = await self.dispatcher.dispatch(self.session, build_message(mid="0001", revision=7, data=b"01"))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].mid, "0002")
        k = await self.dispatcher.dispatch(self.session, build_message(mid="9999", revision=1, data=b""))
        self.assertEqual(k[0].mid, "9999")

    async def test_subscribe_flow(self) -> None:
        await self.dispatcher.dispatch(self.session, build_message(mid="0001", revision=7, data=b"01"))
        resp = await self.dispatcher.dispatch(self.session, build_message(mid="0060", revision=1, data=b""))
        self.assertEqual(resp[0].mid, "0005")
        self.assertIn("0060", self.session.subscriptions)


if __name__ == "__main__":
    unittest.main()

