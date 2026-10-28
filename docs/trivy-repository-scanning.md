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

## Governance repository admission

SecPal/.github invokes the accepted action at
`55bcdb6f00eb7d552da206f83fcdc87cf2c43375` inside its existing required
**Evidence Architecture PR Gate**, immediately after an exact `github.sha`
checkout with persisted credentials disabled. Successful execution and exactly
`CLEAN` are both required before candidate validation tooling runs. Missing,
skipped, cancelled, failed and non-clean scans cannot admit that job.

The action runtime, policy and v4 result contract come from the separately
accepted immutable action archive. Candidate scanner and policy files are
untrusted scan input; they are never the executing scanner's authority. The job
uses only `contents: read` and retains bounded, secret-safe evidence for 14 days.
This does not make the candidate-controlled workflow technically tamper-proof:
normal protected checks, source inspection and the sole maintainer's manual
merge authority still apply.

The central policy validates every exception's expiry, including exceptions for
other repositories. The reviewed Frontend disposition and eight Deployment
dispositions/source-control qualification expire at `2026-11-04T00:00:00Z`;
the exact-blob Android disposition expires at `2026-11-20T00:00:00Z`.
The earliest global deadline is therefore November 4, including scans of
SecPal/.github with no matching findings. Central requalification is recorded
under #1244, preserving completed #1199 and #1236. This consumer adoption does
not renew or relax those entries; a later accepted policy and consumer pin
adoption are needed before the next global deadline.

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

`SECRET` exceptions additionally require `source_blob`: the exact lowercase
40-character Git blob ID of the reviewed file. Admission compares this selector
with independently observed source identity from the exact checked-out commit.
An unchanged path, rationale, generated filename, or finding fingerprint does
not establish source identity. A different committed blob remains actionable,
even when every other selector and the fingerprint are unchanged. Missing or
malformed policy bindings fail closed; no caller input or native scanner field
can provide the source facts used to consume a disposition. Vulnerability and
misconfiguration exception selectors retain their existing contract.

Before scanning, `prepare_target_snapshot` verifies the exact clean checkout and
creates an action-owned Git copy without caller hooks/configuration, shared
objects, hardlinks or borrowed alternates. It materializes authenticated raw Git
blobs without checkout filters, line-ending conversion or export exclusions and
seals the private copy read-only, preserving executable bits and symlinks without
following them during sealing. Trivy, source observation and redaction all read
that same snapshot. Caller mutations cannot change its scanned bytes. No source
worktree/index is written; cleanup restores write permissions only inside the
owned private tool directory before deleting it.

The observation owner, `observe_secret_sources`, rechecks the exact clean snapshot
after scanning. For each secret path it requires a regular file in that commit's
tree, reads the immutable blob with replacement objects disabled, independently
hashes its raw Git object content, and compares the scanned file's raw bytes.
Symlinks, missing files, changed bytes and unverifiable identities fail with
`TARGET_IDENTITY_FAILURE`. Its bounded output contains only the commit and
path-to-blob identities. `normalize_secret_sources` purely validates the closed
observation and exact commit/path coverage, then retains `source_blob` on each
secret finding. Pure policy admission owns the exception comparison; result
assembly performs no additional source observation. Source bytes and matched
captures never enter this fact transport.

## Evidence and redaction

Each action invocation uploads one uniquely named normalized result for 14 days.
Its schema is
[`secpal-trivy-repository-scan-v4.schema.json`](schemas/secpal-trivy-repository-scan-v4.schema.json).
The public result version is `secpal-trivy-repository-scan-v4`; every `SECRET`
requires `source_blob`. The published closed v1, v2 and v3 schemas are preserved unchanged.
Consumers adopting this action revision must select the v4 schema from the same
reviewed governance revision; strict v1/v2/v3 consumers reject the new version rather
than silently interpreting an incompatible finding shape.
It records the exact repository commit, scanner version and archive identity,
vulnerability database identity and freshness, policy identity, deterministic
finding fingerprints, the hash of the trusted invocation/helper/policy bundle,
and one of these states:

- `CLEAN`
- `ACTIONABLE`
- `REVIEW_REQUIRED`
- `UNKNOWN_STALE`

Failure codes locate the rejected boundary without retaining native output.
`SCANNER_FAILURE` identifies a nonzero native filesystem-scan process exit;
`DIAGNOSTIC_ADMISSION_FAILURE` identifies rejection of private diagnostics
after native execution succeeded. `MALFORMED_OUTPUT` identifies missing,
truncated, malformed or unqualified native evidence. These outcomes all remain
`UNKNOWN_STALE`; process success alone cannot establish healthy evidence.
Database, target, scanner-identity and policy failures retain their existing codes.
The diagnostic distinction introduced in v3 is preserved in the v4 closed enum.
Consumers must adopt the v4 schema and action from the same reviewed revision;
older validators reject v4 explicitly instead of silently interpreting a changed result.

The Terraform parser's missing-variable warning remains unqualified except for
the exact source-bound deployment qualification described below. Otherwise a zero
exit with this warning remains `DIAGNOSTIC_ADMISSION_FAILURE`, without publishing
the warning or source. Runtime-only variables are not supplied by the scanner;
the pinned parser substitutes unknown typed values before module evaluation.
Absence of findings cannot establish complete evaluation of dependent resource
relationships, such as a runtime-selected management source range. Earlier retained `SCANNER_FAILURE` results do not
establish which boundary failed when private native evidence is unavailable.

