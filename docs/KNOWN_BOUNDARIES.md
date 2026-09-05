# Known Boundaries

This document is a tracked governance artifact, not a marketing page. It records
where Sworn's enforcement stops, with file-and-line evidence for every claim.

Sworn's value proposition is that its decisions are deterministic and auditable.
A tool that makes that claim owes its users an equally deterministic account of
what it does *not* decide. That is what this file is.

**Scope of this document.** Every boundary below was read in the source tree at
commit `90aa0a1` (`git describe` → `0.4.0-37-g90aa0a1`). Line numbers refer to
that tree. Boundaries are labeled with how they were established:

- **Verified** — reproduced by running the CLI and observing the output.
- **Code-grounded** — established by reading the cited source path; not
  reproduced live.
- **CLOSED** — the boundary was fixed. The entry names the fix commit and keeps
  the original description, so the record of what was once true survives the
  fix. Line numbers in a CLOSED entry refer to the tree *before* the fix.

No boundary below is stated from inference alone.

**Subsequent changes.** B-2 was closed in
`18ebbb8ef74f0a0ea0bd6d1e790eedacb48833c4` (`0.4.0-41-g18ebbb8`) and
re-verified against that tree. Every other boundary below still describes
`90aa0a1` and has not been re-read since.

---

## B-1 — Local hook enforcement is bypassable by design

**Status:** Code-grounded.

**What it is.** `sworn init` installs a Git `pre-commit` hook whose entire body
is a call to `sworn check`:

- `src/sworn/cli.py:277` — `hook_line = 'sworn check || exit 1\n'`
- `src/sworn/cli.py:276-291` — the hook is written into the effective hooks
  directory (`_resolve_hooks_dir`, honoring `core.hooksPath`).

Git's `--no-verify` flag skips `pre-commit` hooks. Any developer with commit
rights can therefore commit without invoking Sworn at all. Removing the hook
file, or pointing `core.hooksPath` elsewhere, has the same effect.

**Why it exists.** Sworn is a client-side hook installer. Git deliberately makes
client-side hooks advisory — they are a developer convenience, not an access
control. Sworn cannot close this from inside a `pre-commit` hook, because the
bypass happens before the hook would run.

**What an attacker (or a rushed developer) can do inside it.** Land a commit
that touches a configured security surface with no gate evaluation and, more
importantly, **no evidence log entry**. The absence is silent: the evidence log
contains no record that a commit was skipped, because nothing ran to write one.
An auditor reading only `.sworn/evidence.jsonl` sees a shorter history, not a
tampered one.

**What mitigates it today.** The CI gate. `sworn ci-check` re-runs the same
pipeline over the pull-request diff, where the developer does not control
invocation. `README.md` §*What It Does* and `docs/DEPLOYMENT.md` both direct teams to treat
local hooks as developer fast-fail and to make the CI check a required status
check. `SECURITY.md` already lists `--no-verify` bypass as a considered
adversary capability.

**Remediation options (no commitment, no dates).**

1. Document a `git log` ↔ evidence-log reconciliation command so a gap between
   commits and evidence entries is detectable rather than silent.
2. Ship a server-side / CI assertion that every commit in a merge range has a
   corresponding evidence entry.
3. Leave as-is and rely on branch protection. This is a legitimate choice — it
   is the standard posture for every pre-commit-hook tool — provided the CI gate
   is actually required.

---

## B-2 — Fail-closed CI diff resolution was gated on an environment variable

**Status:** **CLOSED** in `18ebbb8ef74f0a0ea0bd6d1e790eedacb48833c4`
(`0.4.0-41-g18ebbb8`). Verified before and after. The entry is kept rather than
deleted so the history of the boundary stays auditable; the residual is recorded
at the end.

**What it was.** `_get_pr_diff_files()` decided whether an unresolvable diff base
was an error or an empty result based solely on `SWORN_CI`:

