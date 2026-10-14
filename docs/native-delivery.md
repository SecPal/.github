<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# GitHub-native delivery

Status: proposed cutover. Existing required checks and shared consumers remain
active until their replacements have been independently verified. This document
does not authorize changes to live protection or repositories outside `.github`.

## Delivery contract

Use one branch and pull request for a coherent change. Draft is optional working
state; Ready requests review. The pull request explains the change and relevant
validation. Issues are useful planning records, not prerequisites for every PR.
GitHub reviews and resolved conversations provide review history without local
review counters, persistent lifecycle journals, receipts or routine attestations.

Merge through GitHub only after required checks pass on the current candidate.
Keep signed commits, protected main, linear history, conversation resolution,
admin enforcement, and disabled force pushes and branch deletion. Keep existing
review approval requirements until an administrator makes an explicit decision;
never impose an approval count that the available independent reviewers cannot
satisfy. Automated review supplies advice, not a separate delivery state machine.

Require applicable build, lint and tests, REUSE/license compatibility, and
security checks appropriate to the repository. Preserve CodeQL, dependency and
secret scanning, privacy boundaries, and release artifact integrity. Pin third
party actions to reviewed commits, use least-privilege tokens and locked
dependencies. Product audit trails and release provenance are outside the
retirement of routine PR evidence.

## Cutover safety

Inventory the eight repositories and record actual workflow and runtime callers.
First remove unconsumed delivery machinery and its exclusive tests, fixtures,
schemas and documentation. Keep shared entry points with proven active callers.
Run native replacements on the same candidate while existing mandatory checks
remain enabled. Have an independent reviewer verify successful and failing cases,
including tampered or unsigned commits and failing security checks.

Only then may an administrator replace redundant required contexts with verified
native rules or CI contexts. Remove each old workflow after protection no longer
requires its context and all consumers have migrated. Preserve strict current-base
validation until merge-queue validation has been verified where supported. Save
before/after protection snapshots; rollback restores the previous contexts and
code together. Never leave protection requiring a deleted job.

Keep historical journal branches and GitHub records as history, with no future
delivery dependency. Do not delete records, rewrite published history, reinstall
retired hooks, or publish server changes as part of this first PR.
