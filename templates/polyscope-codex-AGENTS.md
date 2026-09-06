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

## Delivery continuity and authority

- Perform the relevant full preflight on first entry to a delivery. During the
  same delivery, use delta preflight: refresh only facts whose defined
  invalidators may have occurred and freshly read operation-specific volatile
  state at a critical mutation boundary. A new prompt, internal phase, commit,
  or tool handoff alone invalidates no proof and does not require a complete
  graph, ADR, issue, PR, and CI reread.
- Reuse PR/head-bound, staged-tree/validation, lifecycle CURRENT,
  stable-feedback, and work-graph proof until a relevant head, tree, CURRENT
  publication, feedback/reviewed-head, or native graph mutation invalidates it.
  Keep readiness and merge evidence short-lived and read it at the actual
  boundary. Do not create a freshness database, schema, signer, or daemon.
- Before each lifecycle mutation, derive the canonical operation and exact
  preconditions from authenticated current maintained repository authority.
  Prompt expectations may bind identity, intent, scope, mutation budget,
  acceptance, and stop conditions; treat them as assertions to verify, never as
  lifecycle authority. Fail closed before mutation and report any discrepancy.
- Within current authority, commit, push, Draft PR creation, maintained GitHub
  fallback PR creation, receipt or attestation binding, lifecycle publication,
  eligible Ready transition, bounded provider observation, classification,
  in-contract remediation, eligible thread resolution, conditionally authorized
  merge, and bounded read-back are mechanical checkpoints. Do not request a new
  prompt solely because one was reached.
- A current instruction may conditionally authorize a later exact mutation if
  and only if its freshly evaluated maintained gate passes for the unchanged
  authenticated candidate. This remains explicit current authority. New user
  authority is required for material scope expansion, an independently
  deliverable responsibility, Exceptional Recovery, an unresolved material
  trade-off, or another operation not already authorized.
- Prefer native Polyscope PR creation when exposed. If unavailable, continue an
  already-authorized delivery through the smallest maintained GitHub fallback;
  preserve PR identity and report the actual creation path and whether native
  workspace association is authenticated. Tool availability grants no
  lifecycle authority.

## Automated review terminality

- Do not infer review completion from absent comments or zero threads. A
  configured triggered review provider that is queued, pending, running,
  failed, or indeterminate blocks stable-feedback capture and merge even when
  CI is green and GitHub reports mergeability.
- Capture one stable-feedback batch only after every triggered provider has
  affirmative successful terminal evidence, then classify the complete batch
  before coherent remediation. Relevant later feedback or reviewed-head change
  invalidates that snapshot. Remediation does not authorize a second
  unrestricted external review cycle.
- When a current full-delivery instruction authorizes review completion
  observation, wait inside that invocation at bounded 60-to-90-second intervals
  for at most about 30 minutes. Observe only maintained review-provider status,
  not unrelated hosted CI. On expiry report `REVIEW_NOT_TERMINAL`, the exact
  head, and non-terminal providers without claiming a user decision is needed;
  the same workspace may resume later.
- After remediation changes a candidate, repeat focused validation and the
  final-candidate self-review. For material security or authority changes,
  reassess the design from first principles and actively attempt to defeat the
  final trust boundary. Do not impose that heavyweight audit on an ordinary
  small correction.

## Canonical Work-Graph Execution

- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: before beginning explicitly issue-assigned work within a
  declared SecPal epic or sub-epic, consult the read-only canonical resolver
  from the owning `SecPal/.github` checkout:
  `python3 scripts/secpal-work-graph.py`. Its JSON output is the
  machine-readable graph state under the canonical contract.
- Under `docs/work-graph-contract.md`, the canonical work graph is
  authoritative: start from `show <owner/repo#requested-number>` to inspect
  native observable ancestors. Use the explicitly declared owning scope only
  when that output confirms it as an ancestor, then use
  `show <owner/repo#scope-number>`, `ready <owner/repo#scope-number>`, and
  `next <owner/repo#scope-number>` to report the canonical scope root, READY
  leaves, and canonical NEXT defined by the contract. Under the contract,
  repository-qualified identities name each node's actual repository and may
  span repositories. Under the contract, bare issue numbers require an explicit
  `--repo` and must not be used in this managed command guidance. Under the
  contract, the default NEXT invocation lets the canonical resolver obtain the
  authenticated GitHub viewer identity for executor and claim filtering. Under
  the contract, use
  `validate-issue <owner/repo#requested-number>` for the requested issue's
  derived state and structural findings. If native inputs cannot determine the
  declared scope, or any resolver output is incomplete, report incomplete graph
  input as required by the contract; do not guess from issue prose.
- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: clearly surface whether the requested issue is READY,
  blocked, non-leaf, structurally incomplete, or malformed, and whether it
  differs from canonical NEXT. A body-only relationship mirror is not authoritative
  under the contract and must never govern hierarchy,
  dependencies, sibling order, or scope selection.
- Under `docs/work-graph-contract.md`, run
  `validate-issue <owner/repo#requested-number>` before creating or resuming
  delivery state. Under the contract, continue only when that canonical command
  exits successfully. Under the contract, refuse execution when the requested
  issue is blocked, non-leaf, structurally incomplete, or malformed, and report
  the resolver's exact authoritative rule and graph fact. Under the contract, a
  user-selected issue different from canonical NEXT is still an explicit
  selection, but it never overrides the READY execution boundary.
- Under `docs/work-graph-contract.md`, canonical work-graph semantics are
  authoritative: READY siblings remain parallel and NEXT selects one candidate
  for one executor. Under the contract, do not mutate the graph or create dependencies
  between siblings, or silently substitute another issue for
  the explicit user selection.

## Canonical Work-Graph Replanning

- Delegate all classification and graph-placement semantics to
  `docs/work-graph-contract.md`; do not restate or reinterpret them here.
- When that contract requires a graph change, use the owning `SecPal/.github`
  checkout's `python3 scripts/secpal-work-graph-replan.py plan REQUEST.json`,
  inspect the finite plan, then use
  `python3 scripts/secpal-work-graph-replan.py apply PLAN.json --apply` before
  implementation scope expands. Inspect the exact recovery evidence if an
  invocation stops after a write; use the bounded `recover` command only for a
  known outcome.
- The command requires the exact authenticated actor and unchanged canonical
  state; stale state or graph drift fails closed. Never edit a plan to bypass
  those checks or use this boundary as a generic GitHub mutation command.

## Hard Delivery-PR Gate

- Before presenting a delivery PR as technically complete, run the owning
  `SecPal/.github` checkout's `scripts/secpal-pr-advisory.py --enforce` for that
  PR. Treat its #735 findings as a hard boundary and refuse delivery until they
  are clear under `docs/work-graph-contract.md`.
- Delegate graph state to the canonical resolver and lifecycle/disposition
  validity to the maintained lifecycle authority. Do not infer either from PR
  prose, reset lifecycle counters, or restart review after the stable-feedback
  stop condition.
- Supply explicit judgment observations only when review evidence establishes
  the violated contract rule. An independently deliverable second responsibility
  requires graph-first replanning before implementation continues; `--enforce`
  does not claim to infer that architectural judgment from source. Test, line,
  and mutation counts may guide review but never constitute a finding by
  themselves.

## Work-graph semantics

- Node types, native hierarchy and dependency meaning, sibling order, `READY`,
  deterministic `NEXT` selection, replanning, and evidence rules come from the
  canonical contract in `SecPal/.github`, `docs/work-graph-contract.md`.
- These coordination rules layer on top of that contract and never redefine it.
  Where a session-local instruction and the contract disagree about work-graph
  semantics, the contract governs.
