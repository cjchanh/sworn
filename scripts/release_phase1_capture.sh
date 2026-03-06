#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/release_phase1_capture.sh --version VERSION --maintainer NAME --pypi-url URL [--tag TAG] [--out PATH]

Emits a phase-1 release identity record for use in signed release notes or an external operator log.

Required:
  --version VERSION     Release version, e.g. 0.4.0
  --maintainer NAME     Maintainer or release operator identity
  --pypi-url URL        Published PyPI release URL

Optional:
  --tag TAG             Tag name (defaults to VERSION)
  --out PATH            Write markdown to PATH instead of stdout
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=""
TAG=""
MAINTAINER=""
PYPI_URL=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --maintainer)
      MAINTAINER="${2:-}"
      shift 2
      ;;
    --pypi-url)
      PYPI_URL="${2:-}"
      shift 2
      ;;
    --out)
      OUT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1 | phase1 | capture"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$VERSION" || -z "$MAINTAINER" || -z "$PYPI_URL" ]]; then
  echo "FAIL: missing required arguments | phase1 | version, maintainer, and pypi-url are required"
  usage
  exit 1
fi

if [[ -z "$TAG" ]]; then
  TAG="$VERSION"
fi

cd "$ROOT_DIR"

RELEASE_DIR="release-evidence/$VERSION"
if [[ ! -d "$RELEASE_DIR" ]]; then
  echo "FAIL: release evidence missing | phase1 | $RELEASE_DIR"
  exit 1
fi

if [[ ! -f "$RELEASE_DIR/phase0-start-sha.txt" ]]; then
  echo "FAIL: phase0-start-sha.txt missing | phase1 | $RELEASE_DIR/phase0-start-sha.txt"
  exit 1
fi

if ! git rev-parse --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "FAIL: tag missing | phase1 | refs/tags/$TAG"
  exit 1
fi

TAG_OBJECT_SHA="$(git rev-parse "$TAG^{tag}" 2>/dev/null || git rev-parse "$TAG")"
TAGGED_COMMIT_SHA="$(git rev-list -n 1 "$TAG")"
PHASE0_START_SHA="$(cat "$RELEASE_DIR/phase0-start-sha.txt")"
GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

render() {
  cat <<EOF
# Sworn $VERSION Phase-1 Release Identity

Release Tag: $TAG
Tag Object SHA: $TAG_OBJECT_SHA
Tagged Commit SHA: $TAGGED_COMMIT_SHA
Phase-0 Start Commit: $PHASE0_START_SHA
Maintainer: $MAINTAINER
PyPI Release: $PYPI_URL
Generated At (UTC): $GENERATED_AT

## Artifact References

- Phase-0 evidence directory: $RELEASE_DIR
- Dist hashes: $RELEASE_DIR/dist-shas.txt

## Notes

- This record is for signed release notes or an external operator log.
- Do not modify the committed phase-0 evidence directory after tag publication.
EOF
}

if [[ -n "$OUT" ]]; then
  mkdir -p "$(dirname "$OUT")"
  render > "$OUT"
else
  render
fi
