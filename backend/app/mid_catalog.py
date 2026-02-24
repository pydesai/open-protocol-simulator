from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .types import MidDefinition


class MidCatalog:
    def __init__(self, entries: Iterable[MidDefinition]):
        self._entries = {e.mid: e for e in sorted(entries, key=lambda x: x.mid)}

    @classmethod
    def from_file(cls, path: Path) -> "MidCatalog":
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries: list[MidDefinition] = []
        for item in raw:
            entries.append(
                MidDefinition(
                    mid=item["mid"],
                    name=item["name"],
                    category=item["category"],
                    direction=item["direction"],
                    supported_revisions=item.get("supported_revisions", [1]),
                    payload_schema=item.get("payload_schema", {}),
                    ack_strategy=item.get("ack_strategy", "none"),
                    error_rules=item.get("error_rules", []),
                    profile_overrides=item.get("profile_overrides", {}),
                )
            )
        return cls(entries)

    def get(self, mid: str) -> MidDefinition | None:
        return self._entries.get(f"{mid:0>4}"[-4:])

    def contains(self, mid: str) -> bool:
        return f"{mid:0>4}"[-4:] in self._entries

    def mids(self) -> list[str]:
        return list(self._entries.keys())

    def as_list(self) -> list[dict]:
        return [asdict(v) for v in self._entries.values()]

    def len(self) -> int:
        return len(self._entries)

