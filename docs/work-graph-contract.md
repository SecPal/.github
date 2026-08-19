<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Work-Graph And Engineering-Governance Contract

## Status

Canonical. This document is the single organization-wide definition of how
SecPal work is structured, ordered, selected, delivered, and evidenced.

Any repository baseline or Polyscope runtime instruction set that states
work-graph semantics — `AGENTS.md`, and any `.github/copilot-instructions.md` or
`.github/instructions/*.instructions.md` overlay that touches them — MUST
reference this contract instead of redefining them locally. A document that
states none of these semantics, such as an independent review profile, needs no
delegation. Which baselines have already adopted it is rollout state owned by
section 13, not a claim this document makes.

This document defines semantics only. It intentionally contains no tooling, no
schema, and no automation. Read-only graph resolution and advisory validation are
delivered separately under the parent epic.

## Reading This Document

- **MUST** / **MUST NOT** are binding. A violation is a defect in the work, not a
  style preference.
- **SHOULD** / **SHOULD NOT** are strong defaults. Deviating requires a stated
  reason in the issue or pull request.
- **MAY** marks explicitly allowed options.

Rules here come in two kinds, and confusing them is how automation ends up
inventing policy:

- **Machine-derivable rules** — sections 1, 3, and 4. Given identical inputs from
  the categories in section 1.1, two implementations MUST derive identical
  results. Machine-derivable does not mean graph-state-only: section 1.2 names
  the exact inputs each derived value reads.
- **Judgment rules** — sections 2 and 5 to 12. They guide a human or an agent
  deciding scope, evidence, and design. Automation MAY report a suspected
  violation; it MUST NOT silently decide one.

## 1. Source Of Truth

GitHub-native issue data is authoritative. Everything else is a mirror: Markdown
task lists, `Parent:` / `Order:` / `Blocked by:` lines in issue bodies,
project-board fields, roadmap documents, plan files, and agent-local notes.

Rules:

- A mirror MUST NOT be treated as graph state. It never makes a node ready,
  blocked, complete, or selectable.
- When a mirror and native data disagree, native data wins and the mirror MUST be
  corrected or deleted.
- Bootstrap exception: while native links are not yet wired for a node, textual
  `Parent:`, `Order:`, and `Blocked by:` lines MAY carry the intent, and they MUST
  be replaced by native links as soon as the links can be created.
- Duplicating graph state into Markdown SHOULD be avoided entirely. Duplicated
  state is the drift source this contract exists to remove.

### 1.1 Input Categories

Every machine-derivable rule reads from these five categories and from nothing
else:

- **Native graph state** — issue open/closed state and closure reason, native
  parent/sub-issue relationships, native issue dependencies, native sibling
  order.
- **Structural issue content** — only presence facts needed for execution,
  currently whether canonical acceptance criteria are structurally present
  (section 4.1). What those criteria _say_ is judgment, never an input here.
- **Selection metadata** — the recognized priority labels of section 4.3 and
  nothing else. Milestone and assignee are not inputs to any derived value.
- **Execution coordination** — the valid execution claims of section 4.2.
- **Invocation context** — the scope root, and the current executor identity
  wherever claim filtering needs it.

### 1.2 Declared Inputs Per Derived Value

| Derived value | Inputs                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| `BLOCKED`     | native graph state                                                                                           |
| `DONE`        | native graph state                                                                                           |
| `READY`       | native graph state + structural issue content                                                                |
| `ACTIVE`      | everything `READY` reads + valid execution claims                                                            |
| `NEXT`        | scope root + executor identity + native graph state + structural issue content + selection metadata + claims |

Two implementations given identical inputs MUST derive identical `BLOCKED`,
`READY`, `DONE`, `ACTIVE`, and `NEXT`. Any other input is a hidden input and a
defect in the implementation, not a permitted extension.

### 1.3 Precedence

When two sources disagree, resolve in this order (highest first):

1. Security, privacy, legal, and licensing invariants.
2. Native graph state, for every question about topology and progress.
3. Accepted ADRs.
4. The target node's content: its contract, acceptance criteria, and non-goals.
5. This contract.
6. Repository baselines and stack-specific overlays.
7. Non-canonical mirrors: boards, docs, plans, generated summaries.

Levels 2 and 4 never compete, because they answer different questions: level 2
answers where a node sits and whether it is done, level 4 answers what it
promises. A body that contradicts graph state is a mirror to delete, not a
competing source.

Two further consequences make this list usable instead of merely ordered:

- Levels 3 and 4 answer **what to build**; levels 5 and 6 answer **how work is
  structured, selected, and evidenced**. A single node MUST NOT redefine level 5
  or level 6 for itself, and this contract MUST NOT be read as overriding a
  node's declared deliverable.
- A node whose scope contradicts an accepted ADR is mis-specified. Change the ADR
  or change the node; do not deliver the contradiction and do not silently prefer
  the newer text.

A repository baseline MAY add stricter, non-contradictory local rules. It MUST
NOT redefine node types, edge semantics, `READY`, `NEXT`, the epic threshold, or
the evidence rules below.

## 2. Node Types

The graph has exactly three node roles. A node's role follows from what it
contains, not from the label it happens to carry.

### 2.1 Epic

A coordination node with children.

- An epic MUST NOT be delivered by a pull request. It has no implementation
  contract of its own.
