# Evidence report example

`sworn report` summarises `.sworn/evidence.jsonl`. Exit 0 is not an
attestation. `sworn verify` is the integrity command.

```
sworn report
SWORN EVIDENCE REPORT
========================================
Period: 2026-08-01T00:00:00+00:00 — 2026-08-18T00:00:00+00:00
Total commits gated: 47
  Passed: 43
  Blocked: 4
  Pass rate: 91.5%

Top block reasons:
  [4] Security surface: crypto/vault.py

AI tools detected:
  [47] none

Most frequently gated files:
  [4] crypto/vault.py

Chain integrity: VALID
  Chain valid: 47 entries
```

Empty log (after init, before any gated commit):

```
sworn report
No evidence entries found.
```

```
sworn verify
Chain: EMPTY
  EMPTY: no evidence log found
```

`sworn verify` exit code is 1 when the chain is not `VALID`.
