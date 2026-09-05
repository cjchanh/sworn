"""Sworn CLI — deterministic, fail-closed AI code governance."""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from sworn import __version__
from sworn.config import CONFIG_TEMPLATE, SwornConfig, fold_confusables, load_config
from sworn.evidence.log import chain_status, read_entries, verify_chain
from sworn.evidence.report import generate_report
from sworn.pipeline import run_pipeline

_SYMLINK_MODE = "120000"
_DIFF_FILTER = "ACMRTUXB"
_LS_FILES_RECORD = re.compile(
    r"^([0-7]{6}) ([0-9a-f]{40}|[0-9a-f]{64}) ([0-3])\t(.*)$"
)


_KEY_GITIGNORE_PATTERNS = (
    ".sworn/keys/active.key",
    ".sworn/signing.key",
)


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the sworn CLI."""
    parser = argparse.ArgumentParser(
        prog="sworn",
        description="Deterministic, fail-closed AI code governance.",
    )
    parser.add_argument(
        "--version", action="version", version=f"sworn {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize sworn in a git repo")
    init_p.add_argument("--repo-root", type=Path, default=None)

    # check
    check_p = sub.add_parser("check", help="Run gate pipeline on staged files")
    check_p.add_argument("--repo-root", type=Path, default=None)

    # report
    report_p = sub.add_parser("report", help="Generate evidence report")
    report_p.add_argument("--repo-root", type=Path, default=None)
    report_p.add_argument("--json", action="store_true")
    report_p.add_argument("--since", type=str, default=None)
    report_p.add_argument(
        "--cmmc",
        action="store_true",
        help="CMMC compliance report",
    )

    # status
    status_p = sub.add_parser("status", help="Show sworn status")
    status_p.add_argument("--repo-root", type=Path, default=None)

    # verify
    verify_p = sub.add_parser("verify", help="Verify evidence chain integrity")
    verify_p.add_argument("--repo-root", type=Path, default=None)

    # keygen
    keygen_p = sub.add_parser("keygen", help="Generate Ed25519 signing keypair")
    keygen_p.add_argument("--repo-root", type=Path, default=None)

    # ci-check
    ci_p = sub.add_parser("ci-check", help="Run gate pipeline on PR diff files")
    ci_p.add_argument("--repo-root", type=Path, default=None)
    ci_p.add_argument("--base", type=str, default=None)
    ci_p.add_argument(
        "--advisory",
        action="store_true",
        help=(
            "Opt OUT of fail-closed diff-base resolution. An unresolvable base "
            "prints a loud ADVISORY notice and exits 0 instead of blocking. It "
            "never prints PASS, and it does not affect gate verdicts: a kernel "
            "BLOCK still exits 1. Refused when SWORN_CI=1 is set. May also be "
            "requested with SWORN_ADVISORY=1."
        ),
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args.repo_root)
    elif args.command == "check":
        return cmd_check(args.repo_root)
    elif args.command == "report":
        fmt = "json" if args.json else "text"
        return cmd_report(args.repo_root, fmt, args.since, args.cmmc)
    elif args.command == "status":
        return cmd_status(args.repo_root)
    elif args.command == "verify":
        return cmd_verify(args.repo_root)
    elif args.command == "keygen":
        return cmd_keygen(args.repo_root)
    elif args.command == "ci-check":
        return cmd_ci_check(args.repo_root, args.base, args.advisory)

    return 0


def _find_repo_root(override: Path | None = None) -> Path:
    """Find repo root via git or use override."""
    if override:
        return override.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    raise RuntimeError("not a git repository")


def _run_git(
    repo_root: Path,
    args: list[str],
    *,
    timeout: int = 5,
) -> subprocess.CompletedProcess[str]:
    """Run a git command relative to repo_root."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=timeout,
    )


