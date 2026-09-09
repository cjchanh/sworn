# Custom kernels

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

`KernelInput` carries `files`, `actor`, `tool`, `repo_root`, `gate_blocked`,
and `config`. `KernelResult.decision` is `PASS` or `BLOCKED`.

## Kernel contract

Sworn executes kernels even when structural gates already block.

All kernels MUST:

- Be pure (no file writes, network calls, or subprocesses)
- Be side-effect free
- Tolerate partial or failed gate states
- Not depend on a prior structural `PASS`

Purity is a contract, not a sandbox. Custom kernels are unsandboxed
in-process Python. See `KNOWN_BOUNDARIES.md` B-6.