- An epic defines goal, acceptance criteria, non-goals, and its child work plan.
- An epic MAY contain leaves, sub-epics, or both.
- An epic is never `READY` and never `ACTIVE` (section 4.1). Whether it may close
  is governed by section 6.3.

### 2.2 Sub-Epic

An epic whose parent is an epic. It exists to bound one coherent phase, one
repository scope, or one responsibility cluster of a larger epic.

- A sub-epic follows every epic rule at every depth GitHub supports natively, and
  every rule in this contract recurses: a sub-epic of a sub-epic behaves exactly
  like any other epic.
- The graph MUST stay inside GitHub's native limits, currently up to 100
  sub-issues per parent and up to eight levels of nested sub-issues. A plan that
  would exceed either limit MUST be restructured or flattened; inventing custom
  hierarchy storage to hold it is prohibited, because native containment is the
  only authoritative hierarchy.
- A sub-epic SHOULD exist when an epic would otherwise mix unrelated
  responsibilities, span more than one repository per phase, or carry more
  children than a reviewer can hold in one view (about seven is a practical
  ceiling, not a hard limit).

### 2.3 Leaf Delivery Issue

A node without children. It is the only node a pull request may close.

Issue templates call these nodes sub-issues. A sub-issue is a leaf while it has
no children and becomes a sub-epic once it gains them, so the template wording
and this contract describe the same node under different names.

- A leaf MUST carry exactly one contract (see section 5).
- A leaf MUST have acceptance criteria concrete enough to be falsified by
  evidence. Whether they are concrete enough is review judgment; `READY` tests
  only that they are present (section 4.1).
- A leaf that turns out to carry more than one contract MUST be promoted to a
  sub-epic (see section 7.3) rather than absorbing the extra scope.

### 2.4 Epic Threshold

The unit of decomposition is the **contract**, not the pull-request count and not
diff size. This subsection supersedes every earlier repository wording that
counted pull requests instead.

An epic MUST be created before implementation when any of the following holds:

- the work contains two or more independently deliverable contracts,
- the work sequences changes across more than one repository,
- the work has distinct phases whose intermediate states are separately
  reviewable and separately mergeable,
- the work cannot be reviewed safely as one coherent topic.

An epic is NOT required when:

- the work is one contract that merely might need mechanical follow-up pull
  requests such as review fixes, a revert, a rollforward, or a formatting pass,
- a further extension is conceivable but not planned,
- the change is large in lines but singular in contract and reviewable as one
  topic.

Tie-break: if, after applying this test, it is genuinely unclear whether the work
holds one contract or several, create the epic. The doubt that triggers this
tie-break MUST be doubt about contract count. Doubt about pull-request count,
diff size, or duration does not by itself require an epic.

## 3. Edges

### 3.1 Containment (Parent / Sub-Issue)

Native parent/sub-issue links express containment only. A node's **ancestors**
are its parent and, transitively, that parent's ancestors, up to the root.

- Containment MUST NOT be read as ordering.
- Containment MUST NOT be read as blocking. A child is not blocked by its parent,
  and siblings are not blocked by each other through containment.
- A node MUST NOT have more than one parent.
- A node inside an epic MUST be attached to it natively. A standalone leaf that
  needs no epic under section 2.4 is a root node and needs no parent; being
  parentless is not drift.
- Containment MAY cross repositories.

### 3.2 Dependency (Blocked By / Blocks)

Native issue dependencies are the only hard blockers in the graph.

A dependency edge `A blocked by B` is justified only when A cannot be implemented
or its contract cannot even be defined until B's output is merged. Typical valid
grounds:

- A consumes an interface, schema, or contract that B introduces,
- A's acceptance criteria are unverifiable until B exists,
- B changes the invariant ownership or trust boundary that A must respect,
- B is an intentional rollout or release gate, meaning A must not reach users or
  other repositories before B lands.

A rollout gate MUST say so in the dependent node, because a gate is a decision
rather than a technical impossibility and a later reader cannot otherwise tell
the two apart.

A dependency edge MUST NOT be used to express taste, review convenience, a
preferred narrative order, or a wish to avoid merge conflicts.

- Dependencies MAY cross repositories. A cross-repository target MUST be
  identified by its fully qualified issue URL, or an equivalent
  repository-qualified canonical identity, and the relationship MUST remain a
  native GitHub issue dependency.
- If a dependency target cannot be read or resolved, section 3.5 applies and
  resolution fails closed. A native dependency that cannot be created or read
  MUST NOT be replaced by a `Blocked by:` line in a body or by any other mirror.
- GitHub links at most 50 issues per relationship type, so a node carries at most
  50 `blocked by` and 50 `blocks` edges. A plan needing more MUST be restructured,
  for example by depending on an epic that aggregates the prerequisites. Creating
  a second dependency store is prohibited.
- Dependencies are never inherited. A child is unaffected by an edge on its
  parent, and a parent is unaffected by an edge on its child; each node is
  blocked only by its own edges. Every blocker is an explicit native edge.
- A dependency MAY target an epic. The same satisfaction rule applies to every
  node type.
- A dependency is satisfied when, and only when, its target is closed with the
  native closure reason `completed`. Any other closure reason, including
  `not planned` and `duplicate`, leaves the dependency unsatisfied.
- Superseded work is closed as `not planned` and the edge is re-pointed at the
  successor. Closing something as superseded is therefore never a way to satisfy
  a dependency by wording.
