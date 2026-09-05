"""Staged-path gate: index is truth, symlink targets, confusable names."""
from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from sworn.cli import (
    _get_pr_diff_files,
    _get_staged_files,
    _git_z,
    _intent_to_add_paths,
    _is_zero_oid,
    _parse_ls_files_record,
    cmd_check,
    cmd_ci_check,
    cmd_init,
    evaluate_path_gate_candidates,
)
from sworn.config import load_config


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=check,
    )


def _enable_protected_pattern(repo: Path) -> None:
    cmd_init(repo)
    path = repo / ".sworn" / "config.toml"
    text = path.read_text()
    needle = "'(^|/)secrets?/',"
    extra = "'(^|/)secrets?/',\n    '(^|/)protected/',"
    assert needle in text
    path.write_text(text.replace(needle, extra, 1))


def _captured(capsys) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def _stage_symlink(repo: Path, link_name: str, target: str) -> None:
    dest = repo / link_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    os.symlink(target, dest)
    _git(repo, "add", "--", link_name)


class TestStagedPathGate:
    def test_symlink_to_protected_file_blocks(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "protected/key.txt")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected/key.txt" in output

    def test_symlink_to_protected_dir_no_slash_blocks(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "protected")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected" in output

    def test_symlink_still_blocks_after_worktree_deleted(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "protected/key.txt")
        (tmp_repo / "safe-link").unlink()
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected/key.txt" in output

    def test_symlink_escape_blocks(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "../../etc/x")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "symlink-escapes-repo" in output

    def test_literal_pathspec_star_and_hash(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        (tmp_repo / "*").write_text("star")
        _git(tmp_repo, "add", "--", "*")
        _stage_symlink(tmp_repo, "#dummy", "protected/key.txt")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected/key.txt" in output
        assert "index-unreadable" not in output

    def test_confusable_folded_blocks(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        cyrillic_s = "\u0441"
        dirname = f"se{cyrillic_s}rets"
        (tmp_repo / dirname).mkdir()
        (tmp_repo / dirname / "token.txt").write_text("token")
        _git(tmp_repo, "add", "--", f"{dirname}/token.txt")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "confusable-folded" in output or "secrets" in output

    def test_intent_to_add_blocks(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        (tmp_repo / "protected").mkdir()
        (tmp_repo / "protected" / "x.txt").write_text("x")
        _git(tmp_repo, "add", "-N", "--", "protected/x.txt")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected/x.txt" in output

    def test_typechange_pr_ci_check_blocks(self, tmp_repo: Path, capsys):
        branch = _git(tmp_repo, "branch", "--show-current").stdout.strip()
        (tmp_repo / "safe-link").write_text("regular")
        _git(tmp_repo, "add", "--", "safe-link")
        _git(tmp_repo, "commit", "-m", "regular file")
        _git(tmp_repo, "checkout", "-b", "feature")
        (tmp_repo / "safe-link").unlink()
        os.symlink("protected/key.txt", tmp_repo / "safe-link")
        _git(tmp_repo, "add", "--", "safe-link")
        _git(tmp_repo, "commit", "--no-verify", "-m", "typechange to symlink")
        _enable_protected_pattern(tmp_repo)
        result = cmd_ci_check(tmp_repo, branch)
        output = _captured(capsys)
        assert result == 1
        assert "protected/key.txt" in output

    def test_deletion_of_protected_file_passes(self, tmp_repo: Path):
        (tmp_repo / "protected").mkdir()
        (tmp_repo / "protected" / "key.txt").write_text("secret")
        _git(tmp_repo, "add", "--", "protected/key.txt")
        _git(tmp_repo, "commit", "-m", "add protected")
        _enable_protected_pattern(tmp_repo)
        _git(tmp_repo, "rm", "--", "protected/key.txt")
        result = cmd_check(tmp_repo)
        assert result == 0

    def test_plain_ok_file_passes(self, tmp_repo: Path):
        _enable_protected_pattern(tmp_repo)
        (tmp_repo / "src").mkdir()
        (tmp_repo / "src" / "ok.py").write_text("print(1)\n")
        _git(tmp_repo, "add", "--", "src/ok.py")
        result = cmd_check(tmp_repo)
        assert result == 0

    def test_dotdot_style_raw_path_still_blocks(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        (tmp_repo / "subdir").mkdir()
        os.symlink("../protected/key.txt", tmp_repo / "subdir" / "link")
        _git(tmp_repo, "add", "--", "subdir/link")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "protected/key.txt" in output


class TestRound2Findings:
    def test_s2_ok_symlink_returns_only_original_path(self, tmp_repo: Path, capsys):
        _enable_protected_pattern(tmp_repo)
        config_path = tmp_repo / ".sworn" / "config.toml"
        text = config_path.read_text()
        config_path.write_text(
            text.replace("files = []", 'files = ["safe-link"]', 1)
        )
        (tmp_repo / "src").mkdir()
        (tmp_repo / "src" / "ok.py").write_text("print(1)\n")
        _stage_symlink(tmp_repo, "safe-link", "src/ok.py")
        config = load_config(tmp_repo)
        files, reason = evaluate_path_gate_candidates(
            tmp_repo, ["safe-link"], config.security_patterns
        )
        assert files == ["safe-link"]
        assert reason is None
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 0
        assert "1 file(s) gated" in output
        assert "Outside allowlist" not in output

    def test_s2_pattern_hit_runs_pipeline_and_writes_evidence(
        self, tmp_repo: Path, capsys
    ):
        _enable_protected_pattern(tmp_repo)
        config_path = tmp_repo / ".sworn" / "config.toml"
        text = config_path.read_text()
        config_path.write_text(
            text.replace("files = []", 'files = ["src/*"]', 1)
        )
        (tmp_repo / "secrets").mkdir()
        (tmp_repo / "secrets" / "token.txt").write_text("token")
        _git(tmp_repo, "add", "--", "secrets/token.txt")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.is_file()
        entry = json.loads(log.read_text().splitlines()[-1])
        assert entry["decision"] == "BLOCKED"
        assert "allowlist" in entry["gates"]
        assert entry["gates"]["allowlist"] == "BLOCKED"
        assert "SWORN BLOCKED" in output

    def test_s3_get_staged_files_docstring_names_porcelain_v2(self):
        doc = _get_staged_files.__doc__
        assert doc is not None
        assert "porcelain=v2" in doc
        assert "ls-files -s -z" not in doc

    def test_s3_sha256_zero_oid_and_ls_files_record(
        self, tmp_repo: Path, monkeypatch
    ):
        sha256 = "ab" * 32
        parsed = _parse_ls_files_record(f"100644 {sha256} 0\tapp.py")
        assert parsed is not None
        assert parsed[1] == sha256
        assert parsed[3] == "app.py"
        assert _is_zero_oid("0" * 40)
        assert _is_zero_oid("0" * 64)
        assert not _is_zero_oid("0" * 41)
        assert not _is_zero_oid("a" * 40)
        zero64 = "0" * 64
        payload = (
            f"1 .A N... 000000 000000 000000 {zero64} {zero64} protected/x.txt\0"
        )
        monkeypatch.setattr(
            "sworn.cli._git_z", lambda *args, **kwargs: payload
        )
        assert _intent_to_add_paths(tmp_repo) == ["protected/x.txt"]

    def test_s3_collapsed_variant_kind_not_labelled_raw(
        self, tmp_repo: Path, monkeypatch
    ):
        monkeypatch.setattr(
            "sworn.cli._index_record",
            lambda *args, **kwargs: ("100644", "a" * 40),
        )
        _files, reason = evaluate_path_gate_candidates(
            tmp_repo,
            ["src/nested/../ok.py"],
            [re.compile(r"^src/ok\.py$")],
        )
        assert reason is not None
        assert "collapsed" in reason
        assert "variant: raw src/ok.py" not in reason


class TestRound3Findings:
    def test_s2_mixed_pattern_and_escape_still_writes_evidence(
        self, tmp_repo: Path, capsys
    ):
        _enable_protected_pattern(tmp_repo)
        (tmp_repo / "secrets").mkdir()
        (tmp_repo / "secrets" / "token.txt").write_text("token")
        _git(tmp_repo, "add", "--", "secrets/token.txt")
        _stage_symlink(tmp_repo, "out-link", "../../etc/x")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "SWORN BLOCKED" in output
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.is_file()
        entry = json.loads(log.read_text().splitlines()[-1])
        assert entry["decision"] == "BLOCKED"

    def test_s3_non_utf8_git_output_is_runtime_error(
        self, tmp_repo: Path, monkeypatch, capsys
    ):
        def boom(*_args, **_kwargs):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

        monkeypatch.setattr("sworn.cli.subprocess.run", boom)
        with pytest.raises(RuntimeError, match="failed"):
            _git_z(tmp_repo, ["status", "--porcelain=v2", "-z"])
        with pytest.raises(RuntimeError, match="failed"):
            _get_staged_files(tmp_repo)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "SWORN BLOCKED" in output

    def test_s3_readme_security_blurb_names_collapsed_and_hard_blocks(self):
        readme = Path(__file__).resolve().parents[1] / "README.md"
        text = readme.read_text()
        assert "collapsed" in text
        assert "symlink-escapes-repo" in text
        assert "index-unreadable" in text
        assert "contents are not scanned" in text

    def test_s3_ci_check_pattern_block_prints_actor(self, tmp_repo: Path, capsys):
        branch = _git(tmp_repo, "branch", "--show-current").stdout.strip()
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_repo,
            capture_output=True,
        )
        (tmp_repo / "crypto").mkdir()
        (tmp_repo / "crypto" / "vault.py").write_text("secret = 42")
        _git(tmp_repo, "add", "--", "crypto/vault.py")
        _git(tmp_repo, "commit", "--no-verify", "-m", "add crypto")
        cmd_init(tmp_repo)
        result = cmd_ci_check(tmp_repo, branch)
        output = _captured(capsys)
        assert result == 1
        assert "SWORN BLOCKED" in output
        assert "Actor:" in output


class TestR1Findings:
    def test_s1_nfkc_symlink_dir_target_without_slash_blocks(
        self, tmp_repo: Path, capsys
    ):
        cmd_init(tmp_repo)
        fullwidth_secrets = "\uff53\uff45\uff43\uff52\uff45\uff54\uff53"
        _stage_symlink(tmp_repo, "safe-link", fullwidth_secrets)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "SWORN BLOCKED" in output
        assert "nfkc" in output

    def test_s2_hard_block_runs_pipeline_and_writes_evidence(
        self, tmp_repo: Path, capsys
    ):
        _enable_protected_pattern(tmp_repo)
        config_path = tmp_repo / ".sworn" / "config.toml"
        text = config_path.read_text()
        config_path.write_text(
            text.replace("files = []", 'files = ["src/*"]', 1)
        )
        _stage_symlink(tmp_repo, "safe-link", "../../etc/x")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "symlink-escapes-repo" in output
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.is_file()
        entry = json.loads(log.read_text().splitlines()[-1])
        assert entry["decision"] == "BLOCKED"
        assert "allowlist" in entry["gates"]
        assert entry["gates"]["allowlist"] == "BLOCKED"

    def test_s3_nfkc_path_dir_style_slash_blocks(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        fullwidth_secrets = "\uff53\uff45\uff43\uff52\uff45\uff54\uff53"
        (tmp_repo / fullwidth_secrets).write_text("token")
        _git(tmp_repo, "add", "--", fullwidth_secrets)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "nfkc" in output

    def test_s3_pr_diff_timeout_does_not_fall_through(
        self, tmp_repo: Path, monkeypatch
    ):
        monkeypatch.delenv("SWORN_CI", raising=False)
        monkeypatch.delenv("SWORN_BASE_SHA", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        diff_calls = {"n": 0}

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "git" and "diff" in cmd:
                diff_calls["n"] += 1
                if diff_calls["n"] == 1:
                    raise subprocess.TimeoutExpired(cmd, 10)
                return subprocess.CompletedProcess(cmd, 0, stdout="ok.py\0", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("sworn.cli.subprocess.run", fake_run)
        with pytest.raises(RuntimeError, match="timed out"):
            _get_pr_diff_files(tmp_repo, "main")

    def test_s3_pr_diff_decode_error_does_not_fall_through(
        self, tmp_repo: Path, monkeypatch
    ):
        monkeypatch.delenv("SWORN_CI", raising=False)
        monkeypatch.delenv("SWORN_BASE_SHA", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        diff_calls = {"n": 0}

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "git" and "diff" in cmd:
                diff_calls["n"] += 1
                if diff_calls["n"] == 1:
                    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok.py\0", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("sworn.cli.subprocess.run", fake_run)
        with pytest.raises(RuntimeError, match="failed"):
            _get_pr_diff_files(tmp_repo, "main")


class TestR2Findings:
    def test_s1_confusable_file_without_slash_blocks(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        name = "se\u0441rets"
        (tmp_repo / name).write_text("token")
        _git(tmp_repo, "add", "--", name)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "confusable-folded" in output
        assert name in output or "secrets" in output

    def test_s1_confusable_private_file_without_slash_blocks(
        self, tmp_repo: Path, capsys
    ):
        cmd_init(tmp_repo)
        name = "\u0440rivate"
        (tmp_repo / name).write_text("token")
        _git(tmp_repo, "add", "--", name)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "confusable-folded" in output

    def test_s2_hard_block_stock_config_evidence_is_blocked_not_pass(
        self, tmp_repo: Path, capsys
    ):
        cmd_init(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "../../etc/x")
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "symlink-escapes-repo" in output
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.is_file()
        entries = [
            json.loads(line) for line in log.read_text().splitlines() if line.strip()
        ]
        assert entries
        assert all(entry["decision"] != "PASS" for entry in entries)
        assert entries[-1]["decision"] == "BLOCKED"
        assert "symlink-escapes-repo" in entries[-1]["reason"]

    def test_s3_evaluate_never_raises_path_gate_blocked(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        _stage_symlink(tmp_repo, "safe-link", "../../etc/x")
        config = load_config(tmp_repo)
        files, reason = evaluate_path_gate_candidates(
            tmp_repo,
            ["safe-link", "missing-from-index"],
            config.security_patterns,
        )
        assert "safe-link" in files
        assert reason is not None
        assert "symlink-escapes-repo" in reason or "index-unreadable" in reason

    def test_s3_cmd_check_has_no_dead_path_gate_except(self):
        assert "except PathGateBlocked" not in inspect.getsource(cmd_check)
        assert "except PathGateBlocked" not in inspect.getsource(cmd_ci_check)

    def test_s3_mixed_fullwidth_and_cyrillic_blocks(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        name = "\uff53\uff45\u0441\uff52\uff45\uff54\uff53"
        (tmp_repo / name).write_text("token")
        _git(tmp_repo, "add", "--", name)
        result = cmd_check(tmp_repo)
        output = _captured(capsys)
        assert result == 1
        assert "confusable-folded" in output
