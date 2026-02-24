from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Profile:
    name: str
    display_name: str
    description: str
    supported_mids: list[str]
    revision_overrides: dict[str, list[int]]
    notes: dict[str, Any]


class ProfileStore:
    def __init__(self, profiles: dict[str, Profile], active: str):
        if active not in profiles:
            active = next(iter(profiles.keys()))
        self._profiles = profiles
        self._active = active

    @classmethod
    def from_directory(cls, path: Path, active: str) -> "ProfileStore":
        profiles: dict[str, Profile] = {}
        for file in sorted(path.glob("*.json")):
            raw = json.loads(file.read_text(encoding="utf-8"))
            profile = Profile(
                name=raw["name"],
                display_name=raw.get("display_name", raw["name"]),
                description=raw.get("description", ""),
                supported_mids=raw.get("supported_mids", []),
                revision_overrides=raw.get("revision_overrides", {}),
                notes=raw.get("notes", {}),
            )
            profiles[profile.name] = profile
        if not profiles:
            raise RuntimeError(f"No profiles found in {path}")
        return cls(profiles, active)

    @property
    def active(self) -> Profile:
        return self._profiles[self._active]

    @property
    def active_name(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._profiles:
            raise KeyError(name)
        self._active = name

    def names(self) -> list[str]:
        return list(self._profiles.keys())

    def all(self) -> list[Profile]:
        return list(self._profiles.values())

    def get(self, name: str) -> Profile:
        return self._profiles[name]