- Removing an unsatisfied edge is allowed only after confirming that the
  dependent node's contract no longer needs that output.

### 3.3 Sibling Order

Native sub-issue order inside a parent expresses preferred execution order.

- Sibling order is advisory. It biases selection and MUST NOT block execution.
- An executor MAY start any `READY` leaf regardless of its sibling position.
- `Order: <n>` text in an issue body is a bootstrap mirror of native order only.

### 3.4 Real Blockers Versus Preferred Ordering

This distinction is binding, because conflating the two stalls parallel work:

- **Real blocker**: a native dependency edge. It removes the node from the
  executable set.
- **Preferred ordering**: sibling order. It changes selection rank and nothing
  else.

Anything not expressed as a dependency edge is preference. Correcting a
misclassification means moving it between the two, never leaving it in both
(sections 7.1 and 7.4).

### 3.5 Cycles And Malformed Graphs

- The dependency graph MUST be acyclic.
- A node inside a dependency cycle is not `READY`, and neither are the nodes that
  depend on it. Resolution fails closed: a cycle is a replanning trigger, never a
  reason to ignore the edges.
- A leaf with a missing, inaccessible, or unresolvable dependency target is not
  `READY`.
- Containment MUST also be acyclic. A node MUST NOT be its own ancestor. A node
  inside a containment cycle is malformed: it is not `READY`, and resolution
  fails closed until the cycle is broken.
- A node whose native parent, or any ancestor needed to evaluate `READY` or path
  order, cannot be resolved is malformed in the same way: it is not `READY` and
  resolution fails closed. An inaccessible parent is not the same as no parent,
  so such a node MUST NOT be treated as a standalone root leaf, and no mirror
  hierarchy may stand in for it. This applies recursively to every required
  ancestor.

## 4. States, Executable Sets, And `NEXT`

### 4.1 Derived States

Only open/closed is native. All other states are derived and MUST NOT be
duplicated into Markdown. They are predicates rather than a mutually exclusive
lifecycle, so a node may satisfy several at once; only `READY` gates selection.

- **BLOCKED** — true only when the node is open **and** at least one of these
  holds: it has an unsatisfied dependency, it participates in a dependency cycle,
  or one of its dependency targets is missing, inaccessible, or otherwise
  unresolvable. A closed node is never `BLOCKED`. Malformed containment is not
  `BLOCKED` either; it is the separate fail-closed condition of section 3.5.
- **READY** — an open leaf with no children, no unsatisfied dependency, no cycle,
  only open ancestors, and a structurally complete contract. A closed ancestor
  above an open leaf is graph drift: the ancestor was closed before its scope was
  finished, so the leaf stays unexecutable until the ancestor is reopened or the
  leaf is re-parented.
- **ACTIVE** — a `READY` leaf carrying a valid execution claim (see section 4.2).
  Deciding it therefore needs everything `READY` needs plus the claims; the claim
  itself names the executor, so current executor identity is required only to ask
  whether the claim is someone else's, which is what `NEXT` does. Assignment alone
  MUST NOT make a leaf `ACTIVE`, because an assignee records ownership rather than
  execution, and one maintainer routinely owns many leaves while executing one.
- **DONE** — a node closed as `completed`. Any other closure reason means the
  node was abandoned, duplicated, or superseded, which is a valid outcome but not
  a delivery, and it satisfies no dependency (section 3.2). `DONE` is a state
  predicate, not proof: closing an undelivered leaf as `completed` makes it `DONE`
  while violating section 6.1, so a resolver reports the state faithfully and
  governance validation reports the violation.
- **Reopening** returns a node to open. It is then evaluated exactly like any
  other open node, it is no longer `DONE`, and every dependent it had satisfied
  becomes `BLOCKED` again. Reopening is therefore a graph change, not a
  formality, and its effect on dependents MUST be checked before work continues.
- An epic is never `READY` and never `ACTIVE`. An epic is closable only under
  section 6.3.

`BLOCKED` and `DONE` read native graph state only. `READY` additionally reads the
structural issue content defined below, and nothing else. `ACTIVE` is not a graph
state at all: it belongs to execution coordination (section 4.2) and never
changes the other three. Section 1.2 remains the authoritative input list.

**Structurally complete** means the body contains a qualifying acceptance-criteria
heading whose section holds at least one non-empty block before the next heading
of any level.

The candidate MUST be a real top-level ATX heading of the body read as Markdown,
as a standards-compliant parser reports it. Text that only looks like a heading
does not qualify: a heading inside a fenced or indented code block is code, a
heading inside a blockquote or any other container block belongs to that
container, and bold text or a sentence mentioning the phrase is neither. This
specification states the semantic result only; choosing the parser is #669 work,
and hand-rolling one would violate section 12.1.

Once a real heading is identified, it qualifies when this exact procedure yields
`acceptance criteria`:

1. Take the heading's text content, without the leading `#` characters.
2. Remove Unicode whitespace from both ends.
3. Remove one leading `✅` if present, then remove Unicode whitespace from both
   ends again. `✅` is the only decorative prefix recognized, because it is the
   one the canonical issue forms emit.
4. Remove one trailing `:` if present, then remove trailing Unicode whitespace.
5. Compare ASCII-case-insensitively against `acceptance criteria`.

