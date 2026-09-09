[![CI](https://github.com/cjchanh/sworn/actions/workflows/ci.yml/badge.svg)](https://github.com/cjchanh/sworn/actions/workflows/ci.yml)
[![CodeQL](https://github.com/cjchanh/sworn/actions/workflows/codeql.yml/badge.svg)](https://github.com/cjchanh/sworn/actions/workflows/codeql.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/sworncode)](https://pypi.org/project/sworncode/)

# Sworn

Path-pattern git gate and hash-chained evidence log for AI-assisted commits.

## Install

```bash
pip install sworncode
```

## Example — the enforceable path

```bash
sworn ci-check --base origin/main
```

Make that job a required status check. That is the path a local flag cannot skip.

The Git pre-commit hook (`sworn check`) is developer feedback only.
`git commit --no-verify` skips it. See `docs/DEPLOYMENT.md`.

## What it refuses / what it cannot prove

**Refuses** staged paths that match configured sensitive-path patterns
(raw, Unicode-normalised, confusable-folded, collapsed, symlink targets).
Also blocks `index-unreadable` and `symlink-escapes-repo`.
Path patterns only; contents are not scanned.

**Cannot prove**

- Actor identity — recorded from self-asserted `git config user.name`.
- Log-tail truncation — `sworn verify` still reports `VALID` after the last N lines are deleted. Third-party use **requires** an out-of-band expected head hash and entry count (tag, protected artifact, or external pin). Without that pin, truncation is undetectable.
- Organizational trust from a public key stored in the same repository. Whoever controls the repo can replace `.sworn/keys/*.pub` and re-sign.
- `sworn report` is a summary. Its exit code is not an attestation. `sworn verify` is the integrity command. These call sites still verify the hash chain only (`require_signatures` defaults off): `generate_report` (`src/sworn/evidence/report.py:52`), `generate_cmmc_report` (`src/sworn/evidence/cmmc_report.py:69`), `cmd_status` (`src/sworn/cli.py:962`), and the CMMC evidence-integrity kernel (`src/sworn/kernels/cmmc/evidence_integrity.py:43/45/47`; the `:47` `else` ignores signatures).

Full list with file:line evidence: [`docs/KNOWN_BOUNDARIES.md`](docs/KNOWN_BOUNDARIES.md).
Signing model: [`docs/SIGNING.md`](docs/SIGNING.md).
Security reporting: [`SECURITY.md`](SECURITY.md).

## Local check (developer convenience)

```bash
cd your-repo
sworn init
mkdir -p crypto
echo "secret = 'key'" > crypto/vault.py
git add crypto/vault.py
git commit -m "test"
# → SWORN BLOCKED — Security surface: crypto/vault.py
```

## Commands

```bash
sworn init              # Write config + install the local hook
sworn check             # Gate staged files (hook target; skippable)
sworn ci-check          # Gate a PR/CI diff (enforceable path)
sworn verify            # Chain EMPTY/VALID/BROKEN; exit 1 unless VALID
sworn report            # Summary; exit 0 is not an attestation
sworn report --json
sworn report --cmmc     # CMMC evidence-support report
sworn status
sworn keygen            # Ed25519 keypair (needs PyNaCl)
sworn --version
python -m sworn
```

## Configuration

After `sworn init`, edit `.sworn/config.toml`. Defaults and keys: [`docs/config.md`](docs/config.md).

Sensitive-path patterns are case-insensitive regexes such as
`(^|/)(crypto|auth|gates|licensing|keys)/`, `(^|/)secrets?/`, `\.env$`.

## CMMC

The CMMC pack is evidence-support only (CMMC-focused in 0.4.1).
It does not certify compliance, replace a C3PAO, or guarantee an assessment outcome.
See `COMPLIANCE_SCOPE.md`.

## Develop

```bash
pip install -e ".[dev]"
python -m pytest tests -q
```

`.[dev]` installs pytest and PyNaCl. Without PyNaCl, signing tests skip cleanly.

## Requirements

- Python 3.10+
- Git
- Zero runtime dependencies (`tomli` on Python < 3.11)

## Related docs

[`docs/config.md`](docs/config.md) · [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) · [`docs/custom-kernels.md`](docs/custom-kernels.md) · [`docs/report-example.md`](docs/report-example.md) · [`docs/SIGNING.md`](docs/SIGNING.md) · [`docs/KNOWN_BOUNDARIES.md`](docs/KNOWN_BOUNDARIES.md) · [Release readiness checklist](RELEASE_PROCESS.md#release-readiness-checklist) · [`SECURITY.md`](SECURITY.md)

## License

Apache 2.0 — Centennial Defense Systems
