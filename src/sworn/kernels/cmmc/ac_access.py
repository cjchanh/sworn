"""AC.L2-3.1.1/3.1.2 — Access control: actor identity must be resolved."""
from __future__ import annotations

from sworn.kernels.sdk import KernelInput, KernelResult

UNRESOLVED_ACTORS = frozenset({"", "unknown"})


def evaluate(kernel_input: KernelInput) -> KernelResult:
    """BLOCKED when actor identity is unresolved."""
    actor = kernel_input.actor
    tool = kernel_input.tool

    evidence: list[str] = []
    rules: list[str] = []

    if (actor or "").strip().casefold() in UNRESOLVED_ACTORS:
        rules.append("AC.L2-3.1.1")
        evidence.append(
            "Actor identity: unresolved — access cannot be attributed to an "
            "authorized user."
        )
        return KernelResult(
            decision="BLOCKED",
            triggered_rules=rules,
            evidence_summary=evidence,
            required_next_action=(
                "Resolve actor identity (configure git user or the actor "
                "environment) or record a manual attestation before proceeding."
            ),
        )

    evidence.append(f"Actor: {actor}")
    if tool:
        evidence.append(f"AI tool detected: {tool}")
        rules.append("AC.L2-3.1.2")
    else:
        evidence.append("No AI tool detected")

    return KernelResult(
        decision="PASS",
        triggered_rules=rules,
        evidence_summary=evidence,
    )