Native scanner JSON is temporary and is deleted before upload. Secret
normalization allowlists only rule ID, severity, repository-relative path,
line range, and independently observed `source_blob`; Trivy `Match` and `Code`
values never enter retained evidence or the job summary. Misconfiguration evidence retains rule, file, line, and resource
context. Vulnerability evidence retains advisory, package, installed version,
and fixed version where available. The action does not create issues or mutate
source, dependencies, artifacts, releases, deployments, or production.

## Validation fixtures

Immutable GitHub action downloads honor the repository's export attributes.
Only `.github/actions/trivy-repository-scan/` is exported from `.github`;
workflows, templates, instructions, and unrelated actions remain excluded.
`python3 -m unittest tests/secpal-trivy-action-archive.py` archives the exact
tracked candidate bytes with Git's export semantics, verifies the complete
runtime closure against its Git blobs, and exercises its existing configuration
identity from the exported files. Negative cases prove that parent pruning,
runtime file exclusions, and unrelated exports fail qualification. This check
runs in preflight and complete registered validation; it supplements the native
replay and the required genuine external GitHub Actions invocation.

`tests/fixtures/trivy-repository-scan/workspace` stores the unchanged vulnerable
lockfile as a non-active `package-lock.json.in` input. The replay materializes
its actual name only in its disposable workspace. It constructs the original
Containerfile bytes there directly, including CC0 SPDX metadata, before committing
and scanning. No container manifest or container template is tracked in this
fixture directory. The focused regression executes the actual construction
statement and compares the result with immutable Git blob
`57c65dc80accc264edbb1c735300feb47adde2a5`.

The secret template's test value is likewise assembled only in the temporary
directory. The native replay proves all three scanner classes, all original
Lodash and container misconfiguration detections, database identity capture,
and removal of synthetic secret values. Unit fixtures cover stale databases,
malformed output, network/failure envelopes, deterministic normalization, and
closed exception semantics.

The maintained replay exports the candidate action with the existing immutable
archive qualification. It also authenticates the reviewed Android asset from
commit `5d8a5bf357a6315706b25d6b8285a93d2edbad2d` against blob
`f0bc32de9c027ed0bd3b7842642e5d137510e65c`, and runs that exact file in a
temporary Git fixture through an archived action with a disposable source-bound
test policy. The reviewed blob retains one `SECRET` with `IGNORED` metadata and
becomes `CLEAN`. Replacing it with a runtime-generated synthetic SendGrid value
at the identical Android selector and line preserves the fingerprint but yields
one actionable finding and zero exceptions. Both runs require fresh databases,
successful redaction, and private-material cleanup. Only bounded identities and
outcomes survive the replay; the fixture source and native captures are deleted.
This mechanism qualification adds no Android production policy entry. The
separate policy-review delivery must revalidate classification, exact source
lineage, and a future bounded expiry before adoption.

The action rejects gitlinks rather than fetching submodules. Development
packages are explicitly included. Inline scanner suppression directives are
rejected from immutable tracked source before scanning because the pinned tool
omits ignored IaC results before native JSON. Secret scanning disables built-in path skipping and global
allow rules; only the reviewed central exception contract can suppress findings.

