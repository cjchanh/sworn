"""Tests for release automation helpers."""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_static_guard():
    path = ROOT / "scripts" / "release_static_guard.py"
    spec = importlib.util.spec_from_file_location("release_static_guard", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_vocab_ban_positive_control_scratch_copy(tmp_path: Path):
    """Plant one banned word in a scratch tree; the guard must fail."""
    (tmp_path / "README.md").write_text("# scratch\nthis testifies nothing\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.4.1"\ndescription = "ok product"\n'
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("plain notes\n")
    guard = _load_static_guard()
    hits = guard.banned_vocab_hits(tmp_path)
    assert hits, "planted 'testifies' must be detected"
    assert any("testifies" in hit for hit in hits)


def test_vocab_ban_does_not_flag_governance_or_operating():
    guard = _load_static_guard()
    assert guard._scan_text("x", "governance operating systems") == []


def test_vocab_ban_skips_fenced_import_operator():
    guard = _load_static_guard()
    text = "plain prose\n```python\nimport operator\n```\nmore prose\n"
    assert guard._scan_text("x", text) == []


def test_vocab_ban_skips_inline_code_span():
    guard = _load_static_guard()
    assert guard._scan_text("x", "use the `operator` module") == []


def test_vocab_ban_scans_root_markdown(tmp_path: Path):
    (tmp_path / "README.md").write_text("# scratch\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.4.1"\ndescription = "ok product"\n'
    )
    (tmp_path / "CHANGELOG.md").write_text("this is an operator action\n")
    (tmp_path / "docs").mkdir()
    guard = _load_static_guard()
    hits = guard.banned_vocab_hits(tmp_path)
    assert any("CHANGELOG.md" in hit and "operator" in hit for hit in hits)


def test_vocab_ban_skips_internal_root_reports(tmp_path: Path):
    (tmp_path / "README.md").write_text("# scratch\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.4.1"\ndescription = "ok product"\n'
    )
    (tmp_path / "REVIEW.md").write_text("operator receipts testify\n")
    (tmp_path / "UPGRADE_REPORT.md").write_text("governed by operators\n")
    (tmp_path / "docs").mkdir()
    guard = _load_static_guard()
    names = {p.name for p in guard.public_prose_files(tmp_path)}
    assert "REVIEW.md" not in names
    assert "UPGRADE_REPORT.md" not in names
    assert guard.banned_vocab_hits(tmp_path) == []


def test_vocab_public_prose_files_includes_root_md_excludes_internal_reports():
    guard = _load_static_guard()
    names = {p.relative_to(ROOT).as_posix() for p in guard.public_prose_files(ROOT)}
    assert "README.md" in names
    assert "CHANGELOG.md" in names
    assert "RELEASE_PROCESS.md" in names
    assert "GOVERNANCE_OVERVIEW.md" in names
    assert "SECURITY.md" in names
    assert "CONTRIBUTING.md" in names
    assert "COMPLIANCE_SCOPE.md" in names
    assert "release-phase0-manifest-template.md" in names
    assert "REVIEW.md" not in names
    assert "UPGRADE_REPORT.md" not in names


@pytest.mark.parametrize(
    ("word", "name"),
    [
        ("testify", "testify"),
        ("testimony", "testimony"),
        ("receipt", "receipt"),
        ("craft gate", "craft gate"),
        ("TuesdayBar", "TuesdayBar"),
        ("operators", "operators"),
    ],
)
def test_vocab_ban_inflection_positive_control(word: str, name: str):
    guard = _load_static_guard()
    hits = guard._scan_text("x", f"plain {word} here")
    assert f"x | {name}" in hits


def test_readme_relative_link_targets_exist():
    readme = (ROOT / "README.md").read_text()
    targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", readme)
    missing = [
        target
        for target in targets
        if not target.startswith(("http://", "https://", "#"))
        and not (ROOT / target.split("#", 1)[0]).exists()
    ]
    assert missing == []


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
