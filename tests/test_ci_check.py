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


# Boundary B-2 regression suite.
#
# An unresolvable diff base used to print "SWORN PASS — no files in diff" and
# exit 0 unless SWORN_CI=1 was set, so a pipeline that forgot the env var
# reported success precisely when the gate did the least work. These tests pin
# the FAILING case (unresolvable base must block with no env var set), not just
# the passing one, because a gate only ever observed succeeding is not a gate.

BOGUS_SHA = "0" * 40
BOGUS_BRANCH = "nonexistent-branch-xyz"

# Env vars that steer ci-check. Tests must neutralize all of them explicitly so
# the default-path assertions cannot be rescued by ambient CI environment.
_STEERING_VARS = ("SWORN_CI", "SWORN_ADVISORY", "SWORN_BASE_SHA", "GITHUB_BASE_REF")


def _clean_env(**overrides: str):
    """Patch os.environ with the steering vars removed, then apply overrides.

    PATH and friends are preserved because these tests shell out to real git;
    ``clear=True`` alone would break the subprocess calls.
    """
    env = {k: v for k, v in os.environ.items() if k not in _STEERING_VARS}
    env.update(overrides)
    return patch.dict(os.environ, env, clear=True)


class TestCIDiffBaseFailsClosedByDefault:
    """AC1 — an unresolvable diff base blocks with no env var required."""

    def test_unresolvable_full_sha_base_blocks_by_default(self, tmp_repo: Path):
        """The headline failing case: bogus 40-hex base, no SWORN_CI."""
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, BOGUS_SHA)
        assert result == 1

    def test_unresolvable_branch_name_blocks_by_default(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, BOGUS_BRANCH)
        assert result == 1

    def test_empty_base_ref_blocks_by_default(self, tmp_repo: Path):
        """An empty base must not degenerate to a HEAD...HEAD empty diff."""
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, "")
        assert result == 1

    def test_block_output_never_claims_pass(self, tmp_repo: Path, capsys):
        """The two outcomes must not be confusable by a log scraper."""
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, BOGUS_SHA)
        captured = capsys.readouterr()
        assert result == 1
        assert "SWORN PASS" not in captured.out + captured.err
        assert "SWORN BLOCKED" in captured.err

    def test_genuinely_empty_diff_still_passes(self, tmp_repo: Path, capsys):
        """Guard against over-blocking: a resolvable base with no changes passes."""
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, "HEAD")
        captured = capsys.readouterr()
        assert result == 0
        assert "SWORN PASS" in captured.out


class TestCIAdvisoryOptOut:
    """AC2 — advisory is an explicit opt-OUT that never prints a bare PASS."""

    def test_advisory_flag_exits_zero_with_banner(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, BOGUS_SHA, advisory=True)
        captured = capsys.readouterr()
        assert result == 0
        assert "SWORN ADVISORY" in captured.err
        assert "THIS IS NOT A PASS" in captured.err

    def test_advisory_env_var_exits_zero_with_banner(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        with _clean_env(SWORN_ADVISORY="1"):
            result = cmd_ci_check(tmp_repo, BOGUS_SHA)
        captured = capsys.readouterr()
        assert result == 0
        assert "SWORN ADVISORY" in captured.err

    def test_advisory_never_prints_pass_token(self, tmp_repo: Path, capsys):
        """Exit 0 is allowed here; claiming PASS is not."""
        cmd_init(tmp_repo)
        capsys.readouterr()  # drop cmd_init's banner; assert on ci-check alone
        with _clean_env():
            cmd_ci_check(tmp_repo, BOGUS_SHA, advisory=True)
        captured = capsys.readouterr()
        assert "SWORN PASS" not in captured.out + captured.err
        assert captured.out == ""

    def test_advisory_refused_when_ci_mode_declared(self, tmp_repo: Path, capsys):
        """Advisory must not be able to defang a pipeline that declared CI mode."""
        cmd_init(tmp_repo)
        with _clean_env(SWORN_CI="1"):
            result = cmd_ci_check(tmp_repo, BOGUS_SHA, advisory=True)
        captured = capsys.readouterr()
        assert result == 1
        assert "SWORN BLOCKED" in captured.err
        assert "SWORN PASS" not in captured.out + captured.err

    def test_advisory_does_not_downgrade_a_gate_verdict(self, tmp_repo: Path):
        """Advisory relaxes base resolution only — a blocked kernel still exits 1."""
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=tmp_repo, capture_output=True, text=True,
        )
        default_branch = res.stdout.strip()
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_repo, capture_output=True,
        )
        (tmp_repo / "crypto").mkdir()
        (tmp_repo / "crypto" / "vault.py").write_text("secret = 42")
        subprocess.run(
            ["git", "add", "crypto/vault.py"], cwd=tmp_repo, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "add crypto"],
            cwd=tmp_repo, capture_output=True, check=True,
        )
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, default_branch, advisory=True)
        assert result == 1


