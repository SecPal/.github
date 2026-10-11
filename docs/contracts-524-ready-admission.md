<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Contracts #524 Ready admission

This exact registration admits the existing [contracts #524](https://github.com/SecPal/contracts/issues/524)
delivery, [PR #525](https://github.com/SecPal/contracts/pull/525), through
Exact-State-Adoption v3 and the existing pre-enrollment validation-evidence-loss
schema 1.3. It preserves unavailable historical package bytes and the real
current-head receipt identity. The protected contracts journal remains the
sole lifecycle CURRENT selector. Registration becomes issuance authority only
after acceptance on protected central main.

## Authenticated source and chronology

| Fact           | Authenticated evidence                                                                                                                                                      |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Draft creation | PR created 2026-09-29 21:16:32 UTC on H0; complete Ready/Draft timeline has one subsequent Ready event and no conversion to Draft                                           |
| H0             | `5fefdc0d8ed92779bdb74a8efa39baba8fdf331e`; tree `ec724fe0956869ecb57b516818037b0512744fde`; sole parent `335a49de7a92710e7afce69de3f96a50810c56e4`                         |
| Ready          | Operator `aroviqen`, 2026-09-29 21:22:56 UTC; the source at that event is H0                                                                                                |
| Review phase   | One Copilot request at 21:22:57 UTC, one Copilot review at 21:26:08 UTC, automatic Security completion, and one later Code fallback after the provider usage-limit response |
| Code fallback  | `@codex review`, 2026-09-30 17:21:11 UTC, still H0; completed 17:24:51.503157 UTC                                                                                           |
| H1             | `f8e229ef68630e4e8363fb1af4137a53a55a304a`; tree `1098de89884096b2c19c9ad6f88a1eeeb1babe16`; sole parent H0; committed 2026-09-30 19:38:07 UTC                              |
| Current source | OPEN, Ready, H1, branch `issue-524-node26-tooling`                                                                                                                          |

Both source commits pass GitHub verification and direct SSH verification using
the maintained `aroviqen@secpal.app` public key. The complete source range has
only H0 and H1. The timeline has no force push, Ready-to-Draft event, second
Ready transition, or second unrestricted review phase. A provider retry after
the initial usage-limit response does not introduce another review phase.

The [symlink finding](https://github.com/SecPal/contracts/pull/525#discussion_r4138492628)
is material: H0 enumerates workflow names and dereferences matching symlinks
before the existing downstream protection executes. H1 changes that enumeration
to directory entries and requires a regular file before reading it. Its source
regression tests exercise symlinks, FIFOs, and directories. The maintained
thread is resolved and outdated, with the original finding bound to H0.
Independent current-safety probes reject H0 and accept H1; a FIFO target makes
an attempted unsafe read fail by timeout without reading a private file.

## Provider and finite-state binding

The exact retained provider-summary body is in
`tests/fixtures/contracts-525-provider-summary.json`. Its SHA-256 is
`3a6bedf5323de1943cf2560fef461ba1edb0f55ec166666f515dd4fb6900996e`.
It has exactly one completed Code row and one completed Security row, both on
derived provider head H0. Security completed at 2026-09-29 21:25:15.095393 UTC.
The one-remediation chronology retains H0 as provider authority while H1 is the
current source. Duplicate rows, mixed heads, and nonterminal rows fail closed.

The registered observations preserve review 1, remediation 1, Ready true,
Draft false, one Ready transition, Cycle 3 absent, and zero Recovery and
Continuation events. These values derive from the Ready event, authenticated
provider chronology, material finding, signed correction and complete thread
inventory. They are not inferred from commit count alone. The existing
independent review-budget admission required by loss-mode adoption grants no
additional review.

## Historical evidence survey

H1's signed message contains exactly this real trailer:

```text
SecPal-Validation-Receipt: b34ab1e452e4c82e5cef84ad3e4728b206f392517e5c12de2e03f179bfab32f3
```

The maintained durable-store inventory is delivery source history and protected
lifecycle publication. The workflow's `.context/` output scope is gitignored
in both source trees; neither tree contains companion receipt, reviewed-state,
or final-attestation package files. There is no maintained retained local-session
store, and temporary files from another workspace cannot supply authority.

The existing protected journal was surveyed at
`9f811c1a8b8d73190dcbf82b7d53dc0ad38a5df9`, including its complete 18-object
ancestry. No package or receipt identity for this delivery was retained; the
maintained absence verifier independently confirms no CURRENT or native
admission for #524. Ruleset `23668089` protects the existing branch from deletion
and non-fast-forward updates. Available Actions artifacts `8496453472`,
`8496450062`, `8303360440`, and `8303359942` were also opened; their only contents
are JavaScript or Python SARIF reports. PR source, comments, reviews, and threads
contain no historical package bytes. All maintained stores were surveyed.

The acknowledgment therefore records `UNAVAILABLE`, a null historical final
attestation digest, and `historical_bytes_reconstructed: false`. It retains the
signed receipt identity without recreating its missing package. Fresh current
safety has its own digest and does not claim historical byte identity.

## Enrollment boundary

The independently delivered [shared consumer correction #1164](https://github.com/SecPal/.github/issues/1164),
[PR #1165](https://github.com/SecPal/.github/pull/1165), is accepted on protected
central main `e785d0983f70b671fb7e2b2187d8991d02f9e781`. The existing v3 Ready
prior-authority path now composes a genuinely direct schema-1.3
`CURRENT_RECEIPT` adoption root. It retains the issued historical receipt
identity, unavailable companion bytes, authenticated historical Ready
observation, and provider head H0. It requires no post-enrollment Ready event
or zero-receipt recovery publication. The v4 Governance-Amendment path remains
a distinct provenance family.

This contracts-specific registration becomes issuance authority only after
acceptance on protected central main. The existing selector-only issuer and
signed exact-adoption constructors enroll through `enroll_existing_lifecycle`.
Issuance reauthenticates live source, feedback, policy, protection and absence;
journal CAS enforces one enrollment. Read back CURRENT and its H0 provider
binding, then exercise accepted-main Ready prior-authority derivation against
that genuine publication.

Downstream integration authenticates H1 as parent 1 and fresh protected
contracts/main as parent 2, retaining the maintained conflict, validation and
signing gates in the original contracts delivery workspace. This admission
creates no contracts integration candidate, provider request or thread mutation.

## Same-delivery delta preflight

The original #1038 branch, index and ten pending source files were authenticated
against their retained preservation digests before reconciliation. The accepted #1164 delta changed only the shared consumer, its tests and
workflow documentation;
no pending #1038 path overlapped it. A same-branch fast-forward preserved the
implementation, source qualification and temporary evidence.

Fresh observation reauthenticated the unchanged H0/H1 source chronology and
stable feedback digest `2b5edfc8b11e6bd49453fab8d45ad1ab1e669da30c5dc2d38500f279de601bae`.
The journal tip, active protection and four-artifact inventory above also remained
unchanged. Those exact identities preserve the historical signature, provider,
correction and unavailable-package evidence; elapsed time and the new prompt
invalidate none of them.

The earlier shared-consumer rejection is superseded by accepted #1164. Authority
compatibility is revalidated against that accepted implementation. The original
312-test result remains qualification evidence for its unchanged inputs, rather
than proof of the changed consumer. The maintained registered validation invokes
authority suites in separate processes; the combined diagnostic invocation's
temporary importer-cache failure grants no validation authority. Complete
Validation and receipt binding apply to this delivery's final tree. Contracts
source remains read-only throughout.
