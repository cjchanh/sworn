# Sworn Deployment Model

Sworn has two enforcement surfaces:

1. Local commit-time gating through the repository's effective Git pre-commit hook.
2. CI diff gating through `sworn ci-check`.

These surfaces do different jobs.

## Enforcement Contract

Local hooks are a developer fast-fail mechanism.
They improve feedback speed and catch obvious violations before code leaves a workstation.

CI is the authoritative shared enforcement surface.
For a team to claim fail-closed commit governance, the CI job that runs `sworn ci-check` must be a required status check on protected branches.

## Required Team Controls

Use all of the following for production deployment:

- Protected branches for all merge targets.
- Required status checks that include the Sworn CI gate.
- `actions/checkout@v4` with `fetch-depth: 0`.
- A pinned Sworn action ref and pinned package version.
- Review controls that prevent direct pushes from bypassing CI policy.

## Important Limits

- `git commit --no-verify` bypasses local pre-commit hooks.
- Local hook installation does not replace branch protection.
- Actor identity is derived from Git metadata and environment variables.
- Repo-local signing provides tamper-evident integrity, not organizational PKI attestation.

## Supported Git Topologies

Sworn supports:

- standard Git repositories
- repositories using `core.hooksPath`
- Git worktrees

Hook installation and status resolve Git's effective hooks directory instead of assuming `.git/hooks`.

## Recommended GitHub Actions Shape

```yaml
name: Sworn Gate
on: [pull_request]
jobs:
  sworn:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: CentennialDefenseSystemsInc/sworn@0.4.0
        with:
          version: "0.4.0"
```

Make the resulting job a required status check before merge.
