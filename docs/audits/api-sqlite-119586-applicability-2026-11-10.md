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
boundary. Trivy 0.74.0 reports no HIGH/CRITICAL on the FPM subjects. Trivy's absence
alone is not the nonapplicability proof. Grype's original observation, exact
PURL and severity remain visible; only the unchanged central policy may apply
a reviewed disposition. The upstream data issue can remain open independently.

## Exact artifact and runtime evidence

[Current native run 42722113210](https://github.com/SecPal/api/actions/runs/42722113210)
is producing the final artifacts for API head
`cc1fee5d64c393f453bd3706d197569751193a46`. Their exact checkout, subjects,
SPDX associations and binary identities must be authenticated before adding the
corresponding OpenVEX documents. No current-subject document or discovery
manifest is present in this initial draft. No earlier OCI digest or later
rebuild inherits a disposition.

The existing binary investigation linked above records library SHA-256
`b9ed2596aa9aacb17048b7e93e46061e33fd578d4d239badbe23dd3a1fd5e113`
for AMD64 and
`a5f56962738b632566388c8ba4ce131e8e1be84be1d6dd673ce077071362aee6`
for ARM64, native ELF machines 62/183 and no recovery entrypoints. These are
baseline technical controls, not a claim that new OCI subjects were already
verified. Current artifact bytes must establish their actual runtime identity.

The source ID is
`2026-10-09 15:46:58 be8d059e9a49089ab2dce5ed26dd87aaf598fdc5fbe0b107c0dd758464bcd5e3`.
The final filesystem, package ownership, architecture-specific ELF and runtime
provenance must agree. Recovery/shell entrypoints must be absent from the actual
library while ordinary SQLite entrypoints and PHP SQLite/PDO remain functional.

## Review and scope

The operator authorized truthful, independently confirmed nonapplicability via
the existing Reviewed-VEX procedure; no new review authority or upstream waiting
condition is introduced. Independent technical confirmation is recorded through
the existing GitHub review process. The author cannot self-approve this finding.

The technical conclusion and its artifact bindings are submitted through the
existing GitHub code/security review. A generic receipt without assessment of
these applicability facts is not a separately claimed technical opinion.
Activation requires a genuine independent review record, retained by the
existing reviewed manifest; this draft has no such operative manifest.

Validity is bounded to 2026-11-23T00:00:00Z and the two exact FPM subjects only.
The trust manifests must name the actual protected commit containing their
OpenVEX documents, the independent review record and exact OCI/platform pairs.
No statement covers CLI-positive controls, other vulnerabilities, other images,
future rebuilds, released FrankenPHP artifacts or an exception for real risk.
Raw observations and the unchanged Policy 1.0.0 remain authoritative.
