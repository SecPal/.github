<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# API SQLite CLI applicability: CVE-2026-119586

This assessment supports the existing Policy 1.0.0 Reviewed-OpenVEX path for
API #2643. It is not risk acceptance, registry publication, deployment authority,
or a generic SQLite exemption. The proposed finding is `not_affected` with
`vulnerable_code_not_present`, subject to independent review of this evidence.
Only the exact FPM subjects in the accompanying documents are covered.

## Vulnerable code and build boundary

The [CNA record](https://github.com/CVEProject/cvelistV5/blob/main/cves/2026/119xxx/CVE-2026-119586.json)
(last updated 2026-10-30T16:19:09.235Z, rechecked 2026-11-09) describes a
command injection in the SQLite command-line shell. Attacker-controlled schema
text survives recovery as text, including dot-commands; execution requires
replaying that output through a shell that dispatches `.shell` or `.system`.
Ordinary SQLite SQL parsing is not that dot-command dispatcher.

In the [3.54.0 source](https://github.com/sqlite/sqlite/tree/6932c59ee5c280599dfae9e7b431698a7cab9687),
`recoverWriteSchema1` in `ext/recover/sqlite3recover.c` passes schema SQL to
`recoverSqlCallback`; the shell's `recoverSqlCb` prints it. `recoverDatabaseCmd`
connects this callback through `sqlite3_recover_init_sql`. The command dispatcher
in `src/shell.c.in` implements the OS-command execution. These recovery and shell
implementations are separate from the core library amalgamation.

The actual API [APKBUILD](https://github.com/SecPal/api/blob/cc1fee5d64c393f453bd3706d197569751193a46/docker/sqlite/APKBUILD)
uses upstream `sqlite-autoconf-3540000.tar.gz`, SHA-512
`b54e6329627990ad567d948c9a29abbc8178c4dfd6c1aa3923684827aa0830df2cef06b94ddfd0496293b0c503d981ef0b62fd2044abbee887012107d405c366`.
The authenticated archive's `Makefile.in` links `libsqlite3` only from `sqlite3.o`
(lines 138-150), itself compiled only from `sqlite3.c`. The shell is a separate
build target. `sqlite3.c` has SHA-256
`2da161e310ef0aba3465f22a4d12b8a43723236f0942fa76e8aac523c3317243`
and upstream SHA3-256
`8efd453d08a7cfc4c79de5923153036cdc4dcaa254d4f1e617be6a2a98828f9e`.
It contains none of `sqlite3_recover_init_sql`, `recoverDatabaseCmd` or
`recoverSqlCb`. The archive's Makefile SHA-256 is
`788d17f8e234719d4257e112d025afdddd4382d483d29a7c953858e9716bf1f6`.

`libs()` packages only the genuine versioned shared library, SONAME symlink and
license into `sqlite-libs 3.54.0-r0`. The separate CLI package is built as an SDK
control but never installed in the final FPM image. Signed APK installation,
two byte-identical package builds, unchanged public ABI and actual PHP/PDO
runtime use are checked by the existing build and native smoke, not inferred
from a missing filename. No renamed package, stripped CPE, SBOM edit or
alternative scanner input is used.

## Existing controls and scanner disagreement

The retained [initial investigation](https://github.com/SecPal/api/pull/2643#issuecomment-6663254366),
[platform binary evidence](https://github.com/SecPal/.github/issues/636#issuecomment-6739668421)
and [upstream reproduction](https://github.com/anchore/grype/issues/3884)
contain the real library-only and CLI-positive controls. A stock Alpine
3.53.4 CLI image contains the actual executable and reports its version and
FTS5/session options. With the same scanner database, the CLI finding remains
detected; genuine FTS5/session library CVEs also remain detected on 3.53.4.
The authentic 3.54.0 library fixes those three library findings while retaining
the disputed CLI observation. These controls are not covered by this VEX.

Grype 0.121.3 uses `apk-matcher` / `cpe-match`: truthful upstream origin `sqlite`
is expanded to generic `nvd:cpe` SQLite through 3.54.1, losing the CLI component
boundary. Fresh current-head Trivy 0.74.0 reports no HIGH/CRITICAL on any target image. Trivy's absence
alone is not the nonapplicability proof. Grype's original observation, exact
PURL and severity remain visible; only the unchanged central policy may apply
a reviewed disposition. The upstream data issue can remain open independently.

## Exact artifact and runtime evidence

[Native run 42722113210](https://github.com/SecPal/api/actions/runs/42722113210),
producing attempt 1, completed both native runtime integrations. The actual
checkout is `80a186e2540bd8ff16579b7de45b796f98bb9d0a`; its tree
`0e4fb360b6fe5d7fc3e36d5a2e5a7e92393d16fc` equals the GitHub-verified signed API
head `cc1fee5d64c393f453bd3706d197569751193a46`.

GitHub artifact [13721422889](https://github.com/SecPal/api/actions/runs/42722113210/artifacts/13721422889)
(AMD64) ZIP SHA-256 is
`9cfe6034ca93b3919871c62e5e4fc420b6b401ebd8bf76eee6ed58daaf3a968e`;
[13720223792](https://github.com/SecPal/api/actions/runs/42722113210/artifacts/13720223792)
(ARM64) is
`036c89a514a47849997b7f4a72aeafac5860f416b6f4bdc9d9569438014a531a`.
All four manifests/configurations and all 70 layer descriptors were rehashed
from these exact ZIP bytes. SPDX digests, associations, native architectures,
source labels and both exact smoke companions agree.

| Component | Platform    | Manifest digest                                                           | Authoritative SPDX digest                                                 |
| --------- | ----------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| php-fpm   | linux/amd64 | `sha256:54e7afe9859d93b38e884161fe7685fc866b63505ad1cd7a95ebd5df12884a7c` | `sha256:bb9ddc0ab4fe632d2c94568ac336d9914b7d40933c473894fc65c7df4d85ed6c` |
| nginx     | linux/amd64 | `sha256:1d81a6f01dcbe1c9a95ac5f2e2250b5ebeb7658a0adacdabffb1ee7746f08348` | `sha256:5e7e4f9096041b26dab711ce1fcc3e1bfdc7022bd1e6db8a70075d0093f47953` |
| php-fpm   | linux/arm64 | `sha256:504d6810911ab263a835243ea643f0bc5e65d08f1ad9e1d82cf86a6b86f61d95` | `sha256:c4075ab7ddcb2ecb9367af774c19022bb1a53ee0d422ed3cbc4771f1e1ac1d8b` |
| nginx     | linux/arm64 | `sha256:db073d1112a3cb5cf1988a40ddb688914ae0e1b369a02a2f727d5408a48df1f1` | `sha256:f6d2b9740526bbeb9560fc332ebb55f555ad6e9f8436c2529c3bc56799d952d4` |

Both FPM libraries are byte-identical to the previously inspected architecture
controls: AMD64 SHA-256
`b9ed2596aa9aacb17048b7e93e46061e33fd578d4d239badbe23dd3a1fd5e113`,
ARM64 SHA-256
`a5f56962738b632566388c8ba4ce131e8e1be84be1d6dd673ce077071362aee6`.
Actual ELF machines are 62/183. Both expose `sqlite3_open` and exclude
`sqlite3_recover_*` exports. This agrees with the authenticated link rule and
amalgamation boundary, which also excludes static recovery/shell code; exported
symbol absence alone is not the proof. Both final file inventories lack the
CLI. Installed APK records, versioned library bytes and runtime provenance
agree on `sqlite-libs 3.54.0-r0`, truthful origin `sqlite` and recipe SHA-256
`ff107b16a389a8b978f1bd123ce4c7cb5f665f9a5b151940510a6db4b38fa5ed`.
Both FPM inventories contain 55 APKs and zero Go packages; Nginx contains 19
APKs and zero Go packages. These are unpublished CI subjects, not registry
release artifacts. No earlier digest or later rebuild inherits their statement.

The source ID is
`2026-10-09 15:46:58 be8d059e9a49089ab2dce5ed26dd87aaf598fdc5fbe0b107c0dd758464bcd5e3`.
The existing native PHP/PDO, Python FTS5/session and library ABI checks passed
against these exact subjects on both native runners.

The original four-image scan [artifact 13720763672](https://github.com/SecPal/api/actions/runs/42722113210/artifacts/13720763672)
has ZIP SHA-256
`225c5adbb2b2930ff82dce7275772b6eaf3dbbaefa09fe50bd40769e5a978b43`.
All four evidence results are HEALTHY. Nginx is CLEAN on both platforms; FPM
is REVIEW_REQUIRED solely for CVE-2026-119586 on the exact PURLs in the proposed
documents. Trivy has no HIGH/CRITICAL in any target. The original raw results
and policy decisions are unchanged. The pre-VEX qualification correctly fails;
no CLEAN result or release admission is asserted by these documents alone.

## Review and scope

The operator authorized truthful, independently confirmed nonapplicability via
the existing Reviewed-VEX procedure. The author does not self-approve the
technical finding. Document preparation originally recorded that independent
confirmation was pending; the immutable document impact statements retain that
historical creation-time fact.

The subsequent [actual independent technical decision](https://github.com/SecPal/.github/pull/1323#issuecomment-6754950018)
by `chatgpt-codex-connector[bot]`, recorded 2026-11-10T00:07:58Z, supports
`not_affected` / `vulnerable_code_not_present` for exactly the two FPM subjects.
It explicitly assesses the recovery producer, shell callback/command and
OS-command dispatcher, authenticated library link/package boundary, actual
ELF/source-ID identities, OCI/SPDX/runtime association and genuine controls.
It identifies no technical counterexample or missing technical proof in that
chain. This is the substantive decision, not the earlier generic review receipt
or the author's request for an assessment.

The reviewer transparently records that its environment had no authenticated
GitHub session for a second download of the Actions ZIPs. Its exact-subject
assessment uses the signed audit's original authenticated artifact rehashes and
identity associations, plus the original public source/control evidence. It
does not claim to have repeated those byte measurements. The primary exact ZIP,
OCI, SPDX and loaded-library measurements above remain unchanged and retained;
no extra external reviewer or new authority is introduced.

The two documents were independently assessed and protected-merged in
[PR #1323](https://github.com/SecPal/.github/pull/1323), actual verified commit
`3884f032ec511fd5c5a5d72dab8d94aa77f451cb`. The existing `reviewed-vex`
manifests name that real ancestor document commit, canonical document digests,
actual decision URL/author, exact OCI/platform pair and bounded validity.
Normal independent PR review and protected acceptance govern manifest adoption;
the existing trusted adapter must verify the accepted checkout before use.

A local policy replay of the original exact-subject raw evaluations with the
proposed manifests returns HEALTHY/CLEAN for all four subjects. Only the two
FPM CVE-2026-119586 dispositions change to VEX_ACCEPTED; their raw observations
and every unrelated finding remain identical. Supplying only the opposite
platform's manifest leaves FPM REVIEW_REQUIRED. This is a current policy replay
of retained evidence, not a fresh scanner run or protected publication admission.
The actual hosted qualification must run again after protected manifest adoption.

Validity is bounded to 2026-11-23T00:00:00Z and the two exact FPM subjects only.
No statement covers CLI-positive controls, other vulnerabilities, other images,
future rebuilds, released FrankenPHP artifacts or an exception for real risk.
Raw observations and the unchanged Policy 1.0.0 remain authoritative. No registry
publication, deployment, host mutation or release admission is granted here.

## First manual publisher candidate: exact new subjects

The accepted API main commit is `da806926a754d7446cdfa9f6f19ed331e5dbee31`
(GitHub signature verified). Its tree is the same previously accepted
`0e4fb360b6fe5d7fc3e36d5a2e5a7e92393d16fc`. Post-merge
[PHP CI](https://github.com/SecPal/api/actions/runs/42729226562) and
[Quality](https://github.com/SecPal/api/actions/runs/42729226370) succeeded.
The authorized existing manual [publisher run 42757690047](https://github.com/SecPal/api/actions/runs/42757690047),
producing attempt **2**, rebuilt and successfully integrated both architectures.
Attempt 1 was cancelled during a runner package-index download, before any
registry preparation or prepared artifact; its native digests are not adopted.

The authenticated native GitHub archives are
[AMD64 artifact 13737349570](https://github.com/SecPal/api/actions/runs/42757690047/artifacts/13737349570),
ZIP SHA-256 `2650f3df5e8549a65ac447dcb0f75ac5baeb5be8b9a534877bb023cc454fc9d8`,
and [ARM64 artifact 13738555175](https://github.com/SecPal/api/actions/runs/42757690047/artifacts/13738555175),
ZIP SHA-256 `a58d25ec7357048333b336b3b5316eafd27c1a39dd638d9e76fc1ddea8597250`.
Actual downloaded ZIP bytes agree with the GitHub artifact digests and sizes.
All four manifests, configs and 70 layer descriptors were rehashed; accepted
source, Containerfile/context hashes, source epoch, component/platform/non-root
configuration, SPDX associations and exact native smoke companions agree.

| Component | Platform    | Manifest digest                                                           | Authoritative SPDX digest                                                 |
| --------- | ----------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| php-fpm   | linux/amd64 | `sha256:c175e73eeb9b45af5a5c7aac5ce13d90979d79bf264bffbdf05518679e081f2d` | `sha256:cbff5b6ed3519a4449b3be0746f27cdc0290cb49cd793637de8e48a367ba7bd7` |
| nginx     | linux/amd64 | `sha256:86ffda2552cbbe51cbc391fba1a44e73b8ad74f08fdced156cd9fc23346c81d1` | `sha256:69e9ddefdfb42ff07ceaad8f4ecf2446c933afce547c47d7bb3edc67f95870ba` |
| php-fpm   | linux/arm64 | `sha256:70790c63d4ff0fe32fd9b617ef20587d26bb2281ab8c5b17cb51151e44a2cf43` | `sha256:f2053e7278821d7468f0ae47714efd85b0a04d982f34bf663bd7ca114effe62d` |
| nginx     | linux/arm64 | `sha256:5a3fc7bd00c1bdcda861423a7fd370087c5c3c2e5ab33608f98e64d3e7c59531` | `sha256:f820f04fcda5f69ecaad53c8f45df03c8e938f0436a8b122f5faf1146565cb19` |

Both current final layered filesystems contain the genuine `sqlite-libs
3.54.0-r0` package with unchanged origin `sqlite`. Their actual library hashes,
ELF machines and source ID exactly equal the accepted architecture-specific
measurements above. The package identity and upstream PURLs remain truthful.
No SQLite executable is present; the Python `sqlite3` package directory is not a
CLI. The current dynamic symbols expose `sqlite3_open` and lack recovery exports.
These observations bind the new subjects to the accepted amalgamation/link rule
and genuine controls; absence of an executable or export alone is not the proof.
The same APKBUILD is part of the accepted source tree. FPM contains 55 APKs and
zero Go packages; Nginx contains 19 APKs and zero Go packages.

The new OpenVEX documents propose **only** these two current FPM subjects,
using the existing independent technical component decision. At document
creation the new exact-subject binding has not yet received its independent
confirmation. The old decision does not approve different digests. Normal
protected adoption must record the actual new decision and document commit in
the existing trusted manifest format. Expiration remains
`2026-11-23T00:00:00Z`; no extension or blanket applicability is proposed.
Fresh registry scans, OCI/SBOM attestations, native registry-pull integrations
and complete pair admission remain mandatory in the same publisher. These
measurements alone assert neither accepted publication nor deployment authority.
