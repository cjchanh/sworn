"""Static checks for release-facing metadata."""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_action_pins_pypi_install_to_release_version():
    version = _project_version()
    content = (ROOT / "action.yml").read_text()

    assert "latest" not in content
    assert f'default: "{version}"' in content
    assert "pip install sworncode==${{ inputs.version }}" in content


def test_example_workflow_uses_real_release_tag():
    version = _project_version()
    content = (ROOT / "examples" / "sworn-ci.yml").read_text()

    assert f"CentennialDefenseSystemsInc/sworn@{version}" in content


def test_gitignore_covers_active_and_legacy_private_keys():
    content = (ROOT / ".gitignore").read_text()

    assert ".sworn/keys/active.key" in content
    assert ".sworn/signing.key" in content


def test_package_metadata_does_not_advertise_unshipped_soc2_surface():
    content = (ROOT / "pyproject.toml").read_text()

    assert "soc2" not in content


def test_config_template_points_to_repo_backed_docs():
    content = (ROOT / "src" / "sworn" / "config.py").read_text()

    assert "docs/config.md" in content
    assert "sworncode.dev/docs/config" not in content
