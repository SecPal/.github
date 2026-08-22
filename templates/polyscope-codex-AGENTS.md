<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Polyscope Linked-Workspace Coordination

Apply these rules only when the session says it is running inside Polyscope.

## Linked Repositories

- Treat every entry in `workspace_roots` as a separate repository and execution
  root. A linked workspace makes those roots available; it does not move the
  main agent or start an agent in each repository.
- The main agent owns cross-repository sequencing, shared contract decisions,
  integration checks, and the consolidated status.
- Delegate only materially independent repository scopes when parallel
  execution is useful. Assign one owner per affected root, include the exact
  root as that owner's working directory, and keep dependency-ordered work
  sequential. The main agent may own a repository scope directly.
- Do not implement a sibling repository's scope from the primary repository
  merely because its files are reachable by absolute path.
- Partition an Autopilot plan by repository. Each story must name its workspace
  root, dependencies, acceptance criteria, and validation commands.

## Planning Versus Execution

- Determine the active mode and sandbox before using tools. A Polyscope Plan
  session is analysis-only and must not attempt any side effect: no branch change,
  file change, commit, push, GitHub write, or side-effecting connector call.
  Read-only inspection is allowed when it helps produce the plan.
- If the requested outcome requires issues, branches, or other setup, describe
  their exact repositories, contents, links, and ordering in the plan. Put
  approved setup before dependent implementation work.
- A cancelled, denied, or unauthenticated tool result does not prove that the
  user cancelled an action or that stored credentials are invalid. Report the
  actual sandbox, approval, network, or authentication evidence.
- Never attribute that denial to the user unless the user explicitly cancelled
  it.
- After plan approval, select **Use plan for Autopilot** and continue only in
  the resulting writable execution context. Verify that context before the
  first side effect, then execute the approved stories.
- Preserve a branch or worktree already provisioned by Polyscope. Do not switch
  to `main`, create another worktree, or rename the branch unless the approved
  story specifically requires it.

## GitHub Diagnostics

- Distinguish authentication failure from sandboxed networking. Failure to
  reach `api.github.com` does not prove that the stored token is invalid.
- Validate `gh auth status` only in a network-capable Autopilot or Work context
  before treating a GitHub failure as an authentication problem.

## Hosted CI isolation

- Do not read, monitor, poll, wait for, summarize, or gate work on GitHub-hosted CI unless the user explicitly requests CI inspection, check status, merge readiness, or merge authorization in the current instruction.
- A previous request, repository convention, push, PR creation, review-remediation request, or thread-resolution request is not sufficient authorization.
- Local push hooks and local validation remain allowed. GitHub-hosted CI is not
  part of Polyscope execution unless the current instruction explicitly requests
  it. They remain required where repository instructions require them. Push and
  PR creation never imply CI-observation authorization.
- A push never authorizes hosted-CI inspection. After an ordinary push, verify
  only the local and remote branch heads, local validation, signature, and clean
  worktree, then stop.
- Draft PR creation never authorizes hosted-CI inspection. After creating a
  Draft PR, verify its number, base, head branch, and head SHA, report local
  validation, and stop.
- Never wait, poll, sleep, repeat a status read, or keep a Polyscope run active
  for GitHub Actions, CodeQL, check suites, status contexts, workflow runs, or
  merge readiness. An explicitly requested status inspection performs at most
  one bounded current-state read, reports that state, and stops.
- Resolution of fixed review comments is independent of GitHub-hosted CI. It
  must not depend on Required Checks, CodeQL, mergeability, branch protection,
  PR reactions, or unrelated feedback.
- Merge remains a separate operation requiring explicit current user
  authorization.

## Canonical Work-Graph Advisory

- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: before beginning explicitly issue-assigned work within a
  declared SecPal epic or sub-epic, consult the read-only canonical resolver
  from the owning `SecPal/.github` checkout:
  `python3 scripts/secpal-work-graph.py`. Its JSON output is the
  machine-readable graph state under the canonical contract.
- Under `docs/work-graph-contract.md`, the canonical work graph is
  authoritative: start from `show <requested issue>` to inspect native
  observable ancestors. Use the explicitly declared owning scope only when
  that output confirms it as an ancestor, then use `show <scope>`,
  `ready <scope>`, and `next <scope> --executor <current executor>` to report
  the canonical scope root, READY leaves, and canonical NEXT defined by the
  contract. Under the contract, use `validate-issue <requested issue>` for the
  requested issue's derived state and structural findings. If native inputs
  cannot determine the declared scope, or any resolver output is incomplete,
  report incomplete graph input as required by the contract; do not guess from
  issue prose.
- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: clearly surface whether the requested issue is READY,
  blocked, non-leaf, structurally incomplete, or malformed, and whether it
  differs from canonical NEXT. A body-only relationship mirror is not authoritative
  under the contract and must never govern hierarchy,
  dependencies, sibling order, or scope selection.
- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative and advisory, not a hard block: when the user explicitly
  selects a requested issue different from NEXT, report the requested state and
  canonical selection. The explicit user selection is an advisory override
  under the contract; continue with the requested issue. Under the contract, give the
  same prominent reporting for a blocked, non-leaf, malformed, or incomplete
  explicit selection; never call it READY unless the resolver does.
- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: READY siblings remain parallel and NEXT selects one candidate
  for one executor. Under the contract, do not mutate the graph or create dependencies
  between siblings, or silently substitute another issue for
  the explicit user selection.

## Work-graph semantics

- Node types, native hierarchy and dependency meaning, sibling order, `READY`,
  deterministic `NEXT` selection, replanning, and evidence rules come from the
  canonical contract in `SecPal/.github`, `docs/work-graph-contract.md`.
- These coordination rules layer on top of that contract and never redefine it.
  Where a session-local instruction and the contract disagree about work-graph
  semantics, the contract governs.
