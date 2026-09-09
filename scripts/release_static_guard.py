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

# Public-facing prose ban list (README, pyproject description, root *.md, docs/).
BANNED_VOCAB: tuple[tuple[str, str], ...] = (
    ("testify", r"\btestify\b"),
    ("testifies", r"\btestifies\b"),
    ("testimony", r"\btestimony\b"),
    ("receipt", r"\breceipt\b"),
    ("receipts", r"\breceipts\b"),
    ("Tuesday Bar", r"tuesday\s+bar"),
    ("TuesdayBar", r"tuesdaybar"),
    ("craft-gate", r"craft-gate"),
    ("craft gate", r"craft\s+gate"),
    ("operator", r"\boperator\b"),
    ("operators", r"\boperators\b"),
    ("governed", r"\bgoverned\b"),
)

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_INTERNAL_ROOT_REPORTS = frozenset({"REVIEW.md", "UPGRADE_REPORT.md", "AGENTS.md"})


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


def load_project_description(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["description"])


def public_prose_files(root: Path) -> list[Path]:
    """Public-facing prose: README, root ``*.md``, and ``docs/**``.

    Root-level ``REVIEW.md`` and ``UPGRADE_REPORT.md`` are internal reports
    and are excluded from this list.
    """
    files: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path in seen or not path.is_file():
            return
        seen.add(path)
        files.append(path)

    add(root / "README.md")
    for path in sorted(root.glob("*.md")):
        if path.name in _INTERNAL_ROOT_REPORTS:
            continue
        add(path)
    docs = root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".rst"}:
                add(path)
    return files


def _prose_only(text: str) -> str:
    """Drop fenced code blocks and inline code spans before vocab scan.

    A banned word inside backticks is therefore exempt (so `import operator` and
    identifier names never fail a release); prose must keep banned words out of
    backticks too if it wants the guard to see them.
    """
    return _INLINE_CODE_RE.sub(" ", _FENCED_CODE_RE.sub(" ", text))


def _scan_text(label: str, text: str) -> list[str]:
    hits: list[str] = []
    prose = _prose_only(text)
    for name, pattern in BANNED_VOCAB:
        if re.search(pattern, prose, re.IGNORECASE):
            hits.append(f"{label} | {name}")
    return hits


def banned_vocab_hits(root: Path) -> list[str]:
    """Return public-prose hits for the vocabulary ban list."""
    hits = _scan_text("pyproject.toml description", load_project_description(root))
    for path in public_prose_files(root):
        rel = path.relative_to(root).as_posix()
        hits.extend(_scan_text(rel, path.read_text()))
    return hits


def main() -> int:
    version = load_version()

    require_contains(ROOT / "src" / "sworn" / "__init__.py", f'__version__ = "{version}"')
    require_contains(ROOT / "action.yml", f'default: "{version}"')
    require_contains(ROOT / "examples" / "sworn-ci.yml", f"cjchanh/sworn@{version}")
    require_absent(ROOT / "examples" / "sworn-ci.yml", "CentennialDefenseSystemsInc")
    require_contains(ROOT / "docs" / "DEPLOYMENT.md", f"cjchanh/sworn@{version}")
    require_absent(ROOT / "docs" / "DEPLOYMENT.md", "CentennialDefenseSystemsInc")
    require_absent(ROOT / "pyproject.toml", "CentennialDefenseSystemsInc")
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

    vocab_hits = banned_vocab_hits(ROOT)
    if vocab_hits:
        fail("banned public vocabulary | " + "; ".join(vocab_hits))

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
