# RELEASE_PROCESS.md

## Purpose

This document defines the mandatory release workflow for Sworn and binds release claims
to code, security posture, and compliance-scope documentation.

It is intended to prevent scope drift, release ambiguity, and false compliance assertions.

## Scope

Applies to all tagged releases and patch releases in the `sworn` repository.

## Release Authority & Review Model

For Sworn 0.x, release approval authority is:

- Maintainer of record: project owner or delegated release lead for the release cycle.
- Final release decision: maintainer of record.

Decision rules:

- Rule-2 (security-critical) changes require explicit review of:
  - signing
  - CI enforcement
  - resolver
  - kernel logic
  - alignment check against `SECURITY.md` and `COMPLIANCE_SCOPE.md`
- Compliance-affecting changes require documented scope review before tagging.
- Cosmetic and pure test-only changes may be self-approved in a single-owner context.

For multi-maintainer governance, upgrade path is:

- Rule-2 changes: at least two approvers with one designated compliance/security approver.
- Compliance-affecting changes: documented approval from a designated compliance reviewer.
- Any dissent in this process blocks release tagging.

Absence of this approval model for a given change type is a governance defect.

## Action Classification

Each release action is classified by impact:

- Security-critical: Rule-2 surfaces and signature/integrity/CI enforcement behavior
- Compliance-affecting: behavior that changes evidence or compliance interpretation
- Behavioral: functional changes that do not alter documented control claims
- Cosmetic: wording, formatting, and non-functional documentation edits

## Required Normative Alignment

Before release, these artifacts must be internally consistent and version-aligned:

- `pyproject.toml`
- `src/sworn/__init__.py`
- `src/sworn/config.py` (schema expectations as implemented)
- `README.md`
- `SECURITY.md`
- `COMPLIANCE_SCOPE.md`

The release version is authoritative and must match across package metadata and executable
version reporting.

Any mismatch is a release blocker.

## Version Discipline

1. Update version fields before tagging:
   - `pyproject.toml` → project version
   - `src/sworn/__init__.py` → `__version__`
2. Update compliance scope for behavioral deltas in the same commit:
   - kernel behavior changes
   - signing canonicalization semantics
   - CI enforcement semantics
   - threat/guardrail policy changes
3. Ensure `COMPLIANCE_SCOPE.md` and `SECURITY.md` are consistent with shipped behavior.

## Semantic Versioning Discipline

- Patch (`x.y.Z`) releases must not change enforcement semantics or compliance interpretation.
- Minor (`x.Y.z`) releases may add kernels or enforcement surfaces and must update
  `COMPLIANCE_SCOPE.md` in the same commit as the behavior change.
- Major (`X.y.z`) releases may change canonicalization, resolver semantics, or signing contracts
  and must include explicit migration guidance and compatibility constraints.

## Change Classification Matrix

All changes must be classified before release planning and sign-off.

| Change Type | Classification | Examples | Compliance Scope Update Required | Security Review Required |
| --- | --- | --- | --- | --- |
| Documentation-only | Cosmetic | README clarifications, typo fixes | No, unless claim language changes | No |
| Kernel logic change | Compliance-affecting | Evaluation rule changes, return-condition changes, new/removed blockers in `src/sworn/kernels/` | Yes | Yes |
| Signing change | Security-critical / Compliance-affecting | Canonicalization changes, signature payload changes, verification policy changes in `src/sworn/evidence/` | Yes | Yes (Rule-2) |
| CI enforcement change | Security-critical / Compliance-affecting | Base SHA resolution, fallback rules, failure modes in CI mode | Yes | Yes (Rule-2) |
| Resolver logic change | Compliance-affecting | Precedence edits, block aggregation order, primary blocker selection in `src/sworn/resolver.py` | Yes | Yes |
| Test-only change | Behavioral | Added/updated tests with no behavior change | No | No |
| Dependency update | Behavioral/Cosmetic | Library version bump | Yes only if surface impacts security/signing/CI behavior | Yes if security-sensitive surface affected |

Definition guidance:

- Kernel behavior change = any change to `KernelResult` generation, gate conditions, blocker semantics, or side-effect assumptions.
- CI enforcement change = any change affecting whether checks run, how diff scope is computed, or fail-closed outcomes.
- Signing canonicalization delta = any change to canonical JSON creation, signature input, hash-chain fields, or key-selection logic.

## Release Gate (Must all pass)

1. Working tree clean
   - No staged or unstaged local changes are allowed during final tag capture.
2. Reproducible install proof
   - Validate fresh install in a clean Python environment:
     - Use an explicitly selected supported interpreter (`python3.10`-`python3.13`).
     - `python -m venv .venv-release`
     - `source .venv-release/bin/activate`
     - `python -m pip install --upgrade pip setuptools wheel build twine`
     - `python -m pip install .[dev,signing]`
     - `python -m pytest tests -q --tb=short`
   - Confirm CLI and module entrypoint are available:
     - `sworn --version`
     - `python -m sworn --help`
3. Governance checks
   - `python3 ~/.codex/scripts/validate_governance.py --strict`
   - `bash ~/.codex/scripts/bootstrap_codex_governance.sh --repo-root . --check-only`
   - `bash ~/.codex/scripts/run_full_verification.sh`
4. Test + verification
   - `PYTHONPATH=src python3 -m pytest tests -q --tb=short`
   - All tests relevant to changed surfaces pass (Rule-2 and CI paths inclusive).
5. Compliance scope integrity checks
   - `COMPLIANCE_SCOPE.md` reflects exact tagged release behavior.
   - No placeholder language remains in compliance-facing claims.
   - Drift from docs to implementation is reviewed and closed.

