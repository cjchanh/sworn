# Security Policy

## Reporting a Vulnerability

Report security issues privately through **GitHub Security Advisories**:

<https://github.com/cjchanh/sworn/security/advisories/new>

Please do not open a public issue for a security report, and do not disclose the
issue publicly until a fix is available.

Include where you can:

- Affected version (`sworn --version`) and Python version
- The relevant `.sworn/config.toml` (redact keys and private paths)
- Reproduction steps, ideally a minimal repository
- Observed behavior versus expected fail-closed behavior

Sworn is maintained by a single maintainer. Acknowledgement is best-effort; no
response-time or fix-time commitment is made here, because a commitment that is
not met is worse than none. Reports that demonstrate a **fail-open** path — any
input that produces `PASS` or exit `0` where the documented behavior is a block —
are triaged ahead of everything else.

There is no bug bounty.

## Supported Versions

| Version | Supported |
|---|---|
| 0.4.x | Yes |
| 0.3.x | No |
| < 0.3 | No |

Only the latest released minor version receives security fixes. Fixes are
delivered as a new release; patches are not backported to earlier minors.

Note that the `main` branch may be ahead of the latest tag. Verify what you are
running with `sworn --version` and `git describe --tags` before reporting; a
behavior on `main` may not exist in the released artifact, and vice versa.

## Known Boundaries

Sworn's enforcement has documented limits. They are tracked, with
file-and-line evidence and reproduction commands, in
[`docs/KNOWN_BOUNDARIES.md`](docs/KNOWN_BOUNDARIES.md).

Two are load-bearing for anyone deploying Sworn as a control:

- **Local `pre-commit` hooks are bypassable** (`git commit --no-verify`).
  Enforcement requires the CI gate as a required status check.
- **Fail-closed CI diff resolution is gated on `SWORN_CI=1`.** Without it, an
  unresolvable diff base prints `SWORN PASS` and exits `0`.

Read that document before treating a Sworn `PASS` as an assurance claim.

## Scope

**In scope** — reports against these are security reports:

- Any path that yields `PASS` or exit `0` where a block is documented
- Evidence log tampering that verification does not detect
- Signature verification accepting an invalid or mismatched signature
- Hash-chain discontinuity that `sworn verify` reports as `VALID`
- CI diff-base resolution failures that do not fail closed **with `SWORN_CI=1`
  set**
- Private key material written to a location Sworn reports as safe
- Kernel loader behavior that bypasses the fail-closed import path

**Out of scope** — real, but already documented above and in
`docs/KNOWN_BOUNDARIES.md`, so they are not new findings:

- `git commit --no-verify`, hook removal, or `core.hooksPath` redirection
- Arbitrary code execution via a custom kernel the repository already trusts
- A spoofed `git config user.name` being recorded as actor
- `sworn ci-check` not failing closed when `SWORN_CI=1` is **not** set
- `sworn report` exiting `0` on an empty or broken log
- Theft of a private signing key, or compromise of the workstation or CI host
- Absence of PKI, org identity, or C3PAO certification

If you believe one of the out-of-scope items is exploitable in a way the
boundaries document does not describe, that difference is in scope. Report it.

## Security Model Overview

Sworn enforces deterministic, fail-closed governance over AI-assisted code changes.

Security-sensitive surfaces include:

- Evidence signing and verification
- Hash-chain integrity enforcement
- CI diff-base resolution
- Kernel execution semantics
- Key material handling

Changes to these areas are treated as Rule-2 scope.

## Security Objectives

Sworn’s non-negotiable security invariants:

1. Deterministic governance decisions (no nondeterministic pass/fail outcomes).
2. Tamper-evident evidence logging and verification.
3. Fail-closed behavior in signing and CI enforcement.
4. No silent downgrade of enforcement behavior.

Violations of these objectives are release blockers.

## Trust Assumptions

Sworn operates under the following assumptions:

- The repository host enforces branch protection and reviewer controls as configured.
- CI secrets are protected by the CI provider and repository policy.
- Private signing keys are protected outside repository working trees when org-trust posture is claimed.
- Kernel implementations conform to documented purity and determinism constraints.

