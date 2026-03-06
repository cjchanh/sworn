#!/usr/bin/env python3
"""Static release-truth checks for Sworn."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = Path("scripts/release_static_guard.py")
STALE_VERSION = "0.3.0"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def load_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def require_contains(path: Path, needle: str) -> None:
    content = path.read_text()
    if needle not in content:
        fail(f"missing expected content | {path} | {needle}")


def require_absent(path: Path, needle: str) -> None:
    content = path.read_text()
    if needle in content:
        fail(f"forbidden content present | {path} | {needle}")


def main() -> int:
    version = load_version()

    require_contains(ROOT / "src" / "sworn" / "__init__.py", f'__version__ = "{version}"')
    require_contains(ROOT / "action.yml", f'default: "{version}"')
    require_contains(ROOT / "examples" / "sworn-ci.yml", f"CentennialDefenseSystemsInc/sworn@{version}")
    require_contains(ROOT / "examples" / "sworn-ci.yml", f'version: "{version}"')
    require_contains(ROOT / "README.md", f"CMMC-focused in {version}")
    require_contains(ROOT / "COMPLIANCE_SCOPE.md", f"Sworn version {version}")
    require_contains(ROOT / "COMPLIANCE_SCOPE.md", f"reflects Sworn version {version} exactly")

    require_absent(ROOT / "pyproject.toml", '"soc2"')
    require_absent(ROOT / "src" / "sworn" / "cli.py", "--soc2")
    require_absent(ROOT / "src" / "sworn" / "cli.py", "sworncode.dev/packs")
    require_absent(ROOT / "src" / "sworn" / "config.py", "sworncode.dev/docs/config")

    docs_dir = ROOT / "docs"
    if not docs_dir.exists():
        fail(f"docs directory missing | {docs_dir}")
    if not (docs_dir / "config.md").exists():
        fail(f"config docs missing | {docs_dir / 'config.md'}")
    if not (docs_dir / "DEPLOYMENT.md").exists():
        fail(f"deployment docs missing | {docs_dir / 'DEPLOYMENT.md'}")

    if (ROOT / "STATE_REPORT.md").exists():
        fail("repo-root STATE_REPORT.md should not ship on release branch")

    readme = (ROOT / "README.md").read_text()
    if "docs/DEPLOYMENT.md" not in readme or "docs/config.md" not in readme:
        fail("README missing deployment/config doc links")
    if "Every commit is now gated." in readme:
        fail("README overclaims local hook scope")

    process_text = (ROOT / "RELEASE_PROCESS.md").read_text()
    if "release_phase1_capture.sh" not in process_text:
        fail("RELEASE_PROCESS.md missing phase1 capture script reference")

    version_hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if ".git" in path.parts or "dist" in path.parts or "build" in path.parts:
            continue
        if "release-evidence" in path.parts:
            continue
        if ".venv" in path.parts or ".venv-release" in path.parts:
            continue
        if any(part.endswith(".egg-info") or part.endswith(".dist-info") for part in path.parts):
            continue
        if path.suffix in {".pyc"}:
            continue
        rel_path = path.relative_to(ROOT)
        if rel_path == SELF_PATH:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if STALE_VERSION in text:
            version_hits.append(rel_path.as_posix())
    if version_hits:
        fail(f"stale {STALE_VERSION} references outside historical evidence | {version_hits}")

    print(f"PASS: release static guard | version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
