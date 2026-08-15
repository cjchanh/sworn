"""Git helpers for tests.

Some environments refuse writes under a `.git/` directory. These helpers
initialize repos with `--separate-git-dir` so metadata lives in `_git/`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git_init(path: Path) -> None:
    """Initialize a git work tree with metadata in ``path / "_git"``."""
    path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GIT_TEMPLATE_DIR"] = ""
    subprocess.run(
        ["git", "init", "--template=", "--separate-git-dir", str(path / "_git")],
        cwd=path,
        capture_output=True,
        check=True,
        env=env,
    )


def git_hooks_path(repo: Path) -> Path:
    """Resolve the effective hooks directory for a test repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    hook_dir = Path(result.stdout.strip())
    if not hook_dir.is_absolute():
        hook_dir = repo / hook_dir
    return hook_dir