class TestCIBackwardCompatSwornCIEnvVar:
    """SWORN_CI=1 keeps its exact prior meaning: same inputs, same exit codes."""

    def test_sworn_ci_still_blocks_unresolvable_full_sha(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        with _clean_env(SWORN_CI="1"):
            result = cmd_ci_check(tmp_repo, BOGUS_SHA)
        assert result == 1

    def test_sworn_ci_still_requires_full_sha(self, tmp_repo: Path, capsys):
        """The 40-hex format policy remains CI-only, not the local default."""
        cmd_init(tmp_repo)
        with _clean_env(SWORN_CI="1"):
            result = cmd_ci_check(tmp_repo, BOGUS_BRANCH)
        captured = capsys.readouterr()
        assert result == 1
        assert "full base SHA" in captured.err

    def test_local_branch_name_base_is_still_accepted(self, tmp_repo: Path):
        """Without SWORN_CI, a resolvable branch name is not a format error."""
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=tmp_repo, capture_output=True, text=True,
        )
        default_branch = res.stdout.strip()
        cmd_init(tmp_repo)
        with _clean_env():
            result = cmd_ci_check(tmp_repo, default_branch)
        assert result == 0


class TestModuleDirectExitPropagation:
    """B-2 residual (2026-08-18): `python -m sworn.cli` used to swallow
    main()'s exit code — every BLOCK exited 0. The guard makes all three
    invocation shapes (console script, python -m sworn, python -m
    sworn.cli) identical. Pins the FAILING case, not the passing one."""

    def test_module_direct_invocation_propagates_block_exit_code(
        self, tmp_repo: Path
    ):
        import subprocess
        import sys

        repo_root = Path(__file__).resolve().parents[1]
        src = repo_root / "src"
        zeros = "0" * 40
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sworn.cli",
                "ci-check",
                "--base",
                zeros,
                str(tmp_repo) if False else "--repo",
                str(tmp_repo),
            ]
            if False
            else [sys.executable, "-m", "sworn.cli", "ci-check", "--base", zeros],
            capture_output=True,
            text=True,
            cwd=tmp_repo,
            env={
                **os.environ,
                "PYTHONPATH": str(src),
                "SWORN_CI": "",
                "SWORN_ADVISORY": "",
            },
            timeout=60,
        )
        assert result.returncode == 1, (
            f"module-direct shape swallowed the block: rc={result.returncode} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "SWORN BLOCKED" in result.stderr

    def test_module_direct_invocation_pass_shape_still_zero(self, tmp_repo: Path):
        import subprocess
        import sys

        repo_root = Path(__file__).resolve().parents[1]
        src = repo_root / "src"
        # An empty diff against HEAD in a clean repo is a legitimate PASS.
        result = subprocess.run(
            [sys.executable, "-m", "sworn.cli", "ci-check", "--base", "HEAD"],
            capture_output=True,
            text=True,
            cwd=tmp_repo,
            env={
                **os.environ,
                "PYTHONPATH": str(src),
                "SWORN_CI": "",
                "SWORN_ADVISORY": "",
            },
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
