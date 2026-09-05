"""Shared test fixtures for Sworn."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sworn.config import SwornConfig, _compile_patterns, DEFAULT_SECURITY_PATTERNS
from tests.gitutil import git_init

requires_nacl = pytest.mark.skipif(
    importlib.util.find_spec("nacl") is None,
    reason="pynacl not installed — pip install -e .[dev] or .[signing]",
)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with initial commit.

    The repo lives in a subdirectory so callers can also create a sibling
    directory that is not this git work tree.
    """
    repo = tmp_path / "repo"
    git_init(repo)
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=repo, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return repo


@pytest.fixture
def sworn_config() -> SwornConfig:
    """Return a default SwornConfig."""
    return SwornConfig(
        security_patterns=_compile_patterns(DEFAULT_SECURITY_PATTERNS),
        allowlist=[],
        identity_env_vars={"CLAUDE_CODE": "claude-code"},
        kernels_enabled={"security": True, "allowlist": True, "audit": True},
        custom_kernel_dir=".sworn/kernels",
        evidence_log_path=".sworn/evidence.jsonl",
        evidence_hash_chain=True,
    )


@pytest.fixture
def tmp_repo_with_sworn(tmp_repo: Path, sworn_config: SwornConfig) -> Path:
    """A tmp_repo with .sworn/ initialized."""
    sworn_dir = tmp_repo / ".sworn"
    sworn_dir.mkdir()
    (sworn_dir / "config.toml").write_text(
        '[sworn]\nversion = "0.1"\n\n[security]\npatterns = []\n'
    )
    return tmp_repo


@pytest.fixture
def sample_evidence(tmp_repo: Path) -> Path:
    """Create a pre-populated evidence log with 5 entries."""
    log_path = tmp_repo / ".sworn" / "evidence.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    prev_hash = "genesis"
    import hashlib

    for i in range(5):
        entry = {
            "timestamp": f"2026-01-0{i+1}T00:00:00Z",
            "actor": "test",
            "tool": "claude-code" if i % 2 == 0 else None,
            "files": [f"src/file{i}.py"],
            "gates": {"identity": "PASS", "security": "PASS"},
            "kernels": [{"name": "audit", "decision": "PASS"}],
            "decision": "PASS" if i != 3 else "BLOCKED",
            "reason": "" if i != 3 else "Security surface: crypto/key.py",
            "prev_hash": prev_hash,
        }
        line = json.dumps(entry, separators=(",", ":"), sort_keys=True)
        prev_hash = hashlib.sha256(line.encode()).hexdigest()
        with log_path.open("a") as f:
            f.write(line + "\n")

    return log_path


@pytest.fixture
def signing_keypair(tmp_path: Path) -> tuple[Any, Any, Path]:
    """Generate a signing keypair and return (signing_key, verify_key, key_dir)."""
    pytest.importorskip("nacl", reason="pynacl not installed — pip install -e .[dev] or .[signing]")
    from sworn.evidence.signing import (
        generate_keypair,
        load_signing_key,
        load_verify_key,
    )

    key_dir = tmp_path / ".sworn"
    key_dir.mkdir(exist_ok=True)
    priv_path, pub_path = generate_keypair(key_dir)
    sk = load_signing_key(priv_path)
    vk = load_verify_key(pub_path)
    return sk, vk, key_dir
