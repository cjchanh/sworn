"""Identity gate — detect actor and AI tool from environment."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class IdentityResult:
    """Result of identity detection. This gate never blocks."""

    actor: str
    tool: str | None
    confidence: str  # "detected", "inferred", "unknown"


def evaluate_identity(
    env_vars: dict[str, str] | None = None,
    repo_root: Path | None = None,
) -> IdentityResult:
    """Detect the actor and AI tool. Never blocks — always returns a result.

    Actor is read from the git config of ``repo_root`` when provided, so
    evidence is bound to the repository being gated rather than the process cwd.
    """
    if env_vars is None:
        env_vars = {
            "CLAUDE_CODE": "claude-code",
            "CODEX_CLI": "codex",
            "CURSOR_SESSION": "cursor",
        }

    # Check environment variables for AI tool
    tool: str | None = None
    confidence = "unknown"

    for var, tool_name in env_vars.items():
        if os.environ.get(var):
            tool = tool_name
            confidence = "detected"
            break

    actor = _git_actor(repo_root)

    return IdentityResult(actor=actor, tool=tool, confidence=confidence)


def _git_actor(repo_root: Path | None = None) -> str:
    """Get actor name from the gated repo's git config, not ambient cwd."""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=repo_root,
        )
        name = result.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return os.environ.get("USER", "unknown")
