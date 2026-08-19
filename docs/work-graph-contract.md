<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Work-Graph And Engineering-Governance Contract

## Status

Canonical. This document is the single organization-wide definition of how
SecPal work is structured, ordered, selected, delivered, and evidenced.

Every SecPal repository baseline (`AGENTS.md`, `.github/copilot-instructions.md`,
`.github/instructions/*.instructions.md`) and every Polyscope runtime instruction
set references this contract instead of redefining its semantics locally.

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

- **Graph rules** — sections 1, 3, and 4. They are computable from native data
  alone, and two correct implementations MUST produce identical results.
- **Judgment rules** — sections 2 and 5 to 12. They guide a human or an agent
  deciding scope, evidence, and design. Automation MAY report a suspected
  violation; it MUST NOT silently decide one.

## 1. Source Of Truth

GitHub-native issue data is authoritative, and it carries two different kinds of
truth that this contract keeps apart.

**Graph state** defines topology and progress. It is exactly these four fields,
and nothing else ever becomes graph state:

- issue open/closed state and closure reason,
- native parent/sub-issue hierarchy,
- native issue dependencies (`blocked by` / `blocks`),
- native sub-issue ordering inside a parent.

**Issue content** defines what a node promises: its title, body, scope,
acceptance criteria, and non-goals. Content never changes topology, and topology
never changes what a node promises.

**Metadata** — labels, milestone, assignees — carries only the meaning this
contract assigns to it explicitly, currently the priority rank in section 4.3.
Metadata is neither graph state nor contract, so it MUST NOT override either.

Everything else is a mirror: Markdown task lists, `Parent:` / `Order:` / `Blocked
by:` lines in issue bodies, project-board fields, roadmap documents, plan files,
and agent-local notes.

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

### 1.1 Precedence

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
- An epic is never `READY`. Its state is derived from its children.

### 2.2 Sub-Epic

An epic whose parent is an epic. It exists to bound one coherent phase, one
repository scope, or one responsibility cluster of a larger epic.

- A sub-epic follows every epic rule.
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

- Dependencies MAY cross repositories and MUST then be written as
  `owner/repo#number`.
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
- Containment MUST also be acyclic. A node MUST NOT be its own ancestor.

## 4. States, Executable Sets, And `NEXT`

### 4.1 Derived States

Only open/closed is native. All other states are derived and MUST NOT be
duplicated into Markdown.

- **BLOCKED** — an open node with at least one unsatisfied dependency, or a node
  inside a dependency cycle, or a node with an unresolvable dependency target.
- **READY** — an open leaf with no children, no unsatisfied dependency, no cycle,
  only open ancestors, and a structurally complete contract. A closed ancestor
  above an open leaf is graph drift: the ancestor was closed before its scope was
  finished, so the leaf stays unexecutable until the ancestor is reopened or the
  leaf is re-parented.
- **ACTIVE** — a `READY` leaf under an explicit execution claim (see section
  4.2). Assignment alone MUST NOT make a leaf `ACTIVE`, because an assignee
  records ownership rather than execution, and one maintainer routinely owns
  many leaves while executing one.
- **DONE** — a node closed as `completed`. Any other closure reason means the
  node was abandoned or superseded, which is a valid outcome but not a delivery,
  and it satisfies no dependency (section 3.2).
- An epic is never `READY` and never `ACTIVE`. An epic is closable only under
  section 6.3.

`BLOCKED`, `READY`, and `DONE` are derived from graph state alone. `ACTIVE` is
not a graph state at all: it belongs to execution coordination (section 4.2) and
never changes any of the three.

**Structurally complete** means the body contains a Markdown heading whose
normalized text is `acceptance criteria`, followed by at least one non-blank
line before the next heading of any level. Normalization is exactly this, in
order: strip leading emoji and other non-alphanumeric decoration, strip
surrounding whitespace and trailing punctuation, fold case. So `## Acceptance
Criteria`, `### ✅ Acceptance Criteria`, and `## acceptance criteria:` all
qualify, while a body that only mentions the phrase in a sentence does not.

That is deliberately a presence test. Whether the criteria are _good_ is review
judgment and MUST NOT be folded into `READY`. A leaf without them is not
`READY`, and the remedy is to define its contract rather than to start work and
discover it afterwards.

### 4.2 Executable Leaf Set

For a scope root R, the executable leaf set is every `READY` leaf in R's subtree.

- All members of the executable set MAY be executed in parallel by distinct
  executors. Sibling order does not serialize them.
- If the executable set is empty, the correct output is the blocking explanation,
  meaning which dependencies are unsatisfied and which nodes they belong to. It
  is never permission to start a non-`READY` leaf.

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

