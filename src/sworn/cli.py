"""Sworn CLI — deterministic, fail-closed AI code governance."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sworn import __version__
from sworn.config import CONFIG_TEMPLATE, SwornConfig, load_config
from sworn.evidence.log import read_entries, verify_chain
from sworn.evidence.report import generate_report
from sworn.pipeline import run_pipeline


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
    report_p.add_argument(
        "--soc2",
        action="store_true",
        help="SOC 2 compliance report (requires sworn-soc2 pack)",
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
        return cmd_report(args.repo_root, fmt, args.since, args.cmmc, args.soc2)
    elif args.command == "status":
        return cmd_status(args.repo_root)
    elif args.command == "verify":
        return cmd_verify(args.repo_root)
    elif args.command == "keygen":
        return cmd_keygen(args.repo_root)
    elif args.command == "ci-check":
        return cmd_ci_check(args.repo_root, args.base)

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
    return Path.cwd()


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


def cmd_check(repo_root_override: Path | None) -> int:
    """Run the gate pipeline on staged files."""
    repo_root = _find_repo_root(repo_root_override)

    try:
        config = load_config(repo_root)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    # Get staged files
    files = _get_staged_files(repo_root)
    if not files:
        return 0  # Nothing staged, nothing to gate

    result = run_pipeline(repo_root, files, config)

    if result.decision == "PASS":
        print(f"SWORN PASS — {len(files)} file(s) gated")
        if result.tool:
            print(f"  Tool: {result.tool}")
        return 0

    # BLOCKED
    print(f"SWORN BLOCKED — {result.reason}")
    print(f"  Actor: {result.actor}")
    if result.tool:
        print(f"  Tool: {result.tool}")
    for gate, status in result.gate_results.items():
        if status == "BLOCKED":
            print(f"  Gate: {gate} → BLOCKED")
    return 1


def _get_staged_files(repo_root: Path) -> list[str]:
    """Get list of staged files via git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=10,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        pass
    return []


def _get_pr_diff_files(repo_root: Path, base_ref: str | None = None) -> list[str]:
    """Get list of files changed in PR diff."""
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
        if not (
            len(base_ref) == 40
            and all(c in "0123456789abcdefABCDEF" for c in base_ref)
        ):
            raise RuntimeError(
                "CI mode requires full base SHA (40 hex chars) "
                "from github.event.pull_request.base.sha"
            )

    if len(base_ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in base_ref):
        refs = [base_ref]
    else:
        # Try origin/{base} first (CI), fall back to bare {base} (local)
        refs = [f"origin/{base_ref}", base_ref]

    for ref in refs:
        try:
            result = subprocess.run(
                [
                    "git", "diff", "--name-only", "--diff-filter=ACMR",
                    f"{ref}...HEAD",
                ],
                capture_output=True,
                text=True,
                cwd=repo_root,
                timeout=10,
            )
            if result.returncode == 0:
                files = [f for f in result.stdout.strip().split("\n") if f]
                return files
        except Exception:
            continue

    if ci_mode:
        raise RuntimeError(
            "Failed to compute CI diff. Ensure actions/checkout uses "
            "fetch-depth: 0 and the base SHA is available."
        )

    return []


def cmd_ci_check(repo_root_override: Path | None, base_ref: str | None) -> int:
    """Run the gate pipeline on PR diff files (CI mode)."""
    repo_root = _find_repo_root(repo_root_override)

    try:
        config = load_config(repo_root)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    try:
        files = _get_pr_diff_files(repo_root, base_ref)
    except RuntimeError as exc:
        print(f"SWORN BLOCKED — {exc}", file=sys.stderr)
        return 1
    if not files:
        print("SWORN PASS — no files in diff")
        return 0

    result = run_pipeline(repo_root, files, config)

    if result.decision == "PASS":
        print(f"SWORN PASS — {len(files)} file(s) gated (CI)")
        return 0

    print(f"SWORN BLOCKED — {result.reason}")
    for gate, status in result.gate_results.items():
        if status == "BLOCKED":
            print(f"  Gate: {gate} → BLOCKED")
    return 1


def cmd_report(
    repo_root_override: Path | None,
    output_format: str,
    since: str | None,
    cmmc: bool,
    soc2: bool,
) -> int:
    """Generate an evidence report."""
    repo_root = _find_repo_root(repo_root_override)

    if cmmc:
        config = load_config(repo_root)
        log_path = repo_root / config.evidence_log_path
        from sworn.evidence.cmmc_report import generate_cmmc_report
        report = generate_cmmc_report(log_path, config, output_format)
        print(report)
        return 0

    if soc2:
        print("SOC 2 compliance reporting requires the sworn-soc2 pack.")
        print("See: https://sworncode.dev/packs")
        return 0

    config = load_config(repo_root)
    log_path = repo_root / config.evidence_log_path

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
        print(f"Chain integrity: {'VALID' if valid else 'BROKEN'}")
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
    """Verify evidence chain integrity and signatures."""
    repo_root = _find_repo_root(repo_root_override)
    config = load_config(repo_root)
    log_path = repo_root / config.evidence_log_path

    # Load verify key if present
    verify_key = None
    pub_path = repo_root / config.signing_pub_path
    if pub_path.exists():
        try:
            from sworn.evidence.signing import load_verify_key
            if pub_path.is_dir():
                valid, msg = verify_chain(log_path, verify_key_dir=pub_path)
            else:
                verify_key = load_verify_key(pub_path)
                valid, msg = verify_chain(log_path, verify_key=verify_key)
        except Exception as exc:
            print(f"Warning: could not load verify key: {exc}")
            valid = False
            msg = f"failed to verify signatures: {exc}"
    else:
        valid, msg = verify_chain(log_path)
    print(f"Chain: {'VALID' if valid else 'BROKEN'}")
    print(f"  {msg}")
    return 0 if valid else 1


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
