# Sworn Phase-0 Evidence Manifest Template

Manifest Type: Phase-0 pre-tag evidence
Release Version:
Signed Tag: pending phase1
Tag SHA: pending phase1
PyPI Publish Ref: pending phase1
Build Date (UTC):
Maintainer:
Phase-0 Start Commit:
Phase-0 Branch:

## Artifact Inventory

- install.log
- pytest-full.log
- validate_governance.log
- bootstrap_gov.log
- full_verification.log
- pip-bootstrap.log
- sworn-cli.log
- sworn-module-help.txt
- env-version.txt
- env-uname.txt
- pip-freeze.txt
- phase0-start-sha.txt
- working-tree-at-start.txt
- build-timestamp-utc.txt
- dist-shas.txt
- twine-check.log
- evidence-package.tar.gz
- evidence-package.sha256

## Assertions

- Working tree clean before release run
- `python3 -m pip install .[dev,signing]` passed in clean venv
- `python3 -m pytest tests -q --tb=short` passed
- External governance gate (`SWORN_GOVERNANCE_VALIDATE_CMD`) passed, or recorded as skipped if unset
- External bootstrap and full verification gates passed, or recorded as skipped if unset
- `python3 -m build --no-isolation` succeeded
- Release evidence reviewed and retained out-of-repo before signed tag creation
- Signed tag and publish identity must be recorded during phase1 in release notes or external operator log
- Release evidence folder hash recorded

## Hashes

Evidence bundle SHA256:
- evidence-package.sha256:

## Validation Notes

- Any deviation between implementation and signed scope documents is a defect.
- Repo-wide policy drift must be documented before external use.
