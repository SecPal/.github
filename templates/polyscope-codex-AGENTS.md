<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Polyscope linked-workspace coordination

Apply these rules only when the session says it is running inside Polyscope.

## Linked repositories

- Treat every entry in `workspace_roots` as a separate repository and execution
  root. A linked workspace makes those roots available; it does not by itself
  move the main agent or start an agent in each repository.
- When a request or approved plan spans multiple linked repositories,
  explicitly delegate independent repository scopes to subagents. Assign one
  owner per affected root and include that exact root as the subagent's working
  directory. Keep dependency-ordered scopes sequential; run independent scopes
  in parallel.
- The main agent owns cross-repository sequencing, shared contract decisions,
  integration checks, and the consolidated status. Do not implement a sibling
  repository's scope from the primary repository merely because its files are
  reachable by absolute path.
- Partition a plan intended for Autopilot by repository. Every story must name
  its workspace root, dependencies, acceptance criteria, and validation
  commands. After plan approval, explicitly dispatch each story in its named
  root.

## Planning versus execution

- Determine the active mode and sandbox before using tools. A Polyscope Plan
  session is analysis-only and must not attempt any side effect: no branch
  rename, file change, commit, push, GitHub issue creation, or side-effecting
  connector call. Read-only inspection is allowed when it helps produce the
  plan.
- If the requested outcome requires an EPIC, sub-issues, branches, or other
  setup, describe their exact repositories, contents, links, and ordering in
  the plan. Make their creation the first dependency-ordered Autopilot stories,
  before implementation stories.
- A tool result such as cancelled, denied, or unauthenticated does not prove
  that the user cancelled an action or that stored credentials are invalid.
  Never attribute that denial to the user unless the user explicitly cancelled
  it. Report the actual sandbox, approval, network, or authentication evidence.
- After plan approval, select **Use plan for Autopilot** and continue only in the
  resulting writable execution context. Verify that context before the first
  side effect, then execute all approved stories instead of remaining in the
  planning workspace.
- In Autopilot, rename the branch separately in every affected repository before that
  repository's first write, then verify it with
  `git status --short --branch`.

## GitHub diagnostics

- Distinguish authentication failure from sandboxed networking. Failure to
  reach `api.github.com` does not prove that the stored token is invalid.
- Validate `gh auth status` only in a network-capable Autopilot or Work context
  before treating a GitHub failure as an authentication problem.
