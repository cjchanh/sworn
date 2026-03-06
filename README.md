# Sworn

**Deterministic, fail-closed AI code governance. Every commit is sworn.**

Sworn is a Python CLI that installs Git pre-commit hooks in the repository's
effective hooks path, runs a configurable gate pipeline on local commit checks
and CI diff checks, and produces tamper-evident evidence logs.

Cross-tool enforcement for any AI coding tool that commits through git.

## Governance Summary

Sworn gives teams a deterministic gate before commit that blocks risky changes and
produces auditable evidence for compliance programs.

- It solves ambiguous AI-code governance by enforcing explicit, deterministic rules.
- It guarantees fail-closed behavior on signature, hashing, and CI enforcement failures.
- It provides compliance-support reporting (CMMC-focused in 0.4.0).
- It does not certify compliance, replace a C3PAO, or provide a PKI/identity trust service.
- Engineering value: predictable commit outcomes, stronger evidence retention, and simpler policy enforcement.
- Security value: tamper-evident logs, strict fail-closed semantics, and scoped threat assumptions.
- Compliance value: explicit control mapping and explicit “support-only” interpretation.

For full threat model and scope boundaries:

- `SECURITY.md`
- `COMPLIANCE_SCOPE.md`
- `GOVERNANCE_OVERVIEW.md`
- `RELEASE_PROCESS.md`
- `docs/config.md`

## Governance Architecture

Sworn is organized across four layers:

1. Runtime Enforcement → pipeline, resolver, and kernels.
2. Evidence Integrity → canonical JSON, hash-chain, and signatures.
3. Compliance Interpretation → CMMC kernels and report mapping.
4. Release Governance → version discipline and evidence retention.

See `GOVERNANCE_OVERVIEW.md` for the full model and cross-layer bindings.

## Install

```bash
pip install sworncode
```

## Quick Start

```bash
# Initialize in any git repo
cd your-repo
sworn init

# That's it. Every commit is now gated.
# Try committing a file in a sensitive path:
mkdir -p crypto
echo "secret = 'key'" > crypto/vault.py
git add crypto/vault.py
git commit -m "test"
# → SWORN BLOCKED — Security surface: crypto/vault.py
```

## What It Does

Sworn runs a 5-stage gate pipeline during local commit checks and CI diff checks:

1. **Identity** — Detects the actor and AI tool from environment
2. **Security** — Blocks commits touching sensitive paths (configurable)
3. **Allowlist** — Enforces file access control (opt-in)
4. **Kernels** — Runs constraint kernels (built-in + custom)
5. **Evidence** — Logs everything to `.sworn/evidence.jsonl`

Every stage is deterministic. No AI in the governance loop. No network calls.
No probabilistic analysis. A gate either passes or blocks.

## Commands

```bash
sworn init              # Initialize sworn in a git repo
sworn check             # Run gate pipeline (called by pre-commit hook)
sworn report            # Show evidence summary
sworn report --json     # Machine-readable output
sworn report --cmmc     # CMMC evidence-support report
sworn status            # Show initialization and config state
sworn verify            # Verify evidence chain integrity
python -m sworn          # Run command through module entrypoint
sworn --version         # Print version
```

## Configuration

After `sworn init`, edit `.sworn/config.toml`:

```toml
[security]
# Regex patterns for sensitive paths (case-insensitive)
patterns = [
    '(^|/)(crypto|auth|gates|licensing|keys)/',
    '(^|/)secrets?/',
    '\.env$',
]

[allowlist]
# Only these glob patterns allowed (empty = all allowed)
files = []

[kernels]
# Built-in kernels
security = true
allowlist = true
audit = true

# Custom kernels
custom_dir = ".sworn/kernels"
```

## Custom Kernels

Write a Python file in `.sworn/kernels/` with an `evaluate()` function:

```python
from sworn.kernels.sdk import KernelInput, KernelResult

def evaluate(kernel_input: KernelInput) -> KernelResult:
    # Your logic here
    if some_condition:
        return KernelResult(
            decision="BLOCKED",
            triggered_rules=["my_rule"],
            evidence_summary=["Blocked because..."],
        )
    return KernelResult(decision="PASS")
```

## Evidence

Every gate run produces a JSONL entry with SHA256 hash chain:

```bash
sworn report
# SWORN EVIDENCE REPORT
# ========================================
# Total commits gated: 47
#   Passed: 43
#   Blocked: 4
#   Pass rate: 91.5%
# Chain integrity: VALID

sworn verify
# Chain: VALID
#   Chain valid: 47 entries
```

