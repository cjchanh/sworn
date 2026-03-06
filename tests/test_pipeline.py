"""Tests for gate pipeline."""
from __future__ import annotations

from pathlib import Path

from sworn.config import SwornConfig, _compile_patterns
from sworn.pipeline import run_pipeline


def _config(
    security_patterns: list[str] | None = None,
    allowlist: list[str] | None = None,
) -> SwornConfig:
    patterns = security_patterns or [r"(^|/)(crypto|auth|keys)/"]
    return SwornConfig(
        security_patterns=_compile_patterns(patterns),
        allowlist=allowlist or [],
        identity_env_vars={},
        kernels_enabled={"security": True, "allowlist": True, "audit": True},
        custom_kernel_dir=".sworn/kernels",
        evidence_log_path=".sworn/evidence.jsonl",
        evidence_hash_chain=True,
    )


class TestPipeline:
    def test_full_pass(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(tmp_repo, ["src/main.py"], config)
        assert result.decision == "PASS"
        assert result.gate_results["identity"] == "PASS"
        assert result.gate_results["security"] == "PASS"

    def test_security_block(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(tmp_repo, ["crypto/vault.py"], config)
        assert result.decision == "BLOCKED"
        assert result.gate_results["security"] == "BLOCKED"

    def test_allowlist_block(self, tmp_repo: Path):
        config = _config(allowlist=["src/*"])
        result = run_pipeline(tmp_repo, ["deploy/prod.yml"], config)
        assert result.decision == "BLOCKED"
        assert "allowlist" in result.reason.lower() or result.gate_results.get("allowlist") == "BLOCKED"

    def test_kernel_block(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(tmp_repo, ["auth/login.py"], config)
        assert result.decision == "BLOCKED"

    def test_evidence_logged_on_pass(self, tmp_repo: Path):
        config = _config()
        (tmp_repo / ".sworn").mkdir(exist_ok=True)
        run_pipeline(tmp_repo, ["src/main.py"], config)
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.exists()
        assert log.read_text().strip() != ""

    def test_evidence_logged_on_block(self, tmp_repo: Path):
        config = _config()
        (tmp_repo / ".sworn").mkdir(exist_ok=True)
        run_pipeline(tmp_repo, ["crypto/key.py"], config)
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        assert log.exists()

    def test_multiple_blocks_report_first(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(
            tmp_repo, ["crypto/a.py", "auth/b.py"], config
        )
        assert result.decision == "BLOCKED"
        assert "crypto/a.py" in result.reason or "auth/b.py" in result.reason

    def test_empty_file_list_passes(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(tmp_repo, [], config)
        assert result.decision == "PASS"

    def test_threat_kernel_order_deterministic(self, tmp_repo: Path):
        config = _config()
        result = run_pipeline(tmp_repo, ["src/main.py"], config)
        names = [entry["name"] for entry in result.kernel_results]
        assert names == sorted(names)

    def test_threat_legacy_key_layout_blocks_signed_mode(self, tmp_repo: Path):
        legacy_key = tmp_repo / ".sworn" / "signing.key"
        legacy_key.parent.mkdir(exist_ok=True, parents=True)
        legacy_key.write_text("dummy")

        config = _config()
        config.signing_enabled = True
        result = run_pipeline(tmp_repo, ["src/main.py"], config)
        assert result.decision == "BLOCKED"
        assert result.gate_results.get("signing") == "ERROR"
        assert "Legacy signing key layout" in result.reason

    def test_threat_signing_enabled_missing_key_blocks(self, tmp_repo: Path):
        config = _config()
        config.signing_enabled = True

        result = run_pipeline(tmp_repo, ["src/main.py"], config)

        assert result.decision == "BLOCKED"
        assert result.gate_results.get("signing") == "ERROR"
        assert "Signing enabled but signing key is missing" in result.reason

    def test_threat_evidence_write_failure_blocks(self, tmp_repo: Path):
        config = _config()
        (tmp_repo / "readonly").mkdir()
        (tmp_repo / "readonly" / "deep").write_text("blocker")
        config.evidence_log_path = "readonly/deep/evidence.jsonl"

        result = run_pipeline(tmp_repo, ["src/main.py"], config)

        assert result.decision == "BLOCKED"
        assert result.gate_results.get("evidence") == "ERROR"
        assert "Evidence log failure" in result.reason
        assert not (tmp_repo / "readonly" / "deep" / "evidence.jsonl").exists()

    def test_threat_corrupt_existing_evidence_blocks(self, tmp_repo: Path):
        config = _config()
        log = tmp_repo / ".sworn" / "evidence.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("{not-json}\n")

        result = run_pipeline(tmp_repo, ["src/main.py"], config)

        assert result.decision == "BLOCKED"
        assert result.gate_results.get("evidence") == "ERROR"
        assert "Evidence log failure" in result.reason
        assert log.read_text() == "{not-json}\n"
