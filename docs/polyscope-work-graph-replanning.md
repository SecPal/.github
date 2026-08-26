<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Polyscope Work-Graph Replanning

This guide documents the bounded command interface that implements section 7
of [the canonical work-graph contract](work-graph-contract.md). The contract is
the authority for classification, ownership, hierarchy, dependency, ordering,
and evidence semantics; this guide does not redefine them.

## Safety model

`scripts/secpal-work-graph-replan.py` has two phases:

1. `plan REQUEST.json` reads the canonical native GitHub graph and emits a
   finite, inspectable plan bound to the authenticated GitHub actor and a digest
   of the complete relevant snapshot.
2. `apply PLAN.json --apply` recompiles the untrusted plan, authenticates the
   actor again, rereads the same canonical scope, and rejects stale issue state
   or graph drift before the first write.

The apply phase can create an issue with its native parent, reprioritize that
new sub-issue, and add or remove exact native `blocked by` edges. It has no
generic GraphQL, REST, body-edit, re-parent, close, or arbitrary issue-update
operation. Every stable native ID is resolved before the first write. A write
failure stops the invocation without retry; because GitHub does not provide a
transaction spanning these mutations, the command durably records `NO_WRITES`,
`KNOWN_WRITES`, `UNKNOWN_MUTATION_OUTCOME`, or `COMPLETE`. Every state is
authenticated by a signed commit made with the user's controlled Git signing
configuration. The configured signer fingerprint is established independently
of the journal and checked on every state. A deterministic private Git ref keeps
the signed states reachable across ordinary Git maintenance; each replacement
is a signed child of the previous state, so a crash after advancing the ref
cannot invalidate the last durable journal. These private refs are not part of
an ordinary branch push and are never cleaned up implicitly.

The signed journal binds the canonical plan digest, authenticated baseline
snapshot, actor, current issue, applied step prefix, and every exact
GitHub-returned create identity. Recovery authenticates those facts before it
interprets live graph changes. It verifies the current graph as the exact
baseline plus the recorded prefix, rejects unrelated drift, validates only the
remaining suffix, and then continues with the recorded identities. An ordinary
replay with existing recovery state fails closed. The recovery path and private
ref are derived from the exact semantic plan and stored in repository Git state,
so changing the plan file's location cannot bypass replay protection.

After the writes, the command rereads the graph, verifies every intended edge
and sibling position, rejects any unrelated state or relationship change, and
runs the canonical resolver's structural validation. Existing body-only mirror
findings may still be reported; they are never used as mutation preconditions.

## Request representation

A request names one repository-qualified `current_issue`, one explicit
`finding`, and one bounded `operation`. Section 8.1 of the canonical contract is
the sole definition of classification, blocker, timing, and placement
semantics. This guide documents only their JSON transport and the finite command
surface.

## Creating owned work

`CREATE_OWNED_SIBLING` and `CREATE_OWNED_FOLLOWUP` require an `issue` object:

```json
{
  "current_issue": "SecPal/.github#673",
  "finding": {
    "classification": "NEW_RESPONSIBILITY",
    "technically_blocking": false,
    "mechanically_blocking": false,
    "timing": "BEFORE_FREEZE",
    "risk": []
  },
  "operation": {
    "kind": "CREATE_OWNED_SIBLING",
    "issue": {
      "alias": "separate-contract",
      "repository": "SecPal/.github",
      "title": "Deliver the separate contract",
      "body": "## Acceptance Criteria\n\n- The separate result is delivered.\n"
    }
  }
}
```

Every created issue needs canonical acceptance criteria. The planner derives
the exact native placement and ordering steps from the canonical contract.

## Inserting a prerequisite

`INSERT_PREREQUISITE` names either `existing_issue` or a new `issue`, never
both. An existing cross-repository prerequisite keeps its current parent and
repository. A new prerequisite is created under the current leaf's existing
owner and placed before it. `move_current_blockers` lists only the exact current
edges that semantically move onto the prerequisite; every other edge stays
unchanged. The current leaf is then natively blocked by the prerequisite.

```json
{
  "kind": "INSERT_PREREQUISITE",
  "existing_issue": "SecPal/api#44",
  "move_current_blockers": []
}
```

A new prerequisite or responsibility discovered from a standalone root leaf
additionally requires an `epic` issue specification. The bounded plan creates
that root epic, attaches the original leaf and the new leaf natively, and then
adds the required dependency where applicable. An already-existing
prerequisite keeps its ownership and needs no invented parent.

## Promoting and splitting a leaf

`PROMOTE_TO_SUB_EPIC` requires at least two child issue specifications. It also
requires exhaustive `blocked_by_placement` and `blocking_placement` maps whose
keys exactly equal the current leaf's native incoming and outgoing dependency
relationships. Each relationship is assigned to one or more child aliases, or
to `@aggregate` when it genuinely gates the promoted sub-epic. Omission,
unknown aliases, and blanket copying fail closed.

Children are created in declared order. No dependency is inferred between
them, so independently deliverable children remain parallel. A dependent edge
is repointed only to the selected child contracts; a prerequisite edge moves
only to the children that actually consume it.

## Operational use

Keep request and plan files outside tracked source, then run:

```bash
python3 scripts/secpal-work-graph-replan.py plan REQUEST.json > PLAN.json
python3 scripts/secpal-work-graph-replan.py apply PLAN.json --apply
python3 scripts/secpal-work-graph.py validate OWNER/REPO#SCOPE
```

Inspect the emitted classification, actor, owner, snapshot digest, and every
step before applying. Never edit the plan to bypass a failed precondition;
change the request or replan from fresh canonical state instead.

If the command reports `KNOWN_WRITES`, preserve the original plan and the
reported repository-managed recovery state. After confirming the recorded
created identities in GitHub, the same bounded operation can resume with:

```bash
python3 scripts/secpal-work-graph-replan.py recover PLAN.json --apply
```

`UNKNOWN_MUTATION_OUTCOME` is terminal for automatic recovery. Inspect GitHub
state manually; never retry that mutation blindly.

Recovery signing resolves the account home from the operating-system account,
then fixes `HOME`, `XDG_CONFIG_HOME`, and `GNUPGHOME` to that account's canonical
locations for both signing and verification. Git configuration override
families and verifier-program substitution remain disabled. SSH and OpenPGP are
accepted when they are the configured Git signing format; a cryptographically
valid signature from any other fingerprint is rejected.