Accepted: `## Acceptance Criteria`, `### ✅ Acceptance Criteria`,
`## acceptance criteria:`, `#### ACCEPTANCE CRITERIA`.

Rejected: the same headings inside a fenced code block, inside an indented code
block, or inside a blockquote; `## Acceptance Criteria (draft)`; `## Criteria`;
`**Acceptance Criteria**`; `## 🎯 Acceptance Criteria`; any mention inside a
sentence; and a qualifying heading whose section is empty.

That is deliberately a presence test. Whether the criteria are _good_ is review
judgment and MUST NOT be folded into `READY`. A leaf without them is not
`READY`, and the remedy is to define its contract rather than to start work and
discover it afterwards.

### 4.2 Executable Leaf Set

For a scope root R, the executable leaf set is every `READY` leaf in R's subtree.

- All members of the executable set MAY be executed in parallel by distinct
  executors. Sibling order does not serialize them.
- If the executable set is empty, resolution reports why the relevant leaves are
  not `READY`. The reasons are the `READY` conditions themselves: unsatisfied
  dependencies, structurally incomplete contracts, closed ancestors, unresolvable
  or cyclic containment, dependency cycles, or no open leaf in the subtree at all.
  An empty set is never permission to start a non-`READY` leaf.

`READY` is derived from the graph and is reproducible by any reader. An execution
claim is not: it states that an executor is working on the leaf now, so it MUST be
explicit, machine-readable, attributable to one named executor, and releasable or
time-bounded.

A claim that is released, expired, or not attributable to a named executor is
void, and a void claim leaves the leaf plain `READY`. An open pull request counts
as a claim only when it is that leaf's primary delivery pull request under
section 5.2, meaning it carries the machine-recognizable closing relationship to
the leaf. A textual `Part of` reference is not a claim, and neither is a pull
request that merely mentions the leaf.

Whether native data can carry a claim before a pull request exists is resolution
work owned by #669 and #672. Until then an executor that cannot observe claims
treats the executable set as available and lets the delivery pull request reveal
a collision.

### 4.3 Deterministic `NEXT` Selection

`NEXT` is the leaf a lone executor takes now. Its inputs are exactly the ones
section 1.2 declares for it, taken as one consistent snapshot. Given identical
inputs, every implementation MUST return the same result.

Take the executable set of the scope root, remove every leaf whose valid claim
names another executor, then sort the remaining candidates by the following keys,
in order, and take the first:

1. **Priority rank**, descending: `priority: blocker` > `priority: high` >
   `priority: medium` > everything else. Recognition is by exact label name.
   Unlabeled leaves and every other label, including labels a repository has not
   rolled out and labels invented later, share the lowest rank; a leaf carrying
   several recognized labels ranks by the highest one present. A graph with no
   priority labels at all is therefore still fully deterministic, so no
   repository needs a particular label for correct execution.
2. **Path order**, ascending: the vector of native sibling positions from the
   scope root down to the leaf, compared lexicographically. Positions are the
   parent's native sub-issue order, counted the same way at every depth and
   across repositories. A shorter vector that is a prefix of a longer one sorts
   first.
3. **Repository name**, ascending, as `owner/repo`.
4. **Issue number**, ascending.

When the candidate set is non-empty, keys 3 and 4 guarantee a total order, so
`NEXT` is exactly one leaf, always inside the scope root's subtree because the
executable set is.

When the candidate set is empty, `NEXT` is **no selection**, and the result MUST
carry which of these two reasons applies:

- **no ready leaf** — the subtree contains no `READY` leaf at all, so the answer
  belongs with the blocking explanation of section 4.2;
- **all candidates claimed** — `READY` leaves exist, but every one of them
  carries a valid claim naming another executor.

Both are ordinary answers, not failures. A resolver MUST NOT respond to either by
ignoring claims, returning a leaf claimed elsewhere, or starting a non-`READY`
leaf. How the two reasons are encoded is an implementation choice that #669
owns.

Explicit human priority outranks plan shape, and plan shape outranks arbitrary
identifiers. There is deliberately no critical-path heuristic: counting
transitive dependents costs a full traversal, invites disagreement about whether
nodes outside the scope root count, and rarely changes the answer that sibling
order already gives.

## 5. One Contract Per Leaf, One Primary Delivery Pull Request

### 5.1 Contract

A leaf's contract is the observable change it promises: the behavior, interface,
schema, workflow effect, or governance rule that will be true after it merges,
plus the acceptance criteria that falsify it.

- A leaf MUST promise exactly one contract.
- Two changes belong to one contract when neither is independently reviewable and
  independently meaningful. Otherwise they are two contracts and need two leaves.
- Refactoring that is required to deliver the contract is part of the contract.
  Opportunistic cleanup that is merely nearby is not.

### 5.2 Primary Delivery Pull Request

- Exactly one pull request per leaf closes it through a machine-recognizable
  closing relationship, written as `Fixes #<leaf>`. That one is the leaf's
  primary delivery pull request, and it is what the rest of this contract means
  by delivering the leaf.
- A leaf inside an epic additionally references its parent with
  `Part of: #<parent>`. A standalone root leaf has no parent, so it carries no
  `Part of` line, and inventing one to satisfy a template is prohibited.
- Everything the leaf's own contract needs, including review fixes, belongs in
  that one pull request, across as many commits as the work takes. Commit count
  is not a decomposition signal.