## Security Posture & Rule-2 Scope

Sworn’s evidence signing and verification layer is Security-Critical.

Rule-2 scoped behavior includes:

- `src/sworn/evidence/signing.py`
- `src/sworn/evidence/log.py`
- CLI commands in `src/sworn/cli.py` that verify evidence
- CI diff-base resolution in CI mode

This behavior is fail-closed:

- If signing is enabled and signing fails, the pipeline blocks.
- If verification fails, `sworn verify` reports `BROKEN`.
- Missing signature in signed mode is a violation.
- If base resolution fails in CI compliance mode, the check exits fail-closed.

## Deterministic Resolution Contract

Sworn resolution semantics are intentional and fixed:

1. Structural gates execute first.
2. Kernels execute after structural gates.
3. If any kernel returns `BLOCKED`, final result is `BLOCKED`.
4. Primary reason is deterministic by lexical sort of blocked kernel names.
5. All blockers are preserved in `resolution_trace`.
6. No precedence overrides exist.

This design favors clarity and auditability over configurability.

## Kernel Contract (Mandatory for Contributors)

Sworn executes kernels even when structural gates already block.

All kernels MUST:

- Be pure (no file writes, network calls, or subprocesses)
- Be side-effect free
- Tolerate partial or failed gate states
- Not depend on a prior structural `PASS`

Violation is a contract breach and a security defect.

## Evidence Signing Model

### Canonicalization

Sworn signs a deterministic canonical JSON form:

- UTF-8 encoding
- `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
- `signature=""` placeholder during canonicalization
- No trailing newline
- Stable, deterministic field ordering

Canonicalization rules are versioned. Any change increments the internal signing/evidence schema and requires compatibility handling.

### Integrity vs Trust

#### Repo-Local Integrity (Default)

This mode detects tampering after an entry is written, chain discontinuity, and key mismatch relative to repo-local keys.

It does not prove:

- Organizational authority or approval
- Identity beyond Git metadata
- Secure private-key custody

It proves repository-local tamper-evidence.

#### Org-Trust Mode (Recommended for compliance)

To elevate signing into attestation quality:

- Pin public keys via protected branches / CODEOWNERS / policy repo
- Restrict key updates with branch protections and owner controls
- Keep private keys outside the repo working tree (`KMS`, Vault, keychain, or secret manager)
- Run explicit rotation/retirement procedures

Sworn verifies signatures; it does not manage organizational assurance by itself.

## Key Layout & Migration

Current layout:

```text
.sworn/
  keys/
    active.key        # private key
    <key_id>.pub      # committed public key
```

Legacy layout:

```text
.sworn/signing.key
```

Behavior:

- If `.sworn/signing.key` exists and `.sworn/keys/active.key` does not, Sworn blocks when signing is enabled and emits actionable migration instructions.
- Sworn does not silently continue.
- Sworn does not auto-migrate without explicit user action.
- Upgrades from legacy layout require explicit migration guidance before signing is used.

## CI Enforcement (Fail-Closed)

Sworn CI mode uses `github.event.pull_request.base.sha` and fail-closes if resolution is not possible.

- If base SHA resolves, diff is computed deterministically against HEAD.
- If base SHA cannot be resolved in compliance mode, check fails with remediation guidance.
- Silent fallback is not permitted.

Workflow requirement:

```yaml
actions/checkout@v4
with:
  fetch-depth: 0
```

## CMMC Evidence Scope

Sworn’s CMMC pack provides evidence-support mappings to selected NIST SP 800-171 controls and explicitly documented determination statements.

It does not certify compliance, replace a C3PAO, or guarantee assessment outcome.

## Release Readiness Checklist

Before tagging any release:

- Clean reproducible install (`python -m pip install .[dev,signing]` in a clean environment on Python 3.10-3.13)
- Full pytest suite green
- Signing-enabled tamper detection validated
- CI base-resolution failure path validated
- Legacy key migration path validated
- Version bump consistent across package metadata and documentation
- Release evidence generated and reviewed before signed tag capture
- Working tree clean during final tag capture

## Known Residual Risks

- Repo-local signing is not equivalent to organizational attestation.
- Kernel purity is contract-enforced; runtime sandboxing is out of scope today.
- CI enforcement depends on correct workflow configuration and checkout depth.
- Migration from legacy key layouts still requires explicit user action.

## Requirements

- Python 3.10+
- Git
- Zero runtime dependencies (tomli included in stdlib from 3.11)

## License

Apache 2.0 — Centennial Defense Systems