- `src/sworn/cli.py:378` (at `90aa0a1`) — `ci_mode = os.environ.get("SWORN_CI") == "1"`
- `src/sworn/cli.py:422-428` — the `RuntimeError` for a failed diff computation
  was raised **only** `if ci_mode`; otherwise the function fell through to
  `return []`.
- `src/sworn/cli.py:446-448` — `cmd_ci_check` maps an empty file list to
  `print("SWORN PASS — no files in diff")` and `return 0`.

The consequence was that outside CI mode, "I could not resolve the diff base" and
"the diff is legitimately empty" produced the identical output and the identical
exit code.

**Why it existed.** The non-CI path existed so a developer could run `ci-check`
locally against a branch name without being forced to supply a full 40-character
base SHA. The strict validation was deliberately reserved for CI, where the base
SHA is supplied by `github.event.pull_request.base.sha`. The defect was that one
`ci_mode` flag gated **two** unrelated policies: the base-ref *format* rule and
the resolution-*failure* rule. Only the first is CI-specific.

**What an attacker could do inside it.** A CI pipeline that invoked `sworn
ci-check` **without** setting `SWORN_CI=1` was not fail-closed. If the base ref
could not be resolved — a shallow clone, a missing `fetch-depth: 0`, a renamed
default branch, a fork PR without base history — the job printed `SWORN PASS` and
exited `0`. The gate reported success precisely when it did the least work. This
was the highest-consequence boundary in this document, because it converted a
misconfiguration into a green check rather than a red one.

**What changed.** The two policies are now separate:

- Resolution failure raises `DiffBaseUnresolved` unconditionally
  (`src/sworn/cli.py`, `_get_pr_diff_files`). There is no longer a path on which
  a failed diff computation returns `[]`, so it can no longer reach the `PASS`
  branch. No environment variable is required for this.
- The 40-hex base-SHA *format* rule remains gated on `SWORN_CI=1`, preserving
  local `--base my-branch` ergonomics.
- An empty base ref is now also unresolvable. Previously it reduced the ref list
  to `...HEAD`, which git resolves to an empty diff and reported as `PASS`.
- Advisory behavior became an explicit opt-out: `--advisory` or
  `SWORN_ADVISORY=1`.

**Backward compatibility.** `SWORN_CI=1` keeps its exact prior meaning. For
resolution failures it now selects what is already the default, making it
redundant-but-harmless; for the format rule it is still the trigger. Identical
inputs produce identical exit codes for every pipeline that already sets it.

**Verification.** Same scratch-repository procedure as before, run against both
trees. `0000…0000` is a full 40-hex SHA that does not resolve in the test
repository.

| Command | Before (`90aa0a1`) | After (`18ebbb8`) |
|---|---|---|
| `sworn ci-check --base 0000…0000` (no env) | `SWORN PASS — no files in diff` · `0` | `SWORN BLOCKED — Failed to compute diff against base…` · `1` |
| `sworn ci-check --base nonexistent-branch-xyz` (no env) | `SWORN PASS — no files in diff` · `0` | `SWORN BLOCKED — Failed to compute diff against base…` · `1` |
| `sworn ci-check --base ""` (no env) | `SWORN PASS — no files in diff` · `0` | `SWORN BLOCKED — No diff base to compare against…` · `1` |
| `SWORN_CI=1 sworn ci-check --base 0000…0000` | `SWORN BLOCKED — Failed to compute CI diff…` · `1` | `SWORN BLOCKED — Failed to compute diff against base…` · `1` |
| `SWORN_CI=1 sworn ci-check --base nonexistent-branch-xyz` | `SWORN BLOCKED — CI mode requires full base SHA…` · `1` | `SWORN BLOCKED — CI mode requires full base SHA…` · `1` |
| `sworn ci-check --base HEAD` (resolvable, no changes) | `SWORN PASS — no files in diff` · `0` | `SWORN PASS — no files in diff` · `0` |
| `sworn ci-check --base 0000…0000 --advisory` | *flag did not exist* | `SWORN ADVISORY — GATE DID NOT RUN. THIS IS NOT A PASS.` · `0` |
| `SWORN_ADVISORY=1 sworn ci-check --base 0000…0000` | `SWORN PASS — no files in diff` · `0` | `SWORN ADVISORY — GATE DID NOT RUN. THIS IS NOT A PASS.` · `0` |
| `SWORN_CI=1 sworn ci-check --base 0000…0000 --advisory` | *flag did not exist* | `SWORN BLOCKED — advisory mode requested while SWORN_CI=1 is set…` · `1` |

