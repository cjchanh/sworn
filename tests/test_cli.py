"""Tests for sworn CLI."""
from __future__ import annotations

import subprocess
from pathlib import Path

from sworn import __version__
from sworn.cli import (
    _find_repo_root,
    _get_staged_files,
    cmd_init,
    cmd_status,
    cmd_check,
    cmd_verify,
    main,
)
from tests.conftest import requires_nacl
from tests.gitutil import git_hooks_path, git_init


class TestCLI:
    def test_init_creates_sworn_dir(self, tmp_repo: Path):
        result = cmd_init(tmp_repo)
        assert result == 0
        assert (tmp_repo / ".sworn" / "config.toml").exists()

    def test_init_installs_hook(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        hook = git_hooks_path(tmp_repo) / "pre-commit"
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
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=tmp_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        native_hooks = Path(git_dir)
        if not native_hooks.is_absolute():
            native_hooks = tmp_repo / native_hooks
        default_hook = native_hooks / "hooks" / "pre-commit"
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
        git_init(main_repo)
        subprocess.run(["git", "config", "user.name", "test"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=main_repo, capture_output=True, check=True)
        (main_repo / "seed.txt").write_text("seed")
        subprocess.run(["git", "add", "seed.txt"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "worktree", "add", str(worktree)], cwd=main_repo, capture_output=True, check=True)

        result = cmd_init(worktree)

        assert result == 0
        hook = git_hooks_path(worktree) / "pre-commit"
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

    def test_get_staged_files_raises_on_git_failure(self, tmp_repo: Path, monkeypatch):
        import pytest

        def failed_probe(*args, **kwargs):
            return subprocess.CompletedProcess(
                args[0], 128, "", "fatal: not a git repository"
            )

        monkeypatch.setattr(subprocess, "run", failed_probe)

        with pytest.raises(RuntimeError, match="not a git repository"):
            _get_staged_files(tmp_repo)

    def test_find_repo_root_does_not_fall_back_to_cwd(self, tmp_path, monkeypatch):
        import pytest

        def failed_probe(*args, **kwargs):
            return subprocess.CompletedProcess(
                args[0] if args else ["git"], 128, "", "fatal: not a git repository"
            )

        monkeypatch.setattr(subprocess, "run", failed_probe)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(RuntimeError, match="not a git repository"):
            _find_repo_root()

    def test_check_blocks_when_git_probe_fails(
        self, tmp_repo: Path, monkeypatch, capsys
    ):
        cmd_init(tmp_repo)

        def failed_probe(*args, **kwargs):
            return subprocess.CompletedProcess(
                args[0], 128, "", "fatal: not a git repository"
            )

        monkeypatch.setattr(subprocess, "run", failed_probe)

        result = cmd_check(tmp_repo)
        captured = capsys.readouterr()

        assert result == 1
        assert "SWORN BLOCKED" in captured.err

    def test_check_blocks_when_git_probe_cannot_execute(
        self, tmp_repo: Path, monkeypatch, capsys
    ):
        cmd_init(tmp_repo)

        def unrunnable_probe(*args, **kwargs):
            raise OSError("git executable not found")

        monkeypatch.setattr(subprocess, "run", unrunnable_probe)

        result = cmd_check(tmp_repo)
        captured = capsys.readouterr()

        assert result == 1
        assert "SWORN BLOCKED" in captured.err

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
        assert __version__ in captured.out

    def test_report_help_does_not_expose_unshipped_soc2_surface(self, capsys):
        import pytest

        with pytest.raises(SystemExit, match="0"):
            main(["report", "--help"])
        captured = capsys.readouterr()

        assert "--cmmc" in captured.out
        assert "--soc2" not in captured.out

    def test_no_command_shows_help(self, capsys):
        result = main([])
        assert result == 0

    def test_verify_empty_after_init_is_not_valid(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        result = cmd_verify(tmp_repo)
        captured = capsys.readouterr()
        assert result == 1
        assert "Chain: EMPTY" in captured.out
        assert "VALID" not in captured.out

    @requires_nacl
    def test_verify_signed_mode_unsigned_log_fails(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        config_path = tmp_repo / ".sworn" / "config.toml"
        config_path.write_text(
            config_path.read_text() + "\n[signing]\nenabled = true\n"
        )
        (tmp_repo / ".sworn" / "evidence.jsonl").write_text(
            '{"timestamp":"2026-01-01T00:00:00Z","actor":"test","tool":null,'
            '"files":["a.py"],"gates":{"identity":"PASS"},"kernels":[],'
            '"decision":"PASS","reason":"","resolution_trace":{},'
            '"prev_hash":"genesis","signature":"","key_id":""}\n'
        )
        result = cmd_verify(tmp_repo)
        captured = capsys.readouterr()
        assert result == 1
        assert "BROKEN" in captured.out
