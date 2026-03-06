"""Configuration loader for .sworn/config.toml."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError as exc:
        raise ImportError(
            "Python 3.10 requires 'tomli' package: pip install tomli"
        ) from exc

DEFAULT_SECURITY_PATTERNS: list[str] = [
    r"(^|/)(crypto|auth|gates|licensing|keys)/",
    r"(^|/)secrets?/",
    r"\.env$",
    r"(^|/)private/",
]

CONFIG_TEMPLATE = """\
# Sworn configuration
# Docs: https://github.com/CentennialDefenseSystemsInc/sworn/blob/main/docs/config.md

[sworn]
version = "0.4"

[security]
# Regex patterns for sensitive paths. Commits touching these are BLOCKED.
# Case-insensitive matching (handles macOS HFS+/APFS).
patterns = [
    '(^|/)(crypto|auth|gates|licensing|keys)/',
    '(^|/)secrets?/',
    '\\.env$',
    '(^|/)private/',
]

[allowlist]
# If non-empty, ONLY these glob patterns are allowed in gated commits.
# Empty = all files allowed (security patterns still apply).
files = []

[identity]
# Environment variables checked for AI tool detection.
[identity.env_vars]
CLAUDE_CODE = "claude-code"
CODEX_CLI = "codex"
CURSOR_SESSION = "cursor"

[kernels]
# Built-in kernels. Set to false to disable.
security = true
allowlist = true
audit = true

# Custom kernel directory (relative to repo root).
custom_dir = ".sworn/kernels"

# CMMC kernel pack (NIST 800-171 controls).
# cmmc = true  # enable entire pack
# cmmc_ac_access = true  # per-control toggle

[evidence]
# Evidence log path (relative to repo root).
log_path = ".sworn/evidence.jsonl"
# SHA256 hash chain for tamper detection.
hash_chain = true

# [signing]
# Ed25519 evidence signing. Generate keys with: sworn keygen
# enabled = false
# key_path = ".sworn/keys/active.key"
# pub_path = ".sworn/keys/"
"""


@dataclass
class SwornConfig:
    """Parsed sworn configuration."""

    security_patterns: list[re.Pattern[str]] = field(default_factory=list)
    allowlist: list[str] = field(default_factory=list)
    identity_env_vars: dict[str, str] = field(default_factory=dict)
    kernels_enabled: dict[str, bool] = field(default_factory=dict)
    custom_kernel_dir: str = ".sworn/kernels"
    evidence_log_path: str = ".sworn/evidence.jsonl"
    evidence_hash_chain: bool = True
    signing_key_path: str = ".sworn/keys/active.key"
    signing_pub_path: str = ".sworn/keys/"
    signing_enabled: bool = False


def _compile_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    """Compile regex patterns with IGNORECASE. Invalid patterns fail closed."""
    compiled: list[re.Pattern[str]] = []
    for p in raw:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as exc:
            raise ValueError(f"Invalid security pattern '{p}': {exc}") from exc
    return compiled


def load_config(repo_root: Path) -> SwornConfig:
    """Load .sworn/config.toml or return defaults. Fail-closed on invalid."""
    config_path = repo_root / ".sworn" / "config.toml"

    if not config_path.exists():
        return _defaults()

    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse {config_path}: {exc}"
        ) from exc

    return _parse(raw)


def _defaults() -> SwornConfig:
    """Return default configuration."""
    return SwornConfig(
        security_patterns=_compile_patterns(DEFAULT_SECURITY_PATTERNS),
        allowlist=[],
        identity_env_vars={
            "CLAUDE_CODE": "claude-code",
            "CODEX_CLI": "codex",
            "CURSOR_SESSION": "cursor",
        },
        kernels_enabled={"security": True, "allowlist": True, "audit": True},
        custom_kernel_dir=".sworn/kernels",
        evidence_log_path=".sworn/evidence.jsonl",
        evidence_hash_chain=True,
        signing_enabled=False,
    )


def _parse(raw: dict[str, Any]) -> SwornConfig:
    """Parse raw TOML dict into SwornConfig. Fail-closed on invalid values."""
    security = raw.get("security", {})
    patterns_raw = security.get("patterns", DEFAULT_SECURITY_PATTERNS)
    if not isinstance(patterns_raw, list):
        raise ValueError("security.patterns must be a list of strings")

    allowlist_section = raw.get("allowlist", {})
    allowlist_files = allowlist_section.get("files", [])
    if not isinstance(allowlist_files, list):
        raise ValueError("allowlist.files must be a list of strings")

    identity = raw.get("identity", {})
    env_vars = identity.get("env_vars", {})
    if not isinstance(env_vars, dict):
        raise ValueError("identity.env_vars must be a table")

    kernels = raw.get("kernels", {})
    kernels_enabled = {
        "security": kernels.get("security", True),
        "allowlist": kernels.get("allowlist", True),
        "audit": kernels.get("audit", True),
    }

    # CMMC pack: group toggle or per-control
    cmmc_val = kernels.get("cmmc", False)
    if isinstance(cmmc_val, dict):
        kernels_enabled["cmmc"] = True
        for k, v in cmmc_val.items():
            kernels_enabled[f"cmmc_{k}"] = bool(v)
    else:
        kernels_enabled["cmmc"] = bool(cmmc_val)

    evidence = raw.get("evidence", {})

    signing = raw.get("signing", {})
    signing_key_path = signing.get("key_path", ".sworn/keys/active.key")
    signing_pub_path = signing.get("pub_path", ".sworn/keys/")
    signing_enabled = signing.get("enabled", False)
    if not isinstance(signing_enabled, bool):
        raise ValueError("signing.enabled must be true/false")

    return SwornConfig(
        security_patterns=_compile_patterns(patterns_raw),
        allowlist=allowlist_files,
        identity_env_vars=env_vars,
        kernels_enabled=kernels_enabled,
        custom_kernel_dir=kernels.get("custom_dir", ".sworn/kernels"),
        evidence_log_path=evidence.get("log_path", ".sworn/evidence.jsonl"),
        evidence_hash_chain=evidence.get("hash_chain", True),
        signing_key_path=signing_key_path,
        signing_pub_path=signing_pub_path,
        signing_enabled=signing_enabled,
    )
