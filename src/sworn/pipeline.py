"""Gate pipeline — deterministic, fail-closed commit gating."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sworn.config import SwornConfig
from sworn.evidence.log import EvidenceEntry, _now, append_entry
from sworn.gates.allowlist import evaluate_allowlist
from sworn.gates.identity import evaluate_identity
from sworn.gates.security import evaluate_security
from sworn.kernels.sdk import (
    KernelInput,
    KernelResult,
    load_builtin_kernels,
    load_custom_kernels,
)
from sworn.resolver import KernelDisposition, resolve


@dataclass
class PipelineResult:
    """Result of the full gate pipeline."""

    decision: str  # "PASS" or "BLOCKED"
    reason: str = ""
    gate_results: dict[str, str] = field(default_factory=dict)
    kernel_results: list[dict[str, Any]] = field(default_factory=list)
    actor: str = ""
    tool: str | None = None
    resolution_trace: dict[str, Any] = field(default_factory=dict)


def run_pipeline(
    repo_root: Path,
    files: list[str],
    config: SwornConfig,
) -> PipelineResult:
    """Run the full gate pipeline. Deterministic, fail-closed."""
    gate_results: dict[str, str] = {}
    kernel_details: list[dict[str, Any]] = []
    decision = "PASS"
    reason = ""
    resolution_trace: dict[str, Any] = {}

    # 1. Identity (never blocks)
    identity = evaluate_identity(config.identity_env_vars)
    gate_results["identity"] = "PASS"

    # 2. Security
    security = evaluate_security(files, config.security_patterns)
    gate_results["security"] = "PASS" if security.passed else "BLOCKED"
    if not security.passed:
        decision = "BLOCKED"
        reason = security.reason

    # 3. Allowlist (only if not already blocked and allowlist is configured)
    if decision == "PASS" and config.allowlist:
        allowlist = evaluate_allowlist(files, config.allowlist)
        gate_results["allowlist"] = "PASS" if allowlist.passed else "BLOCKED"
        if not allowlist.passed:
            decision = "BLOCKED"
            reason = allowlist.reason
    else:
        gate_results["allowlist"] = "SKIP" if not config.allowlist else "SKIP"

    # 4. Signing layout migration guard (fail-closed in signed mode)
    legacy_key = repo_root / ".sworn" / "signing.key"
    active_key = repo_root / config.signing_key_path
    signing_migration_block = False
    gate_results["signing"] = "SKIP"
    if config.signing_enabled:
        if legacy_key.exists() and not active_key.exists():
            decision = "BLOCKED"
            reason = (
                "Legacy signing key layout detected at .sworn/signing.key. "
                "Migrate to .sworn/keys/active.key before enabling signing."
            )
            gate_results["signing"] = "ERROR"
            signing_migration_block = True

    # 4. Kernels — run unconditionally, collect all results
    kernel_input = KernelInput(
        files=files,
        actor=identity.actor,
        tool=identity.tool,
        repo_root=str(repo_root),
        gate_blocked=decision == "BLOCKED",
        config={
            "security_patterns": config.security_patterns,
            "allowlist": config.allowlist,
            "evidence_hash_chain": config.evidence_hash_chain,
            "evidence_log_path": config.evidence_log_path,
            "kernels_enabled": config.kernels_enabled,
            "signing_pub_path": config.signing_pub_path,
        },
    )

    all_kernels = load_builtin_kernels(config.kernels_enabled)
    custom_dir = repo_root / config.custom_kernel_dir
    all_kernels.extend(load_custom_kernels(custom_dir))
    all_kernels.sort(key=lambda item: item[0])

    dispositions: list[KernelDisposition] = []

    for name, evaluate_fn in all_kernels:
        try:
            result = evaluate_fn(kernel_input)
        except Exception as exc:
            result = KernelResult(
                decision="BLOCKED",
                triggered_rules=["kernel_exception"],
                evidence_summary=[f"Kernel {name} raised: {exc}"],
                required_next_action=f"Fix kernel {name}",
            )

        kernel_details.append(
            {
                "name": name,
                "decision": result.decision,
                "triggered_rules": result.triggered_rules,
                "evidence_summary": result.evidence_summary,
            }
        )

        dispositions.append(
            KernelDisposition(
                name=name,
                decision=result.decision,
                triggered_rules=result.triggered_rules,
                evidence_summary=result.evidence_summary,
            )
        )

    # Resolve kernel dispositions (gate BLOCKED always wins separately)
    trace = resolve(dispositions)
    resolution_trace = asdict(trace)

    if decision == "PASS" and trace.final_decision == "BLOCKED":
        decision = "BLOCKED"
        reason = trace.final_reason

    gate_results["kernels"] = (
        "BLOCKED" if trace.final_decision == "BLOCKED" else "PASS"
    )

    # 5. Load signing key in signed mode (fail-closed)
    signing_key = None
    key_path = repo_root / config.signing_key_path
    if config.signing_enabled and not signing_migration_block:
        from sworn.evidence.signing import (
            SigningError,
            SigningUnavailableError,
            load_signing_key,
        )
        if not key_path.exists():
            decision = "BLOCKED"
            reason = (
                "Signing enabled but signing key is missing at "
                f"{config.signing_key_path}"
            )
            gate_results["signing"] = "ERROR"
        else:
            try:
                signing_key = load_signing_key(key_path)
            except SigningUnavailableError:
                decision = "BLOCKED"
                reason = "Signing key exists but PyNaCl is not installed"
                gate_results["signing"] = "ERROR"
            except SigningError as exc:
                decision = "BLOCKED"
                reason = f"Signing key error: {exc}"
                gate_results["signing"] = "ERROR"
            else:
                gate_results["signing"] = "PASS"
    else:
        if gate_results["signing"] != "ERROR":
            gate_results["signing"] = "SKIP"

    # 6. Evidence (always log, even on block)
    evidence_entry = EvidenceEntry(
        timestamp=_now(),
        actor=identity.actor,
        tool=identity.tool,
        files=files,
        gates=gate_results,
        kernels=kernel_details,
        decision=decision,
        reason=reason,
        resolution_trace=resolution_trace,
    )

    log_path = repo_root / config.evidence_log_path
    try:
        append_entry(
            log_path, evidence_entry, config.evidence_hash_chain,
            signing_key=signing_key,
        )
        gate_results["evidence"] = "PASS"
    except Exception as exc:
        decision = "BLOCKED"
        gate_results["evidence"] = "ERROR"
        original_reason = reason
        reason = f"Evidence log failure: {exc}"
        if original_reason:
            reason = f"{reason} | prior decision: {original_reason}"

    return PipelineResult(
        decision=decision,
        reason=reason,
        gate_results=gate_results,
        kernel_results=kernel_details,
        actor=identity.actor,
        tool=identity.tool,
        resolution_trace=resolution_trace,
    )
