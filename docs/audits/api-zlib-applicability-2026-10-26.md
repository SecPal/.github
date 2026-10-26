<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Exact-subject API zlib applicability review

Status: independent applicability decision PENDING for each CVE. This document
records evidence submitted under [#1268](https://github.com/SecPal/.github/issues/1268);
it is not reviewed OpenVEX, risk acceptance, or API release admission.
The evidence author cannot approve their own applicability assertion.

## Existing authority and review scope

[Policy 1.0.0](../vulnerability-triage-policy.md) owns VEX semantics.
The [trusted adapter](../released-artifact-vulnerability-reevaluation.md) proves
reviewed checkout provenance. Completed #699/#700 are contracts, not active
reviewers; #636 is coordination. Use the existing independent GitHub security
review process and retain an explicit decision for each CVE. A generic
no-code-findings receipt does not establish either applicability decision.

Only after a positive authorized decision may the existing reviewed-OpenVEX
path be used, with real reviewer/review provenance, bounded validity, exact
subjects and components, independent review, and protected merge. Do not infer
a validity period from an unrelated scanner exception or extend an old one.

## Immutable subjects and retained evidence

Source: `SecPal/api@66a22aa331c37a948c218533b532cf54b1571270`.
Actual [publisher 40241417030](https://github.com/SecPal/api/actions/runs/40241417030),
attempt 1. Registry bytes and five index/platform/SPDX attestations were verified
against this source/workflow/attempt in the retained investigation.

| Identity                                     | SHA-256 digest                                                     |
| -------------------------------------------- | ------------------------------------------------------------------ |
| Index                                        | `d4d04a0b063f5ef772bec3e84b919f131c7a93f79f2bcf2aedb293980e874cb8` |
| linux/amd64 manifest                         | `b365d9afa384cdb08f93a06cecc3029314af076728a5d97d2fe63d69023c4014` |
| linux/arm64 manifest                         | `9ad840d7a2e2d919b91d250a71246707563035158213b6c8cec23492a2ddabb7` |
| AMD64 authoritative SPDX                     | `05eef6f6c4342fd66bf93f2d18c030c2605149a8ddc10b49f462f35179d876d2` |
| ARM64 authoritative SPDX                     | `4e376a520d23250413f8e8005c095ba600751905bb93bc12560ec5c081b3828b` |
| Publisher security evidence, canonical JSON  | `3a6f673614b24531828227b15a16c26e9ddae26d0f0a8659ef03e68ea520d988` |
| Original scan/SBOM ZIP, artifact 12617236017 | `e93a42390b014907d19895d4b25a69bbc3e35de400593f6faf78799b014c2adb` |

The [API report](https://github.com/SecPal/api/issues/1609#issuecomment-6405149191)
and [complete evidence request](https://github.com/SecPal/.github/issues/636#issuecomment-6405054339)
bind the original findings and raw observations. HEALTHY is not CLEAN: each
platform still has 12 ACTIONABLE and 218 REVIEW_REQUIRED. Final publisher
acceptance failed. The diagnostic artifact named api-accepted is not admission.

## Debian source, package and actual ELF binding

Component on both subjects: Debian Bookworm zlib1g `1:1.2.13.dfsg-1`.
Actual files: `usr/lib/x86_64-linux-gnu/libz.so.1.2.13` and
`usr/lib/aarch64-linux-gnu/libz.so.1.2.13`.

| Identity              | AMD64                                                              | ARM64                                                              |
| --------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| Official .deb SHA-256 | `d7dd1d1411fedf27f5e27650a6eff20ef294077b568f4c8c5e51466dc7c08ce4` | `52b8b8a145bbe1956bba82034f77022cbef0c3d0885c9e32d9817a7932fe1913` |
| Actual ELF SHA-256    | `7e2a72b4c4b38c61e6962de6e3f4a5e9ae692e732c68deead10a7ce2135a7f68` | `ffb1ab496e6eced03ab679075f9f2c415c7728a145cc7f63d614497102d73822` |
| GNU build ID          | `1f95d5498d283b79505861523e20b3db2afdf518`                         | `567e568e51b0e021ed3b5c1592ef569f4a3ef272`                         |
| ELF machine           | EM_X86_64                                                          | EM_AARCH64                                                         |

OCI extraction checked compressed layer digest/size, uncompressed diffID and
authoritative SPDX file checksums. Each actual library was byte-compared with
its authenticated official .deb and found identical. No image was executed.

The Debian authentication chain was InRelease signatures, signed SHA-256/size
entries for both Packages indexes and Sources, then exact .deb/source files.
The public archive keyring was bound to the verified OCI base; primary signing
fingerprints were compared with [Debian's archive keys](https://ftp-master.debian.org/keys.html).
Three valid gpgv signatures were required; bad, missing, revoked or expired
signature/key states were rejected.

InRelease SHA-256:
`77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa`.
Release date: 2026-07-11; stable Release supplies no Valid-Until. This binds the
installed historical package, not fresh scanner intelligence or release admission.

Exact source files in the [Debian zlib pool](https://deb.debian.org/debian/pool/main/z/zlib/):

| File                             | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| zlib_1.2.13.dfsg-1.dsc           | `3fa1e6b2fc525062aa88207dda52fed8e045373c809d362fe8a2bfbf7cf515a8` |
| zlib_1.2.13.dfsg.orig.tar.bz2    | `71feb7947e3c00ef125f83b79a4e529bde31171e5babe48b391f06758d1ab0a1` |
| zlib_1.2.13.dfsg-1.debian.tar.xz | `f66cf3d4f2d7defcd4d1fd1fb0a11ee39f1e01b42ec7d059c9dc5c1695133c44` |

Reproduction must verify these bindings before inspecting source or ELF data,
not merely compare version strings. Positive symbol controls used separately
authenticated libminizip1 `1.1-8+deb12u1` .deb files for both architectures.
They export the relevant MiniZip entrypoint, were never installed/executed, and
are not asserted vulnerable. A single-byte alteration fails the libz hash check.

## Separate question: CVE-2023-45853

[Debian's record](https://security-tracker.debian.org/tracker/CVE-2023-45853)
distinguishes the source tree from the binary build boundary. The CVE requires
MiniZip `zipOpenNewFileInZip4_64` processing oversized filename, comment or extra
fields. The source contains this implementation under `contrib/minizip/zip.c`.

Authenticated `debian/rules` invokes the top-level configure/make/install.
`Makefile.in` lines 60–70 and 277–278 explicitly link only the core zlib PIC
objects, excluding MiniZip. `debian/zlib1g.install` ships `lib/*/lib*.so.*`.
Both Debian patches modify only the unused MiniZip Makefile.

Actual ELF exports include zlibVersion/deflate/inflate but no MiniZip entrypoint.
Neither authoritative SPDX contains minizip/pyminizip. This supports the
component-scoped assertion that vulnerable MiniZip code is not present in these
zlib1g binaries; symbol absence or package-name absence alone would not suffice.
It does not classify arbitrary embedded MiniZip copies elsewhere.

Exact current policy components, one on each corresponding manifest:

- `pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1`
- `pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=arm64&distro=debian-12.15&epoch=1`

Decision requested: independently establish or reject the existing
`vulnerable_code_not_present` justification for these exact components/subjects.

## Separate question: CVE-2026-85091

[Debian's record](https://security-tracker.debian.org/tracker/CVE-2026-85091)
marks Bookworm vulnerable while describing a nonblocking writer introduced
upstream in 1.3.1.2. The [introducing commit](https://github.com/madler/zlib/commit/81cc0bebedd935daeb81b0b6e475d8786b51af3d)
adds retryable write-stall handling; the [fix](https://github.com/madler/zlib/commit/df84af25dc1942490e1d1c899a07619152a46148)
resets retained external input after a write failure. This discrepancy must be
resolved against actual code, not by preferring the more convenient tracker.

Authenticated 1.2.13 `gzwrite.c` SHA-256:
`c7454689751c8f41ec63a1381a0053fb149095abe1c3b89c8a996b2d7ac8adce`.
The authenticated gzwrite.c/gzguts.h/gzlib.c/gzread.c contain no gz_vacate,
state->again or EAGAIN retry handling. Neither Debian patch backports this path.

The old control flow was inspected separately:

- gz_comp lines 89–92 and 119–122: write failure becomes fatal Z_ERRNO.
- gzwrite lines 267–269 and gzvprintf lines 405–407 reject a stored error.
- gzvprintf lines 454–456 returns on gz_comp failure before its later memmove.

Positive source control: gzwrite.c at immutable introducing commit
`81cc0bebedd935daeb81b0b6e475d8786b51af3d` contains the newer retryable path;
its SHA-256 is `2e809d21020004df9de3192fd438984aa6dc4822f4e27a49f4e6ba6f27d07089`.
Absence of the name gz_vacate alone is not the argument.

Exact current policy components, separate from the MiniZip PURL representation:

- `pkg:deb/debian/zlib1g@1%3A1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&upstream=zlib`
- `pkg:deb/debian/zlib1g@1%3A1.2.13.dfsg-1?arch=arm64&distro=debian-12.15&upstream=zlib`

Decision requested: independently establish or reject nonapplicability of the
reported retained-input/nonblocking writer failure in these exact old binaries.
The MiniZip decision cannot classify this separate CVE.

## Review acceptance and remaining limits

The reviewer must identify which original evidence they independently checked,
give a separate result/justification for each CVE, and name any unresolved gap.
A trusted review must be attributable to a real review record and identity.
Neither the author nor an invented review label can provide that authority.

No reviewed VEX manifest/document exists in this change. After an authorized
positive decision, use the unchanged closed schema/trusted checkout contract;
test exact subjects/components/CVEs, wrong subject/component, expiry and conflicts.
Preserve raw observations and every unrelated API finding.

The API publisher pins SDK `57a1b7ce698a2ef7e253a05e6cf008b9fdab646c`.
It cannot automatically discover a later central VEX commit. The existing
exact-digest reevaluator discovers VEX in its own reviewed immutable checkout.
Any later verification must distinguish bounded zlib disposition from full
publisher/OCI acceptance and must not pretend old scan evidence is fresh.

No API rebuild, publisher retry, host/provider operation, Polyscope change,
enrollment or activation belongs to this review. API #1609 and deployment #92
remain open; READY_FOR_ENROLLMENT remains NOT_ADMITTED.