- A pull request MUST NOT close more than one leaf. Work that cannot be
  reviewed, merged, or delivered independently without leaving a broken
  intermediate state is one atomic delivery contract, so it MUST be modeled as
  one leaf rather than delivered as an exception. Needing to close two leaves at
  once is therefore a modeling defect, and the remedy is to merge them before
  delivery.
- A pull request MUST NOT close an epic through a closing keyword. Epics are
  closed by the closure procedure in section 6.3, because keyword closure skips
  the closure evidence that procedure exists to produce.

### 5.3 After The Primary Pull Request Merges

Once the primary pull request merges, the leaf is `DONE` and stops being a
container for further work:

- A **revert** undoes the delivered change operationally. It does not re-deliver
  the leaf and does not reopen it; if the scope is still wanted, it needs a new
  leaf.
- A **defect found after merge** is new work with its own contract, so it gets
  its own leaf. The fix, including any rollforward, is delivered against that new
  leaf and never against the closed one.
- A **mechanical follow-up** with no independently meaningful contract, such as a
  formatting pass or an infrastructure fix that unblocks delivery, is not a
  second delivery and does not make the original work an epic (section 2.4).

No later pull request may treat a `DONE` leaf as its owning node.

## 6. Delivery And Closure

### 6.1 Leaf Closure

A leaf may be closed as `completed` only when its acceptance criteria are
satisfied by merged work and the evidence rules in sections 9 and 10 are met.
Green CI is supporting evidence, not proof of contract satisfaction. Where
delivery happens through a pull request, that leaf's primary delivery pull
request must have merged.

This is the governance side of `DONE`. Closing a leaf that does not meet these
conditions still makes it `DONE` in GitHub (section 4.1); it makes the closure
wrong, not the state ambiguous.

### 6.2 Deferred Scope

Two obligations always hold, and neither has a materiality threshold:

- An unsatisfied acceptance criterion of the current leaf MUST be resolved or
  replanned. It is never deferred silently.
- A prerequisite the leaf actually needs MUST be tracked under section 7.1.

Everything else discovered along the way becomes a node only when it clears the
materiality threshold in section 7.5. A finding below that threshold is
mentioned in the pull request or dropped, and a `TODO` or `FIXME` marker is not
an acceptable substitute for either outcome.

### 6.3 Epic Closure

An epic closes validly only when no descendant anywhere in its native subtree is
still open, not merely its direct children. Every sub-epic inside it must satisfy
this same rule recursively, so an already-closed sub-epic that still contains an
open leaf does not make its ancestor closable; that sub-epic was closed wrongly
and MUST be reopened or emptied first. Delivered descendants are closed as
`completed`, abandoned ones as `not planned`, and deferred work is re-parented out
of the subtree or re-filed elsewhere before closure. Leaving an open descendant
under a closed epic is the drift that section 4.1 makes unexecutable, so closure
is not a way to defer.

This is a closure rule, not a change to `DONE`. A wrongly closed epic is still
`DONE` in GitHub, exactly as section 4.1 describes, and the invalid closure is
what validation reports.

Closure also requires a comment mapping each acceptance criterion to the exact
child issues and pull requests that satisfied it. The epic is then closed
explicitly, not by a pull-request keyword. The closure procedure, its checklist,
and its comment structure live in `docs/EPIC_WORKFLOW.md`, which implements this
contract and does not extend it.

## 7. Replanning

Replanning is normal execution, not failure. The graph is the plan, so any change
to scope, ownership, or dependency structure MUST land in the native graph
**before** the affected implementation continues. Work that stays inside the
current contract needs no graph mutation at all; requiring one for ordinary
implementation steps would be ceremony, not control.

### 7.1 Missing Prerequisite

First decide whether the discovered work is a separate contract at all. Work that
is genuinely part of the current contract, not independently deliverable, and in
need of no acceptance criteria of its own stays in the current leaf under the
scope rules of section 5.1. Everything else is an independent contract, and the
next question is whether an issue for it already exists.

**The prerequisite already exists.** Add the native dependency from the current
leaf to that issue, leave its ownership and hierarchy exactly as they are, and
park the current leaf until the dependency is satisfied. Do not duplicate the
issue, do not re-parent it because this leaf discovered it, and do not create an
epic merely to give both the same parent. This holds whether the current leaf is
a root leaf or already sits inside an epic, and whether the prerequisite lives in
this repository or another one, since dependencies may cross repositories
(section 3.2) while containment stays untouched.

**The prerequisite does not exist yet.** Only then do the creation flows below
apply, and they still run before implementation continues.

When the current leaf has a parent:

1. Create the prerequisite as a leaf under the same parent.
2. Add a native dependency: the current leaf is blocked by the new leaf.
3. Leave the current work parked; the current leaf is now `BLOCKED`, not `READY`.
4. Re-select `NEXT`.

When the current leaf is a standalone root leaf, it has no parent to create the
prerequisite under, and no parent may be invented. Two independent contracts also
mean the epic threshold of section 2.4 is now met, so:

1. Create an epic for the aggregate goal.
2. Attach the original leaf and the new prerequisite leaf to it as native
   sub-issues, preserving the original leaf's contract unchanged.
3. Add the native dependency from the original leaf to the prerequisite.
4. Continue under normal `READY` and `NEXT` semantics.