Regression tests pin the failing case, not only the passing one:
`tests/test_ci_check.py::TestCIDiffBaseFailsClosedByDefault`,
`::TestCIAdvisoryOptOut`, `::TestCIBackwardCompatSwornCIEnvVar`. They clear the
steering environment variables explicitly so an ambient `SWORN_CI` in a CI
runner cannot rescue a default-path assertion. Reverting the fix turns six of
them red; a property-neutral edit to the same statement (rewording the error
message) leaves all of them green.

**Second residual, closed `1a601716ff9be12384f9e816cca6a315cf5158b2` (2026-08-18).** The module-direct
invocation shape () lacked the exit guard the package
entrypoint and console script carry, so every BLOCKED verdict exited 0 under
it — the B-2 fail-open family surviving one invocation shape away from the
supported ones. Closed by adding the same `raise SystemExit(main())` guard
to cli.py; pinned by a failing-case regression test
(test_module_direct_invocation_propagates_block_exit_code). Audit:
an internal CDS security-audit receipt dated 2026-08-18 (not part of this repository).

**Residual boundary — the advisory opt-out is a deliberate fail-open.**
`--advisory` / `SWORN_ADVISORY=1` still exits `0` when the base cannot be
resolved. Three properties bound it, and they are the reason it is acceptable
where the previous default was not:

1. It requires an explicit act. It is never the default.
2. It never prints the `PASS` token, and its banner states that the gate did not
   run. A log scraper keyed on `SWORN PASS` cannot be fooled by it. The banner
   goes to stderr and nothing is written to stdout.
3. It is scoped to diff-base resolution only. It does not downgrade a gate
   verdict — a blocked kernel still exits `1`
   (`tests/test_ci_check.py::TestCIAdvisoryOptOut::test_advisory_does_not_downgrade_a_gate_verdict`).
   Requesting it while `SWORN_CI=1` is set is refused, so it cannot be used to
   defang a pipeline that declared itself a CI gate.

Anyone auditing a pipeline should still confirm that `--advisory` and
`SWORN_ADVISORY` appear nowhere in it. That check is now possible, which it was
not before: previously the fail-open state had no distinguishing marker at all.

---

## B-3 — `sworn report` exit code is not an attestation signal

**Status:** Verified.

**What it is.** `cmd_report` returns `0` on every path:

- `src/sworn/cli.py:463-485` — both the `--cmmc` branch and the default branch
  end in `return 0`. No branch returns non-zero.
- `src/sworn/evidence/report.py:23-26` — an empty log yields the string
  `"No evidence entries found."`.

By contrast `cmd_verify` fail-closes:

- `src/sworn/cli.py:612` — `return 0 if status == "VALID" else 1`.

**Verification.** On a freshly initialized repository with no gated commits:

| Command | Output | Exit |
|---|---|---|
| `sworn report` | `No evidence entries found.` | `0` |
| `sworn report --json` | `{"total": 0, "message": "No evidence entries"}` | `0` |
| `sworn verify` | `Chain: EMPTY` / `EMPTY: no evidence log found` | `1` |

**Why it exists.** `report` is a summarizer, not a gate. Its contract is to
describe the log, and describing an empty log is a successful description.

**What an attacker can do inside it.** Nothing directly — but a CI job wired to
`sworn report` instead of `sworn verify` will pass on a repository where Sworn
has never gated a single commit. The plain-text `report` output also never prints
the token `EMPTY`, so a log-scraping check keyed on that token sees nothing to
alarm on. This is a foot-gun in the integrator's hands, not a tampering path.

