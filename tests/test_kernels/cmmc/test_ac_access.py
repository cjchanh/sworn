"""Tests for AC.L2-3.1.1/3.1.2 access control kernel."""
from __future__ import annotations

import pytest

from sworn.kernels.cmmc.ac_access import evaluate
from sworn.kernels.sdk import KernelInput


def _input(actor: str = "test", tool: str | None = None) -> KernelInput:
    return KernelInput(files=["a.py"], actor=actor, tool=tool, repo_root="/tmp")


class TestACAccess:
    def test_known_actor_passes(self):
        result = evaluate(_input(actor="cj"))
        assert result.decision == "PASS"

    def test_unknown_actor_blocks(self):
        result = evaluate(_input(actor="unknown"))
        assert result.decision == "BLOCKED"
        assert "AC.L2-3.1.1" in result.triggered_rules

    def test_empty_actor_blocks_with_manual_attestation_next_action(self):
        result = evaluate(_input(actor=""))
        assert result.decision == "BLOCKED"
        assert "AC.L2-3.1.1" in result.triggered_rules
        assert "manual attestation" in result.required_next_action.lower()
        assert any("unresolved" in e.lower() for e in result.evidence_summary)

    @pytest.mark.parametrize("actor", ["", "unknown", "UNKNOWN", "  ", " unknown "])
    def test_unresolved_actor_variants_block(self, actor: str):
        result = evaluate(_input(actor=actor))
        assert result.decision == "BLOCKED"
        assert "AC.L2-3.1.1" in result.triggered_rules

    def test_ai_tool_detected(self):
        result = evaluate(_input(actor="cj", tool="claude-code"))
        assert result.decision == "PASS"
        assert "AC.L2-3.1.2" in result.triggered_rules
        assert any("claude-code" in e for e in result.evidence_summary)

    def test_no_tool_passes(self):
        result = evaluate(_input(actor="cj", tool=None))
        assert result.decision == "PASS"

    def test_unresolved_actor_blocks_even_with_tool(self):
        result = evaluate(_input(actor="unknown", tool="claude-code"))
        assert result.decision == "BLOCKED"
        assert "AC.L2-3.1.2" not in result.triggered_rules

    def test_threat_unknown_actor_blocks(self):
        result = evaluate(_input(actor=""))
        assert result.decision == "BLOCKED"