The original leaf keeps its identity, its number, and its contract in both paths.
Absorbing the prerequisite because the leaf happened to start standalone is
prohibited.

### 7.2 New Responsibility

Work discovered outside the current contract MUST NOT be absorbed by the current
leaf, whatever its size. That rule is absolute: an out-of-scope finding is never
answered by growing the pull request.

Whether it becomes a node is a separate question, answered by section 7.5.
Material work is tracked; immaterial observations are not, because a graph full
of cosmetic nodes hides the work that matters exactly as effectively as losing
the work would.

### 7.3 Sub-Epic Promotion

When a leaf is found to carry several contracts, promote it in place:

- The node keeps its identity and issue number and becomes a sub-epic.
- Its contracts become child leaves, ordered by native sibling order.
- A dependent that needs the aggregate result MAY stay blocked by the promoted
  node as a sub-epic. It unblocks when that node closes as `completed`, exactly as
  any epic dependency does (section 3.2).
- A dependent that needs only part of the promoted work MUST have its edge
  re-pointed to exactly the child or children producing what it needs. Leaving it
  blocked on the whole sub-epic for convenience is prohibited, the edge MUST NOT
  be duplicated to unrelated children, and keeping both an aggregate edge and a
  child edge is correct only when both are independently real prerequisites.
- A prerequisite the promoted leaf was waiting for MUST be attached as a native
  dependency to exactly those children whose implementation it blocks. Children
  do not inherit blockers from a parent, so a prerequisite left only on the
  sub-epic blocks nothing below it.
- A prerequisite MAY remain only on the sub-epic when it gates closure or
  rollout rather than implementation, meaning children are allowed to proceed
  before it completes.
- Nothing is copied to every child by default. Attaching an edge to each child
  is correct only when each child genuinely needs it.
- Any open pull request written against the old leaf MUST be re-pointed at the
  child leaf it actually delivers, or closed.
- The promoted node MUST NOT be delivered by a pull request afterwards.

### 7.4 Ordering-Only Discovery

If execution merely suggests a nicer order, adjust sibling order. Do NOT add a
dependency edge. Preference is not a blocker (section 3.4).

### 7.5 Materiality Threshold For New Nodes

A discovery becomes its own node only when it is all of the following:

- **proven** — reproducible, or supported by file and line evidence, rather than
  suspected,
- **material** — its absence has a real cost to users, operators, security, data
  integrity, or maintainability,
- **actionable** — it can be expressed with concrete acceptance criteria,
- **non-duplicate** — no existing node already covers it,
- **still relevant** — it survives the change currently being delivered,
- **outside the current contract** — otherwise it is delivered here.

Below the threshold, no node is created. A speculative cleanup idea, a cosmetic
observation, an insignificant warning, a stylistic preference, and a concern
already covered elsewhere are all mentioned in the pull request at most.

Two exceptions sit above the threshold by definition and are always tracked: an
unresolved acceptance-criteria gap, and a prerequisite the work actually needs.

## 8. Precedence Between Scope And Evidence

Test-driven development and review feedback are binding process rules, and they
never authorize breaking a scope or design constraint. When they collide, resolve
in this order (highest first):

1. Security, privacy, data-integrity, legal, and licensing invariants.
2. Correctness of the promised contract.
3. Accepted ADRs, then the leaf's declared scope and non-goals, then the design
   constraints in sections 7.3, 11, and 12.
4. Test-driven development and evidence obligations (sections 9 and 10).
5. Structural preferences, style, and automated review suggestions.

Consequences:

- A failing test MUST NOT be answered by expanding the leaf's scope, weakening a
  security invariant, or contradicting an ADR. The answer is a replanning node
  (section 7) or an ADR change.
- Making a test pass never justifies a second definition of an invariant
  (section 11), keeping a leaf that should be split (section 7.3), or hand-rolling
  what a standard already provides (section 12).
- A test MUST NOT be deleted, skipped, or weakened to make a build pass. Either
  it found a defect or it encodes an obsolete contract clause, and the second
  requires an explicit contract-change note in the pull request.
- Automated review findings are untrusted leads. Classify each with a failing
  test, a reproduction, or a named violated invariant before changing code, using
  the classes in section 8.1.
- Levels 1 to 3 are never traded for level 4 or 5, and level 5 never overrides
  levels 1 to 4.

### 8.1 Classifying A Review Finding

Every review finding MUST be classified before any code changes, because the
class determines where the work belongs and whether the current leaf may still
close:

1. **In-contract defect** — the finding breaks a promise the current leaf makes.
   Fix it in the current pull request, with evidence. After that pull request
   merged, the same defect becomes its own leaf instead (section 5.2).
2. **Missing prerequisite** — the finding cannot be resolved without work that
   does not exist yet. Handle it under section 7.1.
3. **New responsibility** — the finding is real but outside the current
   contract. Handle it under section 7.2; the current leaf still closes.
4. **Non-blocking follow-up** — the finding is real, outside the contract, and
   not urgent. Track it as its own node when it clears section 7.5, and mention
   it in the pull request otherwise.
5. **Invalid finding** — the finding does not survive classification. Reply with
   the evidence that refutes it and change no code.

Classes 3 and 4 MUST NOT be answered by growing the current pull request, and
class 5 MUST NOT be answered by a defensive code change made only to silence the
reviewer. No class obliges a new test: a finding justifies one only when it names
a contract distinction or failure class the existing evidence cannot express
(section 10.2).

