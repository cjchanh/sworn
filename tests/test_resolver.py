"""Tests for disposition resolver."""
from __future__ import annotations

import inspect

from sworn.resolver import KernelDisposition, ResolutionTrace, resolve


def _disp(
    name: str,
    decision: str = "PASS",
    rules: list[str] | None = None,
    evidence: list[str] | None = None,
) -> KernelDisposition:
    return KernelDisposition(
        name=name,
        decision=decision,
        triggered_rules=rules or [],
        evidence_summary=evidence or [],
    )


class TestResolver:
    def test_all_pass(self):
        result = resolve([_disp("a"), _disp("b"), _disp("c")])
        assert result.final_decision == "PASS"
        assert result.blocked_by == []
        assert result.applied_overrides == []
        assert result.kernel_order == ["a", "b", "c"]

    def test_single_blocked(self):
        result = resolve([_disp("a"), _disp("b", "BLOCKED", evidence=["bad"])])
        assert result.final_decision == "BLOCKED"
        assert result.blocked_by == ["b"]

    def test_mixed_no_rules_blocked(self):
        result = resolve([
            _disp("a"),
            _disp("b", "BLOCKED", evidence=["issue"]),
            _disp("c"),
        ])
        assert result.final_decision == "BLOCKED"
        assert result.blocked_by == ["b"]

    def test_empty_dispositions_blocked(self):
        # Zero kernels evaluated is a refusal, not a pass (fail-closed).
        result = resolve([])
        assert result.final_decision == "BLOCKED"
        assert result.blocked_by == ["no-kernels-evaluated"]
        assert "No kernels evaluated" in result.final_reason

    def test_resolution_trace_populated(self):
        result = resolve([_disp("a"), _disp("b", "BLOCKED", evidence=["err"])])
        assert isinstance(result, ResolutionTrace)
        assert len(result.dispositions) == 2
        assert result.blocked_by == ["b"]
        assert "Kernel 'b'" in result.final_reason

    def test_deterministic_ordering(self):
        """Same input always produces same output."""
        disps = [
            _disp("z", "BLOCKED", evidence=["z_bad"]),
            _disp("a", "BLOCKED", evidence=["a_bad"]),
            _disp("m"),
        ]
        r1 = resolve(disps)
        r2 = resolve(disps)
        assert r1.blocked_by == r2.blocked_by
        assert r1.final_decision == r2.final_decision
        assert r1.applied_overrides == r2.applied_overrides

    def test_blocked_reason_includes_evidence(self):
        result = resolve([_disp("sec", "BLOCKED", evidence=["crypto/key.py detected"])])
        assert "crypto/key.py detected" in result.final_reason

    def test_all_blocked(self):
        result = resolve([
            _disp("a", "BLOCKED", evidence=["a_err"]),
            _disp("b", "BLOCKED", evidence=["b_err"]),
        ])
        assert result.final_decision == "BLOCKED"
        assert sorted(result.blocked_by) == ["a", "b"]

    def test_no_override_path_exists(self):
        params = inspect.signature(resolve).parameters
        assert "precedence_rules" not in params

    def test_threat_config_cannot_weaken_enforcement(self):
        result = resolve([
            _disp("security", "BLOCKED", evidence=["crypto/key.py"]),
            _disp("allowlist", "BLOCKED", evidence=["deploy/prod.yml"]),
        ])
        assert result.final_decision == "BLOCKED"
        assert result.blocked_by == ["allowlist", "security"]
