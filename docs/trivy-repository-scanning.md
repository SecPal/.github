<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Trivy pre-build repository scanning

The reusable `trivy-repository-scan` action scans one clean local checkout before
build or publication. It has no inputs: the caller owns checkout and the action
requires the workspace `HEAD` to equal the exact lowercase `github.sha`. It
rejects a dirty or sparse workspace, never accepts a remote repository or ref, and has no
source-write, package-publish, deployment, issue-write, or production credential
authority.

## Caller contract

Callers pin both checkout and this action to reviewed 40-character commits. The
job needs only `contents: read` and an explicit timeout.

```yaml
permissions: {}

jobs:
  repository-security:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - name: Check out the exact commit under review
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.sha }}
          persist-credentials: false

      - name: Scan the checked-out repository
        id: repository-scan
        uses: SecPal/.github/.github/actions/trivy-repository-scan@<reviewed-40-character-commit>

      - name: Apply repository-specific acceptance
        env:
          GATE_STATE: ${{ steps.repository-scan.outputs.gate-state }}
        run: ./scripts/apply-repository-security-gate.sh "$GATE_STATE"
```

The shared action always fails for `UNKNOWN_STALE`. A repository adoption may
make `ACTIONABLE` or `REVIEW_REQUIRED` blocking according to that repository's
accepted contract; it must consume the output instead of copying scanner logic.

## Scanner and policy identity

The action downloads Trivy `0.74.0`, verifies the archive against the reviewed
SHA-256 identity, checks the reported version, and invokes filesystem scanning
with `vuln,secret,misconfig` explicitly. Built-in misconfiguration checks are
used from that pinned binary with check updates disabled. Vulnerability and Java
database updates complete before scanning; their metadata and database content
are hashed into the evidence identity. A failed download, stale database,
scanner failure, identity mismatch, or malformed output produces
`UNKNOWN_STALE` and a failing action.

Every Trivy process receives an empty environment apart from a private `HOME`
and an explicit action-owned empty configuration. A checked-out `trivy.yaml` or
caller-provided `TRIVY_*` variable therefore cannot alter scanner selection,
skip paths, database handling, or output behavior.

[`trivy-repository-scan-v1.json`](../policies/trivy-repository-scan-v1.json) is
the sole actionability and exception policy. High and critical vulnerabilities
and misconfigurations are actionable; lower or unknown severities require
review. Every secret finding is actionable. The policy hash is included in each
successful result.

Exceptions require an exact repository identity, class, rule, repository-relative path, disposition,
expiry, rationale, and unique ID in the central policy. `NOT_AFFECTED` is valid
only for vulnerability findings. Expired, duplicate, ambiguous, or malformed
exceptions fail closed. VEX runtime injection is disabled; reviewed VEX may be
enabled only by changing the versioned central policy and binding its document
identity there. The Trivy-native ignore file is intentionally empty so a caller
cannot suppress findings before policy admission.

## Evidence and redaction

Each action invocation uploads one uniquely named normalized result for 14 days.
Its schema is
[`secpal-trivy-repository-scan-v1.schema.json`](schemas/secpal-trivy-repository-scan-v1.schema.json).
It records the exact repository commit, scanner version and archive identity,
vulnerability database identity and freshness, policy identity, deterministic
finding fingerprints, the hash of the trusted invocation/helper/policy bundle,
and one of these states:

- `CLEAN`
- `ACTIONABLE`
- `REVIEW_REQUIRED`
- `UNKNOWN_STALE`

Native scanner JSON is temporary and is deleted before upload. Secret
normalization allowlists only rule ID, severity, repository-relative path, and
line range; Trivy `Match` and `Code` values never enter retained evidence or the
job summary. Misconfiguration evidence retains rule, file, line, and resource
context. Vulnerability evidence retains advisory, package, installed version,
and fixed version where available. The action does not create issues or mutate
source, dependencies, artifacts, releases, deployments, or production.

## Validation fixtures

