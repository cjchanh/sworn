"""Evidence log — append-only JSONL with optional SHA256 hash chain and Ed25519 signing."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sworn.evidence.signing import compute_key_id


class EvidenceLogError(Exception):
    """Fail-closed evidence log error."""


@dataclass
class EvidenceEntry:
    """A single gate pipeline execution record."""

    timestamp: str
    actor: str
    tool: str | None
    files: list[str]
    gates: dict[str, str]
    kernels: list[dict[str, Any]]
    decision: str
    reason: str = ""
    resolution_trace: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = "genesis"
    signature: str = ""
    key_id: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_entry(entry_json: str) -> str:
    return hashlib.sha256(entry_json.encode()).hexdigest()


def canonical_json(
    entry_dict: dict[str, Any],
    *,
    include_signature_and_key_id: bool = False,
) -> str:
    """Produce canonical JSON for hashing and signing.

    The signature and key_id fields are always omitted from the canonical form.
    """
    canonical = dict(entry_dict)
    if not include_signature_and_key_id:
        if "signature" in canonical:
            canonical["signature"] = ""
        if "key_id" in canonical:
            canonical["key_id"] = ""
    return json.dumps(
        canonical,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )


def read_last_hash(log_path: Path) -> str:
    """Read the hash of the last entry. Returns 'genesis' if log is empty."""
    if not log_path.exists():
        return "genesis"
    try:
        with log_path.open("r") as f:
            last_line = ""
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
            if not last_line:
                return "genesis"
            # Hash the canonical form (signature/key_id stripped)
            entry = json.loads(last_line)
            return _hash_entry(canonical_json(entry))
    except json.JSONDecodeError as exc:
        raise EvidenceLogError(
            f"Failed to read previous evidence entry: invalid JSON in {log_path}"
        ) from exc
    except OSError as exc:
        raise EvidenceLogError(
            f"Failed to read previous evidence entry: {exc}"
        ) from exc
    except Exception as exc:
        raise EvidenceLogError(
            f"Failed to read previous evidence entry: {exc}"
        ) from exc


def append_entry(
    log_path: Path,
    entry: EvidenceEntry,
    hash_chain: bool = True,
    signing_key: Any = None,
) -> None:
    """Append an evidence entry to the JSONL log.

    If signing_key is provided, sign the canonical JSON.
    Hash chain is computed on canonical JSON (signature/key_id stripped).
    """
    if hash_chain:
        entry.prev_hash = read_last_hash(log_path)

    entry.signature = ""
    entry.key_id = ""
    entry_dict = asdict(entry)
    canonical = canonical_json(entry_dict)

    # Sign if key provided
    if signing_key is not None:
        from sworn.evidence.signing import sign_entry

        key_id = compute_key_id(signing_key.verify_key)
        entry_dict["key_id"] = key_id
        canonical = canonical_json(entry_dict)
        entry_dict["signature"] = sign_entry(signing_key, canonical)
    else:
        entry_dict["signature"] = ""

    entry_json = canonical_json(
        entry_dict,
        include_signature_and_key_id=True,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(entry_json + "\n")


def read_entries(log_path: Path) -> list[dict[str, Any]]:
    """Read all entries from evidence log."""
    if not log_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with log_path.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def verify_chain(
    log_path: Path,
    verify_key: Any = None,
    verify_key_dir: Path | None = None,
) -> tuple[bool, str]:
    """Verify the hash chain integrity and optional signatures.

    Returns (valid, message).
    If verify_key is provided, verifies all signatures against that key.
    If verify_key_dir is provided, signatures are verified using pub keys
    resolved from each entry's key_id.
    """
    if not log_path.exists():
        return True, "No evidence log found"

    prev_hash = "genesis"
    line_num = 0
    signed_count = 0
    unsigned_count = 0
    verify_with_key_dir = verify_key_dir is not None
    cached_keys: dict[str, Any] = {}

    with log_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_num += 1

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return False, f"Line {line_num}: invalid JSON"

            # Verify hash chain on canonical form
            canonical = canonical_json(entry)
            stored_hash = entry.get("prev_hash", "")
            if stored_hash != prev_hash:
                return False, (
                    f"Line {line_num}: hash chain broken "
                    f"(expected {prev_hash[:16]}..., got {stored_hash[:16]}...)"
                )

            prev_hash = _hash_entry(canonical)

            # Verify signature if verify key supplied
            sig = entry.get("signature", "")
            if sig:
                signed_count += 1
                verify_key_obj = verify_key
                if verify_with_key_dir:
                    key_id = entry.get("key_id", "")
                    if not key_id:
                        return False, f"Line {line_num}: missing key_id for signed entry"
                    if key_id not in cached_keys:
                        if not verify_key_dir.exists():
                            return (
                                False,
                                f"Line {line_num}: verify key directory missing: {verify_key_dir}",
                            )
                        if not verify_key_dir.is_dir():
                            return (
                                False,
                                f"Line {line_num}: expected key directory, found file: {verify_key_dir}",
                            )
                        pub_path = verify_key_dir / f"{key_id}.pub"
                        if not pub_path.exists():
                            return (
                                False,
                                f"Line {line_num}: missing signing key {key_id}.pub",
                            )
                        try:
                            from sworn.evidence.signing import load_verify_key
                            cached_keys[key_id] = load_verify_key(pub_path)
                        except Exception as exc:
                            return False, f"Line {line_num}: {exc}"
                    verify_key_obj = cached_keys[key_id]

                if verify_key_obj is not None:
                    from sworn.evidence.signing import verify_signature

                    if not verify_signature(verify_key_obj, canonical, sig):
                        return False, f"Line {line_num}: signature verification failed"

            else:
                unsigned_count += 1
                if (verify_key is not None or verify_with_key_dir) and line_num > 0:
                    if signed_count > 0:
                        return False, f"Line {line_num}: missing signature in signed log"

    msg = f"Chain valid: {line_num} entries"
    if signed_count > 0:
        msg += f" ({signed_count} signed"
        if unsigned_count > 0:
            msg += f", {unsigned_count} unsigned"
        msg += ")"

    return True, msg
