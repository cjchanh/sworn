# Sworn — Agent Operating Policy

## Purpose
Deterministic, fail-closed AI code governance for git-based engineering workflows.

## Invariants
- Release claims MUST match shipped package metadata, tags, and release evidence.
- Governance gates MUST fail closed on signing, CI diff resolution, and bootstrap drift.
- Compliance language MUST remain support-only and MUST NOT overstate attestation or certification.
- Release evidence MUST be captured before any external exposure step.

## Allowed Commands
- `PYTHONPATH=src python3 -m pytest tests -q --tb=short` — local source verification
- `python3 ~/.codex/scripts/validate_governance.py --root . --json --strict` — repo governance gate
- `bash ~/.codex/scripts/bootstrap_codex_governance.sh --repo-root . --check-only` — bootstrap gate
- `bash ~/.codex/scripts/run_full_verification.sh` — full verification chain
- `python3 -m build --sdist --wheel --no-isolation --outdir /tmp/sworn-buildcheck` — packaging check
- `./scripts/release_phase0_readiness.sh --version <version>` — release evidence generation

## Evidence Location
- `release-evidence/<tag>/` — release readiness logs and manifests
- `.sworn/evidence.jsonl` — runtime tamper-evident evidence chain
- `tests/` — behavior proof for gates, kernels, CI, signing, and reports

## Governance
- Repo-local `AGENTS.md` is required for strict bootstrap pass.
- Phase 0 generates release evidence only; tagging and publish happen after that evidence is reviewed and committed.
- Do not publish or market Sworn from a state where PyPI, git tags, and local version metadata disagree.
