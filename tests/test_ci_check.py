"""Tests for sworn ci-check CLI command."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from sworn.cli import cmd_ci_check, cmd_init


class TestCICheck:
    def test_clean_diff_passes(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        # Create a file and commit it so there's history
        (tmp_repo / "app.py").write_text("print('hello')")
        subprocess.run(["git", "add", "app.py"], cwd=tmp_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add app"],
            cwd=tmp_repo, capture_output=True,
        )
        # ci-check with no diff files should pass
        result = cmd_ci_check(tmp_repo, "HEAD")
        assert result == 0

    def test_no_diff_passes(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        result = cmd_ci_check(tmp_repo, "HEAD")
        assert result == 0

    def test_uses_github_base_ref(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        with patch.dict(os.environ, {"GITHUB_BASE_REF": "main"}):
            # Should use GITHUB_BASE_REF when no --base given
            result = cmd_ci_check(tmp_repo, None)
            # May fail on git diff but shouldn't crash
            assert result in (0, 1)

    def test_security_surface_blocks(self, tmp_repo: Path):
        # Determine default branch name
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=tmp_repo, capture_output=True, text=True,
        )
        default_branch = res.stdout.strip()
        # Create a branch with a security surface file BEFORE init
        # (init installs pre-commit hook which would block the commit)
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_repo, capture_output=True,
        )
        (tmp_repo / "crypto").mkdir()
        (tmp_repo / "crypto" / "vault.py").write_text("secret = 42")
        subprocess.run(
            ["git", "add", "crypto/vault.py"],
            cwd=tmp_repo, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add crypto"],
            cwd=tmp_repo, capture_output=True, check=True,
        )
        # Now init sworn for ci-check
        cmd_init(tmp_repo)
        # Compare against default branch (first commit)
        result = cmd_ci_check(tmp_repo, default_branch)
        assert result == 1

    def test_ci_check_help(self):
        """ci-check subcommand is registered."""
        from sworn.cli import main
        import pytest
        # Should not error on --help
        with pytest.raises(SystemExit, match="0"):
            main(["ci-check", "--help"])

    def test_threat_ci_uses_base_sha_env(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd[0] == "git":
                calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.dict(os.environ, {"SWORN_BASE_SHA": "abcdef1234567890abcdef1234567890abcdef12"}), \
            patch("sworn.cli.subprocess.run", side_effect=fake_run):
            result = cmd_ci_check(tmp_repo, None)

        assert result == 0
        assert any(
            "abcdef1234567890abcdef1234567890abcdef12...HEAD" in " ".join(call)
            for call in calls
            if call[:2] == ["git", "diff"]
        )
        assert not any(
            f"origin/abcdef1234567890abcdef1234567890abcdef12" in " ".join(call)
            for call in calls
            if call[:2] == ["git", "diff"]
        )

    def test_threat_ci_fallback_chain(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        calls: list[list[str]] = []
        diff_calls = 0

        def fake_run(cmd, *args, **kwargs):
            nonlocal diff_calls
            if isinstance(cmd, list) and cmd[0] == "git":
                calls.append(cmd)

            if cmd[:2] == ["git", "diff"]:
                diff_calls += 1
                if diff_calls == 1:
                    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.dict(os.environ, {"SWORN_CI": "0"}, clear=True), \
            patch("sworn.cli.subprocess.run", side_effect=fake_run):
            result = cmd_ci_check(tmp_repo, None)

        assert result == 0
        diff_refs = [
            " ".join(call)
            for call in calls
            if call[:2] == ["git", "diff"]
        ]
        assert any("origin/main...HEAD" in ref for ref in diff_refs)
        assert any("main...HEAD" in ref for ref in diff_refs)

    def test_ci_check_fails_closed_without_base_sha_in_ci_mode(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        with patch.dict(os.environ, {"SWORN_CI": "1"}, clear=False):
            result = cmd_ci_check(tmp_repo, None)
        assert result == 1
