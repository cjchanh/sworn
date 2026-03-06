# GOVERNANCE_OVERVIEW.md

## Purpose

This document unifies Sworn’s governance model into a single interpretation layer.

It connects implementation behavior, trust assumptions, compliance interpretation, and release control into one map.

## Governance Layers

Sworn operates across four layers.

### 1) Runtime Enforcement Layer

Defines what Sworn blocks and allows during execution.

Defined by:

- `src/sworn/pipeline.py`
- `src/sworn/resolver.py`
- `src/sworn/kernels/` and `src/sworn/kernels/cmmc/`

Guarantees:

- Deterministic resolution ordering
- No precedence override configuration
- Fail-closed enforcement when gates are enabled
- Kernel outcomes are represented in `resolution_trace`; structural gate outcomes are recorded separately in `gates`

Bound by:

- `README.md` (behavior contract)

### 2) Evidence Integrity Layer

Defines tamper-evident evidence and verification behavior.

Defined by:

- `src/sworn/evidence/log.py`
- `src/sworn/evidence/signing.py`
- `src/sworn/cli.py` verification commands

Guarantees:

- Canonical JSON signing input is stable per documented serialization rules
- Signature and hash-chain continuity checks are enforced in verification
- Verification failures are treated as broken state
- Missing or invalid signatures in signed mode are treated as failures

Bound by:

- `SECURITY.md` (threat model, trust boundary, non-goals)

### 3) Compliance Interpretation Layer

Defines what Sworn claims for regulatory support.

Defined by:

- `src/sworn/kernels/cmmc/`
- `src/sworn/evidence/cmmc_report.py`

Guarantees:

- Explicit support-only posture for CMMC-related claims
- Control-to-artifact mapping is documented
- Compliance claims are bounded by documented artifact evidence and limitations
- Repo-local integrity is distinguished from organizational attestation

Bound by:

- `COMPLIANCE_SCOPE.md` (control mapping and interpretation boundaries)

### 4) Release Governance Layer

Defines when and how changes can be released.

Defined by:

- `RELEASE_PROCESS.md`

Guarantees:

- Change classification and review model
- Version discipline and semantic constraints
- Required evidence capture and retention model
- Drift escalation and corrective re-release path

## Layer Alignment (Cross-Layer Binding)

- Runtime behavior changes must remain aligned with both `README.md` and `COMPLIANCE_SCOPE.md`.
- Security-sensitive and compliance-sensitive changes must pass Rule-2 review requirements in `RELEASE_PROCESS.md`.
- Evidence integrity and signing behavior must remain aligned between code, `SECURITY.md`, and release evidence package.
- Release claims are valid only when all three dimensions are aligned:
  - Runtime behavior
  - Evidence integrity
  - Compliance interpretation

## Trust Boundary Summary

Sworn provides:

- Deterministic pipeline enforcement
- Tamper-evident evidence generation
- Compliance-support artifact output

Sworn does not provide:

- Organizational identity assurance beyond git metadata
- Key custody assurance
- Host/workstation compromise defense
- CMMC/SOC certifications or assessment outcomes

## Compliance Boundary

Scope is evidence-support only.

- It can support control assessment workflows.
- It cannot replace a C3PAO or organizational policy program.
- It does not certify adequacy of external IAM, training, governance maturity, or secure SDLC outside Sworn’s commit surface.

## Release Boundary

Release validity is governed by `RELEASE_PROCESS.md`.

- Any change touching enforcement, integrity, or compliance semantics requires release-classified review.
- Release is blocked on missing gates, failed checks, or unresolved doc/code drift.
- Evidence artifacts must be retained with immutable association to a release tag.

## Version Boundary

- Compliance interpretation and governance semantics are version-bound.
- Each tagged release is interpreted against:
  - `README.md`
  - `SECURITY.md`
  - `COMPLIANCE_SCOPE.md`
  - `RELEASE_PROCESS.md`
- Drift against these files is a release defect and requires correction before the claim remains valid.

## Interpretation Contract

For any assertion about Sworn:

1. Read runtime enforcement from `README.md`.
2. Read security assumptions from `SECURITY.md`.
3. Read compliance support boundaries from `COMPLIANCE_SCOPE.md`.
4. Read release validity from `RELEASE_PROCESS.md`.
5. Use these four documents together; do not infer claims from any single source.