Normalized candidates stay private until redaction verification correlates
Trivy's cause-line censor masks with immutable Git blobs. Captured values are
used only transiently to reject aliases in all public metadata. Full cause lines
must match every immutable source byte outside censor spans. For the exact
Trivy 0.74.0 archive, raw source lines longer than 100 bytes may instead use the
bounded cause excerpt emitted by pinned
[`findLocation`](https://github.com/aquasecurity/trivy/blob/e1fd17a0ea4a8cf24bc4b4dd7e2cfbf4bb31b994/pkg/fanal/secret/scanner.go#L862).
An excerpt requires exactly one mask-compatible window in the authenticated
source line, including overlapping positions. Zero or multiple positions fail
closed. Each censor span maps to immutable bytes; literal stars alone provide no
capture, mixed literal-star spans are rejected, and textual captures require
strict UTF-8 decoding. At least one real censor span is required per finding.
The length cutoff is applied before removing carriage returns, so CRLF lines
with exactly 100 content bytes can use an authenticated shorter excerpt.
Lossy UTF-8 boundary sanitization remains unsupported: a replacement character
does not prove equality with the immutable visible bytes, and the native
invalid-UTF-8 warning still fails scanner-health admission. No diagnostic
exception is added for this representation.
Missing, mismatched, unsupported, binary, or ambiguous censor evidence fails
closed. Trivy diagnostics
stay private, fail closed on unqualified warnings/errors or malformed/missing log framing
even when the process exits zero, and are discarded. Every Python invocation is
isolated from checkout imports.
The exact absent-cache diagnostic for archive-pinned embedded checks is accepted
once only, with independent confirmation that no external checks cache exists.
Normalization itself consumes captured canonical path strings and performs no
filesystem observation. Only verified normalized evidence enters the bounded
artifact directory.

The maintained native replay generates short and minified long-line secrets at
runtime in temporary Git repositories, verifies each exact commit, and checks
both cause representations and the raw CRLF cutoff. It also exercises the action's stdout, stderr,
summary and artifact boundary for capture leakage and private-file cleanup.
Unit cases reject duplicate excerpt positions, altered visible bytes, missing
censor evidence, unsupported captures, literal-star ambiguity, and aliases in
public metadata. This qualification changes the configuration identity without
changing the scanner archive, action inputs, schema, or central policy. It adds
no exception for a downstream secret finding; a qualified finding remains
actionable until its separate policy disposition is reviewed.

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
versioned documentation advisory through `sync.OnceFunc`. The known-severity Composer
CVE representation has no severity for its advisory source, no usable NVD
severity, and a GHSA `VendorSeverity` entry matching the emitted fallback severity.
Only GHSA and an optional NVD UNKNOWN entry qualify this fallback; additional
vendor sources require independent qualification and remain rejected.
An advisory-source entry, even UNKNOWN, would return before that warning; an
NVD UNKNOWN entry can fall through. GHSA IDs and package-specific overrides are
outside this bounded qualification. The native JSON omits empty
`SeveritySource`; an explicit empty or malformed source is rejected.

A separately qualified native `UNKNOWN` representation omits **both**
`SeveritySource` and `VendorSeverity`. Trivy's pinned DB dependency normalizes
missing severity information to `UNKNOWN` and omits UNKNOWN vendor entries;
native JSON omits those empty fields. This source explanation is not a claim
about the build revision of a downloaded database: actual fresh-database native
qualification independently confirmed the field omissions. Only absent keys
qualify; explicit empty, null, malformed or populated vendor metadata is not
equivalent in this UNKNOWN branch. The Composer/CVE/advisory, scanner, exact
workspace, diagnostic framing/count and database requirements remain mandatory.
No vendor attribution or known severity is invented. The finding remains
`UNKNOWN` and the existing policy classifies it as `REVIEW_REQUIRED`, never
`CLEAN` merely because scanning succeeded. A CLEAN-only caller still blocks it.
Other scanner/parser warnings and errors remain fail-closed.

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

The secret-free `composer-unknown-0.74.0-native.json` fixture retains the bounded
native vulnerability fields observed on 2026-10-15 for
`symfony/http-foundation v8.0.15` / `CVE-2026-108082`, with only the private
artifact path replaced by `.`. Native archive identity and fresh database
identity were authenticated; neither source nor vendor severity fields were
present. Unit mutations reject explicit empty/null/malformed fields, unsupported
vendor metadata or advisory provenance, substituted scan surfaces and stale
databases through the maintained evaluator.

The historical live replay created that two-file Composer development fixture
and required schema-validated `REVIEW_REQUIRED` with the actual native omissions
and fresh database identity. On 2026-10-28, the live feed enriched the same
`CVE-2026-108082` / `symfony/http-foundation v8.0.15` observation to `HIGH`,
with omitted `SeveritySource` and exactly `VendorSeverity: {"ghsa": 3}`.
The previous live UNKNOWN qualification therefore ended.

The requalified live replay requires exactly that HIGH native representation,
the same reviewed fallback advisory, and schema-validated `ACTIONABLE` with
one actionable vulnerability and zero exceptions or review-required findings.
Subject, archive, configuration, policy, fresh database identity and private-file
cleanup remain mandatory. The existing Composer fallback evaluator already
qualifies this representation; no production admission, severity override,
policy exception or qualification expiry changes.

The bounded historical UNKNOWN native fixture and its negative unit mutations
remain as historical evidence and evaluator coverage. They do not establish
current live UNKNOWN scanner coverage. Any later change to the live HIGH
representation again fails closed and requires requalification; the test never
skips the case or accepts arbitrary feed outcomes. The original hosted API
diagnostics/database were not retained, so neither qualification establishes
the historical record-level failure cause.

## Exact deployment source qualification and run-bound controls

Version 4 adds explicit coverage facts for the source-bound deployment
qualification owned by [#1236](https://github.com/SecPal/.github/issues/1236).
Published v1, v2 and v3 schemas remain unchanged. Consumers adopting this
implementation must consume the v4 schema from the same immutable shared
revision. Existing consumers pinned to earlier revisions retain their contracts.

This is repository-static admission, never approval of a concrete cloud run.
A qualified deployment result includes:

- scope REPOSITORY_STATIC;
- run_bound_status REQUIRED_NOT_EXECUTED;
- the actual scanned commit, independently observed Git source identities and
  complete Terraform file inventory;
- four control obligations that remain mandatory at their operations;
- an explicit qualification expiry, initially 2026-10-27 00:00 UTC.

The action summary displays this limitation. CLEAN applies to the static
repository result under its reviewed dispositions. It does not claim that a
runner address, key, image, expiry, provider resource or target execution has
been admitted. No tfvars, defaults, IPs, keys or plan values are fabricated for
the repository scan. The qualification and dispositions require independent
review and protected shared-main acceptance before consumer adoption.

### Why this exact source can be qualified

Pinned Trivy 0.74.0 creates typed unknowns for missing root variables in
pkg/iac/scanners/terraform/parser/parser.go. Its native diagnostic has the
exact module="root" variables="..." framing; variable order is immaterial,
but the full set, multiplicity, diagnostic count and scanner identity matter.

Only the actual deployment module and its existing enforcement sources qualify.
All Terraform paths must match the reviewed inventory; the infrastructure,
scripts, configuration and schema trees and gateway Containerfile must match
their reviewed Git identities. The complete .github source inventory is bound
by a SHA-256 fingerprint of Git identities, including file modes, workflows and
local actions. Two narrowly identified full-SHA references in quality.yml are
normalized in memory: the existing read-only scanner step (avoiding a
self-referential shared commit) and the independent REUSE workflow revision.
The scanned source is never rewritten. The REUSE owner/path, job, permissions,
conditions, commands and every other automation byte/mode remain bound.
Missing, mutable, null or duplicate REUSE references fail closed.

This fingerprint proves Terraform source/control identity; it does **not**
approve a referenced workflow or claim that different Git commits have identical
contents. Native protected delivery independently verifies that a REUSE revision
belongs to accepted SecPal/.github main, using the existing
verify_governance_pin helper in tests/android-consumed-workflow-action-pins.sh
against an authenticated accepted base. That helper rejects foreign ownership,
missing objects and unpublished candidates. Review also verifies the actual
workflow and nested action provenance; the existing required REUSE check must
genuinely execute. The consumer's workflow-action-pin contract owns immutable
reference structure. A 40-character pattern alone is never provenance approval.

This separates independent licensing CI delivery from the bounded Terraform
qualification, without an approved-version list, new network authority, or
general normalization framework. Any REUSE caller permission, execution or job
change still changes the fingerprint. Changes inside the called REUSE workflow
remain owned by central workflow security review, outside Terraform proof. Updating only its accepted immutable revision
does not require renewing Terraform proof or the existing dispositions.
Scanner adoption still independently verifies the accepted shared revision.
Changed guards, inputs, dependencies, schemas, extra modules, unexpected diagnostics, wrong scanner
identity or expiry reject diagnostic admission. Caller/native JSON cannot
supply these source observations.

The source has a fixed resource graph: one network, subnet, disk, instance and
closed firewall rules. No unknown input controls resource multiplicity, public
access presence, flow-log presence, encryption-key choice, OS Login, protocols,
ports, capability settings or the Quadlet health policy.

| Properties                               | Repository-time facts                                                                             | Required concrete-value authority                                                                                                    |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Management SSH                           | TCP22, one source address with literal /32, matching instance/network tags                        | Actual global runner IPv4, fresh Ed25519 public key and exact run/source binding; existing request admission and access rotation     |
| Source, run and image                    | Closed project/profile/type/disk/zone constraints, explicit identity fields                       | Existing trusted control derives actual GitHub run/SHA/time and authenticates exact image evidence                                   |
| Metadata and optional qualification data | Canonical OpenTofu renderer, closed schema/size/provenance constraints and creation preconditions | Existing actual-variable metadata admission before provisioning credentials, then OpenTofu input/precondition checks before creation |
| Target authority                         | Distinct uncredentialed target job, no target-controlled provider commands                        | Existing identity transition must succeed before preparation/handoff/target execution                                                |
| Lifetime and cleanup                     | Maximum three-hour TTL, exact ownership selectors, no broad deletion path                         | Current time, exact continuation/run/instance and janitor/cleanup admission on every operation                                       |
| Gateway health                           | One accepted HealthSpec/Quadlet/systemd owner, bounded probe and failure lifecycle                | Existing native integration validates generated configuration and failure/restart behavior                                           |

[OpenTofu variable validation](https://opentofu.org/docs/language/values/variables/#custom-validation-rules)
remains the language authority; the shared scanner does not reimplement it.
The existing providerless native OpenTofu characterization rejects every missing
required input and malformed security-relevant values before a usable plan.
Existing control tests exercise wrong peer/key/run/target, access rotation,
identity removal, metadata failure and pre-credential ordering. These tests
prove enforcement behavior; they are not a claimed successful provider run.

The qualification does not substitute the parser warning for a completed
dynamic evaluation. It identifies which immutable source and operation guards
own that evaluation. The real trusted-control path still obtains actual
variables and performs those checks on every execution. A failed or absent
check cannot authorize its relevant creation, access or target operation.

### Phase-1 source requalification (#1258)

The independently reviewed deployment PR [#361](https://github.com/SecPal/deployment/pull/361)
has exact head `6c3f7d517526c34223065eba5d81f7924974ee35` and base
`94de4099af88dabcd20065a06194f1550ae43d9c`. Raw Git observation confirms
that only the `scripts` binding changes, from
`26a857dca06796c241fa155f36f513cc15a1bdd8` to
`0b3e423fb58643001b3332d543af8ccd73fa7cba`. The other five bindings
(including the normalized complete automation inventory) and all seven Terraform
paths are identical. That delivery admitted these two complete source profiles for its necessary
main/candidate adoption transition; separately reviewed source/control extensions
are documented below. The candidate
profile starts on 2026-10-24; both expire at the unchanged
**2026-11-04 00:00 UTC** boundary. Any further script/control change, additional
Terraform path, wrong subject or expiry still fails closed.

The complete six-file diff was inspected for effects on the original proof:

- `scripts/standard-installation.py` is a new, explicit administrator-invoked
  public host-base composition. Existing trusted cloud entry points never call
  or import it. It supplies no Terraform variables, credentials, resource
  lifecycle or cloud identity operations.
- `scripts/validate-production-contract.py` extracts the existing exact
  single-root-owned-Quadlet-search-path predicate into a shared function; the
  original validator calls that function with the same values and rejects the
  same states. No cloud guard or metadata admission is changed.
- `scripts/preflight.sh` adds the Phase-1 source regression command. The remaining
  changes are its tests and installation documentation/README references.
- Every other existing script, all infrastructure/configuration/schema sources,
  the gateway Containerfile and automation source inventory retain their exact
  identities. In particular actual-input admission, exact-peer management,
  identity removal, TTL/cleanup and the single Quadlet health authority remain
  unchanged.

Thus the eight existing bounded IGNORED dispositions retain their original risk
rationales and expiry; this additional source qualification neither renews them
nor adds risk acceptance. The Phase-1 installation's own public-only, secret and
premature-authority rejection tests and the existing production-contract
regressions supplement the unchanged Terraform/trusted-control source proof.
They do not demonstrate a native host installation.

The maintained action's complete scan step was executed against that exact head
with pinned Trivy 0.74.0 on 2026-10-24 at 18:10:35 UTC, including vulnerability, secret and
misconfiguration scanning, both real database downloads, snapshot/source
observation, diagnostic admission, redaction and private raw-data cleanup.
The bounded v4 result is CLEAN with exactly eight MISCONFIGURATION findings,
all under the existing scoped dispositions; no new diagnostic was exposed.
Its database identity is
`sha256:8ee3fe66a68149742d0de57f700a2eb43faccd3ace4fbf03269d8b571c38a4a3`
(updated 2026-10-24 01:07:32 UTC; downloaded 18:10:32 UTC;
next update 2026-10-25 13:07:23 UTC). This is dated candidate evidence,
not a perpetual clean assertion. The unchanged scanner previously rejected
the same head with UNKNOWN_STALE / DIAGNOSTIC_ADMISSION_FAILURE.
Temporary raw scanner files and databases were cleaned by the unmodified action;
only its bounded, redacted result remains as workspace evidence.

A downstream consumer pinned to an older shared commit does not receive this
change automatically. After independent review and protected shared-main
acceptance, deployment must separately adopt the accepted immutable scanner and
v4 schema revision and obtain a fresh hosted result for its actual PR commit.
No deployment source or workflow is changed by this qualification.
The result remains `REPOSITORY_STATIC` / `REQUIRED_NOT_EXECUTED`:
neither native Host Enrollment readiness nor production or OCI-artifact approval.

### Maintained alternatives considered

Trivy supports real --tf-vars and Terraform plan inputs. They remain useful
when a real control run supplies them. They are not repository-time defaults:
the source action intentionally accepts no caller input, snapshots only the
exact commit and clears Terraform/scanner environment overrides.

A real plan would require actual run/image/input provenance and admission of
remaining unknown values. Trivy's pinned plan adapter consumes after values;
a plan format or absence of this parser warning alone does not prove complete
evaluation. Creating another renderer, mock plan or credentialed source-scan
authority would add no needed property to the constrained operation path.
This delivery therefore reuses existing OpenTofu/control guards.

### Eight preserved architecture observations

All are genuine configuration observations. None is relabelled NOT_AFFECTED
or removed. The central policy retains each rule/path/class/severity/fingerprint
and applies a separate, expiring IGNORED disposition only with the exact source
qualification. Exceptions cannot suppress a diagnostic failure, stale database,
secret or unrelated finding. There is no generic Terraform exception.

| Rule     | Disposition responsibility and residual risk                                                                                                                                                                     |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DS-0026  | Image HEALTHCHECK is absent; the non-production fixture uses the single effective Quadlet/systemd health authority. This does not qualify a standalone image or production edge.                                 |
| GCP-0031 | Actual public-IP exposure remains; temporary /32 SSH, run-specific key, credential separation, identity removal, TTL and cleanup bound its accepted test use.                                                    |
| GCP-0036 | OS Login is explicitly disabled in favor of the existing temporary management identity. Enabling it changes IAM/login/key authority.                                                                             |
| GCP-0033 | Boot attachment lacks customer-controlled key configuration; it references the separately managed qualification disk.                                                                                            |
| GCP-0034 | Preserve the distinct disk observation. Google-managed at-rest encryption is the accepted disposable-state baseline; no claim of CMEK/CSEK is made.                                                              |
| GCP-0029 | Packet-flow logging is absent. Existing run/resource/workload evidence is not packet-level audit. Collection, metadata privacy, retention/access and cost need a real logging requirement, not an invented sink. |
| GCP-0076 | Preserve the second logging observation and severity under the same logging decision. The residual observability gap is explicitly retained.                                                                     |
| GCP-0075 | PGA is disabled; the exact reviewed instance has external IPv4. This applicability disposition does not remove public exposure or grant Google-service access.                                                   |

The qualification is restricted to non-production, closed ephemeral test
construction without customer production-state inputs. It grants no new
execution authority. A new packet-audit, customer-key-custody, private-transport,
IAM-login or data-sensitivity requirement belongs to its actual owner;
changing the bound source invalidates these dispositions.

Primary platform contracts:
[provider-managed disk encryption](https://docs.cloud.google.com/compute/docs/disks/disk-encryption),
[OS Login identity effects](https://docs.cloud.google.com/compute/docs/oslogin/set-up-oslogin),
[Private Google Access applicability](https://docs.cloud.google.com/vpc/docs/private-google-access)
and [flow-log collection and billing](https://docs.cloud.google.com/vpc/docs/flow-logs).

### Candidate evidence and adoption

The pinned three-class replay of deployment commit
b61cdeb03867a0fb2ac796fbdfddb109d4a2b325 preserves all eight observations and
emits explicit static/run-bound coverage under the #1236 candidate policy.
Database identity is
sha256:814c9069394a8a57432a6e63046615db8681190671174d3949cf9188aceb232c;
updated 2026-10-20 00:59:02 UTC, downloaded 19:56:41 UTC, next update
2026-10-21 19:12:26 UTC. This is candidate qualification evidence, not accepted
deployment security or a successful cloud run.

Only after protected shared-main acceptance may deployment #124 adopt the
new immutable action/schema revision and obtain its own fresh hosted result.
Historical v3 UNKNOWN_STALE / DIAGNOSTIC_ADMISSION_FAILURE and the original
unclassified native SCANNER_FAILURE remain unchanged. No cloud qualification
or infrastructure operation is dispatched by this delivery.

### Rootless XDG source requalification (#1260)

Deployment PR [#362](https://github.com/SecPal/deployment/pull/362) has independently
reviewed head `5ad1e5ba0f8a203745b6b709d8c5123f359e51df` and accepted base
`f50333a57c49598584fddd7e3039953dade2e6fa`. Raw Git observation binds its scripts
tree to `4c6d4144cfc7849196e01e5c4204792f3355dfd2`. All five other source
bindings and all seven Terraform paths are identical to the accepted Phase-1
source. This is one named complete profile, starting 2026-10-25; the two existing
accepted profiles remain intact for the bounded adoption transition. Every
profile still expires **2026-11-04 00:00 UTC**. There is no caller-supplied hash
list, expiry extension or additional risk acceptance.

The complete three-file diff changes only the explicit host-base installer,
its regressions and its existing documentation:

- Podman requires a user-owned XDG directory. The installer now keeps its one
  administrative storage file under root-only ancestry and creates the native
  per-user link/data directories through its existing unprivileged transport.
  The home remains root-owned, service GID, mode 0750.
- Repair recognizes only the exactly verified failed public layout. It preserves
  the storage bytes at the protected location before removing that old public
  file and transferring three explicit directories. Root writes finish before
  the parent becomes user-writable; existing mask inodes are retained.
- Source comparison confirms that `trusted`, `directory`, `publish`,
  `public_file`, `runtime`, `admit_for_enrollment`, account/sub-ID/package,
  dormant-service, SELinux-label and secret/premature-authority checks are
  unchanged. Existing cloud entry points never call or import this installer.
- No provider/Terraform input, metadata, actual-peer/run admission, identity
  transition, lifetime/cleanup, resource multiplicity or Quadlet health authority
  changes. Configuration, schemas, infrastructure, gateway and automation
  identities are unchanged.

Thus the eight existing dispositions retain their original rationales and
expiry. This qualification changes neither native scanner scope nor the
run-bound obligations: `REPOSITORY_STATIC` / `REQUIRED_NOT_EXECUTED` remain
explicit. The 25 deployment regressions and independent code/security review
support the bounded source change; they are not native host acceptance.

On 2026-10-25 at 10:44:36 UTC the unchanged action's complete scan step evaluated
that exact head with pinned Trivy 0.74.0, fresh vulnerability and Java databases,
all three vulnerability/secret/misconfiguration scanners, diagnostic admission,
source snapshots and redaction. It returned CLEAN: eight existing scoped
MISCONFIGURATION dispositions, zero actionable/review-required findings and no
new diagnostic. The database identity was
`sha256:3155935f49d24e05cb296628f8537e2bdbe4438d5668793826bbe91bcd4600ab`
(updated 2026-10-25 00:59:20 UTC; downloaded 10:44:33 UTC;
next update 2026-10-26 07:10:41 UTC).
The unmodified cleanup removed raw scanner/tool files and both database caches;
only bounded redacted evidence remains in the owning workspace. This dated scan
does not confer lasting CLEAN status.

The failing-first candidate test, complete scanner regressions, all-six-binding
negative cases, wrong-subject/time/extra-Terraform-path negatives, and real Git
mutations of the installer, configuration, Terraform and workflow all exercise
fail-closed admission. The exact candidate is re-admitted after restoring its
bytes; expiry at and after the original boundary is rejected.

After independent review and protected central acceptance, deployment must adopt
the accepted full scanner SHA and obtain fresh hosted security/contract checks.
This static proof grants neither native CX33 execution authority nor
`READY_FOR_ENROLLMENT` or production admission. Those remain under their existing
independent owners and operator-approved procedures.

### Architecture-dispatch source requalification (#1264)

Deployment [PR #363](https://github.com/SecPal/deployment/pull/363), independently
reviewed head `40de3c43774fef79652de780f636e087ec4c7391`, adds bounded Phase-1
diagnostics and versioned architecture evidence to accepted base
`27f8e01c138f97530d3dc7a2750934605f0702da`. The exact new complete profile binds:

- `scripts`: `ce6c93f9854ca2938509298f3120981ed992b069`;
- `.secpal`: `c9144f481e6148c42ecd8f8c73552bdbb137d66a`;

All five existing other source/control identities and seven Terraform paths
are unchanged. The observer reads the new control tree directly from raw Git
when present and rejects a file or symlink masquerading as it. The candidate
cannot omit or alter that tree. Existing accepted sources without it remain
valid only through the same bounded transition. This named seven-binding
profile is not an independent hash list; every profile retains the original
**2026-11-04 00:00 UTC** expiry.

The full deployment diff changes only its installer, regressions, current
documentation and the declaration/license. Comparison of actual AST bodies,
ignoring diagnostic decorators, confirms 18 existing policy/verification
functions are unchanged, including protected ancestry/publication, runtime,
account/sub-IDs/packages, SELinux, dormant authority, platform and readiness.
Every existing Native run/change invocation has identical arguments. Public
renderer equivalence, exact legacy repair and rootless safety tests still pass.

The changes locate failures and do not add host commands, relax admission or
alter provider/Terraform behavior. Runtime-user lookup now fails at its actual
command boundary. An independently found parser-depth escape was reproduced
through the real normalizer with a 200,001-byte JSON observation, then bounded
by handling RecursionError. All 34 installer regressions pass. The real
79-operation dispatch passes the unchanged canonical validator; its broader
production-owner/agreement enforcement was explicitly included in independent
review. Generic expression agreement execution remains truthfully empty.

Therefore the eight existing dispositions retain their original rationales
and expiry; there is no new risk acceptance, warning exemption, fabricated
Terraform input or changed scanner policy. REPOSITORY_STATIC and
REQUIRED_NOT_EXECUTED remain explicit and mandatory.

On 2026-10-25 at 13:40:17 UTC, the unchanged action's full scan step evaluated
that exact deployment head with pinned Trivy 0.74.0, fresh vulnerability/Java
databases, all three scanners, diagnostics, snapshots and redaction. Result:
**CLEAN**, eight existing dispositions, zero actionable/review-required findings,
no new diagnostic. Database identity:

`sha256:e78c2db6c9cf036770b5dea9c5997963948537cd8da60c90c32ee3489b0f29fb`

Database update: 2026-10-25 00:59:20 UTC; download: 13:40:14 UTC;
next update: 2026-10-26 12:57:48 UTC. Unmodified cleanup removes raw scanner,
tool and database files; only bounded redacted evidence is retained privately.
This is a dated local full-action execution, not a hosted CI or native receipt.

Failing-first tests reproduce rejection of the new profile and missing control
observation before implementation. Scanner regressions cover all seven changed
or missing bindings, wrong subjects/time/extra Terraform paths, and raw-Git
control-tree type checks. Separate real Git mutations of scripts, declaration,
configuration, Terraform and workflow, plus removal of dispatch controls, are
all rejected. The unchanged exact candidate re-admits; expiry at and after the
original boundary fails closed.

After independent protected central acceptance, deployment must adopt only
that immutable scanner revision and obtain fresh hosted CLEAN security,
contract and required checks plus exact-head integration review. This source
proof cannot grant native host, OCI, READY_FOR_ENROLLMENT or production admission.

### Native host-qualification source requalification (#1266)

Deployment [PR #365](https://github.com/SecPal/deployment/pull/365) has independently
reviewed code/architecture and security PASS at exact head
`042ab9b5060763b78f36369ae549829eb14aed21`, based on accepted main
`56e96e66edba1ad0b0de1682a5f231a7171ee8ae`. Raw Git observation binds the
new complete seven-binding profile to:

- `scripts`: `c17a475b7185349018086ca8683dcf751a339a5a`;
- `.secpal`: `18745a3e7a93c9990e023b8ed5da4031025c631c`.

The gateway Containerfile, configuration, infrastructure, schemas and normalized
complete automation inventory retain their five existing identities; all seven
Terraform paths are unchanged. This is one reviewed complete tuple, not a list
of independently interchangeable hashes. The existing accepted profiles remain
available for bounded adoption. The original **2026-11-04 00:00 UTC** expiry
is unchanged; missing or changed controls, unknown scripts, wrong subjects,
earlier qualification or expiry still fail closed.

The source diff was inspected for effects on the existing Terraform/trusted
control proof:

- The new explicit operator composition stages only the existing canonical
  nonsecret Alpine fixture rootlessly, runs the unchanged #80 harness and
  independently reuses its RPM, SELinux and Quadlet owners. It does not create
  provider resources, supply Terraform values, enroll a host, activate a
  deployment or select/start product images.
- `rocky-control.py` extracts the existing native qualification fact checks into
  a shared function with the identical body. Its GCP entry point retains its
  original schema and exact target/control/run checks. The separate operator
  API scopes existing v4 invariants to independently authenticated bindings;
  it is not a new GCP CLI acceptance option or readiness authority.
- The GCP runner and preparer, historical target, schema file, fixture/RPM/
  SELinux/Quadlet owners, existing public installer and harness bytes are
  unchanged. The new preflight command and declaration supply executable
  coverage for the limited native composition, not authority for other tools.
- The four initial review findings were corrected before qualification:
  protected observation ancestry, generated-authority admission before start
  followed by live process observation, the existing complete explicit-message
  classifier and TERM-first bounded cleanup. Thirteen relevant regressions and
  all 34 existing installer tests pass. The unchanged Rocky architecture owner
  passes; real canonical dispatch covers 151 operations. Independent review
  includes the broader repository-specific ownership/agreement route.

No actual-input, exact-peer, cloud-identity-removal, TTL/cleanup or Terraform
admission boundary changes. The eight existing dispositions retain their
rationales and original expiry without new acceptance. Scanner coverage,
diagnostic/database/scanner admission and protected/redacted evidence are
unchanged. `REPOSITORY_STATIC` / `REQUIRED_NOT_EXECUTED` remain explicit.

This source qualification grants no native host, OCI, enrollment or production
admission. After protected central merge the consumer must adopt the full
accepted shared SHA and obtain fresh CLEAN security/contract/required CI plus
exact-head independent integration review before native execution.

On 2026-10-25 at 16:53:05 UTC, the unchanged maintained action scan step ran
against this exact deployment commit with pinned Trivy 0.74.0, fresh real
vulnerability/Java databases, all three scanner classes, exact snapshots,
diagnostic admission and redaction. Actual result: **CLEAN**, eight existing
dispositions, zero actionable/review-required findings. Database identity:

`sha256:215de45e1dceca5b290d28017ac6546e59c8de900bb4fac14654e08c91e2ea21`

Database update: 2026-10-25 00:59:20 UTC; download: 16:53:02 UTC; next update:
2026-10-26 12:57:48 UTC. This is dated local full-scan evidence, not hosted CI
or native admission. Unchanged action cleanup removed raw tools/databases and
native scan output; only bounded redacted evidence remains. Real modified-source
probes of scripts, declaration, configuration, Terraform and workflow all failed
closed; the restored exact candidate re-admitted.

### Certbot security-closure source requalification (#1284)

Deployment [PR #376](https://github.com/SecPal/deployment/pull/376), tracked by
[#375](https://github.com/SecPal/deployment/issues/375), refreshes the exact
Certbot closure after ordinary Rocky 10.2 security updates. This additional
source tuple is a candidate until independent native GitHub review and protected
central acceptance. Its seven bindings inherit the accepted native Phase-1
profile, replacing only:

- `config`: `68bd29a7c4c159e9ae1f1c9f0b05fda8b95eb012`;
- `schemas`: `1f594b1bb40c9fa415204aa11fce78c3962e1bad`.

Raw Git comparison with protected deployment/main
`b4b0500b74ee879d548b9add95797235d19065a7` establishes that the source changes
only the Certbot package policy, its exact policy-ID schema constraint and
provenance/TLS documentation. The strong closure stays at 106 packages per
architecture, including precisely nine EPEL packages. Eight ordinary Rocky
identities advance; Certbot, EPEL keys and package authority do not change.
The qualifier, native and GCP control code, all seven Terraform paths, complete
normalized automation inventory, gateway Containerfile and dispatch declaration
remain byte-identical to the accepted native Phase-1 qualification. Thus the
actual-input, exact-peer, guest-identity-removal and bounded-lifetime/cleanup
controls retain their reviewed meanings. The package-policy schema amendment
neither supplies Terraform values nor grants provider execution authority.

On 2026-10-28, independently authenticated existing CX23 and CAX21 hosts ran real
native x86_64 and aarch64 transactions and unprivileged client/runtime probes at
signed candidate `017082a85d7fee5a7577927fc7e002ee6a036652`. All 106 exact
installed headers and protected payloads match their authenticated RPM inputs.
Each transaction added 16 packages, without removal, upgrade or downgrade;
required scriptlets and signatures ran with transaction-local signing authority.
EPEL remains disabled and absent from the global keyring. Python 3.12.15 imports
and the Certbot 4.2.0 standalone plugin pass natively on both architectures.
The packaged renewal timer remains disabled/inactive with no service execution
or ACME state. These are package/client results, not full #80 host admission,
certificate-lifecycle activation, production enrollment or permission to execute
a cloud run. Final source and protected-main observations remain consumer duties.

The existing eight dispositions, their residual risks and original
**2026-11-04 00:00 UTC** expiry remain unchanged. The new tuple is admitted only
from 2026-10-28. Missing/changed bindings, half-refreshed tuples, changed Terraform
inventory, wrong subject/repository, earlier qualification and expiry fail closed.
Previous accepted tuples remain available for bounded adoption. Scanner identity,
coverage, diagnostic and database admission, redaction and policy severity do
not change. `REPOSITORY_STATIC` and `REQUIRED_NOT_EXECUTED` remain explicit;
a source-static result cannot execute or replace the four run-bound controls.

### Google 8.8.1 provider source requalification (#1286)

Deployment [#380](https://github.com/SecPal/deployment/issues/380) completes
[PR #373](https://github.com/SecPal/deployment/pull/373) for the retained GCP cleanup
module, then [PR #371](https://github.com/SecPal/deployment/pull/371) for Rocky.
The two complete source tuples remain candidates until independent review and
protected central acceptance. Their original expiry remains
`2026-11-04T00:00:00Z`; previous accepted tuples and all eight dispositions stay
unchanged.

The corrected cleanup source `bd4789f49eed97bbaa25f8a817797cb125d5f70d` inherits
the Certbot-refresh tuple and changes only the `infra/ci-cloud` binding to
`5b7aa70eceb3b9dbc2903b95507b4e9a935ce5b1`. Relative to protected deployment/main
`1ab5c535b4bad5e57af370f20e9e9254aca7c53b`, only the Google version and lockfile
change. The manifest, lock version and lock constraint all select `8.8.1`.
The cleanup-only module does not regain resources or dispatch authority.

The combined Rocky source `c3bd77d12ac76a11cf3005067e911f630b7c6fef` includes
that cleanup correction and changes three bindings:

- `infra/ci-cloud`: `b2980196040355b883a77b5f1011dc4b890af3d0`;
- `scripts`: `036dd0f359dacef017b32f32971cf106bf57e93f`;
- `schemas`: `de6c64e49a24a017a12ed204285dbbc11c9d8d25`.

The complete executable diff is the Rocky manifest/lock update, the transport
version/schema agreement and the authenticated lock/executable identities.
Documentation records the current version. Source review confirms no change to
resources, inputs, metadata, IAM, network rules, exact-peer access, guest identity
removal, TTL, cleanup, observer operations, timeouts or retries. All seven
Terraform paths and the remaining source/control bindings stay unchanged.

Real OpenTofu `1.12.5` readonly initialization verifies the developer-signed Google
`8.8.1` package, key `0C0AF313E5FD9F80`, against the committed lock. Its Linux
amd64 executable SHA-256 is
`bb5ffc0706182cd99e712e09e6cc0d98540a9a2f935fc4e0a4999940ac09c32b`; the exact
Rocky lock SHA-256 is
`48f406706464cc1bd596bc79229069ce8365fd4399de9ea189118abc340c2300`.
The required real producer regression passes in a loopback-only namespace:
executable/process identity, owned socket correlation, inet_diag observations,
unrelated connection exclusion and package-substitution rejection. This is local
producer/package evidence, not a GCP API or cloud-conformance result.

Fresh archive-pinned Trivy `0.74.0` scans use the unchanged three scanner classes
and freshly admitted databases against clean, exact-commit snapshots of the
baseline and both candidates. All eight normalized findings are identical.
Before this qualification both candidates reject with
`UNKNOWN_STALE / DIAGNOSTIC_ADMISSION_FAILURE`; candidate admission produces
`CLEAN` only through the existing eight reviewed dispositions. No finding,
warning, policy severity, database check or secret-redaction rule is removed.
Positive and negative regressions bind each complete tuple, reject partial or
hybrid tuples and preserve subject/date/expiry checks.

`REPOSITORY_STATIC` and `REQUIRED_NOT_EXECUTED` remain explicit. Actual-input and
metadata admission, exact-peer access, identity removal and exact-run lifetime
and cleanup still require the existing trusted operation. No GCP resource,
production endpoint or host service is changed by this qualification. Consumers
may adopt the new immutable scanner revision only after protected acceptance.