def _require_git_repo(repo_root: Path) -> None:
    """Fail if repo_root is not a Git work tree."""
    result = _run_git(repo_root, ["rev-parse", "--git-dir"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{repo_root} is not a git repository")


def _resolve_hooks_dir(repo_root: Path) -> Path:
    """Resolve the effective Git hooks directory, honoring core.hooksPath."""
    _require_git_repo(repo_root)

    hooks_override = _run_git(
        repo_root,
        ["config", "--path", "--get", "core.hooksPath"],
    )
    if hooks_override.returncode == 0:
        raw_path = hooks_override.stdout.strip()
        if raw_path:
            hook_dir = Path(raw_path)
            if not hook_dir.is_absolute():
                hook_dir = repo_root / hook_dir
            return hook_dir.resolve()

    hooks_dir = _run_git(repo_root, ["rev-parse", "--git-path", "hooks"])
    if hooks_dir.returncode != 0:
        raise RuntimeError(
            hooks_dir.stderr.strip() or "Unable to resolve Git hooks directory"
        )

    hook_dir = Path(hooks_dir.stdout.strip())
    if not hook_dir.is_absolute():
        hook_dir = repo_root / hook_dir
    return hook_dir.resolve()


def _warn_for_missing_key_ignores(repo_root: Path) -> None:
    """Warn if private key paths are not protected by .gitignore."""
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        joined = ", ".join(_KEY_GITIGNORE_PATTERNS)
        print(
            "\n  WARNING: No .gitignore found. Add "
            f"{joined} to prevent key leak."
        )
        return

    content = gitignore.read_text()
    missing = [
        pattern for pattern in _KEY_GITIGNORE_PATTERNS
        if pattern not in content and Path(pattern).name not in content
    ]
    if missing:
        print(f"\n  WARNING: Add {', '.join(missing)} to .gitignore")


def _run_git(
    repo_root: Path,
    args: list[str],
    *,
    timeout: int = 5,
) -> subprocess.CompletedProcess[str]:
    """Run a git command relative to repo_root."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=timeout,
    )


def _require_git_repo(repo_root: Path) -> None:
    """Fail if repo_root is not a Git work tree."""
    result = _run_git(repo_root, ["rev-parse", "--git-dir"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{repo_root} is not a git repository")


def _resolve_hooks_dir(repo_root: Path) -> Path:
    """Resolve the effective Git hooks directory, honoring core.hooksPath."""
    _require_git_repo(repo_root)

    hooks_override = _run_git(
        repo_root,
        ["config", "--path", "--get", "core.hooksPath"],
    )
    if hooks_override.returncode == 0:
        raw_path = hooks_override.stdout.strip()
        if raw_path:
            hook_dir = Path(raw_path)
            if not hook_dir.is_absolute():
                hook_dir = repo_root / hook_dir
            return hook_dir.resolve()

    hooks_dir = _run_git(repo_root, ["rev-parse", "--git-path", "hooks"])
    if hooks_dir.returncode != 0:
        raise RuntimeError(
            hooks_dir.stderr.strip() or "Unable to resolve Git hooks directory"
        )

    hook_dir = Path(hooks_dir.stdout.strip())
    if not hook_dir.is_absolute():
        hook_dir = repo_root / hook_dir
    return hook_dir.resolve()


def _warn_for_missing_key_ignores(repo_root: Path) -> None:
    """Warn if private key paths are not protected by .gitignore."""
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        joined = ", ".join(_KEY_GITIGNORE_PATTERNS)
        print(
            "\n  WARNING: No .gitignore found. Add "
            f"{joined} to prevent key leak."
        )
        return

    content = gitignore.read_text()
    missing = [
        pattern for pattern in _KEY_GITIGNORE_PATTERNS
        if pattern not in content and Path(pattern).name not in content
    ]
    if missing:
        print(f"\n  WARNING: Add {', '.join(missing)} to .gitignore")


def cmd_init(repo_root_override: Path | None) -> int:
    """Initialize sworn in a git repo."""
    repo_root = _find_repo_root(repo_root_override)
    try:
        hook_dir = _resolve_hooks_dir(repo_root)
    except RuntimeError:
        print(f"Error: {repo_root} is not a git repository.", file=sys.stderr)
        return 1

    sworn_dir = repo_root / ".sworn"
    sworn_dir.mkdir(exist_ok=True)

    # Write config template
    config_path = sworn_dir / "config.toml"
    if not config_path.exists():
        config_path.write_text(CONFIG_TEMPLATE)
        print(f"  Created {config_path.relative_to(repo_root)}")
    else:
        print(f"  Config already exists: {config_path.relative_to(repo_root)}")

    # Install pre-commit hook
    hook_path = hook_dir / "pre-commit"
    hook_line = 'sworn check || exit 1\n'

    if hook_path.exists():
        content = hook_path.read_text()
        if "sworn check" not in content:
            with hook_path.open("a") as f:
                f.write(f"\n# Sworn gate\n{hook_line}")
            print("  Appended sworn check to existing pre-commit hook")
        else:
            print("  Hook already installed")
    else:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(f"#!/usr/bin/env bash\n# Sworn gate\n{hook_line}")
        hook_path.chmod(0o755)
        print("  Created pre-commit hook")

    print(f"\nSworn initialized in {repo_root}")
    print("Commits that run Git hooks in this repo are now gated.")
    return 0


def _is_zero_oid(oid: str) -> bool:
    return oid == "0" * 40 or oid == "0" * 64


def _print_blocked(reason: str, result: object | None = None) -> int:
    print(f"SWORN BLOCKED — {reason}")
    if result is not None:
        print(f"  Actor: {getattr(result, 'actor', '')}")
        tool = getattr(result, "tool", None)
        if tool:
            print(f"  Tool: {tool}")
        for gate, status in (getattr(result, "gate_results", None) or {}).items():
            if status == "BLOCKED":
                print(f"  Gate: {gate} → BLOCKED")
    return 1


def _path_gate_hard_block(reason: str | None) -> bool:
    if not reason:
        return False
    return reason.startswith("symlink-escapes-repo") or reason.startswith(
        "index-unreadable"
    )


def cmd_check(repo_root_override: Path | None) -> int:
    """Run the gate pipeline on staged files."""
    repo_root = _find_repo_root(repo_root_override)

    try:
        config = load_config(repo_root)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    pattern_reason = None
    files: list[str] = []
    try:
        files = _get_staged_files(repo_root)
        if files:
            files, pattern_reason = evaluate_path_gate_candidates(
                repo_root, files, config.security_patterns
            )
    except RuntimeError as exc:
        print(
            f"SWORN BLOCKED — unable to determine staged files: {exc}",
            file=sys.stderr,
        )
        return 1
    if not files:
        if pattern_reason:
            print(f"SWORN BLOCKED — {pattern_reason}")
            return 1
        return 0  # Nothing staged, nothing to gate

    # A path-gate hit (pattern, symlink target, confusable name, intent-to-add,
    # unreadable index) is handed to the pipeline as the security verdict, so the
    # pipeline blocks, runs the remaining structural gates, and writes the one
    # evidence entry itself. Nothing is written or rewritten outside the pipeline.
    result = run_pipeline(repo_root, files, config, security_reason=pattern_reason)

    if result.decision == "PASS":
        print(f"SWORN PASS — {len(files)} file(s) gated")
        if result.tool:
            print(f"  Tool: {result.tool}")
        return 0

    return _print_blocked(result.reason, result)


def _nul_split(payload: str) -> list[str]:
    return [part for part in payload.split("\0") if part]


def _git_z(
    repo_root: Path,
    args: list[str],
    *,
    timeout: int = 10,
    probe: str = "git probe",
) -> str:
    """Run git with quotepath off and NUL-safe stdout. timeout/OSError -> RuntimeError."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=repo_root,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{probe} timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise RuntimeError(f"{probe} failed: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{probe} failed: {exc}") from exc
    if result.returncode != 0:
        detail = next(
            (line for line in result.stderr.splitlines() if line.strip()), ""
        )
        raise RuntimeError(
            detail.strip() or f"{probe} exited {result.returncode}"
        )
    return result.stdout


def _get_staged_files(repo_root: Path) -> list[str]:
    """Get list of staged files via git.

    Candidate set is ``git diff --cached --name-only -z --diff-filter=ACMRTUXB``
    plus intent-to-add entries from ``git status --porcelain=v2 -z`` rows
    whose index status contains ``A`` and whose index blob is an all-zero
    OID (40 hex on SHA-1 repos, 64 hex on SHA-256 repos).
    ``git diff --cached --diff-filter=A`` misses those. Deletions (D)
    stay excluded.

    A failed probe is never an empty staging area: callers must not be able to
    confuse "git could not answer" with "nothing is staged".

    Raises:
        RuntimeError: the git probe timed out, could not be executed, or exited
            non-zero.
    """
    out = _git_z(
        repo_root,
        [
            "diff",
            "--cached",
            "--name-only",
            "-z",
            f"--diff-filter={_DIFF_FILTER}",
        ],
        probe="git staged-file probe",
    )
    files = _nul_split(out)
    seen = set(files)
    for path in _intent_to_add_paths(repo_root):
        if path not in seen:
            seen.add(path)
            files.append(path)
    return files


def _intent_to_add_paths(repo_root: Path) -> list[str]:
    """Intent-to-add paths from ``git status --porcelain=v2 -z``.

    ``git diff --cached --diff-filter=A`` misses ``git add -N``. This Git
    emits porcelain v2 ``1 .A`` with an all-zero index blob (not an all-zero
    ``ls-files -s`` OID — that field is the empty blob). Rows whose status
    contains ``A`` and whose index blob is the all-zero OID are included.
    """
    out = _git_z(
        repo_root,
        ["status", "--porcelain=v2", "-z"],
        probe="git staged-file probe",
    )
    paths: list[str] = []
    records = _nul_split(out)
    idx = 0
    while idx < len(records):
        rec = records[idx]
        idx += 1
        if rec.startswith("2 "):
            if idx < len(records):
                idx += 1
            continue
        if not rec.startswith("1 "):
            continue
        parts = rec.split(" ", 8)
        if len(parts) < 9:
            continue
        _one, xy, _sub, _mh, _mi, _mw, _hh, index_blob, path = parts
        if "A" not in xy:
            continue
        if _is_zero_oid(index_blob):
            paths.append(path)
    return paths


class PathGateBlocked(Exception):
    """Fail-closed path-gate verdict (index-unreadable, symlink-escapes-repo)."""


def _parse_ls_files_record(record: str) -> tuple[str, str, str, str] | None:
    match = _LS_FILES_RECORD.match(record)
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3), match.group(4)


def _lexical_escapes(path: str) -> bool:
    normalised = posixpath.normpath(path)
    return posixpath.isabs(normalised) or normalised == ".." or normalised.startswith("../")


def _index_record(repo_root: Path, path: str) -> tuple[str, str]:
    """Return (mode, sha) from the index. Pathspec is literal; worktree is ignored."""
    out = _git_z(
        repo_root,
        ["ls-files", "-s", "-z", "--", f":(literal){path}"],
        probe="git index probe",
    )
    matches: list[tuple[str, str, str, str]] = []
    for record in _nul_split(out):
        parsed = _parse_ls_files_record(record)
        if parsed is not None and parsed[3] == path:
            matches.append(parsed)
    if not matches:
        raise PathGateBlocked(f"index-unreadable: {path}")
    for mode, sha, stage, _name in matches:
        if stage == "0":
            return mode, sha
    return matches[0][0], matches[0][1]


def _symlink_blob_target(repo_root: Path, sha: str, raw_path: str) -> str:
    try:
        blob = _git_z(
            repo_root,
            ["cat-file", "-p", sha],
            probe="git index probe",
        )
    except RuntimeError as exc:
        raise PathGateBlocked(f"index-unreadable: {raw_path}") from exc
    if blob.endswith("\n"):
        blob = blob[:-1]
    return blob


def evaluate_path_gate_candidates(
    repo_root: Path,
    paths: list[str],
    patterns: list[re.Pattern[str]] | None = None,
) -> tuple[list[str], str | None]:
    """Return evaluated candidates for both ``check`` and ``ci-check``.

    The staged object is the truth: mode and blob come from the index via
    ``git ls-files -s -z -- ":(literal)<path>"``. The returned path must equal
    ``<path>`` exactly. Worktree ``Path.resolve`` / ``is_symlink`` / ``is_dir``
    / ``exists`` are never used for policy.

    Variants (NFKC, confusable-folded, collapsed, symlink targets) are matched
    locally. Non-matching variants are not returned. A pattern hit returns a
    block reason instead of raising so callers still run the pipeline; the
    matching variant is included only when it differs from the staged path so
    the security stage still records the block. Index/symlink probes are
    skipped once a pattern reason is set. ``index-unreadable`` and
    ``symlink-escapes-repo`` become a block reason the same way, so callers
    still run the pipeline and write evidence.
    """
    originals: list[str] = []
    seen: set[str] = set()
    compiled = patterns or []
    pattern_reason: str | None = None
    match_variant: str | None = None
    hard_block: PathGateBlocked | None = None

    def add_original(item: str) -> None:
        if item and item not in seen:
            seen.add(item)
            originals.append(item)

    def consider(raw: str, variant: str, kind: str) -> None:
        nonlocal pattern_reason, match_variant
        if pattern_reason is not None:
            return
        for pattern in compiled:
            if pattern.search(variant):
                pattern_reason = (
                    f"Security surface: {raw} (variant: {kind} {variant})"
                )
                match_variant = variant
                return

    for path in paths:
        add_original(path)
        nfkc_path = unicodedata.normalize("NFKC", path)
        consider(path, path, "raw")
        consider(path, nfkc_path, "nfkc")
        consider(path, nfkc_path + "/", "nfkc")
        consider(path, fold_confusables(path), "confusable-folded")
        consider(path, fold_confusables(path) + "/", "confusable-folded")
        consider(path, fold_confusables(nfkc_path), "confusable-folded")
        consider(path, fold_confusables(nfkc_path) + "/", "confusable-folded")
        collapsed = posixpath.normpath(path)
        consider(path, collapsed, "collapsed")
        if pattern_reason is not None:
            continue
        if _lexical_escapes(collapsed):
            hard_block = PathGateBlocked(f"symlink-escapes-repo: {path}")
            continue
        try:
            mode, sha = _index_record(repo_root, path)
            if mode != _SYMLINK_MODE:
                continue
            if _is_zero_oid(sha):
                raise PathGateBlocked(f"index-unreadable: {path}")
            target = _symlink_blob_target(repo_root, sha, path)
            nfkc_target = unicodedata.normalize("NFKC", target)
            consider(path, target, "symlink-target")
            consider(path, target + "/", "symlink-target")
            consider(path, nfkc_target, "nfkc")
            consider(path, nfkc_target + "/", "nfkc")
            consider(path, fold_confusables(target), "confusable-folded")
            consider(path, fold_confusables(target) + "/", "confusable-folded")
            consider(path, fold_confusables(nfkc_target), "confusable-folded")
            consider(path, fold_confusables(nfkc_target) + "/", "confusable-folded")
            joined = posixpath.normpath(
                posixpath.join(posixpath.dirname(path), target)
            )
            if _lexical_escapes(joined):
                raise PathGateBlocked(
                    f"symlink-escapes-repo: {path} -> {target}"
                )
            nfkc_joined = unicodedata.normalize("NFKC", joined)
            folded_joined = fold_confusables(joined)
            consider(path, joined, "symlink-target")
            consider(path, joined + "/", "symlink-target")
            consider(path, nfkc_joined, "nfkc")
            consider(path, nfkc_joined + "/", "nfkc")
            consider(path, folded_joined, "confusable-folded")
            consider(path, folded_joined + "/", "confusable-folded")
            consider(path, fold_confusables(nfkc_joined), "confusable-folded")
            consider(path, fold_confusables(nfkc_joined) + "/", "confusable-folded")
        except PathGateBlocked as exc:
            hard_block = exc
            continue
    if match_variant and match_variant not in seen:
        originals.append(match_variant)
    if pattern_reason is not None:
        return originals, pattern_reason
    if hard_block is not None:
        return originals, str(hard_block)
    return originals, None


class DiffBaseUnresolved(RuntimeError):
    """No candidate ref yielded a computable diff.

    Distinct from "the diff is genuinely empty". Callers must not be able to
    confuse "git could not answer" with "nothing changed", because the two have
    opposite security meanings: the first gated no files, the second gated every
    file there was. Subclasses ``RuntimeError`` so existing handlers still catch
    it.
    """


def _is_full_sha(ref: str) -> bool:
    """True if ``ref`` is a full 40-character hex SHA."""
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)


