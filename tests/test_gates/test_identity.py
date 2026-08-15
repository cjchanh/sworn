"""Tests for identity gate."""
from __future__ import annotations

import os
from unittest.mock import patch

from sworn.gates.identity import evaluate_identity
from tests.gitutil import git_init


class TestIdentityGate:
    def test_env_var_detection(self):
        with patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=False):
            result = evaluate_identity({"CLAUDE_CODE": "claude-code"})
            assert result.tool == "claude-code"
            assert result.confidence == "detected"

    def test_no_env_vars_unknown(self):
        with patch.dict(os.environ, {}, clear=True):
            result = evaluate_identity({"NONEXISTENT_VAR": "tool"})
            assert result.tool is None
            assert result.confidence == "unknown"

    def test_multiple_tools_first_match(self):
        with patch.dict(
            os.environ,
            {"CLAUDE_CODE": "1", "CODEX_CLI": "1"},
            clear=False,
        ):
            result = evaluate_identity(
                {"CLAUDE_CODE": "claude-code", "CODEX_CLI": "codex"}
            )
            assert result.tool == "claude-code"

    def test_actor_from_git(self):
        result = evaluate_identity({})
        assert isinstance(result.actor, str)
        assert len(result.actor) > 0

    def test_actor_uses_gated_repo_git_config(self, tmp_repo, tmp_path, monkeypatch):
        """Evidence actor is the gated repo's user.name, not ambient cwd."""
        import subprocess

        subprocess.run(
            ["git", "config", "user.name", "gated-actor"],
            cwd=tmp_repo,
            capture_output=True,
            check=True,
        )
        other = tmp_path / "other"
        git_init(other)
        subprocess.run(
            ["git", "config", "user.name", "cwd-actor"],
            cwd=other,
            capture_output=True,
            check=True,
        )
        monkeypatch.chdir(other)

        result = evaluate_identity({}, repo_root=tmp_repo)
        assert result.actor == "gated-actor"
