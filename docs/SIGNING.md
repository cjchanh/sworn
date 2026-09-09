# Evidence signing model

Threat-model and signing detail moved here from the README so the first
screen stays a product page. Enforcement limits: `KNOWN_BOUNDARIES.md`.

## Fail-closed signing layer

These paths are security-critical:

- `src/sworn/evidence/signing.py`
- `src/sworn/evidence/log.py`
- CLI commands in `src/sworn/cli.py` that verify evidence
- CI diff-base resolution in CI mode

Behavior:

- If signing is enabled and signing fails, the pipeline blocks.
- If verification fails, `sworn verify` reports `BROKEN`.
- Missing signature in signed mode is a violation.
- If base resolution fails in CI, the check exits fail-closed.

## Canonicalization

Sworn signs a deterministic canonical JSON form:

- UTF-8 encoding
- `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
- `signature=""` placeholder during canonicalization
- No trailing newline
- Stable, deterministic field ordering

Canonicalization rules are versioned. Any change increments the internal
signing/evidence schema and requires compatibility handling.

## Integrity vs trust

### Repo-local integrity (default)

This mode detects tampering after an entry is written, chain discontinuity,
and key mismatch relative to repo-local keys.

It does not prove:

- Organizational authority or approval
- Identity beyond Git metadata
- Secure private-key custody
- Truncation of the evidence log tail (see `KNOWN_BOUNDARIES.md` B-11)

It proves repository-local tamper-evidence only.

### Org-trust mode

To treat signatures as attestation-quality:

- Pin public keys outside the protected repo (separate policy repo, KMS, or
  a verifier-supplied `--` equivalent: an out-of-band expected public key)
- Restrict key updates with branch protections and owner controls
- Keep private keys outside the repo working tree (KMS, Vault, keychain, or
  secret manager)
- Run explicit rotation/retirement procedures

Sworn verifies signatures against keys it is given. It does not manage
organizational assurance by itself. A public key committed under
`.sworn/keys/` is under the same write authority as the log it protects.

## Key layout and migration

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

- If `.sworn/signing.key` exists and `.sworn/keys/active.key` does not,
  Sworn blocks when signing is enabled and emits migration instructions.
- Sworn does not silently continue.
- Sworn does not auto-migrate without explicit user action.

## Resolution contract

1. Structural gates execute first.
2. Kernels execute after structural gates.
3. If any kernel returns `BLOCKED`, final result is `BLOCKED`.
4. Primary reason is deterministic by lexical sort of blocked kernel names.
5. All blockers are preserved in `resolution_trace`.
6. No precedence overrides exist.

Kernels must be pure (no file writes, network calls, or subprocesses),
side-effect free, and tolerant of a prior structural block. Purity is a
contract, not a sandbox (`KNOWN_BOUNDARIES.md` B-6).

## CI enforcement

Sworn CI mode uses `github.event.pull_request.base.sha` and fail-closes if
resolution is not possible. Workflow requirement:

```yaml
actions/checkout@v4
with:
  fetch-depth: 0
```

See `DEPLOYMENT.md`.
