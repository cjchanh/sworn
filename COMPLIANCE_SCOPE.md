# COMPLIANCE_SCOPE.md

## Scope Statement

Sworn provides evidence support tooling for selected governance controls in regulated development environments.

Sworn does not certify compliance.

Sworn does not guarantee assessment outcomes.

Sworn produces structured, tamper-evident evidence artifacts that may support compliance programs.

## Control Coverage Model

Sworn’s CMMC pack maps kernel outputs to selected NIST SP 800-171 practices.

Coverage categories:

- Enforced – Sworn deterministically enforces behavior at runtime.
- Detective – Sworn detects violations but does not prevent them.
- Evidence-Only – Sworn records artifacts relevant to assessment but does not enforce policy.
- Out of Scope – Sworn does not address this requirement.

## Current CMMC Coverage (Sworn version 0.3.0)

| Control | Category | Enforcement Surface | Evidence Artifact | Limitations |
| --- | --- | --- | --- | --- |
| AC.L2-3.1.1 | Detective | Identity gate + cmmc AC kernel | Evidence log entry (`actor`, `tool`, `decision`) | Does not block unresolved actor; relies on git metadata accuracy |
| AC.L2-3.1.2 | Evidence-Only | Tool detection note in cmmc AC kernel | Evidence log entry (`tool`) + cmmc report summary | No scope-validation gate; no org-level IAM enforcement |
| AU.L2-3.3.1 | Enforced | Evidence log + hash chain (`sworn verify`) | Evidence log entry + chain continuity proofs | Repo-local integrity only |
| AU.L2-3.3.2 | Evidence-Only | Resolution trace assembly | Resolution trace in evidence entry | Does not validate review quality |
| CM.L2-3.4.1 | Detective | Config presence gate checks | Gate result in evidence log | Does not validate config quality |
| CM.L2-3.4.2 | Enforced | Security gate + cmmc CM kernel | Evidence log entry + blocking reason | Depends on correct config |
| CM.L2-3.4.5 | Enforced | Allowlist/security pattern kernels | Evidence log entry + trace evidence | No runtime file-system sandbox |
| SC.L2-3.13.1 | Detective | Boundary-pattern kernel evaluation | Evidence log entry + cmmc report summary | Pattern-based, not semantic |
| SI.L2-3.14.1 | Evidence-Only | Governance execution trace | Evidence log `resolution_trace` + `sworn report --cmmc` summary | Does not guarantee remediation |

## Determination Statement Boundaries

Sworn:

- Produces artifacts usable during assessment.
- Demonstrates enforcement logic execution.
- Demonstrates tamper-evident logging.

Sworn does NOT:

- Validate organizational policy adequacy.
- Prove identity assurance beyond git actor metadata.
- Prove separation of duties.
- Prove key custody governance.
- Prove secure SDLC outside commit governance surface.

## Auditor Interpretation Guardrails

Sworn evidence supports:

- “Show me how AI-assisted commits are gated.”
- “Show me tamper-evident logging.”
- “Show me CI enforcement behavior.”

Sworn evidence does not support:

- “Prove your organization enforces least privilege IAM.”
- “Prove your key management program.”
- “Prove workstation integrity.”

Sworn does not claim that enforcement equals organizational policy adequacy.
Enforcement signals demonstrate technical gating behavior, not policy sufficiency.

## Trust Model Reminder

Repo-local signing ≠ organizational attestation.

Org-trust mode requires:

- Protected branches
- Key pinning
- External custody controls
- Role-based governance

Sworn verifies what exists; it does not create a PKI.

## Known Residual Compliance Gaps

- No built-in identity federation validation
- No enforced key rotation policy
- No runtime isolation for kernels
- No centralized org policy enforcement in 0.x
- CI enforcement depends on workflow correctness

## Versioning

This document reflects Sworn version 0.3.0 exactly.
Any deviation between tagged release behavior and this document is a defect.

Changes to kernel behavior, signing semantics, or CI enforcement require updating this scope document.

## Normative Alignment

This document is the normative source for compliance scope interpretation.

The following must remain aligned:

- `src/sworn/kernels/cmmc/`
- `src/sworn/evidence/cmmc_report.py`
- `README.md`
- `SECURITY.md`

If kernel behavior changes, this document must be updated in the same commit.

Compliance interpretation is bound to the version tag associated with this document.

## Why This Document Matters

Without this document:

- Assessors may over-infer guarantees.
- Sales discussions become ambiguous.
- Scope creep becomes inevitable.

With it:

- You control interpretation.
- You define support boundaries.
- You prevent accidental compliance claims.

## References and Separation

- `README.md` → Behavioral overview
- `SECURITY.md` → Threat model + trust boundary
- `COMPLIANCE_SCOPE.md` → Regulatory coverage precision

This triad is intentionally explicit about intent and boundaries.
