"""Tests for evidence log."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sworn.evidence.log import (
    EvidenceEntry,
    EvidenceLogError,
    append_entry,
    canonical_json,
    read_entries,
    read_last_hash,
    verify_chain,
)
from sworn.evidence.signing import verify_signature


class TestEvidenceLog:
    def test_append_and_read(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        entry = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=["a.py"],
            gates={"identity": "PASS"},
            kernels=[],
            decision="PASS",
        )
        append_entry(log, entry, hash_chain=False)
        entries = read_entries(log)
        assert len(entries) == 1
        assert entries[0]["actor"] == "test"

    def test_hash_chain_genesis(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        assert read_last_hash(log) == "genesis"

    def test_hash_chain_corrupt_log_fails_closed(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        log.write_text("{not-json}\n")
        with pytest.raises(EvidenceLogError, match="invalid JSON"):
            read_last_hash(log)

    def test_hash_chain_integrity(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        for i in range(3):
            entry = EvidenceEntry(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                actor="test",
                tool=None,
                files=[f"file{i}.py"],
                gates={"identity": "PASS"},
                kernels=[],
                decision="PASS",
            )
            append_entry(log, entry, hash_chain=True)

        valid, msg = verify_chain(log)
        assert valid, msg

    def test_tampered_chain_detected(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        for i in range(3):
            entry = EvidenceEntry(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                actor="test",
                tool=None,
                files=[f"file{i}.py"],
                gates={"identity": "PASS"},
                kernels=[],
                decision="PASS",
            )
            append_entry(log, entry, hash_chain=True)

        # Tamper with line 2
        lines = log.read_text().splitlines()
        entry2 = json.loads(lines[1])
        entry2["actor"] = "tampered"
        lines[1] = json.dumps(entry2, separators=(",", ":"), sort_keys=True)
        log.write_text("\n".join(lines) + "\n")

        valid, msg = verify_chain(log)
        assert not valid
        assert "broken" in msg.lower()

    def test_write_failure_no_crash(self, tmp_path: Path):
        log = tmp_path / "readonly" / "deep" / "evidence.jsonl"
        # Create parent as a file to make mkdir fail
        (tmp_path / "readonly").mkdir()
        (tmp_path / "readonly" / "deep").write_text("blocker")
        entry = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=[],
            gates={},
            kernels=[],
            decision="PASS",
        )
        try:
            append_entry(log, entry)
            assert False, "Should have raised"
        except (NotADirectoryError, OSError):
            pass  # Expected — fail-closed behavior tested via pipeline

    def test_append_corrupt_existing_log_fails_closed(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        log.write_text("{not-json}\n")
        entry = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=[],
            gates={},
            kernels=[],
            decision="PASS",
        )
        with pytest.raises(EvidenceLogError, match="invalid JSON"):
            append_entry(log, entry, hash_chain=True)

    def test_signed_entry_has_signature(self, tmp_path: Path, signing_keypair):
        sk, vk, _ = signing_keypair
        log = tmp_path / "evidence.jsonl"
        entry = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=["a.py"],
            gates={"identity": "PASS"},
            kernels=[],
            decision="PASS",
        )
        append_entry(log, entry, hash_chain=True, signing_key=sk)
        entries = read_entries(log)
        assert len(entries) == 1
        assert entries[0]["signature"] != ""

    def test_unsigned_entry_no_signature(self, tmp_path: Path):
        log = tmp_path / "evidence.jsonl"
        entry = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=["a.py"],
            gates={"identity": "PASS"},
            kernels=[],
            decision="PASS",
        )
        append_entry(log, entry, hash_chain=True)
        entries = read_entries(log)
        assert entries[0]["signature"] == ""

    def test_signed_chain_valid(self, tmp_path: Path, signing_keypair):
        sk, vk, _ = signing_keypair
        log = tmp_path / "evidence.jsonl"
        for i in range(3):
            entry = EvidenceEntry(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                actor="test",
                tool=None,
                files=[f"file{i}.py"],
                gates={"identity": "PASS"},
                kernels=[],
                decision="PASS",
            )
            append_entry(log, entry, hash_chain=True, signing_key=sk)

        valid, msg = verify_chain(log, verify_key=vk)
        assert valid, msg
        assert "signed" in msg.lower()

    def test_signed_chain_tampered_detected(self, tmp_path: Path, signing_keypair):
        sk, vk, _ = signing_keypair
        log = tmp_path / "evidence.jsonl"
        for i in range(3):
            entry = EvidenceEntry(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                actor="test",
                tool=None,
                files=[f"file{i}.py"],
                gates={"identity": "PASS"},
                kernels=[],
                decision="PASS",
            )
            append_entry(log, entry, hash_chain=True, signing_key=sk)

        # Tamper with entry data but keep signature
        lines = log.read_text().splitlines()
        entry_data = json.loads(lines[1])
        entry_data["actor"] = "tampered"
        lines[1] = json.dumps(entry_data, separators=(",", ":"), sort_keys=True)
        log.write_text("\n".join(lines) + "\n")

        valid, msg = verify_chain(log, verify_key=vk)
        assert not valid

    def test_unsigned_chain_still_valid_without_pubkey(self, tmp_path: Path):
        """Backward compat: unsigned entries verified normally without verify_key."""
        log = tmp_path / "evidence.jsonl"
        for i in range(2):
            entry = EvidenceEntry(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                actor="test",
                tool=None,
                files=[f"f{i}.py"],
                gates={"identity": "PASS"},
                kernels=[],
                decision="PASS",
            )
            append_entry(log, entry, hash_chain=True)

        valid, msg = verify_chain(log)
        assert valid

    def test_mixed_signed_unsigned_with_pubkey(self, tmp_path: Path, signing_keypair):
        """Unsigned entry after signed entries breaks when verifying with pubkey."""
        sk, vk, _ = signing_keypair
        log = tmp_path / "evidence.jsonl"

        # First entry: signed
        entry1 = EvidenceEntry(
            timestamp="2026-01-01T00:00:00Z",
            actor="test",
            tool=None,
            files=["a.py"],
            gates={"identity": "PASS"},
            kernels=[],
            decision="PASS",
        )
        append_entry(log, entry1, hash_chain=True, signing_key=sk)

        # Second entry: unsigned
        entry2 = EvidenceEntry(
            timestamp="2026-01-02T00:00:00Z",
            actor="test",
            tool=None,
            files=["b.py"],
            gates={"identity": "PASS"},
            kernels=[],
            decision="PASS",
        )
        append_entry(log, entry2, hash_chain=True)

        valid, msg = verify_chain(log, verify_key=vk)
        assert not valid
        assert "missing signature" in msg.lower()

    def test_threat_canonical_deterministic_across_key_order(self):
        data_a = {
            "decision": "PASS",
            "actor": "alice",
            "signature": "x",
            "key_id": "key",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": ["a.py"],
        }
        data_b = {
            "files": ["a.py"],
            "timestamp": "2026-01-01T00:00:00Z",
            "actor": "alice",
            "decision": "PASS",
            "key_id": "key",
            "signature": "y",
        }
        assert canonical_json(data_a) == canonical_json(data_b)

    def test_threat_canonical_matches_between_hash_and_sign(
        self, tmp_path: Path, signing_keypair
    ):
        sk, vk, _ = signing_keypair
        log = tmp_path / "evidence.jsonl"
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

        written = json.loads(log.read_text().splitlines()[0])
        canonical = canonical_json(written)
        assert verify_signature(vk, canonical, written["signature"])

    def test_threat_signature_survives_dict_reorder(self):
        data = {
            "decision": "PASS",
            "actor": "ci",
            "files": ["a.py"],
            "signature": "abc",
            "key_id": "def",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        reordered = {
            "key_id": "def",
            "signature": "abc",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": ["a.py"],
            "actor": "ci",
            "decision": "PASS",
        }
        assert canonical_json(data) == canonical_json(reordered)
