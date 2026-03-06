#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  local code=$?
  if command -v deactivate >/dev/null 2>&1; then
    deactivate >/dev/null 2>&1 || true
  fi
  if [[ -d "${RUNNER_VENV:-}" ]]; then
    rm -rf "$RUNNER_VENV"
  fi
  if [[ $code -ne 0 ]]; then
    echo "FAIL: phase0 aborted | phase0 | exit code $code | inspect release artifacts for partial state"
  fi
}

trap cleanup EXIT

USAGE() {
  cat <<'EOF'
Usage:
  ./scripts/release_phase0_readiness.sh [--version VERSION] [--python PYTHON_BIN]

Required:
  - Clean git working tree
  - Supported Python 3.10-3.13 available for release proof
  - Access to ~/.codex/scripts/validate_governance.py

Options:
  --version VERSION  Override release version (defaults to pyproject.toml version)
  --python PYTHON_BIN
                    Python executable to use (default: first available of python3.12, python3.13, python3.11, python3.10)
  -h, --help        Show this help
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER_BIN="${SWORN_RELEASE_PYTHON:-}"
VERSION="${SWORN_VERSION_OVERRIDE:-}"
VENV_PY=""
VENV_SWORN=""
START_SHA=""
START_STATUS=""

resolve_runner() {
  if [[ -z "$RUNNER_BIN" ]]; then
    local candidate
    for candidate in python3.12 python3.13 python3.11 python3.10; do
      if command -v "$candidate" >/dev/null 2>&1; then
        RUNNER_BIN="$candidate"
        break
      fi
    done
  fi

  if [[ -z "$RUNNER_BIN" ]]; then
    echo "FAIL: supported Python 3.10-3.13 not found | phase0 | pass --python explicitly"
    exit 1
  fi

  if [[ "$RUNNER_BIN" != */* ]]; then
    RUNNER_BIN="$(command -v "$RUNNER_BIN")"
  fi
}

validate_runner_version() {
  local version major minor
  version="$("$RUNNER_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  major="${version%%.*}"
  minor="${version##*.}"

  if [[ "$major" != "3" ]]; then
    echo "FAIL: unsupported Python major | phase0 | $RUNNER_BIN -> $version"
    exit 1
  fi

  if (( minor < 10 || minor > 13 )); then
    echo "FAIL: release proof requires Python 3.10-3.13 | phase0 | $RUNNER_BIN -> $version"
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --python)
      RUNNER_BIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      USAGE
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1 | phase0 | unrecognized CLI"
      USAGE
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT_DIR/pyproject.toml" ]]; then
  echo "FAIL: pyproject.toml missing | phase0 | no version source | $ROOT_DIR/pyproject.toml"
  exit 1
fi

if [[ -z "$VERSION" ]]; then
  VERSION="$(grep -E '^version[[:space:]]*=' "$ROOT_DIR/pyproject.toml" | head -n 1 | sed -E 's/version[[:space:]]*=[[:space:]]*["'\'']([^"'\'']+)["'\''].*/\1/')"
fi

if [[ -z "${VERSION}" ]]; then
  echo "FAIL: release version not resolved | phase0 | set --version or fix pyproject.toml"
  exit 1
fi

resolve_runner

if ! command -v "$RUNNER_BIN" >/dev/null; then
  echo "FAIL: python binary missing | phase0 | RUNNER_BIN=$RUNNER_BIN"
  exit 1
fi

if [[ ! -x "$RUNNER_BIN" ]]; then
  echo "FAIL: python not executable | phase0 | $RUNNER_BIN"
  exit 1
fi

validate_runner_version

cd "$ROOT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "FAIL: dirty working tree | phase0 | git status must be clean before release run"
  git status --short
  exit 1
fi

START_SHA="$(git rev-parse HEAD)"
START_STATUS="$(git status --short)"

if [[ ! -f "$HOME/.codex/scripts/validate_governance.py" ]]; then
  echo "FAIL: governance validation script missing | phase0 | $HOME/.codex/scripts/validate_governance.py"
  exit 1
fi

if [[ ! -f "$HOME/.codex/scripts/bootstrap_codex_governance.sh" ]]; then
  echo "FAIL: bootstrap script missing | phase0 | $HOME/.codex/scripts/bootstrap_codex_governance.sh"
  exit 1
fi

if [[ ! -f "$HOME/.codex/scripts/run_full_verification.sh" ]]; then
  echo "FAIL: full verification script missing | phase0 | $HOME/.codex/scripts/run_full_verification.sh"
  exit 1
fi

RELEASE_DIR="release-evidence/$VERSION"
mkdir -p "$RELEASE_DIR"

LOG() { echo "SOLID: $1 | $2 | $3 | $4"; }

run_step() {
  local name="$1"
  local cmd="$2"
  local out="$3"
  echo "SOLID: phase0 start | $name | $cmd"
  {
    cd "$ROOT_DIR"
    eval "$cmd"
  } | tee "$out"
}

RUNNER_VENV="$ROOT_DIR/.venv-release"
rm -rf "$RUNNER_VENV"
$RUNNER_BIN -m venv "$RUNNER_VENV"
VENV_PY="$RUNNER_VENV/bin/python"
VENV_SWORN="$RUNNER_VENV/bin/sworn"

printf '%s\n' "$START_SHA" | tee "$RELEASE_DIR/phase0-start-sha.txt"
printf '%s\n' "$START_STATUS" | tee "$RELEASE_DIR/working-tree-at-start.txt"

run_step "bootstrap env" "$VENV_PY -m pip install --upgrade pip setuptools wheel build twine" "$RELEASE_DIR/pip-bootstrap.log"
run_step "repro install" "$VENV_PY -m pip install .[dev,signing]" "$RELEASE_DIR/install.log"
run_step "cli sanity" "$VENV_SWORN --version" "$RELEASE_DIR/sworn-cli.log"
run_step "module help" "$VENV_PY -m sworn --help" "$RELEASE_DIR/sworn-module-help.txt"

run_step "tests" "$VENV_PY -m pytest tests -q --tb=short" "$RELEASE_DIR/pytest-full.log"

run_step "governance strict" "$VENV_PY ~/.codex/scripts/validate_governance.py --root . --strict" "$RELEASE_DIR/validate_governance.log"
run_step "bootstrap check" "bash ~/.codex/scripts/bootstrap_codex_governance.sh --repo-root . --check-only" "$RELEASE_DIR/bootstrap_gov.log"
run_step "full verification" "bash ~/.codex/scripts/run_full_verification.sh" "$RELEASE_DIR/full_verification.log"

run_step "python version" "$VENV_PY --version" "$RELEASE_DIR/env-version.txt"
run_step "pip freeze" "$VENV_PY -m pip freeze | sort" "$RELEASE_DIR/pip-freeze.txt"
uname -a | tee "$RELEASE_DIR/env-uname.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee "$RELEASE_DIR/build-timestamp-utc.txt"

rm -rf "$ROOT_DIR/dist"
$VENV_PY -m build --no-isolation
shasum -a 256 dist/* | sort | tee "$RELEASE_DIR/dist-shas.txt"
run_step "twine check" "$VENV_PY -m twine check dist/*" "$RELEASE_DIR/twine-check.log"

cat > "$RELEASE_DIR/MANIFEST.md" <<EOF
Sworn $VERSION Phase-0 Release Evidence Manifest

Manifest Type: Phase-0 pre-tag evidence
Release Tag: pending phase1
Tag SHA: pending phase1
PyPI Publish Ref: pending phase1
Build Date (UTC): $(cat "$RELEASE_DIR/build-timestamp-utc.txt")
Maintainer: pending phase1
Phase-0 Start Commit: $(cat "$RELEASE_DIR/phase0-start-sha.txt")
Phase-0 Branch: $(git rev-parse --abbrev-ref HEAD)

Evidence Artifacts
- install.log
- pytest-full.log
- validate_governance.log
- bootstrap_gov.log
- full_verification.log
- pip-bootstrap.log
- sworn-cli.log
- sworn-module-help.txt
- env-version.txt
- env-uname.txt
- pip-freeze.txt
- phase0-start-sha.txt
- working-tree-at-start.txt
- build-timestamp-utc.txt
- dist-shas.txt
- twine-check.log
- evidence-package.tar.gz
- evidence-package.sha256

Assertions
- Tests passed in clean venv
- Signing available under [dev,signing] release proof and CLI invocation succeeded
- Governance checks passed via validate_governance.py --root . --strict
- Bootstrap and full verification checks passed
- Canonicalization and hash-chain behavior unchanged from tagged baseline
- CI fail-closed semantics unchanged
- Compliance scope bound to code version in this release
- Release evidence requires review and commit before any signed tag or publish step
- Signed tag and publish identity must be recorded during phase1 outside the committed phase0 snapshot
EOF

TMP_EVIDENCE_PACKAGE="$(mktemp /tmp/sworn-evidence-package.XXXXXX)"
rm -f "$TMP_EVIDENCE_PACKAGE"
TMP_EVIDENCE_PACKAGE="${TMP_EVIDENCE_PACKAGE}.tar.gz"

tar -czf "$TMP_EVIDENCE_PACKAGE" \
  -C "$ROOT_DIR" \
  "release-evidence/$VERSION" \
  pyproject.toml src/sworn/__init__.py SECURITY.md COMPLIANCE_SCOPE.md RELEASE_PROCESS.md GOVERNANCE_OVERVIEW.md README.md
mv "$TMP_EVIDENCE_PACKAGE" "$RELEASE_DIR/evidence-package.tar.gz"
shasum -a 256 "$RELEASE_DIR/evidence-package.tar.gz" | tee "$RELEASE_DIR/evidence-package.sha256"

echo "SOLID: phase0 complete | release evidence captured | $VERSION | commit release-evidence/$VERSION before tagging"