Failure of any item blocks tagging.

## Release Phases

Sworn release flow is intentionally split:

### Phase 0 — Evidence generation

- Run `./scripts/release_phase0_readiness.sh --version <version>` from a clean tree.
- Review generated `release-evidence/<version>/`.
- Commit release evidence and any release-contract updates before tag capture.
- Treat the phase-0 manifest as a pre-tag snapshot. It records the starting commit and branch, not the future signed tag object.

### Phase 1 — Tag and publish

- Start from the committed Phase-0 state with a clean working tree.
- Create the signed tag for the exact commit that already contains release evidence.
- Publish the package and record the signed tag identity plus publish reference in release notes or an external operator log.
- If a portable release bundle is required, rebuild or annotate it after phase1 so it reflects the final signed tag metadata.

Combining evidence generation and tag capture in one dirty working tree is prohibited.

## Release Readiness Checklist

- [ ] Version bump completed in code and package metadata.
- [ ] Documentation triad is aligned:
  - `README.md`
  - `SECURITY.md`
  - `COMPLIANCE_SCOPE.md`
- [ ] Reproducible install pass in clean environment.
- [ ] Governance scripts pass in strict mode.
- [ ] Full test suite pass (no regressions in touched scope).
- [ ] CI fail-closed behavior verified (base SHA missing path handled as BLOCK).
- [ ] Signed-mode migration behavior tested (legacy layout path rejection).
- [ ] Key material handling behavior validated.
- [ ] Signed tag and release notes prepared with scope caveats.

## Release Evidence Capture (Mandatory)

For every tagged release, capture and retain artifacts in an auditable location:

- `.github/workflows/`-independent default path: `release-evidence/<tag>/`
- Tag value used in artifact path names (for example: `release-evidence/0.3.0/`)

Capture at minimum:

- Pytest output:
  - `PYTHONPATH=src python3 -m pytest tests -q --tb=short | tee release-evidence/<tag>/pytest-full.log`
- Governance outputs:
  - `python3 ~/.codex/scripts/validate_governance.py --root . --strict | tee release-evidence/<tag>/validate_governance.log`
  - `bash ~/.codex/scripts/bootstrap_codex_governance.sh --repo-root . --check-only | tee release-evidence/<tag>/bootstrap_gov.log`
  - `bash ~/.codex/scripts/run_full_verification.sh | tee release-evidence/<tag>/full_verification.log`
- Environment fingerprint:
  - `python --version | tee release-evidence/<tag>/env-version.txt`
  - `uname -a | tee release-evidence/<tag>/env-uname.txt`
  - `pip freeze | sort | tee release-evidence/<tag>/pip-freeze.txt`
- Reproducible install record:
  - `python -m pip install .[dev,signing]` log in `release-evidence/<tag>/install.log`
  - `sworn --version | tee release-evidence/<tag>/sworn-cli.log`
  - `python -m sworn --help | tee release-evidence/<tag>/sworn-module-help.txt`
- VCS context:
  - `git rev-parse HEAD | tee release-evidence/<tag>/phase0-start-sha.txt`
  - `git status --short | tee release-evidence/<tag>/working-tree-at-start.txt`
- Release identity:
  - Signed tag reference, tag object SHA, and publish reference stored in release notes or external operator log after Phase 0 evidence is committed
- Artifact integrity:
  - Build artifacts with `python -m build --no-isolation` and store `sha256` manifest at `release-evidence/<tag>/dist-shas.txt`

Absence of these artifacts is an incomplete release and blocks final sign-off.

## Evidence Retention Integrity

Release artifacts must be immutable after tag publication.

Acceptable retention models:

- Committed prior to tagging in the repository under `release-evidence/<tag>/`.
- Attached to a signed GitHub Release asset bundle.
- Stored in an external audit repository with an accompanying SHA-256 manifest.

Evidence artifacts must be:

- Stored in a non-ephemeral location.
- Associated with the exact signed release tag.
- Recorded with integrity hashes.
- Committed before tag capture when the in-repo retention model is used.

For the in-repo model, the committed phase-0 bundle is the pre-tag evidence snapshot.
The exact signed-tag identity is finalized in release notes or an external operator log during phase1.

Modifying artifacts after tag publication invalidates the release record and requires
corrective re-release.

## Drift Escalation

If post-release review finds drift between any of the following:

- Implementation and `COMPLIANCE_SCOPE.md`
- Signing behavior and `SECURITY.md`
- CI enforcement code and documented fail-closed guarantees
- Version strings and documented release scope

Then:

1. Mark the release as defective.
2. Halt further distribution under the current tag.
3. Issue a corrective patch or revoke and re-issue under corrected version/tag discipline.
4. Update affected documentation in the same release cycle.

Compliance claims remain invalid until corrected evidence and documentation are present.

## Signing and Attestation Path

- Default mode remains repo-local integrity mode.
- Do not present repo-local signing as organizational attestation.
- Any future claims of org-trust posture require explicit evidence of:
  - key pinning controls
  - key custody separation
  - branch-protection enforcement
  - role-based signing policy

## Post-Release Controls

- Keep compliance artifacts under review for any security-sensitive change.
- Any signed behavior or kernel behavior change requires a follow-up compliance-scope update
  in the next release commit.
- If behavior changes without a compliant documentation update, release is considered defective
  and requires immediate remediation.

## Exception handling

If any required gate fails:
- Do not proceed with tag creation.
- Fix root cause.
- Re-run affected gates.
- Record rationale in release notes before unblocking.

Release process failures are non-compliance findings until fully resolved.
