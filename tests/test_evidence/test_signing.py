"""Tests for Ed25519 evidence signing."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

pytest.importorskip("nacl", reason="pynacl not installed — pip install -e .[dev] or .[signing]")

from sworn.config import SwornConfig, _compile_patterns
from sworn.evidence.log import EvidenceEntry, append_entry, read_entries, verify_chain
from sworn.evidence.signing import (
    SigningError,
    generate_keypair,
    load_signing_key,
    load_verify_key,
    sign_entry,
    verify_signature,
)
from sworn.pipeline import run_pipeline


@pytest.fixture
def key_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".sworn" / "keys"
    d.mkdir(parents=True)
    return d


class TestKeypairGeneration:
    def test_generate_creates_files(self, key_dir: Path):
        priv, pub = generate_keypair(key_dir)
        assert priv.exists()
        assert pub.exists()

    def test_private_key_permissions_600(self, key_dir: Path):
        priv, _ = generate_keypair(key_dir)
        mode = stat.S_IMODE(os.stat(priv).st_mode)
        assert mode == 0o600

    def test_refuses_overwrite(self, key_dir: Path):
        generate_keypair(key_dir)
        with pytest.raises(SigningError, match="already exists"):
            generate_keypair(key_dir)

    def test_pub_key_is_hex(self, key_dir: Path):
        priv, pub = generate_keypair(key_dir)
        content = pub.read_text().strip()
        bytes.fromhex(content)  # should not raise


class TestKeyLoading:
    def test_load_roundtrip(self, key_dir: Path):
        priv_path, pub_path = generate_keypair(key_dir)
        sk = load_signing_key(priv_path)
        vk = load_verify_key(pub_path)
        assert sk is not None
        assert vk is not None

    def test_corrupt_key_fails_closed(self, key_dir: Path):
        key_file = key_dir / "active.key"
        key_file.write_text("not-valid-hex\n")
        with pytest.raises(SigningError, match="Failed to load"):
            load_signing_key(key_file)

    def test_missing_key_fails_closed(self, key_dir: Path):
        with pytest.raises(SigningError):
            load_signing_key(key_dir / "nonexistent.key")


class TestSignAndVerify:
    def test_sign_and_verify(self, key_dir: Path):
        priv_path, pub_path = generate_keypair(key_dir)
        sk = load_signing_key(priv_path)
        vk = load_verify_key(pub_path)

        data = '{"decision":"PASS","timestamp":"2026-01-01T00:00:00Z"}'
        sig = sign_entry(sk, data)
        assert verify_signature(vk, data, sig)

    def test_tampered_data_fails(self, key_dir: Path):
        priv_path, pub_path = generate_keypair(key_dir)
        sk = load_signing_key(priv_path)
        vk = load_verify_key(pub_path)

        data = '{"decision":"PASS"}'
        sig = sign_entry(sk, data)
        assert not verify_signature(vk, data + "x", sig)

    def test_wrong_key_fails(self, tmp_path: Path):
        d1 = tmp_path / "k1"
        d1.mkdir()
        d2 = tmp_path / "k2"
        d2.mkdir()

        p1, _ = generate_keypair(d1)
        _, pub2 = generate_keypair(d2)

        sk1 = load_signing_key(p1)
        vk2 = load_verify_key(pub2)

        data = '{"test": true}'
        sig = sign_entry(sk1, data)
        assert not verify_signature(vk2, data, sig)

    def test_signature_deterministic(self, key_dir: Path):
        priv_path, _ = generate_keypair(key_dir)
        sk = load_signing_key(priv_path)

        data = '{"stable":"content"}'
        sig1 = sign_entry(sk, data)
        sig2 = sign_entry(sk, data)
        # Ed25519 signatures are deterministic for same key + message
        assert sig1 == sig2


def test_threat_key_id_in_signed_entry(tmp_path: Path):
    keys = tmp_path / ".sworn" / "keys"
    keys.mkdir(parents=True)
    priv, _ = generate_keypair(keys)
    sk = load_signing_key(priv)

    log = tmp_path / ".sworn" / "evidence.jsonl"
    entry = EvidenceEntry(
        timestamp="2026-01-01T00:00:00Z",
        actor="test",
        tool=None,
        files=["a.py"],
        gates={"identity": "PASS"},
        kernels=[],
        decision="PASS",
    )
    append_entry(log, entry, hash_chain=False, signing_key=sk)
    records = read_entries(log)
    assert records[0]["key_id"] != ""
    assert len(records[0]["key_id"]) == 16


def test_threat_key_exists_but_signing_disabled_no_signature(
    tmp_repo: Path,
):
    key_root = tmp_repo / ".sworn" / "keys"
    key_root.mkdir(parents=True, exist_ok=True)
    priv, pub = generate_keypair(key_root)
    config = SwornConfig(
        security_patterns=_compile_patterns([r"(^|/)(crypto|auth|keys)/"]),
        allowlist=[],
        identity_env_vars={"CLAUDE_CODE": "claude-code"},
        kernels_enabled={"security": True, "allowlist": True, "audit": True},
        custom_kernel_dir=".sworn/kernels",
        evidence_log_path=".sworn/evidence.jsonl",
        evidence_hash_chain=True,
        signing_key_path=".sworn/keys/active.key",
        signing_pub_path=".sworn/keys/",
        signing_enabled=False,
    )

    run_pipeline(tmp_repo, ["src/main.py"], config)
    log = (tmp_repo / ".sworn" / "evidence.jsonl")
    records = read_entries(log)
    assert records[-1]["signature"] == ""


def test_threat_verify_uses_key_id_lookup(tmp_path: Path):
    keys = tmp_path / ".sworn" / "keys"
    keys.mkdir(parents=True)
    priv, pub = generate_keypair(keys)
    sk = load_signing_key(priv)

    log = tmp_path / ".sworn" / "evidence.jsonl"
    entry = EvidenceEntry(
        timestamp="2026-01-01T00:00:00Z",
        actor="test",
        tool=None,
        files=["a.py"],
        gates={"identity": "PASS"},
        kernels=[],
        decision="PASS",
    )
    append_entry(log, entry, hash_chain=False, signing_key=sk)

    valid, msg = verify_chain(log, verify_key_dir=keys)
    assert valid, msg