def _get_pr_diff_files(repo_root: Path, base_ref: str | None = None) -> list[str]:
    """Get list of files changed in PR diff.

    A failed probe is never an empty diff. If no candidate ref yields a
    computable diff, this raises ``DiffBaseUnresolved`` rather than returning
    ``[]`` — unconditionally, whether or not ``SWORN_CI`` is set. Returning an
    empty list here would make an unresolvable base indistinguishable from a
    clean diff, which is the fail-open path this function must not have.

    ``SWORN_CI=1`` continues to govern exactly one thing: the stricter *base-ref
    format* policy that requires a full 40-hex SHA. That is a CI-specific
    requirement (the base SHA comes from ``github.event.pull_request.base.sha``)
    and is deliberately not the local default, so a developer can still run
    ``ci-check --base my-branch``. Pipelines already setting ``SWORN_CI=1``
    therefore see no behavior change.

    Raises:
        DiffBaseUnresolved: no candidate ref produced a computable diff, or the
            resolved base ref was empty.
        RuntimeError: CI mode was declared and the base ref is missing or is not
            a full 40-hex SHA.
    """
    ci_mode = os.environ.get("SWORN_CI") == "1"
    if base_ref is None:
        base_ref = os.environ.get("SWORN_BASE_SHA")
        if not base_ref:
            base_ref = os.environ.get("GITHUB_BASE_REF", "main")

    if ci_mode:
        if not base_ref:
            raise RuntimeError(
                "CI mode requires base ref: pass --base or set SWORN_BASE_SHA"
            )
        if not _is_full_sha(base_ref):
            raise RuntimeError(
                "CI mode requires full base SHA (40 hex chars) "
                "from github.event.pull_request.base.sha"
            )

    # An empty base is unresolvable, not a comparison against HEAD: without this
    # the ref list degenerates to "...HEAD", which git happily resolves to an
    # empty diff and would report as PASS.
    if not base_ref.strip():
        raise DiffBaseUnresolved(
            "No diff base to compare against: pass --base or set SWORN_BASE_SHA"
        )

    if _is_full_sha(base_ref):
        refs = [base_ref]
    else:
        # Try origin/{base} first (CI), fall back to bare {base} (local)
        refs = [f"origin/{base_ref}", base_ref]

    for ref in refs:
        try:
            out = _git_z(
                repo_root,
                [
                    "diff",
                    "--name-only",
                    "-z",
                    f"--diff-filter={_DIFF_FILTER}",
                    f"{ref}...HEAD",
                ],
                probe="git pr-diff probe",
            )
        except RuntimeError as exc:
            cause = exc.__cause__
            if isinstance(
                cause,
                (subprocess.TimeoutExpired, OSError, UnicodeDecodeError),
            ):
                raise
            continue
        return _nul_split(out)

    raise DiffBaseUnresolved(
        f"Failed to compute diff against base {base_ref!r} "
        f"(tried: {', '.join(refs)}). Ensure the base ref is fetched — in CI, "
        "actions/checkout needs fetch-depth: 0 and the base SHA available."
    )


