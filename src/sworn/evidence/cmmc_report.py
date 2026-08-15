"""CMMC evidence support report generator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sworn.config import SwornConfig
from sworn.evidence.log import chain_status, read_entries, verify_chain

CMMC_CONTROLS = [
    ("AC.L2-3.1.1", "Limit system access to authorized users"),
    ("AC.L2-3.1.2", "Limit system access to functions authorized users are permitted to execute"),
    ("AU.L2-3.3.1", "Create and retain system audit logs and records"),
    ("AU.L2-3.3.2", "Ensure actions can be uniquely traced to individual users"),
    ("CM.L2-3.4.1", "Establish and maintain baseline configurations"),
    ("CM.L2-3.4.2", "Establish and enforce security configuration settings"),
    ("CM.L2-3.4.5", "Define, document, approve, and enforce access restrictions"),
    ("SC.L2-3.13.1", "Monitor, control, and protect communications at boundaries"),
    ("SI.L2-3.14.1", "Identify, report, and correct system flaws in a timely manner"),
]


def _assess_control(
    control_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess a single control against evidence entries."""
    evidence_count = 0
    met = False
    last_verified = ""

    for entry in entries:
        kernels = entry.get("kernels", [])
        for kernel in kernels:
            rules = kernel.get("triggered_rules", [])
            if control_id in rules:
                evidence_count += 1
                last_verified = entry.get("timestamp", "")
                if kernel.get("decision") == "PASS":
                    met = True

    return {
        "control_id": control_id,
        "status": "SUPPORTED (indirect)"
        if met and control_id == "SI.L2-3.14.1"
        else ("SUPPORTED" if met else "NOT_SUPPORTED"),
        "evidence_count": evidence_count,
        "last_verified": last_verified,
    }


def generate_cmmc_report(
    log_path: Path,
    config: SwornConfig,
    output_format: str = "text",
) -> str:
    """Generate CMMC compliance report.

    Args:
        log_path: Path to evidence JSONL log.
        config: SwornConfig instance.
        output_format: "text" or "json".

    Returns:
        Formatted report string.
    """
    entries = read_entries(log_path)
    valid, chain_msg = verify_chain(log_path)
    status = chain_status(valid, chain_msg)

    controls: list[dict[str, Any]] = []
    for control_id, _desc in CMMC_CONTROLS:
        assessment = _assess_control(control_id, entries)
        controls.append(assessment)

    met_count = sum(1 for c in controls if c["status"].startswith("SUPPORTED"))
    total = len(controls)

    report_data = {
        "controls": controls,
        "evidence_chain": {
            "valid": status == "VALID",
            "status": status,
            "message": chain_msg,
            "total_entries": len(entries),
        },
        "metadata": {
            "controls_met": met_count,
            "controls_total": total,
            "coverage": f"{met_count}/{total}",
        },
    }

    if output_format == "json":
        return json.dumps(report_data, indent=2)

    return _format_text(report_data)


def _format_text(data: dict[str, Any]) -> str:
    """Format report as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("CMMC Level 2 — Evidence Support Report")
    lines.append("This report summarizes governance evidence that may support assessment. "
                 "It does not certify compliance.")
    lines.append("=" * 60)
    lines.append("")

    meta = data["metadata"]
    lines.append(f"Coverage: {meta['coverage']} controls assessed")
    lines.append("")

    # Control assessment table
    lines.append(f"{'Control':<16} {'Status':<20} {'Evidence':<10} {'Last Verified'}")
    lines.append("-" * 60)

    for ctrl in data["controls"]:
        lines.append(
            f"{ctrl['control_id']:<16} {ctrl['status']:<10} "
            f"{ctrl['evidence_count']:<10} {ctrl['last_verified'] or 'never'}"
        )

    lines.append("")

    # Evidence chain
    chain = data["evidence_chain"]
    lines.append(f"Evidence Chain: {chain['status']}")
    lines.append(f"  {chain['message']}")
    lines.append(f"  Total entries: {chain['total_entries']}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
