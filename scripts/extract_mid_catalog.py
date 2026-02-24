#!/usr/bin/env python3
"""Extract Open Protocol MID catalog and revision hints from the PDF spec text."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MID_INDEX_RE = re.compile(r"^MID\s+(\d{4})\s+(.+?)\s*\.{3,}\d+\s*$")
MID_IN_LINE_RE = re.compile(r"\bMID\s+(\d{4})\b")

# Captures:
# - "revision 7"
# - "revision 000-001"
# - "revisions 1,2 and 3"
# - "revision 1, 2 and 3"
REV_RANGE_RE = re.compile(r"\brevision(?:s)?\s+(\d{1,3})\s*-\s*(\d{1,3})", re.IGNORECASE)
REV_LIST_RE = re.compile(r"\brevision(?:s)?\s+([0-9,\sand]+)", re.IGNORECASE)
REV_ONLY_RE = re.compile(r"\brevision(?:s)?\s+(\d{1,3})\b", re.IGNORECASE)


@dataclass
class MidMeta:
    mid: str
    name: str
    category: str
    direction: str
    supported_revisions: list[int]
    payload_schema: dict
    ack_strategy: str
    error_rules: list[str]
    profile_overrides: dict


def _run_pdftotext(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _normalize_name(raw_name: str) -> str:
    name = " ".join(raw_name.split())
    return name.strip().replace(" .", ".")


def _infer_category(name: str) -> str:
    n = name.lower()
    if "communication start" in n or "communication stop" in n or "keep alive" in n:
        return "session"
    if "subscribe" in n:
        return "subscription_start"
    if "unsubscribe" in n:
        return "subscription_stop"
    if "acknowledge" in n or "acknowledgement" in n:
        return "ack"
    if "upload request" in n or n.endswith("request"):
        return "request"
    if "upload reply" in n or n.endswith("reply"):
        return "reply"
    if (
        n.startswith("select ")
        or n.startswith("set ")
        or n.startswith("reset ")
        or n.startswith("execute ")
        or n.startswith("abort ")
        or n.startswith("disable ")
        or n.startswith("enable ")
        or n.startswith("flash ")
        or "command" in n
    ):
        return "command"
    return "event_or_data"


def _infer_direction(name: str, category: str) -> str:
    n = name.lower()
    if "acknowledge" in n and ("communication acknowledge" in n or "keep alive" in n):
        return "bidirectional"
    if category in {"request", "subscription_start", "subscription_stop", "command"}:
        return "integrator_to_controller"
    if category in {"reply", "event_or_data"} and (
        "upload" in n
        or "result" in n
        or "alarm" in n
        or "status" in n
        or "data" in n
        or "selected" in n
    ):
        return "controller_to_integrator"
    if category == "session":
        return "bidirectional"
    if category == "ack":
        return "bidirectional"
    return "bidirectional"


def _infer_ack_strategy(category: str) -> str:
    if category in {"subscription_start", "subscription_stop", "command"}:
        return "app_ack_0005_or_0004"
    if category == "request":
        return "direct_reply_or_0004"
    if category == "event_or_data":
        return "special_ack_or_9997_9998"
    if category == "ack":
        return "none"
    if category == "session":
        return "session_specific"
    return "none"


def _parse_revision_tokens(token_text: str) -> list[int]:
    token_text = token_text.lower().replace("and", ",")
    values: list[int] = []
    for part in token_text.split(","):
        p = part.strip()
        if not p:
            continue
        if p.isdigit():
            values.append(int(p))
    return values


def _extract_revisions(lines: Iterable[str]) -> dict[str, set[int]]:
    revisions: dict[str, set[int]] = defaultdict(set)
    for line in lines:
        mids = MID_IN_LINE_RE.findall(line)
        if not mids:
            continue

        # Range first, since it may also match single-number expressions.
        for m in REV_RANGE_RE.finditer(line):
            start = int(m.group(1))
            end = int(m.group(2))
            lo, hi = sorted((start, end))
            for mid in mids:
                for rev in range(lo, hi + 1):
                    revisions[mid].add(rev)

        list_match = REV_LIST_RE.search(line)
        if list_match:
            nums = _parse_revision_tokens(list_match.group(1))
            for mid in mids:
                for rev in nums:
                    revisions[mid].add(rev)

        for m in REV_ONLY_RE.finditer(line):
            rev = int(m.group(1))
            for mid in mids:
                revisions[mid].add(rev)

        # "Revision 0-1" can get consumed as single "0" in some OCR lines.
        if "0-1" in line:
            for mid in mids:
                revisions[mid].update({0, 1})
    return revisions


def build_catalog(spec_pdf: Path) -> list[MidMeta]:
    text = _run_pdftotext(spec_pdf)
    lines = [line.strip() for line in text.splitlines()]
    known_mids = sorted({m.group(1) for m in (re.match(r"^MID\s+(\d{4})\b", line) for line in lines) if m})

    names: dict[str, str] = {}
    for line in lines:
        m = MID_INDEX_RE.match(line)
        if not m:
            continue
        mid = m.group(1)
        name = _normalize_name(m.group(2))
        names[mid] = name

    # Add MIDs listed at line-start in the document even if the index title is missing.
    for mid in known_mids:
        names.setdefault(mid, f"MID {mid} (Undocumented title in index)")

    revisions = _extract_revisions(lines)

    catalog: list[MidMeta] = []
    for mid in sorted(names.keys()):
        name = names[mid]
        category = _infer_category(name)
        direction = _infer_direction(name, category)
        revs = sorted(revisions.get(mid) or {1})
        catalog.append(
            MidMeta(
                mid=mid,
                name=name,
                category=category,
                direction=direction,
                supported_revisions=revs,
                payload_schema={},
                ack_strategy=_infer_ack_strategy(category),
                error_rules=[],
                profile_overrides={},
            )
        )
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec-pdf",
        default="OpenProtocol_Specification_R_2.16.0.pdf",
        help="Path to Open Protocol specification PDF",
    )
    parser.add_argument(
        "--output",
        default="backend/data/mid_catalog.json",
        help="Output catalog path",
    )
    args = parser.parse_args()

    spec_pdf = Path(args.spec_pdf)
    output = Path(args.output)

    catalog = build_catalog(spec_pdf)
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = [m.__dict__ for m in catalog]
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload)} MID entries to {output}")


if __name__ == "__main__":
    main()
