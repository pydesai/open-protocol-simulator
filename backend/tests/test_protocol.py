from __future__ import annotations

import unittest

from app.protocol import build_message, next_sequence, parse_stream_buffer


class ProtocolTests(unittest.TestCase):
    def test_build_and_parse_ascii(self) -> None:
        msg = build_message(mid="0001", data=b"01", revision=7, sequence_number=1)
        buffer = bytearray(msg.raw)
        parsed = parse_stream_buffer(buffer)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].mid, "0001")
        self.assertEqual(parsed[0].revision, 7)
        self.assertEqual(parsed[0].header.sequence_int, 1)
        self.assertEqual(parsed[0].data, b"01")

    def test_stream_resync_on_bad_prefix(self) -> None:
        good = build_message(mid="0003", data=b"", revision=1)
        buffer = bytearray(b"XXXX" + good.raw)
        parsed = parse_stream_buffer(buffer)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].mid, "0003")

    def test_next_sequence_wrap(self) -> None:
        self.assertEqual(next_sequence(1), 2)
        self.assertEqual(next_sequence(99), 1)


if __name__ == "__main__":
    unittest.main()

