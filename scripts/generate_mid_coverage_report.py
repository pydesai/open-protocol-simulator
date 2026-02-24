#!/usr/bin/env python3
"""Generate MID coverage report by profile."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    catalog = json.loads((root / "backend/data/mid_catalog.json").read_text())
    atlas = json.loads((root / "backend/data/profiles/atlas_pf.json").read_text())
    cleco = json.loads((root / "backend/data/profiles/cleco.json").read_text())

    lines: list[str] = []
    lines.append("# MID Coverage Report")
    lines.append("")
    lines.append(f"Total MIDs in catalog: **{len(catalog)}**")
    lines.append("")
    lines.append("| MID | Name | Atlas | Cleco | Revisions (Base) |")
    lines.append("|---|---|---:|---:|---|")
    for item in catalog:
        mid = item["mid"]
        name = item["name"]
        atlas_support = "Y" if mid in atlas["supported_mids"] else "N"
        cleco_support = "Y" if mid in cleco["supported_mids"] else "N"
        revs = atlas["revision_overrides"].get(mid, item.get("supported_revisions", [1]))
        lines.append(f"| {mid} | {name} | {atlas_support} | {cleco_support} | {','.join(str(r) for r in revs)} |")

    out = root / "docs/MID_COVERAGE.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

