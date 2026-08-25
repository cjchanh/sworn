# Review — sworn `UPGRADE_REPORT.md`

Local review of this checkout only. The upgrade was not re-done. Nothing was pushed. This is not a /100.

Package version in-tree is **0.4.0** (`src/sworn/__init__.py`, `pyproject.toml`). `git describe` is `0.4.0-17-g563931b`. Tag `0.4.0` exists and is 17 commits behind `HEAD`. The writer’s claim that *this* tree is not the tagged 0.4.0 artifact holds.

## Checks re-run

| # | Writer check | Result |
| --- | --- | --- |
| 1 | `PYTHONPATH=src python3 -m pytest tests -q --tb=short` | **207 passed** in 8.08s. Teardown printed pytest `rm_rf` warnings on `.git` paths (sandbox `PermissionError`); tests still passed. |
| 2 | Fresh `sworn init` then `sworn verify` | `Chain: EMPTY` / `EMPTY: no evidence log found` / exit 1. `VALID` not printed. |
| 3 | Actor bound to gated repo, not cwd | `test_actor_bound_to_gated_repo` and `test_actor_uses_gated_repo_git_config` passed. `_git_actor` uses `cwd=repo_root`. |
| 4 | Security-surface block stores `required_next_action` on the `security` kernel in `.sworn/evidence.jsonl` | Present: `"Remove security-surface files or adjust config"`. |
| 5 | `kernels.cmmc = true`, resolved actor, `sworn report --cmmc --json` | Live pipeline PASS tagged `AC.L2-3.1.1`; report showed `SUPPORTED` / `evidence_count: 1` from that PASS, not a synthetic log. |
| 6 | `[signing] enabled = true`, no `.pub` keys | Missing `.sworn/keys/`: `Chain: BROKEN` / exit 1. Empty keys dir: `BROKEN` / `no public keys found`. |
| 7 | README / `COMPLIANCE_SCOPE.md` vs `pipeline.py` / `identity.py` | Identity is documented as record-only and never blocks. Code never sets `gates.identity` to `BLOCKED`. |

Named-check unit tests also re-run in isolation: 7 passed (actor binding, allowlist-after-security-block, next-action log, EMPTY verify, signed unsigned log, AC PASS tag).

## What holds

- Identity actor is `git config user.name` of `repo_root`. Pipeline always passes `repo_root` into `evaluate_identity`. Fallback remains `$USER` then `"unknown"`.
- Each evidence `kernels[]` object stores `required_next_action`. Confirmed in JSONL on a security block.
- When an allowlist is configured, it still evaluates after a security block (`test_allowlist_recorded_when_security_already_blocked`). Unconfigured allowlist is still `SKIP` (expected).
- CMMC AC kernel tags `AC.L2-3.1.1` on PASS for a resolved actor and BLOCKED for empty/`unknown` (case/whitespace variants). Live `sworn report --cmmc --json` can show `SUPPORTED` from that PASS tag.
- `sworn verify` maps missing/empty log to `EMPTY` and exit 1. Hash/JSON failures are `BROKEN`. Signed mode fail-closes verify on missing pub path, empty pub dir, and unsigned entries (`require_signatures`).
- README pipeline list matches this tree: identity never blocks; signing is a stage; CMMC commented off; `keygen` and `ci-check` exist. `docs/config.md` matches identity-does-not-block and EMPTY-is-not-attest.
- `COMPLIANCE_SCOPE.md` now says AC.L2-3.1.1 is opt-in kernel enforcement and the identity gate only records. Tagged `0.4.0` still called that control Detective.
- Stock `sworn init` does not enable `kernels.cmmc`. `_defaults()` / template leave the pack off.

## What fails

None of the seven named reviewer checks failed.

Two writer sentences are broader than the code:

1. “`sworn verify` / reports distinguish `EMPTY` / `VALID` / `BROKEN`.” `sworn verify` and `sworn report --cmmc` do. Plain `sworn report` on a missing/empty log returns `No evidence entries found.` and never prints `EMPTY`/`VALID`/`BROKEN`.
2. “Coverage for … AC PASS tagging” is unit-level (`test_known_actor_passes`) plus synthetic CMMC-report logs. There is no pytest that runs the pipeline with `cmmc=true` and then asserts `SUPPORTED` on a real JSONL. The live path works; the suite does not join the two ends.

`generate_report` / `generate_cmmc_report` call `verify_chain` without `require_signatures`. Signed-mode fail-close is `sworn verify` only. A report can still say `VALID` on an unsigned chain that `sworn verify` would call `BROKEN`.

## What is still false

Writer’s residual list is still true of this tree:

- CMMC pack is off by default. Unresolved actor is not blocked by a stock `sworn init`. AC.L2-3.1.1 is not live enforcement until `kernels.cmmc = true`.
- Actor is repo `user.name`, else `$USER`, else `unknown`. Not IAM, MFA, or org attestation. `$USER` is treated as resolved and will PASS the AC kernel.
- Repo-local Ed25519 signatures are not organizational attestation. No PKI or key-custody proof.
- Kernel purity is a contract. `load_custom_kernels` `exec_module`s repo `*.py` with no sandbox.
- `read_entries` still `continue`s on corrupt JSON. Confirmed: after appending `{not-json}`, `read_entries` returned 2 rows while `verify_chain` was `BROKEN` (`Line 3: invalid JSON`). `sworn report` can undercount while verify is `BROKEN`.
- `required_next_action` is on `kernels[]` only. `KernelDisposition` / `resolution_trace.dispositions` omit it (keys: `decision`, `evidence_summary`, `name`, `triggered_rules`).
- Local `ci-check` without `SWORN_CI=1` and a 40-hex base SHA returns `[]` when every ref lookup fails, then prints `SWORN PASS — no files in diff` and exits 0. Fail-closed CI is env-gated. Confirmed live with a nonexistent `--base`.
- These changes are not tag `0.4.0`. `COMPLIANCE_SCOPE.md` still titles coverage “Sworn version 0.4.0” and says it “reflects Sworn version 0.4.0 exactly,” which is false for both the tagged artifact (17 commits behind; AC.L2-3.1.1 was Detective there) and this working tree’s own versioning rule.
- README PyPI / homepage badges describe a published package, not this working tree.

Do not treat this commit as release-ready, CMMC-certified, or org-trust attest. That stop-line in the upgrade report holds.
