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

## Advisory work-graph selection

Before the first implementation side effect, apply this procedure only when the
session says it is running inside Polyscope and the current workspace has a
structured issue assignment:

1. Read the configured Polyscope database in read-only mode and resolve the
   current workspace path canonically. Require exactly one active
   `worktrees.path` record whose path resolves to that same canonical path, join
   its `repositories.name`, and require both `issue_number` and `issue_url`. If
   zero or more than one active record matches, report that the structured
   assignment is unavailable or malformed, do not select or guess a row,
   record, or identity, and preserve the existing behavior. Treat either case as
   no structured issue assignment available. For the unique record, parse
   `issue_url`; its repository and issue number must match
   `repositories.name` and `issue_number`. If they disagree, report an
   inconsistent, malformed structured assignment and do not choose either
   identity. Only a consistent repository and issue are explicitly selected
   work. Never infer selection from a branch name, free-form task prose, issue
   body, or guessed issue number.
2. Locate `scripts/secpal-work-graph.py` through the registered
   `SecPal/.github` repository path. For every resolver invocation, capture
   stdout and the exit status. When the status is 0 or 1 and stdout parses as a
   valid JSON envelope whose schema is `secpal-work-graph/v1`, consume and
   surface that result. Status 1 is a meaningful reported result, not a generic
   command failure. Status 2 or 3, missing or invalid JSON output, or a schema
   other than `secpal-work-graph/v1` means the resolver invocation is unavailable
   or failed; report that condition and do not invent graph state. The semantics
   remain solely in `docs/work-graph-contract.md`; do not derive them
   independently.
3. Run `validate-issue` for the requested issue, then `show` to inspect its
   resolver-provided node role and native ancestor chain; do not guess or infer
   the node role from an issue title, prose, or body mirror. If the requested
   issue is a non-leaf, use the requested issue itself as scope. This includes
   an epic or sub-epic; for a root epic, scope is the requested issue itself.
   For a non-leaf, `ready` and `next` describe its descendant delivery leaves.
   If the requested issue is a leaf with a containing native epic or sub-epic,
   use the nearest containing native epic or sub-epic as its advisory scope. For
   example, for `#664` → `#667` → `#672`, use scope `#667`; do not automatically
   climb to `#664`. For a standalone root leaf, scope is the requested issue
   itself. If the resolver cannot establish the node role or required native
   containment completely and consistently, surface its fail-closed result and
   do not guess a scope, `ready`, or `next`.
4. For a resolved scope, run `ready` and `next`. Let `next` use its authenticated
   GitHub executor default unless the session provides a different current
   authenticated executor, in which case pass that identity with `--executor`.
   Visibly report the requested issue and its exact resolver state or reasons,
   the scope, the `ready` set, canonical `next`, and whether selection is
   aligned.

Interpret the resolver output only as an advisory selection result:

- If the requested issue is canonical `next`, report that it is aligned and
  continue normally.
- If the requested issue is `ready` but another leaf is `next`, report the
  advisory mismatch, the requested issue, full `ready` set, and canonical
  `next`. As advisory rollout behavior, continue the explicitly selected issue;
  do not silently switch work.
- If the requested issue is blocked, surface its blocker and exact reason, plus
  the `ready` set and `next` where resolvable. Do not describe it as `ready`.
- If it is a non-leaf, surface that status and the descendant `ready` set and
  `next`; do not present the epic as a delivery leaf.
- If it is structurally incomplete, surface the exact resolver reason and do
  not invent `ready`. If resolution is malformed, inaccessible, or incomplete,
  surface the fail-closed result and do not guess `ready` or `next`.

Structured assignment remains the explicitly selected work during this
advisory rollout behavior. A mismatch, blocked issue, or non-leaf does not by
itself cause a hard work-graph refusal: continue the selected issue after the
visible advisory, subject to every independent security, sandbox, scope, and
execution-mode restriction. Hard enforcement belongs to #675.

Keep `ready` siblings parallel: `next` is ranking for one executor, not graph
topology, blocking, or a dependency. Do not add dependencies, do not reorder
siblings, and do not otherwise mutate the graph. Body-only pseudo-relationships
are never execution inputs, including `Parent:`, `Order:`, `Blocked by:`, and
Markdown child lists.

## Work-graph semantics

- Node types, native hierarchy and dependency meaning, sibling order, `READY`,
  deterministic `NEXT` selection, replanning, and evidence rules come from the
  canonical contract in `SecPal/.github`, `docs/work-graph-contract.md`.
- These coordination rules layer on top of that contract and never redefine it.
  Where a session-local instruction and the contract disagree about work-graph
  semantics, the contract governs.
