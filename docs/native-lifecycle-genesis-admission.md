<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Native Lifecycle Genesis Admission

Native lifecycle genesis trust and lifecycle CURRENT selection are separate
authorities.

The protected `secpal-lifecycle-publications` branch remains the single linear,
append-only journal and the sole selector of a delivery's dynamic CURRENT
terminal. A `SECPAL_NATIVE_LIFECYCLE_GENESIS_ADMISSION` entry in that same
journal answers only whether one immutable native genesis is admitted. It does
not contain a terminal authority digest and cannot select CURRENT.

## Trust ownership

| Question                                | Authoritative object                                                                                                                                                   |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Who may create native genesis evidence? | The closed initialization signer role and signed `SECPAL_DELIVERY_LIFECYCLE_INITIALIZATION`                                                                            |
| What proves genesis admission?          | A domain-separated admission signed by the maintained genesis-admission role, or one exact enrollment object in the closed pre-#774 compatibility-publication registry |
| When is admission globally reachable?   | When its exact CAS successor is visible in protected journal ancestry                                                                                                  |
| What proves uniqueness?                 | Complete ancestry traversal rejects a second delivery identity or initialization digest admission                                                                      |
| What selects CURRENT?                   | The latest valid lifecycle publication for the delivery in protected journal ancestry                                                                                  |
| What prevents rollback?                 | Live deletion/non-fast-forward protection plus immutable predecessor binding                                                                                           |
| What prevents competing genesis?        | Closed identity/digest admission indexes and exact journal CAS                                                                                                         |
| What resolves concurrent enrollment?    | One expected-predecessor CAS wins; a loser has no visible admission and must begin a fresh bounded operation                                                           |

Initialization creation binds the repository, delivery issue, pull request,
static initial head, validation receipt digest, final attestation digest,
initialization signer, signature, and digest. Lifecycle-authority events and
snapshots own finite state derivation. Publication signatures own each journal
statement. Journal ancestry owns ordering. Consumers only compare expectations
with the independently selected verified result.

No mutable checkout, caller-selected signer, consumer constraint, or lifecycle
publication can admit its own genesis.

## Ordinary native enrollment

The supported order is:

1. create and sign the native initialization and lifecycle genesis;
2. verify the complete native derivation without treating it as admission;
3. append one independently signed genesis admission by exact CAS;
4. observe and verify that admission through protected journal ancestry;
5. append the native lifecycle enrollment by a second exact CAS; and
6. let journal ancestry select the dynamic CURRENT terminal.

An admission without enrollment is harmless: it selects no terminal. An
enrollment without an earlier reachable admission fails closed. Two publishers
starting from the same journal tip cannot both append; the CAS loser produces no
globally visible object. A retry is a fresh operation against newly verified
ancestry. A second or competing admission for one delivery fails closed.

The maintained writer surface exposes this order directly:
`admit_native_genesis` appends the admission, `enroll_existing_lifecycle`
requires that admission in its freshly observed ancestry, and
`advance_current_terminal` preserves the admitted initialization while appending
one exact lifecycle successor. Callers cannot combine these operations or pass
an alternate journal, trust policy, signer set, or CURRENT selector.

## Maintained compatibility publications

The existing `delivery_initializations` entries for issues 692, 674, and 735
remain static initialization roots. Their `current_*` fields continue to serve
the strict ordinary #750 verifier for callers that have not adopted
journal-selected CURRENT; journal traversal does not use those fields to select
a terminal.

A separate closed `historical_compatibility_publications` registry binds the
only enrollment objects allowed to use the pre-#774 ordering exception:

- issue 692 / PR 757: object `52e76a4eef0fdbb297c16d4bcf64b813bef84062`,
  publication digest
  `ace5dd8f514870f33d734d6e8f6f7371b48783c6a6823d6a496b895f4cc0ac5e`;
- issue 674 / PR 758: object `80950f8908f29ead325eb99caf1977e51fad37e1`,
  publication digest
  `b5fa17ae18f5fc7208c7e13b9c361d59adc0128446404e79bbf42587679cbfad`;
- issue 735 / PR 759: object `2a5c2d9554ca7b70fd4f2e486da18ae9697af912`,
  publication digest
  `abd53fe73fc29257656151b3ad3777cbe72012102a5a5bcec95ec23529c0e211`.

Each entry also binds the repository, original PR, static initial head,
initialization digest, and native historical proof mode. Journal traversal
admits compatibility only when the immutable object being inspected and its
signed document match every maintained binding.

Adding a new branch-local `delivery_initializations` entry cannot authorize
ordinary publication. Reusing one of the static initializations in a different
publication object cannot authorize publication either. New native delivery
enrollment requires a preceding protected-journal admission. Existing
compatibility publications are not a template for future enrollment and must
not be expanded for that purpose.

## Issue 736 bootstrap repair

Issue 736 predates the admission boundary but lacks a maintained compatibility
anchor. The one-time `BOOTSTRAP_REPAIR_NATIVE_GENESIS` operation is allowed only
by the closed `bootstrap_genesis_repairs` policy entry for repair issue 774. It
binds the exact original native enrollment publication and independently checks:

- repository `SecPal/.github`, issue 736, and pull request 760;
- initial head `9cce12e839e5f998137cc58fea90d0a5a0a45f63`;
- initialization digest
  `6477407a86182f6bc9964089382f288e13dbb2e0b096edb2bf4e1c228452e628`;
- validation receipt digest and final attestation digest from the signed
  initialization;
- the accepted initialization signer and its valid domain-separated signature;
- enrollment publication object
  `0bb379a9af38bb14a49c651104d31149bb6c7f18` and its exact signed digest; and
- a unique matching native initialization with no competing admission.

The repair is appended; it does not rewrite the target enrollment or any later
publication. Only this maintained repair may authenticate a publication that
precedes its admission. Ordinary admissions must precede enrollment. The repair
cannot create a lifecycle, reset a counter, represent recovery or continuation,
adopt legacy history, or select CURRENT.

After issue 774 is merged, `repair_published_native_genesis` is the only writer
surface for that maintained exception. It reads the exact target publication by
immutable object ID, constructs the domain-separated repair admission, verifies
the complete resulting ancestry before CAS, and fails if the repair is absent,
stale, duplicated, competing, or already consumed.

Issue 774 itself uses the already-maintained ordinary one-parent delivery
evidence compatibility boundary: exact source validation receipt, final
attestation, signed commit, Draft/Ready review lifecycle, hosted checks, and
squash merge. It does not claim normal native lifecycle publication while the
boundary it repairs is unavailable. After the signed issue 774 repair is merged,
the maintained code may append the bounded repair operation and immediately
verify the unchanged ancestry from merged `main`.

`NATIVE_GENESIS_ADMISSION != LIFECYCLE_CURRENT`.
