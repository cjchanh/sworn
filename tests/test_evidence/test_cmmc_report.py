"""Tests for CMMC compliance report generator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sworn.config import SwornConfig, _compile_patterns, DEFAULT_SECURITY_PATTERNS
from sworn.evidence.cmmc_report import generate_cmmc_report


def _write_cmmc_log(log_path: Path, entries_data: list[dict] | None = None) -> None:
    """Write evidence log with CMMC kernel results."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prev_hash = "genesis"

    if entries_data is None:
        entries_data = [
            {
                "kernels": [
                    {"name": "cmmc_ac_access", "decision": "PASS",
                     "triggered_rules": ["AC.L2-3.1.1", "AC.L2-3.1.2"], "evidence_summary": ["Actor: cj"]},
                    {"name": "cmmc_au_records", "decision": "PASS",
                     "triggered_rules": ["AU.L2-3.3.1"], "evidence_summary": ["Hash chain enabled"]},
                    {"name": "cmmc_si_flaw", "decision": "PASS",
                     "triggered_rules": ["SI.L2-3.14.1"], "evidence_summary": ["Pipeline running"]},
                ],
            },
            {
                "kernels": [
                    {"name": "cmmc_sc_boundary", "decision": "BLOCKED",
                     "triggered_rules": ["SC.L2-3.13.1"], "evidence_summary": [".env detected"]},
                ],
            },
        ]

    for i, data in enumerate(entries_data):
        entry = {
            "timestamp": f"2026-01-0{i + 1}T00:00:00Z",
            "actor": "test", "tool": None, "files": [f"f{i}.py"],
            "gates": {"identity": "PASS"}, "decision": "PASS", "reason": "",
            "resolution_trace": {}, "prev_hash": prev_hash, "signature": "",
        }
        entry["kernels"] = data.get("kernels", [])
        canonical = dict(entry)
        canonical["signature"] = ""
        canonical_json = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
        prev_hash = hashlib.sha256(canonical_json.encode()).hexdigest()
        line = json.dumps(entry, separators=(",", ":"), sort_keys=True)
        with log_path.open("a") as f:
            f.write(line + "\n")


def _config() -> SwornConfig:
    return SwornConfig(
        security_patterns=_compile_patterns(DEFAULT_SECURITY_PATTERNS),
        evidence_hash_chain=True,
    )


class TestCMMCReport:
    def test_all_controls_in_text_output(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "text")
        assert "AC.L2-3.1.1" in report
        assert "SC.L2-3.13.1" in report
        assert "CMMC Level 2" in report
        assert "Evidence Support Report" in report

    def test_json_structure(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "json")
        data = json.loads(report)
        assert "controls" in data
        assert "evidence_chain" in data
        assert "metadata" in data
        assert len(data["controls"]) == 9

    def test_empty_log_handling(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        report = generate_cmmc_report(log_path, _config(), "text")
        assert "0/9" in report

    def test_block_counts_accurate(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "json")
        data = json.loads(report)
        supported_controls = [c for c in data["controls"] if c["status"].startswith("SUPPORTED")]
        # AC.L2-3.1.1, AC.L2-3.1.2, AU.L2-3.3.1, SI.L2-3.14.1 should be supported
        assert len(supported_controls) >= 3

    def test_chain_integrity_reflected(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "json")
        data = json.loads(report)
        assert data["evidence_chain"]["valid"] is True
        assert data["evidence_chain"]["status"] == "VALID"

    def test_empty_log_chain_is_empty_not_valid(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        report = generate_cmmc_report(log_path, _config(), "json")
        data = json.loads(report)
        assert data["evidence_chain"]["status"] == "EMPTY"
        assert data["evidence_chain"]["valid"] is False

    def test_per_control_evidence_count(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "json")
        data = json.loads(report)
        ac_control = next(c for c in data["controls"] if c["control_id"] == "AC.L2-3.1.1")
        assert ac_control["evidence_count"] >= 1

    def test_threat_cmmc_report_no_compliance_claim(self, tmp_path: Path):
        log_path = tmp_path / ".sworn" / "evidence.jsonl"
        _write_cmmc_log(log_path)
        report = generate_cmmc_report(log_path, _config(), "text")
        assert "may support assessment" in report.lower()
        assert "compliance" not in report.split("\n")[0].lower()
