"""Tests for sworn keygen CLI command."""
from __future__ import annotations

import re
from pathlib import Path

from sworn.cli import cmd_keygen, cmd_init


class TestKeygen:
    def test_keygen_creates_keypair(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        result = cmd_keygen(tmp_repo)
        assert result == 0
        key_dir = tmp_repo / ".sworn" / "keys"
        assert (key_dir / "active.key").exists()
        pub_files = list(key_dir.glob("*.pub"))
        assert len(pub_files) == 1

    def test_keygen_refuses_overwrite(self, tmp_repo: Path):
        cmd_init(tmp_repo)
        cmd_keygen(tmp_repo)
        result = cmd_keygen(tmp_repo)
        assert result == 1

    def test_keygen_requires_init(self, tmp_repo: Path):
        result = cmd_keygen(tmp_repo)
        assert result == 1

    def test_keygen_warns_gitignore(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        # No .gitignore in tmp_repo
        cmd_keygen(tmp_repo)
        captured = capsys.readouterr()
        assert re.search(r"active.key", captured.out, re.IGNORECASE)
        assert re.search(r"signing.key", captured.out, re.IGNORECASE)

    def test_keygen_warns_when_legacy_path_missing_from_gitignore(self, tmp_repo: Path, capsys):
        cmd_init(tmp_repo)
        (tmp_repo / ".gitignore").write_text(".sworn/keys/active.key\n")

        cmd_keygen(tmp_repo)
        captured = capsys.readouterr()

        assert "WARNING: Add .sworn/signing.key to .gitignore" in captured.out