Violation of these assumptions reduces assurance guarantees and shifts findings into out-of-model risk.

## Threat Model

### Assets

- Evidence log integrity
- Signature authenticity
- Governance decision determinism
- CI enforcement surface

### Adversary Capabilities Considered

1. Modifies evidence log after commit
2. Strips or tampers with signatures
3. Replays or reorders entries
4. Attempts to bypass pre-commit with `--no-verify`
5. Attempts to exploit CI shallow clone behavior
6. Attempts to exploit nondeterministic kernel ordering
7. Attempts to introduce override-based precedence bypass

### Adversary Capabilities NOT Covered

1. Theft of private signing key
2. Compromise of developer workstation
3. Compromise of CI secrets
4. Malicious kernel implementation
5. Git history rewriting outside Sworn detection surface

Sworn detects integrity violations. It does not defend against host compromise.

Item 4 above is expanded in [`docs/KNOWN_BOUNDARIES.md`](docs/KNOWN_BOUNDARIES.md)
B-6. Note also that capability 4 in *Adversary Capabilities Considered*
(`--no-verify` bypass) is **accounted for, not prevented** — the design response
is the CI gate, not a local defense. See B-1 in the same document.

## Integrity Guarantees

### Hash Chain

- Each entry includes `prev_hash`.
- Chain discontinuity invalidates verification.

### Signature

- Ed25519 signatures over canonical JSON.
- Canonicalization:
  - UTF-8
  - `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
  - `signature=""` placeholder
- Verification fails closed on mismatch.

## CI Enforcement Model

In CI mode:

- Base SHA must be provided.
- If diff base cannot be resolved, Sworn fails.
- Silent fallback is not permitted.
- Requires `fetch-depth: 0`.

CI misconfiguration results in block, not bypass.

## Kernel Execution Model

Kernels:

- Execute even if structural gates block.
- Must be pure and side-effect free.
- Must tolerate partial pipeline state.
- Must not mutate repository state.

Violations are security defects.

## Key Management

### Default

- Private key: `.sworn/keys/active.key` (gitignored)
- Public keys: `.sworn/keys/*.pub` (committed)

### Migration

Legacy `.sworn/signing.key` layout blocks signed mode until explicitly migrated.

No silent auto-migration occurs.

## Trust Model

Sworn supports two trust postures:

### Repo-Local Integrity

- Detects tampering relative to stored public keys.
- Does not prove organizational authority.

### Org-Trust Mode

Requires:

- Public key pinning
- Protected branch enforcement
- External private-key custody controls
- Explicit rotation policy

Sworn verifies signatures. It does not provide a PKI.

## Non-Goals

Sworn does not:

- Certify CMMC or SOC 2 compliance
- Replace a C3PAO
- Prevent private key theft
- Prevent workstation compromise
- Enforce org-level identity governance
- Provide sandbox isolation for kernels

## Security Severity Classification

Security-Critical (Rule-2):

- Signing canonicalization changes
- Hash-chain structure or verification behavior changes
- Resolver block-semantics changes (including ordering and precedence)
- CI fail-closed enforcement changes
- Kernel behavior changes that alter blocking guarantees

Security-Critical changes require:

- Explicit review
- Required test coverage
- Classification and release handling in `RELEASE_PROCESS.md`

All other changes are non-security-critical by default and follow normal development workflow.

## Requirements for Security-Sensitive Changes

Contributions touching the surfaces listed above must:

- Include test coverage, including a test that the gate **blocks**, not only
  that it returns a result
- Preserve fail-closed semantics on every path
- Maintain canonicalization stability
- Avoid introducing override logic in the resolver

To report a vulnerability, see [Reporting a Vulnerability](#reporting-a-vulnerability).

## What This Document Is For

`README.md` explains what Sworn does.

This file states what Sworn defends against, what it explicitly does not defend
against, where the trust boundaries sit, and which assumptions an auditor should
not make. [`docs/KNOWN_BOUNDARIES.md`](docs/KNOWN_BOUNDARIES.md) carries the
evidence for the second of those, with file-and-line citations and reproduction
commands.

A `PASS` from Sworn is a statement about the checks that ran. It is not a
statement about the checks that were disabled, bypassed, or never reached.
