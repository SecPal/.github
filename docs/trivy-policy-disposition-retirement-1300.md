<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Retirement of recurring repository-scan dispositions (#1300)

This is a source proposal under [#710](https://github.com/SecPal/.github/issues/710).
It is not protected acceptance, a consumer-pin update, or permission to merge.
No expiry is renewed. The candidate policy has zero exceptions. Scanner/tool,
database freshness, redaction, thresholds, OCI admission and branch protection
remain unchanged.

## Evidence and classification

Current protected sources inspected on 2026-11-04:

- frontend: `7b2a45cbcefe876da02ae12807234f7196802857`
- Android: `f99a90b68fae8aa10b13da15a5c98fdaac5da49d`
- deployment: `bf2282e3e112ac003360ecb3dff390eafe282dbd`

The same pinned Trivy 0.74.0 archive and fresh vulnerability/Java databases scanned
all three clean checkouts with explicit vuln, secret and misconfig scanners,
development dependencies and pinned embedded checks. Package inventories include
braces 3.0.3 and deepmerge 4.3.1. Native vulnerability findings for both are
currently absent, also in independent minimal package canaries. The lodash
4.17.23 positive canary detects CVE-2026-2950 and CVE-2026-4800 with that same DB.
Absence of one advisory in today's DB is not proof that a package is generally
safe or that future findings may be suppressed.

The current vulnerability database file SHA-256 is
`dc46f80922f985bb63542481d71bacd708893c48b926a4eb2a581929455a43a0`.
It is the digest-authenticated official DB used by the unchanged #1299
qualification. The full combined database identity, metadata, commands,
redacted observations and exact source identities are retained in the #1300
qualification record.

| Retired entry                                       | Independent current classification                                                                                                                                                                                                                                                                                              | Remaining admission                                                                                                                                                                                            |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| frontend-braces-cve-2026-93687-not-affected-1199    | Obsolete finding: upstream withdrew GHSA-vfj7-8cjw-p6xm on October 23; pinned scanner inventories the package without this CVE.                                                                                                                                                                                                 | No waiver; any future native finding follows unchanged severity policy.                                                                                                                                        |
| android-country-reference-sendgrid-1199             | Proven false positive in exact source blob f0bc32de9c027ed0bd3b7842642e5d137510e65c. A minified public ISO country list matches the pinned detector; no credential contributes.                                                                                                                                                 | Removing IGNORED makes the current Android source ACTIONABLE. Fix the source representation and rebuild/adopt authenticated web assets before CLEAN.                                                           |
| deployment-ds-0026-1236                             | Deliberate architecture: the non-production gateway has one Quadlet HealthSpec/HealthCmd authority with bounded probes, Notify=healthy and HealthOnFailure=kill. An image probe would duplicate it.                                                                                                                             | Retained native LOW finding requires review; no automatic architecture waiver.                                                                                                                                 |
| deployment-gcp-0031-1236                            | Real residual public-IP exposure. Runner /32 SSH, per-run identity, identity removal and TTL reduce exposure but do not eliminate it.                                                                                                                                                                                           | Native HIGH remains ACTIONABLE; no NOT_AFFECTED claim.                                                                                                                                                         |
| deployment-gcp-0033-1236                            | Deliberate key-custody configuration: boot attachment uses Google-managed encryption. Missing CMEK/CSEK is not an unencrypted disk. No customer-key requirement is established for this ephemeral non-customer workload.                                                                                                        | Native LOW remains REVIEW_REQUIRED, independently of disk-resource observation.                                                                                                                                |
| deployment-gcp-0034-1236                            | Same deliberate key-custody configuration, separately observed disk resource.                                                                                                                                                                                                                                                   | Native LOW remains REVIEW_REQUIRED; keep both disk findings.                                                                                                                                                   |
| deployment-gcp-0036-1236                            | Deliberate management architecture: OS Login is disabled in favor of scoped per-run Ed25519 access, blocked project keys, exact-peer enforcement and cleanup.                                                                                                                                                                   | Native MEDIUM remains REVIEW_REQUIRED; static intent does not prove an actual cloud run.                                                                                                                       |
| deployment-gcp-0075-1236                            | Deliberate topology: Private Google Access has no effect on the current external-IPv4 instance. Provider semantics and source both support this narrow conclusion.                                                                                                                                                              | Native LOW remains REVIEW_REQUIRED; topology changes invalidate the reasoning.                                                                                                                                 |
| deployment-gcp-0029-1236                            | Real residual audit gap: VPC flow logging is absent. Resource/provenance/cleanup evidence does not provide packet-flow visibility.                                                                                                                                                                                              | Native LOW remains REVIEW_REQUIRED.                                                                                                                                                                            |
| deployment-gcp-0076-1236                            | Same real logging gap, separately observed MEDIUM check.                                                                                                                                                                                                                                                                        | REVIEW_REQUIRED; keep both flow-log findings.                                                                                                                                                                  |
| frontend-deepmerge-cve-2026-93753-not-affected-1288 | Technically unreachable through the inspected build caller: exactly one deepMerge({}, staticDefaults) at module initialization. Real current-module instrumentation confirms caller options never reach it. No patched package/caller release exists. Native DB currently reports no CVE; the upstream advisory remains active. | No retained path-only NOT_AFFECTED waiver. If the scanner reports the LOW CVE again, it remains REVIEW_REQUIRED until a supported fix/removal or independently accepted identity-bound technical proof exists. |

Original findings, rationales, selectors and exact original expiry values are
preserved byte-for-byte in
[`historical-policy-20261104.json`](../tests/fixtures/trivy-repository-scan/historical-policy-20261104.json).
That file is test/audit history, never runtime policy. Historical tests still
exercise complete finding metadata, exact-blob source substitution, changed
source/control identities and all eight deployment observations.

The current deployment scan independently still fails diagnostic admission:
its source/run-bound qualification expires on November 4. This proposal neither
renews that qualification nor interprets missing Terraform values as completed
evaluation. Deployment remains UNKNOWN_STALE until its own source-coverage
contract can be accepted. Even with healthy coverage, the eight unexcepted
observations prevent CLEAN. Removing an exception is not remediation.

## Independent evidence

This assessment revisits, rather than inherits, historical decisions:

- [#1139](https://github.com/SecPal/.github/pull/1139) review 5416459789 identified
  the missing commit binding of the original braces waiver. Removing every
  current path-only waiver prevents its reuse on changed components.
- [#1195](https://github.com/SecPal/.github/pull/1195) review 5501415516 required
  authenticating the production Android commit/path/blob. Current source is
  independently reauthenticated and matched against the exact pinned detector.
- [#1200](https://github.com/SecPal/.github/pull/1200) review 5507874156 explicitly
  left qualification judgment to human review; dates are not technical proof.
- [#1237](https://github.com/SecPal/.github/pull/1237),
  [#1245](https://github.com/SecPal/.github/pull/1245) and
  [#1289](https://github.com/SecPal/.github/pull/1289) preserve the original
  source/control and deepmerge assessments. No independent approval is inferred
  from empty review lists or a review that could not run.

Current checks include real Node instrumentation of the integrity-locked
node-resolve/deepmerge sources, real Vite minification and pinned native Trivy
detection of old/new country output, current source inspection and the maintained
14-test Quadlet contract suite. No provider, container, application or live-host
operation is used to invent run-bound evidence.

Primary references:

- [withdrawn braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
- [active deepmerge advisory](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
- [pinned SendGrid detector](https://github.com/aquasecurity/trivy/blob/v0.74.0/pkg/fanal/secret/builtin-rules.go)
- [default Google encryption](https://docs.cloud.google.com/docs/security/encryption/default-encryption)
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/configure-private-google-access)
- [OS Login](https://docs.cloud.google.com/compute/docs/oslogin)
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs)

## Semantics and negative proofs

Structural policy errors remain fail-closed. An expired valid disposition is
inapplicable at finding admission; it cannot suppress the finding and cannot
invalidate unrelated scan health. Exact-boundary expiry also withdraws
suppression. Scanner errors, unverified scanner identity, stale/malformed DB
evidence and unsupported diagnostics still yield UNKNOWN_STALE.

All eleven current exceptions are removed, including the still-unexpired Android
entry. No new technical exemption, VEX document, auto-renewal, alternate scanner,
risk acceptance or unbounded ignore is introduced. Retired source/component
waivers cannot be inherited even before their old deadlines. Secret-byte changes
and source/control changes still invalidate the historical exact technical proof.

The source candidate builds on the unchanged signed #1299 commit
`705e734ec61a948b025db3055c42776fbf2b340b`. Its replay file remains byte-identical.
This is an explicit source dependency, not an edit or approval of Draft #1299.
Draft #1298 is untouched.

## Protected delivery and consumer pins

Protected current main is
`12cc0feddc25ac5e3cb5bcba5383db10c0332c9a`.
The current governance gate executes the accepted action at
`e6626097efc7770557b2a6abaede5c09592e8948`, never the candidate's scanner or policy.
That accepted revision rejects a clean independent observation because of global
expired dispositions. Candidate tests cannot repair or authorize that authority.

After protected acceptance, use its verified immutable main revision R:

| Repository | Exact consumer location                                                      | Current accepted action revision         |
| ---------- | ---------------------------------------------------------------------------- | ---------------------------------------- |
| .github    | .github/workflows/quality.yml                                                | e6626097efc7770557b2a6abaede5c09592e8948 |
| frontend   | .github/workflows/reusable-repository-security.yml                           | f94b47c6a44f924b11b2802ac1c334f20b2e93a9 |
| android    | .github/workflows/reusable-repository-security.yml                           | 72e3b32a88513f381aa6cd769618bf197106d794 |
| deployment | .github/workflows/quality.yml                                                | f94b47c6a44f924b11b2802ac1c334f20b2e93a9 |
| api        | .github/workflows/reusable-repository-security.yml and publish-container.yml | f94b47c6a44f924b11b2802ac1c334f20b2e93a9 |
| contracts  | .github/workflows/local-openapi-lint.yml                                     | 72e3b32a88513f381aa6cd769618bf197106d794 |
| secpal.app | .github/workflows/quality.yml and deploy-uberspace.yml                       | 72e3b32a88513f381aa6cd769618bf197106d794 |
| operations | No current scanner consumer                                                  | NONE                                     |

R must exist on protected accepted main and pass independent source review,
signature/provenance and external-action packaging qualification before
repository-specific consumer PRs may adopt it. No placeholder, self-reference,
candidate-only authority, temporary Required Check disablement, branch-protection
change or OCI risk acceptance repairs this bootstrap.

If the existing trusted gate cannot admit this correction through a separately
accepted route, delivery is BLOCKED at the named old action/required gate. This
task does not invent an exceptional merge route. Frontend source encoding must
also be accepted before Android adopts that exact frontend revision and
rebuilds its pinned assets through the existing authenticated build. Until then
the old Android bytes remain honestly blocked by the proposed zero-exception
policy; current deployment remains blocked for its own reasons.