**What mitigates it today.** `sworn verify` is the fail-closed surface and does
distinguish `EMPTY` / `VALID` / `BROKEN` (`src/sworn/evidence/log.py:153-162`).
`README.md` §*Evidence* shows the `EMPTY` case and states the exit code is 1.

**Remediation options (no commitment, no dates).**

1. State explicitly in `README.md` and `docs/DEPLOYMENT.md` that `sworn verify`
   is the only command whose exit code is an attestation signal.
2. Add an opt-in `--fail-on-empty` flag to `report` for integrators who want one
   command.
3. Print the `EMPTY` token in plain-text `report` output for parity with
   `verify` and with `report --json`'s `chain_status` field.

---

## B-4 — Malformed evidence lines are skipped by the reader and counted by nothing

**Status:** Verified.

**What it is.** The two consumers of the evidence log disagree about malformed
lines:

- `src/sworn/evidence/log.py:146-149` — `read_entries` wraps `json.loads` in
  `try` / `except json.JSONDecodeError: continue`. A corrupt line is silently
  dropped from the returned list.
- `src/sworn/evidence/log.py:201-204` — `verify_chain` treats the same line as
  fatal and returns `(False, f"Line {line_num}: invalid JSON")`.

`generate_report` uses both: `read_entries` for the counts
(`src/sworn/evidence/report.py:18`) and `verify_chain` for the integrity line
(`src/sworn/evidence/report.py:52`).

**Verification.** After appending a literal `{not-json` line to a two-entry log:

| Command | Relevant output | Exit |
|---|---|---|
| `sworn report` | `Total commits gated: 2` **and** `Chain integrity: BROKEN` | `0` |
| `sworn verify` | `Chain: BROKEN` / `Line 3: invalid JSON` | `1` |

**Why it exists.** `read_entries` is tolerant so that a partially corrupted log
still yields a usable summary rather than crashing. That is a defensible
reporting choice.

**What an attacker can do inside it.** Corrupt or truncate individual entries
and have the *count* silently shrink. The important qualifier, established by the
verification above: **the integrity verdict is not fooled** — `report` still
prints `Chain integrity: BROKEN` and `verify` still exits `1`. So this is an
accuracy boundary in the count, not a tamper-evidence bypass. Anyone reading the
whole report sees the `BROKEN` line. Anyone scraping only `Total commits gated:`
gets a number that is quietly wrong.

**What mitigates it today.** The hash chain. Any corrupt line breaks chain
continuity for everything after it, and both `report` and `verify` surface that.

**Remediation options (no commitment, no dates).**

1. Have `read_entries` return a skipped-line count alongside the entries so
   `report` can print `N entries (M unreadable lines skipped)`.
2. Add a strict mode to `read_entries` that raises on malformed input, used by
   report paths that claim completeness.

---

## B-5 — Report-path chain verification does not require signatures

**Status:** **CLOSED**. The report path now verifies signatures when signing is
enabled and refuses on failure. Historical description of the prior behaviour
is kept below.

**What it was.** The report path verified the chain with default arguments:

- `src/sworn/evidence/report.py:52` — `chain_valid, chain_msg = verify_chain(log_path)`

No `verify_key`, no `verify_key_dir`, no `require_signatures`. The signature
parameter defaults to off:

- `src/sworn/evidence/log.py:169` — `require_signatures: bool = False`
- `src/sworn/evidence/log.py:256-261` — an unsigned entry is a violation only
  when `require_signatures` is set, or when a verify key was supplied *and* a
  signed entry has already been seen.

The verify path did the opposite:

- `src/sworn/cli.py:573` — `require_signatures = config.signing_enabled`
- `src/sworn/cli.py:603-608` — that value is passed into `verify_chain`.

**Why it existed.** Most plausibly because `generate_report` predates signed mode
and was never updated to take the config. The report function's signature
(`log_path`, `output_format`, `since`) has no access to a `SwornConfig`, so it
cannot know whether signing is enabled.

