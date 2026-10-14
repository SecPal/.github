<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Proposed GitHub-native delivery end state

This temporary proposal describes the intended result of the simplification.
It is not an active delivery contract. Existing canonical instructions, required
checks and shared consumers remain effective until their reviewed cutover.
After migration, this proposal will be removed and concise contribution guidance
will live in the established repository documentation.

## Proposed delivery path

The intended delivery path is one branch and pull request for a coherent change.
Draft would be an optional working state, and Ready would request review.
The PR would explain the change and relevant validation; issues would provide
planning records without becoming prerequisites for every delivery.
GitHub reviews and resolved conversations would supply review history without
custom counters, lifecycle journals, receipts or routine attestations.

GitHub would permit merging only after the required candidate checks pass.
The security baseline would retain signed commits, protected main, linear
history, conversation resolution, admin enforcement, disabled force pushes and
branch deletion, and the existing review approval requirements. Automated review
would supply advice rather than a separate delivery state machine.

Applicable build, lint, tests, REUSE/license compatibility and security checks
would remain. Dependency and secret scanning, CodeQL, reviewed immutable action
pins, locked dependencies and least-privilege tokens would continue protecting
the technical change. Product audit trails and release artifact provenance are
separate guarantees, outside the retirement of routine PR ceremony.

## Proposed transition

The migration would remove unconsumed machinery and its exclusive tests,
fixtures, schemas and guides first. Shared paths would stay available until
their actual callers migrate. Required contexts would be changed only after
independent verification, with their producers deleted afterwards.

The accepted [loose-check decision](https://github.com/SecPal/.github/issues/727)
would use strict=false after verifying required candidate checks and native
conflict detection. This would not require a merge queue or promise testing
against every subsequently advanced main commit.

Rollback would restore the previous code and protection together, without
requiring a deleted job. Historical journal branches and GitHub records would
remain available as history, without future delivery readers or writers.
This proposal performs no live protection change or server installation.
