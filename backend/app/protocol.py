from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .types import OpenProtocolHeader, OpenProtocolMessage


NUL = b"\x00"


def zero_pad_int(value: int, width: int) -> str:
    return str(value).rjust(width, "0")


def next_sequence(seq: int) -> int:
    return 1 if seq >= 99 else seq + 1


def parse_header(raw_header: bytes) -> OpenProtocolHeader:
    if len(raw_header) != 20:
        raise ValueError("header must be exactly 20 bytes")
    text = raw_header.decode("ascii", errors="strict")
    return OpenProtocolHeader(
        length=int(text[0:4]),
        mid=text[4:8],
        revision=text[8:11],
        no_ack_flag=text[11],
        station_id=text[12:14],
        spindle_id=text[14:16],
        sequence_number=text[16:18],
        message_parts=text[18],
        message_part_number=text[19],
    )


def build_header(header: OpenProtocolHeader) -> bytes:
    header_text = (
        zero_pad_int(header.length, 4)
        + f"{header.mid:0>4}"
        + f"{header.revision: >3}"[-3:]
        + (header.no_ack_flag or " ")[0]
        + f"{header.station_id: >2}"[-2:]
        + f"{header.spindle_id: >2}"[-2:]
        + f"{header.sequence_number: >2}"[-2:]
        + (header.message_parts or " ")[0]
        + (header.message_part_number or " ")[0]
    )
    return header_text.encode("ascii")


def build_message(
    mid: str,
    data: bytes = b"",
    *,
    revision: int | str = 1,
    no_ack_flag: str = " ",
    station_id: str = "  ",
    spindle_id: str = "  ",
    sequence_number: int | str = 0,
    message_parts: str = " ",
    message_part_number: str = " ",
    append_nul: bool = True,
    binary: bool = False,
) -> OpenProtocolMessage:
    seq = (
        f"{int(sequence_number):02d}"
        if isinstance(sequence_number, int)
        else f"{sequence_number: >2}"[-2:]
    )
    rev = f"{int(revision):03d}" if isinstance(revision, int) else f"{revision: >3}"[-3:]

    length = 20 + len(data)
    header = OpenProtocolHeader(
        length=length,
        mid=f"{mid:0>4}"[-4:],
        revision=rev,
        no_ack_flag=no_ack_flag,
        station_id=station_id,
        spindle_id=spindle_id,
        sequence_number=seq,
        message_parts=message_parts,
        message_part_number=message_part_number,
    )
    header_bytes = build_header(header)
    raw = header_bytes + data
    if append_nul:
        raw += NUL
    return OpenProtocolMessage(header=header, data=data, raw=raw, binary=binary)


def parse_stream_buffer(buffer: bytearray) -> list[OpenProtocolMessage]:
    messages: list[OpenProtocolMessage] = []
    while True:
        if len(buffer) < 4:
            return messages
        length_field = bytes(buffer[0:4])
        if not all(48 <= b <= 57 for b in length_field):
            # Drop one byte and resync.
            del buffer[0]
            continue
        length = int(length_field.decode("ascii"))
        if length < 20:
            del buffer[0:4]
            continue
        if len(buffer) < length:
            return messages

        raw_payload = bytes(buffer[:length])
        del buffer[:length]

        # ASCII messages are usually NUL-terminated but length excludes NUL.
        if buffer[:1] == NUL:
            del buffer[:1]
            raw_payload_with_nul = raw_payload + NUL
        else:
            raw_payload_with_nul = raw_payload

        header = parse_header(raw_payload[:20])
        data = raw_payload[20:]
        binary = header.mid == "0900"
        messages.append(
            OpenProtocolMessage(
                header=replace(header, length=length),
                data=data,
                raw=raw_payload_with_nul,
                binary=binary,
            )
        )


def ascii_payload(*parts: str) -> bytes:
    return "".join(parts).encode("ascii")


def format_mid_ack_payload(mid: str) -> bytes:
    return f"{mid:0>4}"[-4:].encode("ascii")


def format_mid_error_payload(mid: str, code: int) -> bytes:
    return f"{mid:0>4}{code:02d}".encode("ascii")


def encode_variable_fields(fields: Iterable[tuple[int, str, str, str, str, str]]) -> bytes:
    """Encode variable data fields.

    Field tuple:
    - pid (int, 5 digits)
    - data_type (2 chars)
    - unit (3 chars)
    - step_no (4 chars)
    - value (string)
    - length_override (3 chars or empty for auto)
    """

    encoded_fields: list[bytes] = []
    for pid, data_type, unit, step_no, value, length_override in fields:
        value_bytes = value.encode("ascii", errors="ignore")
        length = length_override if length_override else f"{len(value_bytes):03d}"
        encoded_fields.append(
            (
                f"{pid:05d}{length}{data_type: >2}{unit: >3}{step_no:0>4}".encode("ascii")
                + value_bytes
            )
        )
    return f"{len(encoded_fields):03d}".encode("ascii") + b"".join(encoded_fields)

