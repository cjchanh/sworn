"""Report generator — human-readable and JSON summaries from evidence log."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sworn.evidence.log import chain_status, read_entries, verify_chain


def generate_report(
    log_path: Path,
    output_format: str = "text",
    since: str | None = None,
) -> str:
    """Generate a report from the evidence log."""
    entries = read_entries(log_path)

    if since:
        entries = [e for e in entries if e.get("timestamp", "") >= since]

    if not entries:
        if output_format == "json":
            return json.dumps({"total": 0, "message": "No evidence entries"})
        return "No evidence entries found."

    total = len(entries)
    passed = sum(1 for e in entries if e.get("decision") == "PASS")
    blocked = sum(1 for e in entries if e.get("decision") == "BLOCKED")

    # Collect block reasons
    block_reasons: Counter[str] = Counter()
    for e in entries:
        if e.get("decision") == "BLOCKED":
            reason = e.get("reason", "unknown")
            block_reasons[reason] += 1

    # Collect files
    all_files: Counter[str] = Counter()
    for e in entries:
        for f in e.get("files", []):
            all_files[f] += 1

    # Tools detected
    tools: Counter[str] = Counter()
    for e in entries:
        tool = e.get("tool") or "none"
        tools[tool] += 1

    # Chain integrity
    chain_valid, chain_msg = verify_chain(log_path)
    status = chain_status(chain_valid, chain_msg)

    # Date range
    timestamps = [e.get("timestamp", "") for e in entries]
    first = min(timestamps) if timestamps else "—"
    last = max(timestamps) if timestamps else "—"

    if output_format == "json":
        return json.dumps(
            {
                "total": total,
                "passed": passed,
                "blocked": blocked,
                "pass_rate": round(passed / total * 100, 1) if total else 0,
                "top_block_reasons": dict(block_reasons.most_common(5)),
                "top_files": dict(all_files.most_common(10)),
                "tools": dict(tools),
                "date_range": {"first": first, "last": last},
                "chain_valid": status == "VALID",
                "chain_status": status,
                "chain_message": chain_msg,
            },
            indent=2,
        )

    # Text format
    lines: list[str] = []
    lines.append("SWORN EVIDENCE REPORT")
    lines.append("=" * 40)
    lines.append(f"Period: {first} — {last}")
    lines.append(f"Total commits gated: {total}")
    lines.append(f"  Passed: {passed}")
    lines.append(f"  Blocked: {blocked}")
    if total:
        lines.append(f"  Pass rate: {passed / total * 100:.1f}%")
    lines.append("")

    if block_reasons:
        lines.append("Top block reasons:")
        for reason, count in block_reasons.most_common(5):
            lines.append(f"  [{count}] {reason}")
        lines.append("")

    if tools:
        lines.append("AI tools detected:")
        for tool, count in tools.most_common(5):
            lines.append(f"  [{count}] {tool}")
        lines.append("")

    if all_files:
        lines.append("Most frequently gated files:")
        for f, count in all_files.most_common(5):
            lines.append(f"  [{count}] {f}")
        lines.append("")

    lines.append(f"Chain integrity: {status}")
    lines.append(f"  {chain_msg}")

    return "\n".join(lines)
