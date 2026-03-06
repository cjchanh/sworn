# Sworn Configuration

Sworn reads configuration from `.sworn/config.toml` in the repository root.

## Minimal Layout

```toml
[sworn]
version = "0.4"

[security]
patterns = [
  '(^|/)(crypto|auth|gates|licensing|keys)/',
  '(^|/)secrets?/',
  '\.env$',
  '(^|/)private/',
]

[allowlist]
files = []

[identity.env_vars]
CLAUDE_CODE = "claude-code"
CODEX_CLI = "codex"
CURSOR_SESSION = "cursor"

[kernels]
security = true
allowlist = true
audit = true
custom_dir = ".sworn/kernels"

[evidence]
log_path = ".sworn/evidence.jsonl"
hash_chain = true

[signing]
enabled = false
key_path = ".sworn/keys/active.key"
pub_path = ".sworn/keys/"
```

## Security Patterns

`[security].patterns` is a list of case-insensitive regular expressions.
Any staged file that matches one of these patterns blocks the gate.
Invalid regex values fail closed during config load.

## Allowlist

`[allowlist].files` is a list of glob patterns.
If the list is non-empty, only matching files are allowed through the gate.
Security-pattern blocks still win even when a file is allowlisted.

## Identity

`[identity.env_vars]` maps environment variables to AI tool labels written into evidence.
Identity detection is evidence-oriented. It does not provide organizational IAM assurance.

## Kernels

`[kernels]` enables built-in kernels and sets `custom_dir` for repo-local custom kernels.
Custom kernels must be deterministic and side-effect free.

## Evidence

`[evidence].log_path` controls where append-only JSONL evidence is written.
`[evidence].hash_chain = true` enables the SHA-256 chain used by `sworn verify`.

If evidence cannot be extended safely, Sworn now blocks the gate instead of degrading.

## Signing

`[signing].enabled = true` requires a valid private key at `key_path`.
If signing is enabled and the key is missing or unreadable, Sworn blocks the gate.

Private key paths that should be gitignored:

- `.sworn/keys/active.key`
- `.sworn/signing.key` (legacy layout)

Public verification keys live under `.sworn/keys/*.pub`.