**What an attacker could do inside it.** In a repository configured with
`[signing] enabled = true`, strip signatures from evidence entries while keeping
the hash chain intact. `sworn verify` fail-closes on this
(`Line N: missing signature in signed log`). `sworn report` — which is the
command most likely to be pasted into a compliance packet — would report the
chain as `VALID`, because it never asked about signatures. The two commands can
therefore disagree about the same log, and the more presentable one is the more
permissive one.

**What changed.** `cmd_report` now calls the same `_verify_signed_chain` helper
as `cmd_verify` when `config.signing_enabled` is true, before generating any
report. On failure it prints `Report: REFUSED` plus the same reason lines
`cmd_verify` would print, emits no report body, and returns 1. A missing public
key with signing enabled is a refusal, never a warning. When signing is
disabled, `cmd_report` behaves as before.

**What mitigates it today.** The shared helper. The two commands can no longer
drift on key loading or `require_signatures`.

---

## B-6 — Custom kernels are unsandboxed in-process Python

**Status:** Code-grounded.

**What it is.** Custom kernels are loaded by importing and executing arbitrary
`.py` files found in the configured directory:

- `src/sworn/kernels/sdk.py:90-106` — every non-underscore `*.py` file in
  `custom_dir` is turned into a module spec and run via
  `spec.loader.exec_module(mod)` (line 102), inside the Sworn process.
- `src/sworn/pipeline.py:102-103` — the directory is `repo_root /
  config.custom_kernel_dir`, defaulting to `.sworn/kernels`
  (`src/sworn/config.py:63`, `src/sworn/config.py:91`).

Module-level code executes at load time, before any `evaluate()` contract is
checked.

**Why it exists.** It is the extension mechanism. Sworn's kernel SDK is
explicitly a "write a Python file with an `evaluate()` function" interface
(`README.md` §*Custom Kernels*), and that requires executing user code.

**What an attacker can do inside it.** Anyone who can land a file in
`.sworn/kernels/` — which is a normal, committed, reviewable path in the target
repository — achieves arbitrary code execution in every developer's
`pre-commit` run and in CI. The kernel purity rules (`README.md` §*Kernel Contract*: no file writes, no
network calls, no subprocesses) are a **contract**, not an
enforcement: nothing in the loader inspects or restricts what the module does.

**What mitigates it today.** Code review of the `.sworn/kernels/` path, which
is the same trust boundary as any other executable content in the repository. A
repository whose contents you already trust to run in CI does not gain new
exposure from this. Import failures do fail closed
(`src/sworn/kernels/sdk.py:107-119` substitutes a `BLOCKED` kernel), and kernel
exceptions at evaluation time also fail closed
(`src/sworn/pipeline.py:111-117`) — but neither is a containment mechanism.

