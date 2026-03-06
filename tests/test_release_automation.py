"""Tests for release automation helpers."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_static_guard_passes_on_current_tree():
    result = subprocess.run(
        [sys.executable, "scripts/release_static_guard.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: release static guard" in result.stdout


def test_release_phase0_runs_static_guard_and_smoke_harness():
    content = (ROOT / "scripts" / "release_phase0_readiness.sh").read_text()

    assert "scripts/release_static_guard.py" in content
    assert "release-static-guard.log" in content
    assert "scripts/release_smoke.py" in content
    assert "release-smoke.log" in content


def test_release_phase1_capture_help_is_available():
    result = subprocess.run(
        ["bash", "scripts/release_phase1_capture.sh", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Usage:" in result.stdout