## 9. Evidence Classes

A leaf MUST be evidenced in proportion to what it promises and to how it can
fail. The classes below are the available kinds of proof, not a checklist to
fill: an acceptance criterion is satisfied by whichever class actually proves
it, and one evidence item MAY prove several criteria at once.

Evidence is never counted. Neither a test count nor a coverage percentage tells
anyone whether the contract holds.

### 9.1 Behavior And Contract Evidence

Tests that assert the promised observable behavior at the contract boundary: the
public API, HTTP contract, CLI surface, exported function, workflow effect, or
user-visible behavior.

- Required wherever a leaf changes observable behavior, at the granularity of
  materially distinct behavior rather than per acceptance criterion.
- Written first and observed failing before the implementation exists.
- Asserts the promise, not the implementation shape. A test that must change
  whenever an internal helper is renamed is not behavior evidence.
- A behavior-preserving refactor SHOULD leave these tests untouched. Having to
  rewrite them is evidence that they were pinned to structure, or that the
  refactor changed behavior after all.

### 9.2 Integration And Real Evidence

A check that exercises the real collaborator instead of a substitute: real
database, real HTTP layer, real filesystem, real serialization, real workflow
execution, real cross-repository contract.

- Required when the leaf's risk lives in a seam. A **seam** is one materially
  distinct integration contract or risk boundary, not a collaborator and not a
  call site: one database can hold several seams, while many call sites can share
  one. Typical seams are persistence, I/O, authentication and authorization,
  protocol or schema compatibility, CI and automation behavior, and
  cross-repository contracts.
- Prove every materially distinct seam with the smallest sufficient evidence set.
  One realistic scenario that crosses several seams proves all of them; splitting
  it into one check per seam is the counting error section 10.1 prohibits.
- A mock-only proof is insufficient for a seam contract, because a mock asserts
  the assumption rather than the behavior.
- When real evidence is unavailable, what happens depends on whose contract needs
  it, and section 9.4 decides that. Filing a follow-up node never converts missing
  required evidence into sufficient evidence.

### 9.3 Structural And Characterization Evidence

Tests that pin current behavior before a refactor, or that assert a stated
structural invariant such as licensing headers, action pinning, or forbidden
imports.

- Legitimate and often valuable, especially before refactoring untested code.
- MUST be classified as structural where it is recorded, so it cannot be read as
  proof that the promised behavior holds.
- MUST be tied to a stated invariant. A structural test that encodes an
  implementation preference or a prose shape without a stated invariant is noise
  and MUST be removed.

### 9.4 Evidence That Cannot Be Produced Yet

Some evidence exists only after deployment, on real hardware, in a live
environment, or once another repository exists. That is not a reason to lower the
bar; it is a question about which contract owns the evidence, and the answer is
decided before implementation is called complete.

- If the leaf promises the real-world outcome, that evidence is required for
  closure. Missing access does not satisfy the contract, and filing a follow-up
  node does not either. The leaf stays open, or its contract is replanned under
  section 7 to promise only what it can actually prove.
- If the real-world validation is deliberately a later contract, model it that
  way first: an implementation leaf plus a validation leaf under a shared parent,
  with a dependency wherever the real requirement gates it. The implementation
  leaf then closes on its own contract, while the aggregate goal stays incomplete
  until the validation leaf is `DONE`, because an epic cannot close with an open
  child (section 6.3).

Splitting evidence into its own leaf is a contract decision, not a routine step.
One validation leaf can carry many seams at once, and this section never
justifies one leaf per seam or per test.

### 9.5 Leaves Without Executable Behavior

A leaf that changes no executable behavior, such as governance text or
documentation, MUST state that explicitly and provide the relevant structural or
review evidence instead. It MUST NOT claim behavior evidence it does not have.

## 10. Evidence Stop Condition And Test Pruning

### 10.1 Proportional Evidence

The obligation is that the contract is sufficiently proven, not that each clause
owns a test:

- Every acceptance criterion MUST be sufficiently evidenced, by whichever class
  fits its nature: behavior, integration or real-system, structural, or a
  recorded manual verification.
- One test or evidence item MAY prove several acceptance criteria. Splitting it
  to achieve a one-to-one mapping is prohibited.
- The target is the smallest non-redundant evidence set that proves the
  contract, not the largest defensible one.

### 10.2 Stop Condition

Stop adding evidence once all of the following are sufficiently proven:

- every materially distinct behavior the leaf promises,
- every distinct failure class it must handle,
- every seam identified in section 9.2 that this leaf's own contract covers,
- every named security or data-integrity invariant it touches.

A new test is justified by a distinction the existing evidence cannot express. A
review finding that names no new distinction or failure class is not such a
justification. Where a distinction fits inside an existing test, strengthen that
test instead of adding a parallel one.

Coverage is a gate, never evidence. A configured repository coverage floor is an
independent validation gate that MUST still be satisfied, and a percentage names
no behavior, failure class, or invariant, so it never proves the contract. Satisfy
a floor with meaningful contract or failure-path evidence. If only meaningless
tests could satisfy it, the coverage policy needs its own review under section
7.5; do not weaken or bypass the gate inside the current leaf, and do not
manufacture redundant or implementation-shape tests to clear it.

### 10.3 Pruning And Consolidation