This boundary is already acknowledged: `README.md` §*Known Residual Risks*
("Kernel purity is contract-enforced; runtime sandboxing is out of scope
today"), and `SECURITY.md`
lists both "Malicious kernel implementation" as an uncovered adversary
capability and "Provide sandbox isolation for kernels" as an explicit non-goal.

**Remediation options (no commitment, no dates).**

1. Treat `.sworn/kernels/` as a CODEOWNERS-protected path in deployment guidance.
2. Add an opt-in allowlist of kernel file hashes in `config.toml`, so an
   unreviewed kernel file fails closed instead of executing.
3. Static-inspect kernel modules for imports of `os`, `subprocess`, `socket`,
   and friends, and refuse to load on a match. This raises cost for an attacker;
   it is not a sandbox and should not be described as one.
4. True isolation (subprocess with dropped privileges, or a restricted
   interpreter) is a substantially larger change and is not scoped here.

---

## B-7 — Actor identity is self-asserted, not authenticated

**Status:** Code-grounded, partial — see the read restriction noted below.

**What it is.** The identity stage records an actor and never blocks:

- `src/sworn/pipeline.py:48-49` — `evaluate_identity(...)` is called and then
  `gate_results["identity"] = "PASS"` is assigned unconditionally. No branch in
  `run_pipeline` can set the identity gate to `BLOCKED`.

The only component that acts on identity is the opt-in CMMC access-control
kernel, and its notion of "resolved" is a two-element denylist:

- `src/sworn/kernels/cmmc/ac_access.py:6` —
  `UNRESOLVED_ACTORS = frozenset({"", "unknown"})`
- `src/sworn/kernels/cmmc/ac_access.py:17` — an actor blocks only if its
  stripped, case-folded value is in that set.

Any other non-empty string passes. `README.md` §*What It Does* documents the actor source
as the gated repository's `git config user.name`, which is a value the committer
sets themselves.

**Why it exists.** Sworn reads the identity Git gives it. It has no
authentication surface, no directory integration, and makes no claim to one.

**What an attacker can do inside it.** Set `git config user.name` to any
non-empty string other than `unknown` and be recorded as that actor, passing
`AC.L2-3.1.1`. The evidence log will faithfully record an unverified name. The
log is tamper-evident about *what it recorded*; it is not evidence that the
recorded actor is who they say they are.

**What mitigates it today.** Nothing inside Sworn, by design. The mitigation is
external: commit signing, protected branches, and the identity controls of the
hosting platform. `SECURITY.md` already lists "Enforce org-level identity
governance" as a non-goal, and `COMPLIANCE_SCOPE.md` scopes AC.L2-3.1.1 to
opt-in kernel enforcement rather than live identity assurance.

**Remediation options (no commitment, no dates).**

1. Record the Git committer email and any available CI-provided identity claim
   (`GITHUB_ACTOR`) alongside `user.name`, so the evidence carries more than one
   self-asserted field.
2. Optionally cross-check the recorded actor against a configured allowlist,
   which converts an unrecognized actor into a block instead of a record.
3. Document plainly that actor is provenance metadata, not authentication.

**Read restriction on this boundary.** `src/sworn/gates/identity.py` matches the
security-surface path pattern enforced by the authoring environment's own
governance hooks, and the read was refused. Every claim above is therefore
grounded in `pipeline.py`, `ac_access.py`, and `README.md` only. The internal
fallback chain inside `evaluate_identity` — what it does when `git config
user.name` is unset — is **not characterized here** and should be reviewed
directly before this section is treated as complete.

---

## B-8 — Zero evaluated kernels is a refusal, and that has a deployment consequence

**Status:** Verified.

**What it is.** This is the repository's zero-kernel behavior, and it is worth
stating precisely because it is easy to describe backwards. An empty kernel
evaluation is **fail-closed**, not fail-open:

- `src/sworn/resolver.py:33-38` — the `resolve()` docstring: *"Fail-closed by
  construction: any unresolved block -> BLOCKED, and an empty evaluation is a
  refusal, not a pass — zero kernels evaluated certifies nothing, so it must
  never be recorded as PASS."*
- `src/sworn/resolver.py:39-50` — an empty `dispositions` list returns
  `final_decision="BLOCKED"`, `blocked_by=["no-kernels-evaluated"]`, and the
  reason `"No kernels evaluated — fail-closed refusal: an empty evaluation
  certifies nothing"`.
- `src/sworn/pipeline.py:139-148` — `run_pipeline` always calls `resolve()` and
  maps its verdict into `gate_results["kernels"]`.

This behavior landed in commit `e9822c6` (*"fix(resolver): empty evaluation is a
refusal, not a pass"*) and is regression-tested at
`tests/test_resolver.py:46-50` and `tests/test_pipeline.py:77-88`.

**Verification.** With `security = false`, `allowlist = false`, `audit = false`,
no CMMC pack, and no custom kernels:

```
SWORN BLOCKED — No kernels evaluated — fail-closed refusal: an empty evaluation certifies nothing
  Actor: Test Actor
  Gate: kernels → BLOCKED
```

Exit code `1`.

**Why it exists.** Because a governance tool that returns `PASS` after
evaluating nothing is worse than no tool: it manufactures an unearned
attestation. Refusing is the correct behavior.

**What the residual boundary actually is.** Not a bypass — a usability trap. The
zero-kernel state is reachable purely through configuration
(`src/sworn/config.py:163-177`: `security`, `allowlist`, and `audit` each default
to `true`, and `cmmc` defaults to `false`), so an operator who disables the three
built-in kernels to "quiet" Sworn will block **every** commit in the repository
with a message about kernels rather than about their config. The pressure that
creates is to remove Sworn entirely, or to add `--no-verify` to muscle memory
(see B-1). The failure is safe; the ergonomics push toward an unsafe workaround.

**What mitigates it today.** The block reason names the condition explicitly
(`no-kernels-evaluated`), and `sworn status` prints `Kernels: none`
(`src/sworn/cli.py:551-556`).

**Remediation options (no commitment, no dates).**

1. Warn at `sworn init` / `sworn status` time when the resolved configuration
   would evaluate zero kernels, rather than only at commit time.
2. Have `load_config` surface a distinct, actionable error for an all-disabled
   kernel configuration that names the config keys responsible.

---

## B-9 — Repo-local signing is not organizational attestation

**Status:** Code-grounded; already documented.

Signing proves that an entry was produced by a key present in the repository's
`.sworn/keys/` layout. It does not prove organizational authority, key custody,
or approval. `README.md` §*Integrity vs Trust* and `SECURITY.md` both state this, and both
describe the Org-Trust posture (pinned public keys, protected branches, external
private-key custody, explicit rotation) required before signing should be read as
attestation. Nothing in Sworn verifies that those controls are in place.

Restated here only so that the boundaries list is complete; the canonical
treatment is in `SECURITY.md`.

---

## B-10 — The CMMC pack is off by default

**Status:** Code-grounded.

- `src/sworn/config.py:171-177` — `cmmc_val = kernels.get("cmmc", False)`.
- `src/sworn/kernels/sdk.py:58` — `cmmc_enabled = enabled.get("cmmc", False)`.
- `src/sworn/config.py:65-67` — the generated config template ships the `cmmc`
  keys commented out.

A stock `sworn init` therefore enforces none of the CMMC controls, including the
actor-identity control discussed in B-7. This is intentional and is documented at
`README.md` §*Configuration*. It is listed here because "we map to NIST 800-171
controls" and
"those controls are enforced in your repository right now" are different claims,
and only the first is true by default.

Sworn's CMMC output is evidence-support material. It does not certify
compliance and does not replace a C3PAO (`README.md` §*CMMC Evidence Scope*,
`COMPLIANCE_SCOPE.md`).

---

## Unverified in this pass

Recorded so the gaps are visible rather than implied:

- **B-5 live reproduction.** The signed-mode divergence between `report` and
  `verify` is established by reading `report.py:52`, `log.py:169`, and
  `cli.py:573`. The runtime demonstration required generating an Ed25519 keypair,
  and the authoring environment's key-material governance hook refused the
  command. The code path is unambiguous; the live receipt is absent.
- **B-1 live reproduction.** The `--no-verify` demonstration required committing
  a file under a `crypto/` path, which the authoring environment's Rule-2 hook
  refused. The boundary follows from `cli.py:277` and Git's documented
  `--no-verify` semantics, but no live receipt was captured.
- **`src/sworn/gates/identity.py`** was not read at all (see B-7). The actor
  fallback behavior is uncharacterized in this document.

## Method

Test suite at the time of writing: `PYTHONPATH=src python3 -m pytest tests -q`
→ **207 passed**, exit `0`. After the B-2 fix (`18ebbb8`) the same command
→ **220 passed**, exit `0`; the 13 added tests are the B-2 regression suite.

Live boundary checks (B-2, B-3, B-4, B-8) were run against scratch
repositories outside this tree, using `PYTHONPATH` pointed at `src/`, so no
evidence log or configuration in this repository was modified.