`tests/fixtures/trivy-repository-scan/workspace` contains a vulnerable source
lockfile, a rejected container configuration, and a secret template whose test
value is assembled only in a temporary directory. The native replay runs the
pinned scanner and proves all three result classes, database identity capture,
and removal of the synthetic secret value. Unit fixtures cover stale database,
malformed output, network/failure envelopes, deterministic normalization, and
closed exception semantics.

The action rejects gitlinks rather than fetching submodules. Development
packages are explicitly included. Inline scanner suppression directives are
rejected from immutable tracked source before scanning because the pinned tool
omits ignored IaC results before native JSON. Secret scanning disables built-in path skipping and global
allow rules; only the reviewed central exception contract can suppress findings.

Normalized candidates stay private until redaction verification correlates
Trivy's cause-line censor masks with immutable Git blobs. Captured values are
used only transiently to reject aliases in all public metadata. Missing,
truncated, binary, or ambiguous censor evidence fails closed. Trivy diagnostics
stay private, fail closed on unqualified warnings/errors or malformed/missing log framing
even when the process exits zero, and are discarded. Every Python invocation is
isolated from checkout imports.
The exact absent-cache diagnostic for archive-pinned embedded checks is accepted
once only, with independent confirmation that no external checks cache exists.
Normalization itself consumes captured canonical path strings and performs no
filesystem observation. Only verified normalized evidence enters the bounded
artifact directory.

## Composer severity fallback qualification

The exact Trivy 0.74.0 severity fallback advisory is qualified once per process
against the same parsed native result used for normalization. Other warnings,
additional warnings, changed text, malformed framing, and parser errors still
fail closed. No caller input selects diagnostic policy. Qualification requires
the reviewed version/archive identity, the exact scan workspace, and native
Composer (`lang-pkgs` / `composer`) CVE findings from the PHP Security Advisories
Database with an omitted `SeveritySource`. Every finding with an omitted source
must satisfy this reviewed context; unsupported ecosystems and representations
remain fail-closed when the advisory is present.

The pinned [`autoDetectSeverity` implementation](https://github.com/aquasecurity/trivy/blob/v0.74.0/pkg/vulnerability/vulnerability.go)
first considers the advisory source and NVD (and GHSA for GHSA IDs). Its last
fallback returns the database severity with an empty source and emits the full
versioned documentation advisory through `sync.OnceFunc`. The reviewed Composer
CVE representation has no severity for its advisory source, no usable NVD
severity, and a GHSA `VendorSeverity` entry matching the emitted fallback severity.
Only GHSA and an optional NVD UNKNOWN entry qualify this fallback; additional
vendor sources require independent qualification and remain rejected.
An advisory-source entry, even UNKNOWN, would return before that warning; an
NVD UNKNOWN entry can fall through. GHSA IDs and package-specific overrides are
outside this bounded qualification. The native JSON omits empty
`SeveritySource`; an explicit empty or malformed source is rejected.

This does not attribute the fallback severity to a particular vendor. Trivy DB
v2 explicitly describes its fallback `Severity` as not source-attributable.
Normalized evidence already binds the emitted severity, advisory, package and
version to the content identity of the complete database, exact scanner archive,
and trusted configuration implementation. Together those identities reproduce
the source-selection decision; no public diagnostic text or schema expansion
is needed. Freshness, central exception policy, and immutable-source secret
redaction still gate admission after scanner execution. No mutation or
publication authority is added.

The hermetic `composer-0.74.0-native.json` fixture retains only bounded,
secret-free vulnerability fields observed from the exact archive on 2026-10-04
with `symfony/http-foundation` v5.4.0 in `packages-dev`. The live replay preserves
the generic fixture, adds this Composer development lockfile, and exercises the
maintained action's scan step. It requires vulnerability, misconfiguration and
synthetic-secret findings with exact subject/scanner/database/policy/configuration
identity, checks public logs/summary/evidence for secret leakage, and confirms
private native files are deleted. Unknown diagnostics and real parser/process
failures remain negative cases. Callers must explicitly review and adopt the
accepted immutable scanner revision; this correction does not change any API
caller pin.