ADVISORY_BANNER = """\
============================================================
SWORN ADVISORY — GATE DID NOT RUN. THIS IS NOT A PASS.
  {reason}
  Advisory mode was requested (--advisory / SWORN_ADVISORY=1),
  so this exits 0 having gated zero files. This exit code is
  not an assurance signal. Remove --advisory to fail closed.
============================================================"""


def cmd_ci_check(
    repo_root_override: Path | None,
    base_ref: str | None,
    advisory: bool = False,
) -> int:
    """Run the gate pipeline on PR diff files (CI mode)."""
    repo_root = _find_repo_root(repo_root_override)

    advisory = advisory or os.environ.get("SWORN_ADVISORY") == "1"
    if advisory and os.environ.get("SWORN_CI") == "1":
        # Two contradictory switches. Refusing is the fail-closed reading: a
        # declared CI gate must not be downgradable by an advisory opt-out.
        print(
            "SWORN BLOCKED — advisory mode requested while SWORN_CI=1 is set. "
            "Refusing to downgrade a declared CI gate; unset one of them.",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_config(repo_root)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    pattern_reason = None
    files: list[str] = []
    try:
        files = _get_pr_diff_files(repo_root, base_ref)
        if files:
            files, pattern_reason = evaluate_path_gate_candidates(
                repo_root, files, config.security_patterns
            )
    except DiffBaseUnresolved as exc:
        if advisory:
            print(ADVISORY_BANNER.format(reason=exc), file=sys.stderr)
            return 0
        print(f"SWORN BLOCKED — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"SWORN BLOCKED — {exc}", file=sys.stderr)
        return 1
    if not files:
        if pattern_reason:
            print(f"SWORN BLOCKED — {pattern_reason}")
            return 1
        print("SWORN PASS — no files in diff")
        return 0

    # A path-gate hit (pattern, symlink target, confusable name, intent-to-add,
    # unreadable index) is handed to the pipeline as the security verdict, so the
    # pipeline blocks, runs the remaining structural gates, and writes the one
    # evidence entry itself. Nothing is written or rewritten outside the pipeline.
    result = run_pipeline(repo_root, files, config, security_reason=pattern_reason)

    if result.decision == "PASS":
        print(f"SWORN PASS — {len(files)} file(s) gated (CI)")
        return 0

    return _print_blocked(result.reason, result)


def _verify_signed_chain(
    repo_root: Path,
    config: SwornConfig,
    log_path: Path,
) -> tuple[bool, str]:
    """Load repo-local verify keys and verify the evidence chain.

    Returns (ok, reason). reason is the same two-line output cmd_verify prints.
    Fail-closed: a missing public key with signing enabled is a refusal.
    """
    require_signatures = config.signing_enabled

    verify_key = None
    verify_key_dir = None
    pub_path = repo_root / config.signing_pub_path
    if pub_path.exists():
        try:
            from sworn.evidence.signing import load_verify_key
            if pub_path.is_dir():
                pubs = list(pub_path.glob("*.pub"))
                if pubs:
                    verify_key_dir = pub_path
                elif require_signatures:
                    return False, (
                        "Chain: BROKEN\n"
                        "  Signing enabled but no public keys found"
                    )
            else:
                verify_key = load_verify_key(pub_path)
        except Exception as exc:
            return False, f"Chain: BROKEN\n  failed to verify signatures: {exc}"
    elif require_signatures:
        return False, (
            "Chain: BROKEN\n"
            "  Signing enabled but public key path missing: "
            f"{config.signing_pub_path}"
        )

    valid, msg = verify_chain(
        log_path,
        verify_key=verify_key,
        verify_key_dir=verify_key_dir,
        require_signatures=require_signatures,
    )
    status = chain_status(valid, msg)
    return status == "VALID", f"Chain: {status}\n  {msg}"


def cmd_report(
    repo_root_override: Path | None,
    output_format: str,
    since: str | None,
    cmmc: bool,
) -> int:
    """Generate an evidence report."""
    repo_root = _find_repo_root(repo_root_override)
    config = load_config(repo_root)
    log_path = repo_root / config.evidence_log_path

    if config.signing_enabled:
        ok, reason = _verify_signed_chain(repo_root, config, log_path)
        if not ok:
            print("Report: REFUSED")
            print(reason)
            return 1

    if cmmc:
        from sworn.evidence.cmmc_report import generate_cmmc_report
        report = generate_cmmc_report(log_path, config, output_format)
        print(report)
        return 0

    report = generate_report(log_path, output_format, since)
    print(report)
    return 0


def cmd_status(repo_root_override: Path | None) -> int:
    """Show sworn status."""
    repo_root = _find_repo_root(repo_root_override)

    sworn_dir = repo_root / ".sworn"
    initialized = sworn_dir.exists()

    print(f"Repo: {repo_root}")
    print(f"Initialized: {'yes' if initialized else 'no'}")

    if not initialized:
        print("\nRun 'sworn init' to get started.")
        return 0

    # Config
    config_path = sworn_dir / "config.toml"
    print(f"Config: {'present' if config_path.exists() else 'missing (using defaults)'}")

    # Hook
    hook_installed = False
    try:
        hook_path = _resolve_hooks_dir(repo_root) / "pre-commit"
    except RuntimeError:
        hook_path = None
    if hook_path is not None and hook_path.exists():
        hook_installed = "sworn check" in hook_path.read_text()
    print(f"Hook: {'installed' if hook_installed else 'not installed'}")

    # Signing
    try:
        config = load_config(repo_root)
        key_path = repo_root / config.signing_key_path
        pub_path = repo_root / config.signing_pub_path
        if key_path.exists():
            print("Signing: enabled (key present)")
        elif pub_path.exists() and pub_path.is_dir():
            if any(p.suffix == ".pub" for p in pub_path.iterdir()):
                print("Signing: verify-only (pub key(s) present)")
            else:
                print("Signing: disabled (no key)")
        elif pub_path.exists():
            print("Signing: verify-only (pub key present)")
        else:
            print("Signing: disabled (no key)")
    except Exception:
        pass

    # Evidence
    try:
        config = load_config(repo_root)
        log_path = repo_root / config.evidence_log_path
        entries = read_entries(log_path)
        print(f"Evidence entries: {len(entries)}")
        if entries:
            last = entries[-1]
            print(f"Last gate: {last.get('decision', '?')} at {last.get('timestamp', '?')}")

        # Chain
        valid, msg = verify_chain(log_path)
        print(f"Chain integrity: {chain_status(valid, msg)}")
    except Exception:
        print("Evidence: unable to read")

    # Kernels
    try:
        config = load_config(repo_root)
        enabled = [k for k, v in config.kernels_enabled.items() if v]
        print(f"Kernels: {', '.join(enabled) if enabled else 'none'}")
        print(f"Security patterns: {len(config.security_patterns)}")
        print(f"Allowlist: {len(config.allowlist)} pattern(s)" if config.allowlist else "Allowlist: disabled")
    except Exception:
        pass

    return 0


def cmd_verify(repo_root_override: Path | None) -> int:
    """Verify evidence chain integrity and signatures.

    EMPTY (no log / no entries) and BROKEN exit 1. VALID exits 0.
    When signing is enabled, unsigned entries and missing public keys fail closed.
    """
    repo_root = _find_repo_root(repo_root_override)
    config = load_config(repo_root)
    log_path = repo_root / config.evidence_log_path
    ok, reason = _verify_signed_chain(repo_root, config, log_path)
    print(reason)
    return 0 if ok else 1


def cmd_keygen(repo_root_override: Path | None) -> int:
    """Generate Ed25519 signing keypair."""
    repo_root = _find_repo_root(repo_root_override)
    sworn_dir = repo_root / ".sworn"

    if not sworn_dir.exists():
        print("Error: run 'sworn init' first", file=sys.stderr)
        return 1

    try:
        from sworn.evidence.signing import generate_keypair
    except Exception:
        print("Error: PyNaCl required: pip install 'sworncode[signing]'", file=sys.stderr)
        return 1

    config = load_config(repo_root)
    key_dir = (repo_root / config.signing_key_path).parent

    try:
        priv_path, pub_path = generate_keypair(key_dir)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"  Created {priv_path.relative_to(repo_root)} (private — DO NOT COMMIT)")
    print(f"  Created {pub_path.relative_to(repo_root)} (public — safe to commit)")
    _warn_for_missing_key_ignores(repo_root)

    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess test
    # B-2 residual (2026-08-18): the package entrypoint (sworn/__main__.py)
    # and the console script both propagate main()'s exit code; invoking this
    # module directly used to discard it, so EVERY verdict — BLOCKED
    # included — exited 0. Verified live: bogus --base printed "SWORN
    # BLOCKED" and the process exited 0. One guard, all three shapes
    # identical. Regression: tests/test_ci_check.py::
    # test_module_direct_invocation_propagates_block_exit_code.
    import sys as _sys

    raise SystemExit(main(_sys.argv[1:]))
