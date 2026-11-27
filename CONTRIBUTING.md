<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Contributing to SecPal

Read the [Code of Conduct](CODE_OF_CONDUCT.md) and start in the repository that
owns the work. The [architecture navigation](docs/architecture.md) lists those
owners. Report vulnerabilities through the [security policy](SECURITY.md).

## Development setup

For an assigned Herdr workspace, use the
[workspace setup](WORKSPACE_SETUP.md). In a local clone, follow the target
repository's README and agent instructions for language versions, dependencies
and validation.

For this repository, use Git, system-installed Node.js 26 and npm, Python 3,
pre-commit and REUSE. Install the Python validation dependencies in a virtual environment
and set up the hooks from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements/requirements.txt
./scripts/setup-pre-commit.sh
```

Run focused checks while editing and use `./scripts/preflight.sh` for the complete
local suite when applicable. The Evidence Architecture validator accepts the
system Node executable or the maintained GitHub runner tool cache. Herdr's
user-toolchain path alone is insufficient for that check. A local container
with a system Node installation can run the same preflight against a copy of
the candidate tree. See [Git hook setup and troubleshooting](docs/HOOK_SETUP_TROUBLESHOOTING.md)
and the [AI instruction validation contract](docs/VALIDATION_SYSTEM.md) for
their respective checks.

## Pull requests

Follow [issue-first planning](docs/planning.md) and the
[native WorkGraph contract](docs/work-graph-contract.md). Every PR must address exactly ONE logical topic.
Use the PR template, link the issue the PR completes, and state validation
results. Follow the target repository's test guidance and deliver through
GitHub reviews, required checks and protected merge.

### PR size recommendation

600 changed lines is a reviewability recommendation. Keep a coherent change
with its tests and documentation. Split independent work when that makes
review clearer.

### Spike branch policy

Use `spike/` branches for short-lived experiments. The shared Node test workflow
skips spike branches. Bring any result intended for `main` through a regular
topic branch, with the applicable tests and protected delivery.

## Signing commits

Use the existing SSH signing identity and configuration. Verify the local
commit with `git verify-commit HEAD`. GitHub must verify every PR commit.

A new signed commit does not validate earlier unsigned history.
If the PR contains unverified commits, start a replacement branch from
protected `main` and carry forward the reviewed changes as signed commits.
Link the original PR to preserve its review history.

## Licensing and contributor agreement

Follow the [licensing policy](docs/licensing-policy.md) for SPDX, REUSE and
third-party notices. The [Contributor License Agreement](CLA.md) defines the
contributor grant and describes how to sign it. The maintainer and succession
process are defined in [GOVERNANCE.md](GOVERNANCE.md).