These obligations cover only the tests this change touches: the ones it adds,
modifies, or makes obsolete, and the ones it exposes as redundant by replacing
the contract they protected. Within that boundary, and before requesting review,
the author MUST:

- merge tests that differ only in irrelevant fixture detail into parameterized
  cases,
- delete tests that no longer map to any contract clause,
- delete tests that assert internals that the change just made private or
  removed,
- delete tests that pin prose or implementation shape without a named invariant.

Unrelated legacy test debt is out of scope by definition and MUST NOT enter the
current leaf, however tempting the cleanup looks. Ignore it when immaterial,
track it when it clears section 7.5, and never absorb it merely because this
section discusses pruning (sections 7.2 and 7.5).

Test count is not a quality metric. Redundant tests slow every future change,
so leaving them behind is a cost, not caution. Deleting a test to silence a
failure is prohibited (section 8).

## 11. Authoritative Invariant Ownership

Every invariant MUST have exactly one authoritative owner: one definition of
what the rule is, identifiable from the code or its documentation. Ownership is
about the definition, not about the number of places that enforce it.

Enforcement MAY happen at as many points as the architecture and its trust
boundaries require. Each enforcement point MUST derive from, reference, or stay
demonstrably consistent with the authoritative definition.

What this forbids is a second definition: copy-pasted validation carrying its own
literal list, so that the copies drift and no reader can tell which one the
system actually means.

### 11.1 Multiple Enforcement Points

Redundant enforcement is expected, not discouraged, at trust boundaries:

- untrusted input crossing a process or network boundary, validated at the edge
  while the domain still enforces its own invariant,
- authorization at each independently reachable entry point, for example
  middleware, policy, and query scoping, because each is separately reachable,
- database constraints backing an application invariant, because other writers can
  reach the database,
- fail-closed safety checks whose failure would be catastrophic or irreversible.

Sharing the implementation is the default, and independent enforcement is
allowed where sharing it would weaken the boundary, for example where the outer
layer must not import the inner layer, or where a shared failure would disable
both checks at once. Independent enforcement MUST name the authoritative owner it
defends.

Layers do not have to fail identically, and they do not have to see the same
representation. Different error types, messages, and status codes are expected,
and an edge layer may accept a transport form that it normalizes before the
domain sees a canonical form. What layers MUST NOT do is disagree semantically:
after normalization they must accept the same set of real-world values. Two
layers that would answer differently about the same value are two definitions,
which is the failure this section exists to prevent.

The multi-layer authorization guidance in `docs/development-principles.md` is
such a case. It does not license a second definition of the rule being enforced.

## 12. Standards Before Custom, And Finite Allowlists

### 12.1 Standards Before Custom

Prefer an existing standard, platform feature, framework mechanism, or maintained
library when it exists, is maintained, matches the required semantics, and is
already available.

- These MUST NOT be hand-rolled: cryptography, authentication and token handling,
  parsers and protocol primitives including URL, email, date, and HTML,
  canonicalization and escaping, scope and symbol analysis of a language, and
  framework lifecycle behavior.
- GitHub-native hierarchy, dependency, state, and ordering MUST NOT be
  reimplemented in SecPal code, per section 1.

The rule bans reimplementing the primitive, never layering policy on top of it.
Parsing HTML with a standard parser and then applying SecPal content policy,
resolving symbols through a language API and then applying SecPal rules, or using
the framework's auth lifecycle and then enforcing SecPal authorization, are all
the intended shape. SecPal's guard-book rules, tenancy model, and regulatory
logic are legitimately custom, MUST NOT be contorted into a generic library, and
MUST NOT be rejected merely for being custom. Equally, a dependency
MUST NOT be added for something the standard library already does or for logic
that is trivial and stable.

### 12.2 Finite Allowlists

Where the valid set is finite, closed, and known, enumerate it and reject
everything else, failing closed on unknown values. Denylists MUST NOT be the
primary control, because they silently accept whatever nobody thought of.

Where the domain is genuinely open-ended, such as free text, user-supplied names,
or extensible identifiers, an allowlist is the wrong tool. Use structural
validation plus correct escaping at each sink instead. Choosing an allowlist for
an open-ended domain produces false rejections and pressure to bypass the control,
which is a worse outcome than the control's absence.

## 13. Repository Adoption

- Repository baselines reference this contract. They MUST NOT restate its
  semantics in divergent wording, because a restatement is a second source of
  truth.
- A baseline MAY add stricter, non-contradictory rules scoped to its repository,
  and MAY define stack-specific detail such as commands, frameworks, and paths.
- On conflict, this contract wins for work-graph and governance semantics, and
  the repository baseline wins for stack-specific technical detail.
- Adoption by the other SecPal repositories is owned by rollout epic #666 and its
  repository migration issues. It is deliberately not a condition for this
  specification being complete, since #666 depends on this foundation.
- Graph resolution tooling and validation are owned by #669 and #670. This
  document stays free of tooling.

## Related Guidance

- [AGENTS.md](../AGENTS.md)
- [docs/planning.md](planning.md)
- [docs/EPIC_WORKFLOW.md](EPIC_WORKFLOW.md)
- [docs/development-principles.md](development-principles.md)
- [docs/adr/20260415-issue-first-planning-governance-adr013.md](adr/20260415-issue-first-planning-governance-adr013.md)
