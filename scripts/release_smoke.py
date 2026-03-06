#!/usr/bin/env python3
"""Release smoke scenarios for locally built Sworn artifacts."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SmokeLogger:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def log(self, message: str) -> None:
        line = f"SOLID: {message}"
        self._lines.append(line)
        print(line)

    def write(self, path: Path | None) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self._lines) + "\n")


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def init_git_repo(path: Path) -> None:
    run(["git", "init", "-q"], cwd=path)
    run(["git", "config", "user.name", "smoke-test"], cwd=path)
    run(["git", "config", "user.email", "smoke@test.local"], cwd=path)
    run(["git", "commit", "--allow-empty", "-m", "init"], cwd=path)


def repo_python(venv_dir: Path) -> str:
    return str(venv_dir / "bin" / "python")


def append_signing_enabled(repo: Path) -> None:
    config = repo / ".sworn" / "config.toml"
    with config.open("a") as f:
        f.write("\n[signing]\nenabled = true\nkey_path = \".sworn/keys/active.key\"\npub_path = \".sworn/keys/\"\n")


def smoke_happy_path(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-pass-") as tmp:
        repo = Path(tmp)
        init_git_repo(repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(repo)])
        (repo / "app.py").write_text("print('ok')\n")
        run(["git", "add", "app.py"], cwd=repo)
        result = run([py, "-m", "sworn", "check", "--repo-root", str(repo)], check=False)
        if result.returncode != 0 or "SWORN PASS" not in result.stdout:
            raise RuntimeError(f"happy path failed\n{result.stdout}\n{result.stderr}")
        logger.log("release smoke | happy path commit gate passed")


def smoke_security_block(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-block-") as tmp:
        repo = Path(tmp)
        init_git_repo(repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(repo)])
        (repo / "private").mkdir()
        (repo / "private" / "data.py").write_text("secret = 1\n")
        run(["git", "add", "private/data.py"], cwd=repo)
        result = run([py, "-m", "sworn", "check", "--repo-root", str(repo)], check=False)
        if result.returncode == 0 or "SWORN BLOCKED" not in result.stdout:
            raise RuntimeError(f"security block failed\n{result.stdout}\n{result.stderr}")
        logger.log("release smoke | sensitive path block held")


def smoke_missing_signing_key(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-signing-") as tmp:
        repo = Path(tmp)
        init_git_repo(repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(repo)])
        append_signing_enabled(repo)
        (repo / "app.py").write_text("print('signed')\n")
        run(["git", "add", "app.py"], cwd=repo)
        result = run([py, "-m", "sworn", "check", "--repo-root", str(repo)], check=False)
        if result.returncode == 0 or "signing key is missing" not in (result.stdout + result.stderr):
            raise RuntimeError(f"missing signing key did not block\n{result.stdout}\n{result.stderr}")
        logger.log("release smoke | missing signing key blocked in signed mode")


def smoke_corrupt_evidence(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-corrupt-") as tmp:
        repo = Path(tmp)
        init_git_repo(repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(repo)])
        evidence = repo / ".sworn" / "evidence.jsonl"
        evidence.write_text("{not-json}\n")
        (repo / "app.py").write_text("print('again')\n")
        run(["git", "add", "app.py"], cwd=repo)
        result = run([py, "-m", "sworn", "check", "--repo-root", str(repo)], check=False)
        if result.returncode == 0 or "Evidence log failure" not in (result.stdout + result.stderr):
            raise RuntimeError(f"corrupt evidence did not block\n{result.stdout}\n{result.stderr}")
        logger.log("release smoke | corrupt evidence log blocked extension")


def smoke_hooks_path(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-hooks-") as tmp:
        repo = Path(tmp)
        init_git_repo(repo)
        run(["git", "config", "core.hooksPath", ".githooks"], cwd=repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(repo)])
        hook = repo / ".githooks" / "pre-commit"
        if not hook.exists():
            raise RuntimeError(f"hooksPath pre-commit missing: {hook}")
        logger.log("release smoke | core.hooksPath installation honored")


def smoke_worktree(py: str, logger: SmokeLogger) -> None:
    with tempfile.TemporaryDirectory(prefix="sworn-smoke-worktree-") as tmp:
        root = Path(tmp)
        main_repo = root / "main"
        worktree = root / "wt"
        main_repo.mkdir()
        init_git_repo(main_repo)
        (main_repo / "seed.txt").write_text("seed\n")
        run(["git", "add", "seed.txt"], cwd=main_repo)
        run(["git", "commit", "-m", "seed"], cwd=main_repo)
        run(["git", "worktree", "add", str(worktree)], cwd=main_repo)
        run([py, "-m", "sworn", "init", "--repo-root", str(worktree)])
        hooks_dir = run(["git", "rev-parse", "--git-path", "hooks"], cwd=worktree).stdout.strip()
        hook_path = Path(hooks_dir)
        if not hook_path.is_absolute():
            hook_path = worktree / hook_path
        if not (hook_path / "pre-commit").exists():
            raise RuntimeError(f"worktree pre-commit missing: {hook_path / 'pre-commit'}")
        logger.log("release smoke | git worktree hook installation honored")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release smoke scenarios against local dist artifacts.")
    parser.add_argument("--version", required=True, help="Release version to install from dist/")
    parser.add_argument("--log", type=Path, default=None, help="Optional log file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version
    logger = SmokeLogger()

    wheels = sorted((ROOT / "dist").glob(f"sworncode-{version}-*.whl"))
    if not wheels:
        raise SystemExit(f"missing wheel for version {version} in dist/")
    wheel = wheels[0]

    with tempfile.TemporaryDirectory(prefix="sworn-smoke-venv-") as tmp:
        venv_root = Path(tmp)
        run([sys.executable, "-m", "venv", str(venv_root)])
        py = repo_python(venv_root)
        run([py, "-m", "pip", "install", str(wheel)])

        version_result = run([py, "-m", "sworn", "--version"])
        if version not in version_result.stdout:
            raise RuntimeError(f"installed version mismatch\n{version_result.stdout}\n{version_result.stderr}")
        logger.log(f"release smoke | installed built wheel version {version}")

        smoke_happy_path(py, logger)
        smoke_security_block(py, logger)
        smoke_missing_signing_key(py, logger)
        smoke_corrupt_evidence(py, logger)
        smoke_hooks_path(py, logger)
        smoke_worktree(py, logger)

    logger.log(f"release smoke | PASS: version {version}")
    logger.write(args.log)
    print(f"PASS: release smoke | version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