`NEXT` is the single leaf a lone executor takes now. It is deterministic over
three inputs together: one scope root, one snapshot of native graph state, and
one snapshot of the valid execution claims at that moment. Given identical
inputs, every implementation MUST return the same leaf. Graph state alone does
not determine `NEXT`, because valid claims remove candidates; that is why the
claim snapshot is part of the input rather than an afterthought.

Take the executable set of the scope root, remove every leaf whose valid claim
names another executor, then sort by the following keys, in order, and take the
first:

1. **Priority rank**, descending: `priority: blocker` > `priority: high` >
   `priority: medium` > everything else. Unlabeled leaves and labels outside this
   list share the lowest rank; a leaf carrying several priority labels ranks by
   the highest one present.
2. **Path order**, ascending: the vector of native sibling positions from the
   scope root down to the leaf, compared lexicographically. Positions are the
   parent's native sub-issue order, counted the same way at every depth and
   across repositories. A shorter vector that is a prefix of a longer one sorts
   first.
3. **Repository name**, ascending, as `owner/repo`.
4. **Issue number**, ascending.

Keys 3 and 4 guarantee a total order, so `NEXT` is always unique, and the result
is always inside the scope root's subtree because the executable set is.

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

- Exactly one pull request per leaf closes it, using `Fixes #<leaf>` plus
  `Part of: #<parent>`. That one is the leaf's primary delivery pull request, and
  it is what the rest of this contract means by delivering the leaf.
- Other pull requests touching the same leaf are allowed only as a revert, a
  rollforward for a defect found after merge, or an unblocking infrastructure fix.
  They MUST NOT carry new contract scope, and a post-merge defect MUST get its own
  leaf.
- A pull request MUST NOT close more than one leaf. Work that cannot be
  reviewed, merged, or delivered independently without leaving a broken
  intermediate state is one atomic delivery contract, so it MUST be modeled as
  one leaf rather than delivered as an exception. Needing to close two leaves at
  once is therefore a modeling defect, and the remedy is to merge them before
  delivery.
- A pull request MUST NOT close an epic through a closing keyword. Epics are
  closed by the closure procedure in section 6.3, because keyword closure skips
  the closure evidence that procedure exists to produce.

## 6. Delivery And Closure

### 6.1 Leaf Closure

A leaf closes when its acceptance criteria are satisfied by merged work and the
evidence rules in sections 9 and 10 are met. Green CI is supporting evidence, not
proof of contract satisfaction.

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

An epic closes only when no child of it is still open. Delivered children are
closed as `completed`, abandoned ones as `not planned`, and deferred work is
re-parented out of the epic or re-filed elsewhere before closure. Leaving an open
child under a closed epic is the drift that section 4.1 makes unexecutable, so
closure is not a way to defer.

Closure also requires a comment mapping each acceptance criterion to the exact
child issues and pull requests that satisfied it. The epic is then closed
explicitly, not by a pull-request keyword. The closure procedure, its checklist,
and its comment structure live in `docs/EPIC_WORKFLOW.md`, which implements this
contract and does not extend it.

## 7. Replanning

Replanning is normal execution, not failure. The graph is the plan, so replanning
MUST update the native graph **before** the affected work continues.

### 7.1 Missing Prerequisite

When a leaf cannot satisfy its acceptance criteria because a prerequisite does
not exist:

1. Create the prerequisite as a leaf under the same parent.
2. Add a native dependency: the current leaf is blocked by the new leaf.
3. Leave the current work parked; the current leaf is now `BLOCKED`, not `READY`.
4. Re-select `NEXT`.

The prerequisite MAY instead be implemented inside the current pull request only
when it is small, in-topic, and already inside the current contract. If it needs
its own acceptance criteria, it is not in the current contract.

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
- Nodes that were blocked by the promoted leaf stay blocked by it as a sub-epic.
  They unblock when it closes as `completed`, exactly as any epic dependency does
  (section 3.2).
- Prerequisites the promoted leaf was itself waiting for MUST be reattached only
  to the child or children that actually need them, and MUST NOT be copied to
  every child merely because the parent once carried them. A prerequisite that
  every child genuinely needs MAY stay on the sub-epic instead of being
  duplicated.
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
- When real evidence is genuinely unavailable in the environment, the leaf MUST
  record what could not be verified rather than claiming coverage. An unverified
  seam is material by definition, so the outstanding verification is tracked
  under section 7.5.

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

### 9.4 Leaves Without Executable Behavior

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
- every seam identified in section 9.2,
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

Layers do not have to fail identically. Different error types, messages, and
status codes are expected and appropriate to each layer. What they MUST NOT do is
disagree about what is accepted: two layers that admit different input sets are
two definitions, which is the failure this section exists to prevent.

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

This rule does not devalue domain code. SecPal's guard-book rules, tenancy model,
and regulatory logic are legitimately custom, MUST NOT be contorted into a generic
library, and MUST NOT be rejected merely for being custom. Equally, a dependency
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
