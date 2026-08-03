"""Disposition resolver — deterministic kernel conflict resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class KernelDisposition:
    """A single kernel's verdict."""

    name: str
    decision: Literal["PASS", "BLOCKED"]
    triggered_rules: list[str] = field(default_factory=list)
    evidence_summary: list[str] = field(default_factory=list)


@dataclass
class ResolutionTrace:
    """Auditable resolution of all kernel dispositions."""

    dispositions: list[KernelDisposition]
    final_decision: Literal["PASS", "BLOCKED"]
    final_reason: str
    blocked_by: list[str]
    kernel_order: list[str] = field(default_factory=list)
    applied_overrides: list[str] = field(default_factory=list)


def resolve(
    dispositions: list[KernelDisposition],
) -> ResolutionTrace:
    """Resolve kernel dispositions into a single decision.

    Fail-closed by construction: any unresolved block -> BLOCKED, and an
    empty evaluation is a refusal, not a pass — zero kernels evaluated
    certifies nothing, so it must never be recorded as PASS.
    """
    if not dispositions:
        return ResolutionTrace(
            dispositions=[],
            kernel_order=[],
            applied_overrides=[],
            final_decision="BLOCKED",
            final_reason=(
                "No kernels evaluated — fail-closed refusal: "
                "an empty evaluation certifies nothing"
            ),
            blocked_by=["no-kernels-evaluated"],
        )

    blocked_set = {
        d.name for d in dispositions if d.decision == "BLOCKED"
    }

    blocked_by = sorted(blocked_set)

    if blocked_by:
        by_name = {d.name: d for d in dispositions}
        reasons = []
        for name in blocked_by:
            d = by_name[name]
            summary = "; ".join(d.evidence_summary[:2]) if d.evidence_summary else "no details"
            reasons.append(f"Kernel '{d.name}': {summary}")
        final_reason = " | ".join(reasons)
        final_decision: Literal["PASS", "BLOCKED"] = "BLOCKED"
    else:
        final_reason = "All kernels passed"
        final_decision = "PASS"

    kernel_order = [d.name for d in dispositions]

    return ResolutionTrace(
        dispositions=list(dispositions),
        kernel_order=kernel_order,
        applied_overrides=[],
        final_decision=final_decision,
        final_reason=final_reason,
        blocked_by=blocked_by,
    )
