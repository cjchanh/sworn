"""Tests for sworn CLI."""
from __future__ import annotations

import subprocess
from pathlib import Path

from sworn.cli import cmd_init, cmd_status, cmd_check, main


class TestCLI:
    def test_init_creates_sworn_dir(self, tmp_repo: Path):
        result = cmd_init(tmp_repo)
        assert result == 0
        assert (tmp_repo / ".sworn" / "config.toml").exists()

    def test_init_installs_hook(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        assert hook.exists()
        assert "sworn check" in hook.read_text()

    def test_init_honors_core_hooks_path(self, tmp_repo: Path):
        subprocess.run(
            ["git", "config", "core.hooksPath", ".githooks"],
            cwd=tmp_repo,
            capture_output=True,
            check=True,
        )

        result = cmd_init(tmp_repo)

        assert result == 0
        hook = tmp_repo / ".githooks" / "pre-commit"
        assert hook.exists()
        assert "sworn check" in hook.read_text()
        default_hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        assert not default_hook.exists() or "sworn check" not in default_hook.read_text()

    def test_init_idempotent(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        result = cmd_init(tmp_repo)
        assert result == 0
        # Config not overwritten
        assert (tmp_repo / ".sworn" / "config.toml").exists()

    def test_init_supports_git_worktree(self, tmp_path: Path):
        main_repo = tmp_path / "main"
        worktree = tmp_path / "wt"
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "clone", tmp_path.as_posix(), main_repo.as_posix()], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=main_repo, capture_output=True, check=True)
        (main_repo / "seed.txt").write_text("seed")
        subprocess.run(["git", "add", "seed.txt"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "worktree", "add", worktree], cwd=main_repo, capture_output=True, check=True)

        result = cmd_init(worktree)

        assert result == 0
        hooks_dir = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        hook = Path(hooks_dir)
        if not hook.is_absolute():
            hook = worktree / hook
        hook = hook / "pre-commit"
        assert hook.exists()
        assert "sworn check" in hook.read_text()

    def test_init_non_git_fails(self, tmp_path: Path):
        result = cmd_init(tmp_path)
        assert result == 1

    def test_check_clean_files(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        # Stage a clean file
        (tmp_repo / "app.py").write_text("print('hello')")
        subprocess.run(
            ["git", "add", "app.py"], cwd=tmp_repo, capture_output=True
        )
        result = cmd_check(tmp_repo)
        assert result == 0

    def test_check_no_staged_files(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        result = cmd_check(tmp_repo)
        assert result == 0  # Nothing to gate

    def test_status_not_initialized(self, tmp_repo: Path):
        result = cmd_status(tmp_repo)
        assert result == 0

    def test_status_uses_effective_hooks_path(self, tmp_repo: Path, capsys):
        subprocess.run(
            ["git", "config", "core.hooksPath", ".githooks"],
            cwd=tmp_repo,
            capture_output=True,
            check=True,
        )
        cmd_init(tmp_repo)

        result = cmd_status(tmp_repo)
        captured = capsys.readouterr()

        assert result == 0
        assert "Hook: installed" in captured.out

    def test_version(self, capsys):
        import pytest
        with pytest.raises(SystemExit, match="0"):
            main(["--version"])
        captured = capsys.readouterr()
        assert "0.3.0" in captured.out

    def test_no_command_shows_help(self, capsys):
        result = main([])
        assert result == 0
