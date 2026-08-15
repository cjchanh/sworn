"""Tests for report generator."""
from __future__ import annotations

import json
from pathlib import Path

from sworn.evidence.report import generate_report


class TestReport:
    def test_text_output(self, sample_evidence: Path):
        report = generate_report(sample_evidence)
        assert "SWORN EVIDENCE REPORT" in report
        assert "Total commits gated: 5" in report

    def test_json_output(self, sample_evidence: Path):
        report = generate_report(sample_evidence, output_format="json")
        data = json.loads(report)
        assert data["total"] == 5
        assert data["passed"] == 4
        assert data["blocked"] == 1
        assert data["chain_status"] == "VALID"
        assert data["chain_valid"] is True

    def test_empty_log(self, tmp_path: Path):
        log = tmp_path / "empty.jsonl"
        report = generate_report(log)
        assert "No evidence entries" in report

    def test_date_filtering(self, sample_evidence: Path):
        report = generate_report(
            sample_evidence, output_format="json", since="2026-01-03"
        )
        data = json.loads(report)
        assert data["total"] == 3
