# Upgrade report — sworn (local, unreleased)

This checkout is package version **0.4.0**. These edits are local and untagged.
They are not a release, a /100, or a readiness grade.

## What changed

Evidence/attest was recording the wrong actor, dropping kernel next-actions, tagging AC.L2-3.1.1 only on block (so reports never showed real PASS support), and treating a missing/empty chain as `VALID`. Docs claimed identity enforcement and omitted shipped commands. Smallest wiring to make those claims match the code:

### Runtime

- Identity actor is `git config user.name` of the **gated repo** (`repo_root`), not process cwd.
- Kernel `required_next_action` is stored on each evidence `kernels[]` object.
- Structural allowlist still runs after a security block so `gates.allowlist` in the log is not silently `SKIP`.
- CMMC AC kernel tags `AC.L2-3.1.1` on PASS when the actor is resolved (still BLOCKED on unresolved).
- `sworn verify` / reports distinguish `EMPTY` / `VALID` / `BROKEN`. Empty or missing log is not `VALID`; CLI exits 1.
- Signed mode (`signing.enabled = true`) fail-closes verify on missing public keys and on unsigned entries (`require_signatures`).

### Docs

- README pipeline list matches the code (identity never blocks; signing is a stage; CMMC pack off by default; `keygen` / `ci-check` exist).
- `COMPLIANCE_SCOPE.md`: AC.L2-3.1.1 is enforced by the **opt-in** cmmc AC kernel. The identity gate only records.
- `docs/config.md`: identity does not block; empty verify is not an attest.

### Tests

- Coverage for actor binding, next-action persistence, EMPTY verify, signed-mode unsigned rejection, AC PASS tagging, allowlist-on-prior-block.
- Test repos use `git init --separate-git-dir` (`tests/gitutil.py`) because this environment cannot write a `.git/` directory.

`PYTHONPATH=src python3 -m pytest tests -q --tb=short` → **207 passed** in this run.

## What is still false / incomplete

- **CMMC pack is still off by default.** Unresolved actor is not blocked unless `kernels.cmmc = true`. AC.L2-3.1.1 is not live enforcement in a stock `sworn init`.
- **Actor is not identity assurance.** It is repo `user.name` (else `$USER` / `unknown`). Not IAM, not MFA, not org attestation.
- **Repo-local signatures ≠ organizational attestation.** No PKI, no key-custody proof.
- **Kernel purity is a contract**, not a sandbox. Custom kernels can still do I/O if they ignore the SDK rules.
- **`read_entries` still skips corrupt JSON lines.** `sworn report` can undercount while `sworn verify` says `BROKEN`.
- **`required_next_action` is not in `resolution_trace`** (only in `kernels[]`).
- **Local `ci-check` without `SWORN_CI=1` and a 40-hex base SHA can PASS on an empty diff** when base resolution fails. Fail-closed CI is env-gated.
- **These changes are not tagged 0.4.0.** `COMPLIANCE_SCOPE.md` still names version 0.4.0. A tagged 0.4.0 artifact from PyPI/git does not include this diff.
- **PyPI / homepage badges in README** describe a published package, not this working tree.

## How a reviewer should check

1. `PYTHONPATH=src python3 -m pytest tests -q --tb=short` — expect 207 passed (or the current count if more tests were added after this commit).
2. Fresh init, no gated commits:
   ```bash
   sworn init --repo-root /path/to/other-git-repo
   sworn verify --repo-root /path/to/other-git-repo
   ```
   Expect `Chain: EMPTY` and exit 1. Not `VALID`.
3. Actor binding: `git config user.name` in repo A vs cwd in repo B; `run_pipeline(repo_A, ...)` must record A's name. Covered by `test_actor_bound_to_gated_repo` and `test_actor_uses_gated_repo_git_config`.
4. Block a security-surface file; open `.sworn/evidence.jsonl` and confirm the `security` kernel object has `required_next_action`.
5. Enable `kernels.cmmc = true`, PASS a resolved actor, then `sworn report --cmmc --json`: `AC.L2-3.1.1` should be able to show `SUPPORTED` from a real PASS tag (not only from synthetic test logs).
6. With `[signing] enabled = true` and no `.pub` keys, `sworn verify` must be `BROKEN`, not `VALID`.
7. Diff README / `COMPLIANCE_SCOPE.md` against `src/sworn/pipeline.py` and `src/sworn/gates/identity.py`: identity must not be described as a blocking gate.

Do not treat this commit as release-ready, CMMC-certified, or org-trust attest.
