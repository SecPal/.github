#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Normalize and admit bounded Trivy repository-scan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "secpal-trivy-repository-scan-v4"
OBSERVATION_VERSION = "secpal-trivy-repository-observation-v3"
POLICY_ID = "secpal-trivy-repository-policy-v1"
GATE_STATES = {"CLEAN", "ACTIONABLE", "REVIEW_REQUIRED", "UNKNOWN_STALE"}
FAILURE_CODES = {
    "TARGET_IDENTITY_FAILURE",
    "SCANNER_IDENTITY_FAILURE",
    "NETWORK_FAILURE",
    "DATABASE_FAILURE",
    "SCANNER_FAILURE",
    "DIAGNOSTIC_ADMISSION_FAILURE",
    "MALFORMED_OUTPUT",
    "POLICY_FAILURE",
}
FINDING_CLASSES = {"VULNERABILITY", "SECRET", "MISCONFIGURATION"}
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
RFC3339_RE = re.compile(
    r"(?P<second>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d{1,9}))?Z\Z"
)
TRIVY_VERSION = "0.74.0"
TRIVY_ARCHIVE_ID = "sha256:2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a"
SEVERITY_FALLBACK_DIAGNOSTIC = (
    "Using severities from other vendors for some vulnerabilities. Read "
    "https://trivy.dev/docs/v0.74/guide/scanner/vulnerability#severity-selection for details."
)
# Deployment#124 proof: #1236, requalified by #1244 on 2026-10-21.
# #1249 excludes only the independently provenance-approved REUSE revision.
# Exact source facts and unexecuted run obligations remain unchanged.
# The named existing control path validates concrete values before operations.
# Changes to any bound control/module or expiry require independent requalification.
DEPLOYMENT_TERRAFORM_ID = "deployment-ephemeral-1236"
DEPLOYMENT_TERRAFORM_EXPIRES = "2026-11-04T00:00:00Z"
DEPLOYMENT_TERRAFORM_BINDINGS = {
    "containers/phase-b-gateway/Containerfile": "7ddb40ddbd863f5150cfc261ff0049485ea3018d",
    "config": "2d4766e35ebea3e8cab85c35e77db5ce09a52f49",
    "infra/ci-cloud": "5a6905f320172fb5f6fc170c039a0bc8b7cf8684",
    "schemas": "2a793d4d0773656f2cfea6b489a7d5149d97c2f8",
    "scripts": "26a857dca06796c241fa155f36f513cc15a1bdd8",
    ".github": "sha256:f6de216e2ff4934a36e9796bf8ab73d0fbdfd4778b857930c3dbd5a8f1afc0bb"
}
# #1258 independently qualifies deployment#361's public-only Phase-1 composition.
# The five other bindings and all Terraform paths are identical to protected main.
# Retain that main state only through the same existing qualification expiry.
DEPLOYMENT_PHASE_ONE_BINDINGS = {
    **DEPLOYMENT_TERRAFORM_BINDINGS,
    "scripts": "0b3e423fb58643001b3332d543af8ccd73fa7cba",
}
# #1260 qualifies deployment#362's reviewed rootless XDG correction only.
# All other source/control identities, obligations and the original expiry hold.
DEPLOYMENT_PHASE_ONE_XDG_BINDINGS = {
    **DEPLOYMENT_TERRAFORM_BINDINGS,
    "scripts": "4c6d4144cfc7849196e01e5c4204792f3355dfd2",
}
# #1264 qualifies deployment#363's reviewed bounded diagnostics and dispatch
# evidence. Bind the new versioned control tree as well as the exact scripts.
DEPLOYMENT_PHASE_ONE_DISPATCH_BINDINGS = {
    **DEPLOYMENT_TERRAFORM_BINDINGS,
    "scripts": "ce6c93f9854ca2938509298f3120981ed992b069",
    ".secpal": "c9144f481e6148c42ecd8f8c73552bdbb137d66a",
}
# #1266 qualifies deployment#365's independently reviewed native #80 composition.
# Keep all other source/control identities, dispositions and the original expiry.
DEPLOYMENT_PHASE_ONE_NATIVE_BINDINGS = {
    **DEPLOYMENT_PHASE_ONE_DISPATCH_BINDINGS,
    "scripts": "c17a475b7185349018086ca8683dcf751a339a5a",
    ".secpal": "18745a3e7a93c9990e023b8ed5da4031025c631c",
}
DEPLOYMENT_TERRAFORM_PATHS = (
    'infra/ci-cloud/digitalocean/versions.tf',
    'infra/ci-cloud/gcp-rocky/main.tf',
    'infra/ci-cloud/gcp-rocky/metadata.tf',
    'infra/ci-cloud/gcp-rocky/outputs.tf',
    'infra/ci-cloud/gcp-rocky/variables.tf',
    'infra/ci-cloud/gcp-rocky/versions.tf',
    'infra/ci-cloud/gcp/versions.tf',
)
DEPLOYMENT_TERRAFORM_VARIABLES = frozenset((
    "project_id", "bootstrap_service_account", "trusted_control_sha", "target_sha",
    "profile", "zone", "machine_type", "disk_type", "disk_size_gib",
    "exact_image_self_link", "run_id", "run_attempt", "runner_ipv4",
    "ssh_public_key", "created_at", "expires_at",
))
DEPLOYMENT_RUN_BOUND_CONTROLS = (
    "actual-input-validation-and-metadata-admission",
    "exact-peer-management-access",
    "cloud-identity-removal-before-target",
    "bounded-lifetime-and-exact-run-cleanup",
)

Timestamp = tuple[datetime, int]


class ContractError(ValueError):
    """Raised when evidence does not satisfy the closed contract."""


def _git(workspace: Path, arguments: list[str], *, index: Path | None = None,
         accepted_return_codes: tuple[int, ...] = (0,)) -> bytes:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("GIT_"):
            environment.pop(name)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    if index is not None:
        environment["GIT_INDEX_FILE"] = str(index)
    completed = subprocess.run(
        [
            "git",
            "--no-replace-objects",
            "--literal-pathspecs",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.filemode=true",
            "-c",
            "core.symlinks=true",
            "-C",
            str(workspace),
            *arguments,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    if completed.returncode not in accepted_return_codes:
        raise ContractError("Git target verification failed")
    return completed.stdout


def verify_target(workspace: Path, commit: str) -> None:
    """Require the worktree's complete bytes to equal the expected commit."""
    if not COMMIT_RE.fullmatch(commit):
        raise ContractError("commit identity must be an exact lowercase SHA")
    try:
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as error:
        raise ContractError("workspace is unavailable") from error
    if not resolved_workspace.is_dir():
        raise ContractError("workspace must be a directory")

    top_level = Path(
        _git(resolved_workspace, ["rev-parse", "--show-toplevel"])
        .decode("utf-8")
        .strip()
    ).resolve(strict=True)
    checked_out_commit = _git(resolved_workspace, ["rev-parse", "HEAD"]).decode("ascii").strip()
    if top_level != resolved_workspace or checked_out_commit != commit:
        raise ContractError("workspace does not identify the expected commit")

    entries = _git(resolved_workspace, ["ls-tree", "-r", "-z", commit])
    if any(record.startswith(b"160000 ") for record in entries.split(b"\0")):
        raise ContractError("gitlinks cannot be completely scanned as local files")

    # The pinned scanner drops inline-ignored IaC findings before native JSON.
    # No caller-owned source directive may replace reviewed central exceptions.
    inline_ignores = _git(
        resolved_workspace,
        ["grep", "-a", "-i", "-l", "-z", "-e",
         "trivy" + r"[[:space:]]*:[[:space:]]*ignore", commit, "--"],
        accepted_return_codes=(0, 1),
    )
    if inline_ignores:
        raise ContractError("source contains unsupported inline scanner suppression")

    tracked = _git(resolved_workspace, ["ls-files", "-v", "-z"])
    for record in tracked.split(b"\0"):
        if record and (record[:1] == b"S" or record[:1].islower()):
            raise ContractError("tracked paths use unsupported index flags")

    with tempfile.TemporaryDirectory(prefix="secpal-trivy-target-") as temporary:
        clean_index = Path(temporary) / "index"
        _git(resolved_workspace, ["read-tree", commit], index=clean_index)
        _git(resolved_workspace, ["update-index", "--refresh"], index=clean_index)
        _git(
            resolved_workspace,
            ["diff-files", "--quiet", "--no-ext-diff", "--ignore-submodules=none", "--"],
            index=clean_index,
        )

    status = _git(
        resolved_workspace,
        ["status", "--porcelain", "--untracked-files=all", "--ignored=matching"],
    )
    if status:
        raise ContractError("workspace contains paths outside the expected commit")


def _verify_composer_severity_fallback(native: dict[str, Any] | None,
                                      scanner: dict[str, Any] | None,
                                      workspace: str | None) -> None:
    """Qualify only the observed Composer fallback from pinned autoDetectSeverity.

    The source returns DB Severity with an omitted SeveritySource after preferred
    vendors fail. CVE Composer advisories have no package-specific severity override.
    Do not infer a source: the DB's fallback severity is not source-attributable.
    """
    if scanner is None or native is None or workspace is None:
        raise ContractError("severity fallback context is unavailable")
    verified_scanner = _validate_scanner(scanner)
    if (verified_scanner["version"] != TRIVY_VERSION
            or verified_scanner["immutable_id"] != TRIVY_ARCHIVE_ID):
        raise ContractError("severity fallback scanner is unqualified")
    if not isinstance(native, dict) or native.get("SchemaVersion") != 2:
        raise ContractError("severity fallback native schema is unqualified")
    _validate_scan_surface(native, workspace)
    results = native.get("Results")
    if not isinstance(results, list):
        raise ContractError("severity fallback native results are unqualified")
    fallbacks = 0
    for result in results:
        if not isinstance(result, dict):
            raise ContractError("severity fallback result is malformed")
        target = _path(result.get("Target"))
        for vulnerability in _finding_collection(result, "Vulnerabilities"):
            if not isinstance(vulnerability, dict):
                raise ContractError("severity fallback vulnerability is malformed")
            finding = _vulnerability(target, vulnerability)
            vendors = vulnerability.get("VendorSeverity")
            if "SeveritySource" in vulnerability:
                source = _string(vulnerability["SeveritySource"], "severity source")
                if result.get("Type") == "composer":
                    data_source = vulnerability.get("DataSource")
                    if (not isinstance(data_source, dict) or not isinstance(vendors, dict)
                            or any(not isinstance(k, str) or not k or type(v) is not int
                                   or v not in range(5) for k, v in vendors.items())):
                        raise ContractError("Composer severity provenance is malformed")
                    advisory_source = _string(data_source.get("BaseID", data_source.get("ID")), "advisory source")
                    preferred = [advisory_source]
                    if finding["rule_id"].startswith("GHSA-"):
                        preferred.append("ghsa")
                    preferred.append("nvd")
                    selected = next((vendor for vendor in preferred if vendor in vendors), None)
                    if (source != selected or (source != advisory_source and vendors[source] == 0)
                            or vendors[source] != (
                            "UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"
                    ).index(finding["severity"])):
                        raise ContractError("Composer severity provenance is inconsistent")
                continue
            # Restrict admission to the reviewed real representation. NVD UNKNOWN
            # falls through; even UNKNOWN in the advisory's own source returns
            # immediately and cannot explain this warning. GHSA IDs use another
            # preferred-source branch and remain outside this qualification.
            if (result.get("Class") != "lang-pkgs" or result.get("Type") != "composer"
                    or re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", finding["rule_id"]) is None
                    or vulnerability.get("DataSource") != {
                        "ID": "php-security-advisories",
                        "Name": "PHP Security Advisories Database",
                        "URL": "https://github.com/FriendsOfPHP/security-advisories",
                    }):
                raise ContractError("severity fallback native provenance is unqualified")
            if finding["severity"] == "UNKNOWN":
                # The qualified native UNKNOWN representation omits both
                # provenance fields, not an explicit empty/null/malformed map.
                if "VendorSeverity" in vulnerability:
                    raise ContractError("severity fallback native provenance is unqualified")
            elif (not isinstance(vendors, dict) or not vendors
                    or any(not isinstance(k, str) or not k or type(v) is not int
                           or v not in range(5) for k, v in vendors.items())
                    or set(vendors) - {"ghsa", "nvd"}
                    or vendors.get("nvd", 0) != 0
                    or ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL").index(
                        finding["severity"]) != vendors.get("ghsa")):
                raise ContractError("severity fallback native provenance is unqualified")
            fallbacks += 1
    if not fallbacks:
        raise ContractError("severity fallback vulnerability is unavailable")


def github_source_fingerprint(identities: dict[str, str], quality: bytes) -> str:
    """Bind automation semantics, excluding two independently approved revisions.

    Scanned bytes are never changed. Every other automation byte/mode remains
    bound, including new workflows, local actions, permissions and commands.
    """
    caller = ".github/workflows/quality.yml"
    if caller not in identities:
        raise ContractError("repository security caller identity is unavailable")
    pattern = rb"(?m)^(        uses: SecPal/\.github/\.github/actions/trivy-repository-scan@)[0-9a-f]{40}( # main)$"
    normalized, count = re.subn(pattern, rb"\g<1>" + b"0" * 40 + rb"\g<2>", quality)
    if count != 1:
        raise ContractError("repository security caller pin representation is unqualified")
    # REUSE is independent licensing CI. This removes only its immutable
    # revision from the Terraform proof, not its job, owner, permissions or
    # execution. Native protected delivery owns accepted-main provenance;
    # normalization is not approval of a referenced workflow (see #1249).
    reuse_pattern = rb"(?m)^(    uses: SecPal/\.github/\.github/workflows/reusable-reuse\.yml@)([0-9a-f]{40})( # main)$"
    reuse_pins = re.findall(reuse_pattern, quality)
    if len(reuse_pins) != 1 or reuse_pins[0][1] == b"0" * 40:
        raise ContractError("independent REUSE pin representation is unqualified")
    normalized = re.sub(reuse_pattern, rb"\g<1>" + b"0" * 40 + rb"\g<3>", normalized)
    sources = dict(identities)
    mode, kind, _ = sources[caller].split(" ", 2)
    sources[caller] = mode + " " + kind + " " + _sha256(normalized)
    return _sha256(sources)


def observe_deployment_terraform(workspace: Path, commit: str) -> dict[str, Any]:
    """Observe source identities only; no Terraform interpretation or execution."""
    directories = {"infra/ci-cloud", "scripts", "config", "schemas"}
    caller = ".github/workflows/quality.yml"
    files = [path for path in DEPLOYMENT_TERRAFORM_BINDINGS
             if path not in directories and path != ".github"]
    # Reuse the existing raw-Git/byte observation owner for regular files.
    facts = observe_secret_sources(workspace, commit, [*files, caller])
    quality_blob = facts["blobs"].pop(caller)
    bindings = dict(facts["blobs"])
    # Old accepted sources have no dispatch-control tree. When present, it is
    # mandatory source evidence, and the existing type check rejects impostors.
    if _git(workspace, ["ls-tree", "-z", commit, "--", ".secpal"]):
        directories.add(".secpal")
    for path in sorted(directories):
        entry = _git(workspace, ["ls-tree", "-z", commit, "--", path]).split(b"\0")
        if len(entry) != 2 or entry[-1]:
            raise ContractError("control tree identity is unavailable")
        metadata, name = entry[0].split(b"\t", 1)
        mode, kind, identity = metadata.split(b" ")
        if mode != b"040000" or kind != b"tree" or name != path.encode():
            raise ContractError("control source is not a Git tree")
        bindings[path] = _source_blob(identity.decode("ascii"))
    terraform_paths = []
    github_sources = {}
    for record in _git(workspace, ["ls-tree", "-r", "-z", commit]).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            name = path.decode("utf-8")
            if name.endswith((".tf", ".tf.json")):
                terraform_paths.append(name)
            if name.startswith(".github/"):
                github_sources[name] = metadata.decode("ascii")
    bindings[".github"] = github_source_fingerprint(
        github_sources, _observe_blob(workspace, quality_blob))
    return {"commit": commit, "bindings": bindings, "terraform_paths": sorted(terraform_paths)}


def qualify_deployment_terraform(
    facts: dict[str, Any], repository: str, commit: str, completed_at: str,
) -> dict[str, Any]:
    """Purely admit the reviewed source/control proof, never concrete run values."""
    if (repository != "SecPal/deployment" or not COMMIT_RE.fullmatch(commit)
            or not isinstance(facts, dict)
            or set(facts) != {"commit", "bindings", "terraform_paths"}
            or facts["commit"] != commit
            or not (
                facts["bindings"] == DEPLOYMENT_TERRAFORM_BINDINGS
                or (facts["bindings"] == DEPLOYMENT_PHASE_ONE_BINDINGS
                    and _timestamp(completed_at) >= _timestamp("2026-10-24T00:00:00Z"))
                or (facts["bindings"] == DEPLOYMENT_PHASE_ONE_XDG_BINDINGS
                    and _timestamp(completed_at) >= _timestamp("2026-10-25T00:00:00Z"))
                or (facts["bindings"] == DEPLOYMENT_PHASE_ONE_DISPATCH_BINDINGS
                    and _timestamp(completed_at) >= _timestamp("2026-10-25T00:00:00Z"))
                or (facts["bindings"] == DEPLOYMENT_PHASE_ONE_NATIVE_BINDINGS
                    and _timestamp(completed_at) >= _timestamp("2026-10-25T00:00:00Z"))
            )
            or facts["terraform_paths"] != list(DEPLOYMENT_TERRAFORM_PATHS)
            or not _timestamp("2026-10-20T00:00:00Z") <= _timestamp(completed_at)
            < _timestamp(DEPLOYMENT_TERRAFORM_EXPIRES)):
        raise ContractError("Terraform source/run-bound qualification is unavailable")
    return {
        "qualification_id": DEPLOYMENT_TERRAFORM_ID,
        "scope": "REPOSITORY_STATIC",
        "run_bound_status": "REQUIRED_NOT_EXECUTED",
        "source_commit": commit,
        "source_bindings": dict(facts["bindings"]),
        "terraform_paths": list(facts["terraform_paths"]),
        "required_at_operation": list(DEPLOYMENT_RUN_BOUND_CONTROLS),
        "expires_at": DEPLOYMENT_TERRAFORM_EXPIRES,
    }


def _validate_coverage(coverage: dict[str, Any], repository: str, commit: str,
                       completed_at: str) -> dict[str, Any]:
    if not isinstance(coverage, dict):
        raise ContractError("Terraform coverage is malformed")
    expected = qualify_deployment_terraform(
        {"commit": coverage.get("source_commit"), "bindings": coverage.get("source_bindings"),
         "terraform_paths": coverage.get("terraform_paths")},
        repository, commit, completed_at,
    )
    if coverage != expected:
        raise ContractError("Terraform coverage differs from the reviewed contract")
    return expected


def _verify_terraform_warning(message: str, coverage: dict[str, Any] | None,
                              scanner: dict[str, Any] | None) -> None:
    # The pinned parser uses typed unknowns. Acknowledging their scope requires
    # the exact source/control proof and explicit unexecuted run-bound status.
    if coverage is None or scanner is None:
        raise ContractError("Terraform diagnostic coverage is unqualified")
    identity = _validate_scanner(scanner)
    if (identity["version"] != TRIVY_VERSION
            or identity["immutable_id"] != TRIVY_ARCHIVE_ID
            or coverage.get("qualification_id") != DEPLOYMENT_TERRAFORM_ID
            or coverage.get("run_bound_status") != "REQUIRED_NOT_EXECUTED"):
        raise ContractError("Terraform diagnostic identity is unqualified")
    prefix = ("[terraform parser] Variable values were not found in the environment or "
              'variable files. Evaluating may not work correctly.\tmodule="root" variables=')
    if not message.startswith(prefix):
        raise ContractError("Terraform diagnostic representation is unqualified")
    names = json.loads(message[len(prefix):])
    if not isinstance(names, str):
        raise ContractError("Terraform diagnostic variables are malformed")
    variables = names.split(", ")
    if (len(variables) != len(DEPLOYMENT_TERRAFORM_VARIABLES)
            or set(variables) != DEPLOYMENT_TERRAFORM_VARIABLES):
        raise ContractError("Terraform diagnostic coverage differs from source proof")


def verify_diagnostics(content: str, cache_directory: Path, *,
                       native: dict[str, Any] | None = None,
                       scanner: dict[str, Any] | None = None,
                       workspace: str | None = None,
                       coverage: dict[str, Any] | None = None) -> None:
    """Check pinned Trivy's private log framing without returning log material."""
    if not content.strip():
        raise ContractError("scanner diagnostics are unavailable")
    # --skip-check-update deliberately uses archive-pinned embedded checks.
    # Trivy labels its absent-cache fallback ERROR. Authenticate only that exact
    # transport diagnostic, once, while proving no external checks were loaded.
    checks = cache_directory / "policy" / "content"
    if checks.exists() or checks.is_symlink():
        raise ContractError("external check bundle is not admitted")
    expected_fallback = '[misconfig] Falling back to embedded checks\terr=' + json.dumps(
        'failed to check cache: cache does not exist at ' + json.dumps(str(checks))
    )
    fallbacks = 0
    advisories = 0
    terraform_warnings = 0
    for line in content.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3 or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", fields[0]
        ) is None:
            raise ContractError("scanner diagnostics indicate unknown scan health")
        if fields[1] == "ERROR" and fields[2] == expected_fallback:
            fallbacks += 1
        elif fields[1] == "WARN" and fields[2] == SEVERITY_FALLBACK_DIAGNOSTIC:
            advisories += 1
        elif fields[1] == "WARN" and fields[2].startswith("[terraform parser]"):
            _verify_terraform_warning(fields[2], coverage, scanner)
            terraform_warnings += 1
        elif fields[1] not in {"INFO", "DEBUG"} or not fields[2]:
            raise ContractError("scanner diagnostics indicate unknown scan health")
    if fallbacks != 1:
        raise ContractError("pinned embedded check selection is unavailable")
    if terraform_warnings != (1 if coverage is not None else 0):
        raise ContractError("Terraform diagnostic count differs from qualified scope")
    if advisories:
        if advisories != 1:
            raise ContractError("severity fallback diagnostic count is unqualified")
        _verify_composer_severity_fallback(native, scanner, workspace)


def configuration_identity() -> str:
    """Bind the trusted implementation, invocation and policy bundle by content."""
    root = Path(__file__).resolve().parents[1]
    paths = (
        ".github/actions/trivy-repository-scan/action.yml",
        "scripts/secpal-trivy-repository-scan.py",
        "policies/trivy-repository-scan-v1.json",
        "policies/trivy-repository-scan-ignore-v1.yaml",
        "policies/trivy-repository-secret-v1.yaml",
    )
    return _sha256({path: _sha256((root / path).read_bytes()) for path in paths})


def verify_redaction(native: dict[str, Any], candidate: dict[str, Any], workspace: Path,
                     repository: str, commit: str) -> None:
    """Reject secret aliases before a private candidate becomes public evidence.

    Correlate full cause lines or pinned bounded excerpts with immutable Git blobs.
    Captures remain transient; ambiguous positions and binary masks fail closed.
    """
    if candidate["subject"] != _validate_subject(repository, commit):
        raise ContractError("redaction subject differs from the authenticated target")
    if candidate["gate_state"] == "UNKNOWN_STALE" and candidate["findings"] == []:
        return
    captures: set[str] = set()
    for result in native["Results"]:
        for secret in _finding_collection(result, "Secrets"):
            target = _path(result["Target"])
            source = _git(workspace, ["cat-file", "blob", commit + ":" + target])
            lines = source.split(b"\n")
            location = _location(secret)
            if location is None:
                raise ContractError("secret censor location is unavailable")
            start, end = location["start_line"], location["end_line"]
            code = secret.get("Code")
            if not isinstance(code, dict) or not isinstance(code.get("Lines"), list):
                raise ContractError("secret censor evidence is unavailable")
            causes = [line for line in code["Lines"] if isinstance(line, dict) and line.get("IsCause") is True]
            numbers = [line.get("Number") for line in causes]
            if numbers != list(range(start, end + 1)) or any(type(n) is not int for n in numbers):
                raise ContractError("secret censor line coverage is ambiguous")
            found = False
            for line in causes:
                number = line["Number"]
                if number > len(lines) or not isinstance(line.get("Content"), str):
                    raise ContractError("secret censor source is unavailable")
                raw_line = lines[number - 1]
                original = raw_line.replace(b"\r", b"")
                try:
                    mask = line["Content"].encode("utf-8", errors="strict")
                except UnicodeError:
                    raise ContractError("secret censor content is unsupported") from None
                if not mask:
                    raise ContractError("secret censor content is unavailable")
                if len(mask) == len(original):
                    if any(a != b and b != 42 for a, b in zip(original, mask)):
                        raise ContractError("secret censor source is ambiguous")
                else:
                    # Trivy 0.74.0 findLocation (e1fd17a0): cause lines over
                    # 100 bytes use match context. Admit only this pinned scanner
                    # and exactly one compatible position, including overlapping
                    # windows. Fixed-width byte wildcards preserve censor spans;
                    # visible bytes are escaped literals, never regex syntax.
                    scanner = candidate.get("scanner", {})
                    if (not isinstance(scanner, dict)
                            or scanner.get("version") != TRIVY_VERSION
                            or scanner.get("immutable_id") != TRIVY_ARCHIVE_ID):
                        raise ContractError("secret censor excerpt scanner is unqualified")
                    if len(raw_line) <= 100 or len(mask) >= len(original):
                        raise ContractError("secret censor excerpt representation is unsupported")
                    pattern = b"".join(
                        b".{" + str(len(part)).encode("ascii") + b"}" if part.startswith(b"*")
                        else re.escape(part)
                        for part in re.split(rb"(\*+)", mask) if part
                    )
                    windows = re.finditer(rb"(?=" + pattern + rb")", original, re.DOTALL)
                    window = next(windows, None)
                    if window is None:
                        raise ContractError("secret censor excerpt source is unavailable")
                    if next(windows, None) is not None:
                        raise ContractError("secret censor excerpt source is ambiguous")
                    original = original[window.start():window.start() + len(mask)]
                for match in re.finditer(rb"\*+", mask):
                    value = original[match.start():match.end()]
                    if value == match.group():
                        continue
                    if b"*" in value:
                        raise ContractError("secret censor span is ambiguous")
                    try:
                        capture = value.decode("utf-8", errors="strict")
                    except UnicodeError:
                        raise ContractError("secret censor capture is unsupported") from None
                    captures.add(capture)
                    found = True
            if not found:
                raise ContractError("secret censor span is unavailable")
    def strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for member in value.values():
                yield from strings(member)
        elif isinstance(value, list):
            for member in value:
                yield from strings(member)
    if any(capture in value for value in strings(candidate) for capture in captures):
        raise ContractError("candidate evidence contains captured material")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _timestamp(value: str) -> Timestamp:
    if not isinstance(value, str):
        raise ContractError("timestamps must use UTC Z form")
    match = RFC3339_RE.fullmatch(value)
    if match is None:
        raise ContractError("timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(match.group("second") + "+00:00")
    except ValueError as error:
        raise ContractError("timestamp is malformed") from error
    if parsed.tzinfo != timezone.utc:
        raise ContractError("timestamps must be UTC")
    fraction = match.group("fraction") or ""
    return parsed, int(fraction.ljust(9, "0") or "0")


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _source_blob(value: Any) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise ContractError("source blob must be an exact lowercase Git SHA")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    return _string(value, field)


def _line(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ContractError(f"{field} must be a positive integer")
    return value


def _path(value: Any) -> str:
    candidate = _string(value, "finding path").replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    parsed = PurePosixPath(candidate)
    if parsed.is_absolute() or not candidate or ".." in parsed.parts:
        raise ContractError("finding path must be repository-relative")
    return parsed.as_posix()


def _severity(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("finding severity must be a non-empty string")
    normalized = value.upper()
    if normalized not in SEVERITIES:
        raise ContractError("finding severity is unsupported")
    return normalized


def _validate_subject(repository: str, commit: str) -> dict[str, str]:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ContractError("repository identity must be owner/name")
    if not COMMIT_RE.fullmatch(commit):
        raise ContractError("commit identity must be an exact lowercase SHA")
    return {"repository": repository, "commit": commit}


def _validate_scanner(scanner: dict[str, Any]) -> dict[str, str]:
    if not isinstance(scanner, dict) or set(scanner) != {"name", "version", "immutable_id", "configuration_sha256"}:
        raise ContractError("scanner identity is malformed")
    if scanner["name"] != "trivy":
        raise ContractError("scanner must be Trivy")
    version = _string(scanner["version"], "scanner version")
    immutable_id = _string(scanner["immutable_id"], "scanner immutable identity")
    if not SHA256_RE.fullmatch(immutable_id):
        raise ContractError("scanner immutable identity must be sha256")
    configuration = _string(scanner["configuration_sha256"], "scanner configuration identity")
    if not SHA256_RE.fullmatch(configuration):
        raise ContractError("scanner configuration identity must be sha256")
    return {"name": "trivy", "version": version, "immutable_id": immutable_id,
            "configuration_sha256": configuration}


def _validate_database(
    database: dict[str, Any], observed_at: Timestamp | None = None
) -> dict[str, str]:
    if not isinstance(database, dict):
        raise ContractError("database identity is malformed")
    required = {"status", "identity", "updated_at", "next_update", "downloaded_at"}
    if set(database) != required:
        raise ContractError("database identity has missing or unknown fields")
    status = database["status"]
    if status not in {"FRESH", "STALE"}:
        raise ContractError("database status must be FRESH or STALE")
    identity = _string(database["identity"], "database identity")
    if not SHA256_RE.fullmatch(identity):
        raise ContractError("database identity must be sha256")
    updated_at = _string(database["updated_at"], "database updated_at")
    next_update = _string(database["next_update"], "database next_update")
    downloaded_at = _string(database["downloaded_at"], "database downloaded_at")
    updated = _timestamp(updated_at)
    next_time = _timestamp(next_update)
    downloaded = _timestamp(downloaded_at)
    if (
        updated > downloaded
        or updated >= next_time
        or (observed_at is not None and downloaded > observed_at)
    ):
        raise ContractError("database freshness chronology is invalid")
    return {
        "status": status,
        "identity": identity,
        "updated_at": updated_at,
        "next_update": next_update,
        "downloaded_at": downloaded_at,
    }


def _location(source: dict[str, Any]) -> dict[str, int] | None:
    start = _line(source.get("StartLine"), "start line")
    end = _line(source.get("EndLine"), "end line")
    if start is None and end is None:
        return None
    if start is None:
        start = end
    if end is None:
        end = start
    assert start is not None and end is not None
    if end < start:
        raise ContractError("finding line range is inverted")
    return {"start_line": start, "end_line": end}


def _fingerprint(finding: dict[str, Any]) -> str:
    stable = {
        key: finding[key]
        for key in (
            "class",
            "rule_id",
            "path",
            "location",
            "package",
            "installed_version",
            "resource",
        )
        if key in finding
    }
    return _sha256(stable)


def _vulnerability(target: str, native: dict[str, Any]) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "class": "VULNERABILITY",
        "rule_id": _string(native.get("VulnerabilityID"), "vulnerability ID"),
        "severity": _severity(native.get("Severity")),
        "path": target,
        "package": _string(native.get("PkgName"), "package name"),
        "installed_version": _string(native.get("InstalledVersion"), "installed version"),
    }
    fixed = _optional_string(native.get("FixedVersion"), "fixed version")
    if fixed is not None:
        finding["fixed_version"] = fixed
    title = _optional_string(native.get("Title"), "vulnerability title")
    if title is not None:
        finding["title"] = title
    finding["fingerprint"] = _fingerprint(finding)
    return finding


def _secret(target: str, native: dict[str, Any]) -> dict[str, Any]:
    # Deliberately allowlist metadata. Trivy Match, Code and Layer are never copied.
    finding: dict[str, Any] = {
        "class": "SECRET",
        "rule_id": _string(native.get("RuleID"), "secret rule ID"),
        "severity": _severity(native.get("Severity")),
        "path": target,
    }
    location = _location(native)
    if location is None:
        raise ContractError("secret location is required")
    finding["location"] = location
    finding["fingerprint"] = _fingerprint(finding)
    return finding


def _misconfiguration(target: str, native: dict[str, Any]) -> dict[str, Any]:
    rule_id = native.get("AVDID") or native.get("ID")
    finding: dict[str, Any] = {
        "class": "MISCONFIGURATION",
        "rule_id": _string(rule_id, "misconfiguration rule ID"),
        "severity": _severity(native.get("Severity")),
        "path": target,
    }
    cause = native.get("CauseMetadata") or {}
    if not isinstance(cause, dict):
        raise ContractError("misconfiguration cause metadata is malformed")
    location = _location(cause)
    if location is not None:
        finding["location"] = location
    resource = _optional_string(cause.get("Resource"), "misconfiguration resource")
    if resource is not None:
        finding["resource"] = resource
    title = _optional_string(native.get("Title"), "misconfiguration title")
    if title is not None:
        finding["title"] = title
    message = _optional_string(native.get("Message"), "misconfiguration message")
    if message is not None:
        finding["message"] = message
    finding["fingerprint"] = _fingerprint(finding)
    return finding


def _finding_collection(result: dict[str, Any], field: str) -> list[Any]:
    if field not in result:
        return []
    value = result[field]
    if not isinstance(value, list):
        raise ContractError("Trivy finding collection is malformed")
    return value


def _validate_scan_surface(native: dict[str, Any], workspace: str) -> None:
    if native.get("ArtifactType") not in {"filesystem", "repository"}:
        raise ContractError("Trivy output is not a filesystem repository scan")
    artifact_name = _string(native.get("ArtifactName"), "Trivy filesystem artifact")
    intended_workspace = _string(workspace, "intended scan workspace")
    if os.path.normpath(artifact_name) != os.path.normpath(intended_workspace):
        raise ContractError("Trivy scan artifact differs from the intended workspace")


def normalize_native(
    native: dict[str, Any],
    *,
    repository: str,
    commit: str,
    workspace: str,
    scanner: dict[str, Any],
    database: dict[str, Any],
    completed_at: str,
) -> dict[str, Any]:
    """Purely normalize captured Trivy JSON into a private candidate observation."""
    if not isinstance(native, dict) or native.get("SchemaVersion") != 2:
        raise ContractError("Trivy output schema version is missing or unsupported")
    _validate_scan_surface(native, workspace)
    results = native.get("Results")
    if not isinstance(results, list):
        raise ContractError("Trivy Results must be an array")
    completed = _timestamp(completed_at)
    normalized_database = _validate_database(database, completed)
    if completed >= _timestamp(normalized_database["next_update"]):
        normalized_database["status"] = "STALE"

    findings: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            raise ContractError("Trivy result entry is malformed")
        if _finding_collection(result, "ExperimentalModifiedFindings"):
            raise ContractError("Trivy suppressed findings bypass central policy")
        target = _path(result.get("Target"))
        vulnerabilities = _finding_collection(result, "Vulnerabilities")
        secrets = _finding_collection(result, "Secrets")
        misconfigurations = _finding_collection(result, "Misconfigurations")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise ContractError("Trivy vulnerability is malformed")
            findings.append(_vulnerability(target, vulnerability))
        for secret in secrets:
            if not isinstance(secret, dict):
                raise ContractError("Trivy secret is malformed")
            findings.append(_secret(target, secret))
        for misconfiguration in misconfigurations:
            if not isinstance(misconfiguration, dict):
                raise ContractError("Trivy misconfiguration is malformed")
            status = misconfiguration.get("Status")
            if status not in {"FAIL", "PASS"}:
                raise ContractError("Trivy misconfiguration status is unsupported")
            if status == "FAIL":
                findings.append(_misconfiguration(target, misconfiguration))

    findings.sort(key=lambda item: (item["fingerprint"], item["class"], item["path"]))
    return {
        "schema_version": OBSERVATION_VERSION,
        "subject": _validate_subject(repository, commit),
        "scanner": _validate_scanner(scanner),
        "database": normalized_database,
        "completed_at": completed_at,
        "scanners": ["vuln", "secret", "misconfig"],
        "findings": findings,
    }


def _observe_blob(workspace: Path, blob: str) -> bytes:
    """Read and authenticate raw Git object bytes; never emit captures."""
    _source_blob(blob)
    source = _git(workspace, ["cat-file", "blob", blob])
    identity = hashlib.sha1(b"blob " + str(len(source)).encode("ascii") + b"\0" + source).hexdigest()
    if identity != blob:
        raise ContractError("scanned source differs from the immutable blob")
    return source


def observe_secret_sources(workspace: Path, commit: str, paths: list[str]) -> dict[str, Any]:
    """Observe bounded blob identities from the exact clean checked-out commit.

    Never consume scanner/caller source hashes or Git replacement objects. Read
    raw bytes independently to authenticate both the tree entry and scanned file.
    No source bytes or policy decisions leave this observation boundary.
    """
    verify_target(workspace, commit)
    root = workspace.resolve(strict=True)
    blobs: dict[str, str] = {}
    for path in sorted(set(paths)):
        if _path(path) != path:
            raise ContractError("source observation path is not canonical")
        entries = _git(root, ["ls-tree", "-z", commit, "--", path]).split(b"\0")
        if len(entries) != 2 or entries[-1] != b"":
            raise ContractError("source tree entry is unavailable")
        metadata, name = entries[0].split(b"\t", 1)
        mode, kind, object_id = metadata.split(b" ")
        if mode not in {b"100644", b"100755"} or kind != b"blob" or name != path.encode("utf-8"):
            raise ContractError("source tree entry is not a regular file")
        blob = _source_blob(object_id.decode("ascii"))
        source = _observe_blob(root, blob)
        file = root / path
        if file.resolve(strict=True) != file or file.read_bytes() != source:
            raise ContractError("scanned source differs from the immutable blob")
        blobs[path] = blob
    return {"commit": commit, "blobs": blobs}


def prepare_target_snapshot(workspace: Path, commit: str, destination: Path) -> None:
    """Copy the exact target into action-owned, read-only scanner storage.

    The caller worktree and index stay untouched; caller repository config and
    hooks are not copied. Git objects are independent copies, never caller
    hardlinks or borrowed alternates. Scanner and observer use the same snapshot.
    """
    verify_target(workspace, commit)
    root = workspace.resolve(strict=True)
    target = destination.resolve(strict=False)
    if target.is_relative_to(root) or root.is_relative_to(target) or target.exists():
        raise ContractError("snapshot must be a new private path outside the caller")
    _git(root, ["clone", "--no-hardlinks", "--dissociate", "--no-checkout", "--", str(root), str(target)])
    _git(target, ["-c", "core.hooksPath=/dev/null", "update-ref", "--no-deref", "HEAD", commit])
    _git(target, ["read-tree", commit])
    # Materialize raw objects rather than running checkout smudge filters or
    # applying platform line-ending conversions. Export attributes cannot omit
    # any tracked file. One observation owner authenticates all blob bytes.
    for record in _git(target, ["ls-tree", "-r", "-z", commit]).split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, kind, object_id = metadata.split(b" ")
        name = raw_name.decode("utf-8")
        if (_path(name) != name or PurePosixPath(name).parts[0] == ".git"
                or kind != b"blob" or mode not in {b"100644", b"100755", b"120000"}):
            raise ContractError("snapshot tree entry is unsupported")
        source = _observe_blob(target, object_id.decode("ascii"))
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == b"120000":
            path.symlink_to(os.fsdecode(source))
        else:
            path.write_bytes(source)
            path.chmod(0o755 if mode == b"100755" else 0o644)
    verify_target(target, commit)
    # Preserve executable bits and symlinks; never follow a source symlink when
    # sealing private storage. The private parent is owned by the action.
    for path in target.rglob("*"):
        if not path.is_symlink():
            mode = path.stat().st_mode
            path.chmod(0o555 if path.is_dir() else 0o444 | (mode & 0o111))
    target.chmod(0o555)


def normalize_secret_sources(observation: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    """Purely bind independently observed source facts to normalized secrets.

    This internal seam accepts only observe_secret_sources output. Native JSON
    and the closed caller interface cannot supply these facts.
    """
    if (not isinstance(sources, dict) or set(sources) != {"commit", "blobs"}
            or sources["commit"] != observation["subject"]["commit"]
            or not isinstance(sources["blobs"], dict)):
        raise ContractError("source observation identity is malformed or mismatched")
    paths = {finding["path"] for finding in observation["findings"] if finding["class"] == "SECRET"}
    if set(sources["blobs"]) != paths:
        raise ContractError("source observation coverage differs from secret findings")
    blobs = {path: _source_blob(blob) for path, blob in sources["blobs"].items()}
    findings = [
        {**finding, "source_blob": blobs[finding["path"]]} if finding["class"] == "SECRET"
        else dict(finding) for finding in observation["findings"]
    ]
    return {**observation, "findings": findings}


def _validate_policy(policy: dict[str, Any], completed_at: str) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise ContractError("policy must be an object")
    expected = {"id", "version", "required_scanners", "actions", "exceptions", "vex"}
    if set(policy) != expected or policy.get("id") != POLICY_ID:
        raise ContractError("policy identity or fields are invalid")
    version = _string(policy.get("version"), "policy version")
    if policy.get("required_scanners") != ["vuln", "secret", "misconfig"]:
        raise ContractError("policy must require the three repository scanners")
    actions = policy.get("actions")
    if not isinstance(actions, dict) or set(actions) != FINDING_CLASSES:
        raise ContractError("policy action matrix is incomplete")
    for finding_class, severity_actions in actions.items():
        if not isinstance(severity_actions, dict) or set(severity_actions) != SEVERITIES:
            raise ContractError(f"policy action matrix is incomplete for {finding_class}")
        if any(value not in {"ACTIONABLE", "REVIEW_REQUIRED"} for value in severity_actions.values()):
            raise ContractError("policy action must be ACTIONABLE or REVIEW_REQUIRED")
    exceptions = policy.get("exceptions")
    if not isinstance(exceptions, list):
        raise ContractError("policy exceptions must be an array")
    now = _timestamp(completed_at)
    seen: set[str] = set()
    seen_selectors: set[tuple[str, str, str, str]] = set()
    for exception in exceptions:
        required = {"id", "repository", "class", "rule_id", "path", "disposition", "expires_at", "rationale"}
        if isinstance(exception, dict) and exception.get("class") == "SECRET":
            required.add("source_blob")
        if isinstance(exception, dict) and "qualification_id" in exception:
            required.add("qualification_id")
            if (exception["qualification_id"] != DEPLOYMENT_TERRAFORM_ID
                    or exception.get("repository") != "SecPal/deployment"
                    or exception.get("class") != "MISCONFIGURATION"):
                raise ContractError("exception qualification is not supported")
        if not isinstance(exception, dict) or set(exception) != required:
            raise ContractError("policy exception is malformed")
        exception_id = _string(exception["id"], "exception ID")
        if exception_id in seen:
            raise ContractError("policy exception IDs must be unique")
        seen.add(exception_id)
        if exception["class"] not in FINDING_CLASSES:
            raise ContractError("policy exception class is invalid")
        if exception["class"] == "SECRET":
            _source_blob(exception["source_blob"])
        rule_id = _string(exception["rule_id"], "exception rule ID")
        path = _path(exception["path"])
        repository = _string(exception["repository"], "exception repository")
        if not REPOSITORY_RE.fullmatch(repository):
            raise ContractError("exception repository must be exact owner/name")
        selector = (repository, exception["class"], rule_id, path)
        if selector in seen_selectors:
            raise ContractError("policy exception selectors must be unique")
        seen_selectors.add(selector)
        if exception["disposition"] not in {"IGNORED", "NOT_AFFECTED"}:
            raise ContractError("policy exception disposition is invalid")
        if exception["disposition"] == "NOT_AFFECTED" and exception["class"] != "VULNERABILITY":
            raise ContractError("VEX NOT_AFFECTED applies only to vulnerabilities")
        if _timestamp(exception["expires_at"]) <= now:
            raise ContractError("policy exception is expired")
        if ("qualification_id" in exception
                and _timestamp(exception["expires_at"]) > _timestamp(DEPLOYMENT_TERRAFORM_EXPIRES)):
            raise ContractError("exception outlives its source qualification")
        _string(exception["rationale"], "exception rationale")
    vex = policy.get("vex")
    if vex != {
        "documents": [],
        "accepted_statuses": ["not_affected", "fixed"],
        "runtime_injection": False,
    }:
        raise ContractError("VEX policy must be closed and runtime injection disabled")
    return {"id": POLICY_ID, "version": version, "sha256": _sha256(policy)}


def _apply_exception(
    finding: dict[str, Any], exceptions: list[dict[str, Any]], repository: str,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matches = [
        exception
        for exception in exceptions
        if exception["repository"] == repository
        and exception["class"] == finding["class"]
        and exception["rule_id"] == finding["rule_id"]
        and exception["path"] == finding["path"]
    ]
    if len(matches) > 1:
        raise ContractError("more than one exception matches a finding")
    result = dict(finding)
    if matches and finding["class"] == "SECRET":
        blob = _source_blob(finding.get("source_blob"))
        matches = [exception for exception in matches if exception["source_blob"] == blob]
    if matches and "qualification_id" in matches[0]:
        matches = [exception for exception in matches if coverage is not None
                   and exception["qualification_id"] == coverage["qualification_id"]]
    if matches:
        result["exception"] = {
            "id": matches[0]["id"],
            "disposition": matches[0]["disposition"],
            "expires_at": matches[0]["expires_at"],
        }
    return result


def admit(observation: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Purely apply the reviewed organization policy to one observation."""
    if not isinstance(observation, dict) or observation.get("schema_version") != OBSERVATION_VERSION:
        raise ContractError("observation schema is invalid")
    policy_identity = _validate_policy(policy, observation["completed_at"])
    coverage = None
    if observation["subject"]["repository"] == "SecPal/deployment" and "coverage" not in observation:
        raise ContractError("deployment source coverage is required")
    if "coverage" in observation:
        coverage = _validate_coverage(observation["coverage"], observation["subject"]["repository"],
                                      observation["subject"]["commit"], observation["completed_at"])
    if observation.get("scanners") != policy["required_scanners"]:
        raise ContractError("required scanners were not explicitly observed")
    for finding in observation["findings"]:
        if finding["class"] == "SECRET":
            _source_blob(finding.get("source_blob"))
    exceptions = [
        {**exception, "path": _path(exception["path"])}
        for exception in policy["exceptions"]
    ]
    findings = [_apply_exception(finding, exceptions, observation["subject"]["repository"], coverage) for finding in observation["findings"]]
    active = [finding for finding in findings if "exception" not in finding]
    actions = [policy["actions"][finding["class"]][finding["severity"]] for finding in active]
    if observation["database"]["status"] != "FRESH":
        gate_state = "UNKNOWN_STALE"
    elif "ACTIONABLE" in actions:
        gate_state = "ACTIONABLE"
    elif actions:
        gate_state = "REVIEW_REQUIRED"
    else:
        gate_state = "CLEAN"
    if gate_state not in GATE_STATES:
        raise AssertionError("unreachable gate state")
    summary = {
        "total": len(findings),
        "actionable": sum(
            1
            for finding in active
            if policy["actions"][finding["class"]][finding["severity"]] == "ACTIONABLE"
        ),
        "review_required": sum(
            1
            for finding in active
            if policy["actions"][finding["class"]][finding["severity"]] == "REVIEW_REQUIRED"
        ),
        "excepted": len(findings) - len(active),
    }
    operation = {"name": "TRIVY_REPOSITORY_SCAN", "status": "SUCCEEDED"}
    if gate_state == "UNKNOWN_STALE":
        operation = {
            "name": "TRIVY_REPOSITORY_SCAN",
            "status": "FAILED",
            "failure_code": "DATABASE_FAILURE",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "subject": observation["subject"],
        "scanner": observation["scanner"],
        "database": observation["database"],
        "completed_at": observation["completed_at"],
        "policy": policy_identity,
        "operation": operation,
        "gate_state": gate_state,
        "summary": summary,
        "findings": findings,
        **({"coverage": coverage} if coverage is not None else {}),
    }


def unknown_result(
    *, repository: str, commit: str, failure_code: str, completed_at: str
) -> dict[str, Any]:
    if failure_code not in FAILURE_CODES:
        raise ContractError("failure code is not recognized")
    _timestamp(completed_at)
    return {
        "schema_version": SCHEMA_VERSION,
        "subject": _validate_subject(repository, commit),
        "completed_at": completed_at,
        "operation": {
            "name": "TRIVY_REPOSITORY_SCAN",
            "status": "FAILED",
            "failure_code": failure_code,
        },
        "gate_state": "UNKNOWN_STALE",
        "summary": {"total": 0, "actionable": 0, "review_required": 0, "excepted": 0},
        "findings": [],
    }


def database_identity(
    metadata_paths: list[Path], database_paths: list[Path], observed_at: str
) -> dict[str, str]:
    observed = _timestamp(observed_at)
    if not metadata_paths or not database_paths:
        raise ContractError("database metadata and files are required")
    records: list[dict[str, Any]] = []
    updated_values: list[tuple[Timestamp, str]] = []
    next_values: list[tuple[Timestamp, str]] = []
    downloaded_values: list[tuple[Timestamp, str]] = []
    for path in metadata_paths:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ContractError("database metadata is malformed")
        updated_at = _string(metadata.get("UpdatedAt"), "database UpdatedAt")
        next_update_at = _string(metadata.get("NextUpdate"), "database NextUpdate")
        downloaded_at = _string(metadata.get("DownloadedAt"), "database DownloadedAt")
        updated = _timestamp(updated_at)
        next_update = _timestamp(next_update_at)
        downloaded = _timestamp(downloaded_at)
        if updated > downloaded or updated >= next_update or downloaded > observed:
            raise ContractError("database metadata chronology is invalid")
        updated_values.append((updated, updated_at))
        next_values.append((next_update, next_update_at))
        downloaded_values.append((downloaded, downloaded_at))
        records.append({"metadata": metadata, "sha256": _sha256(path.read_bytes())})
    for path in database_paths:
        if not path.is_file():
            raise ContractError("database file is missing")
        records.append({"database_file": path.name, "sha256": _sha256(path.read_bytes())})
    earliest_next = min(next_values, key=lambda item: item[0])
    result = {
        "status": "FRESH" if observed < earliest_next[0] else "STALE",
        "identity": _sha256(records),
        "updated_at": min(updated_values, key=lambda item: item[0])[1],
        "next_update": earliest_next[1],
        "downloaded_at": max(downloaded_values, key=lambda item: item[0])[1],
    }
    return _validate_database(result, observed)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(value) + "\n", encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluate(arguments: argparse.Namespace) -> int:
    completed_at = arguments.completed_at
    try:
        native = _load(arguments.native)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        _write(
            arguments.output,
            unknown_result(
                repository=arguments.repository,
                commit=arguments.commit,
                failure_code="MALFORMED_OUTPUT",
                completed_at=completed_at,
            ),
        )
        return 1
    try:
        database = _load(arguments.database)
        _validate_database(database, _timestamp(completed_at))
    except (ContractError, KeyError, TypeError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        _write(
            arguments.output,
            unknown_result(
                repository=arguments.repository,
                commit=arguments.commit,
                failure_code="DATABASE_FAILURE",
                completed_at=completed_at,
            ),
        )
        return 1
    try:
        policy = _load(arguments.policy)
        _validate_policy(policy, completed_at)
    except (ContractError, KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError, OSError):
        _write(
            arguments.output,
            unknown_result(
                repository=arguments.repository,
                commit=arguments.commit,
                failure_code="POLICY_FAILURE",
                completed_at=completed_at,
            ),
        )
        return 1
    try:
        # Capture filesystem identity here; normalization is replayable without it.
        observed_workspace = str(Path(arguments.workspace).resolve(strict=True))
        observed_native = dict(native)
        observed_native["ArtifactName"] = str(Path(native["ArtifactName"]).resolve(strict=True))
        observation = normalize_native(
            observed_native,
            repository=arguments.repository,
            commit=arguments.commit,
            workspace=observed_workspace,
            scanner={
                "name": "trivy",
                "version": arguments.scanner_version,
                "immutable_id": arguments.scanner_identity,
                "configuration_sha256": configuration_identity(),
            },
            database=database,
            completed_at=completed_at,
        )
        try:
            sources = observe_secret_sources(
                Path(observed_workspace), arguments.commit,
                [finding["path"] for finding in observation["findings"] if finding["class"] == "SECRET"],
            )
            observation = normalize_secret_sources(observation, sources)
        except (ContractError, OSError, UnicodeError):
            _write(arguments.output, unknown_result(
                repository=arguments.repository, commit=arguments.commit,
                failure_code="TARGET_IDENTITY_FAILURE", completed_at=completed_at,
            ))
            return 1
        try:
            coverage = None
            if arguments.repository == "SecPal/deployment":
                facts = observe_deployment_terraform(Path(observed_workspace), arguments.commit)
                coverage = qualify_deployment_terraform(
                    facts, arguments.repository, arguments.commit, completed_at)
                observation["coverage"] = coverage
            verify_diagnostics(
                arguments.diagnostics.read_text(encoding="utf-8"), arguments.cache_dir,
                native=observed_native, scanner=observation["scanner"],
                workspace=observed_workspace, coverage=coverage,
            )
        except (ContractError, OSError, UnicodeError, ValueError, TypeError):
            _write(arguments.output, unknown_result(
                repository=arguments.repository, commit=arguments.commit,
                failure_code="DIAGNOSTIC_ADMISSION_FAILURE", completed_at=completed_at,
            ))
            return 1
        result = admit(observation, policy)
    except (ContractError, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError, OSError):
        _write(
            arguments.output,
            unknown_result(
                repository=arguments.repository,
                commit=arguments.commit,
                failure_code="MALFORMED_OUTPUT",
                completed_at=completed_at,
            ),
        )
        return 1
    _write(arguments.output, result)
    return 1 if result["gate_state"] == "UNKNOWN_STALE" else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--native", type=Path, required=True)
    evaluate.add_argument("--diagnostics", type=Path, required=True)
    evaluate.add_argument("--cache-dir", type=Path, required=True)
    evaluate.add_argument("--database", type=Path, required=True)
    evaluate.add_argument("--policy", type=Path, required=True)
    evaluate.add_argument("--repository", required=True)
    evaluate.add_argument("--commit", required=True)
    evaluate.add_argument("--workspace", required=True)
    evaluate.add_argument("--scanner-version", required=True)
    evaluate.add_argument("--scanner-identity", required=True)
    evaluate.add_argument("--completed-at", required=True)
    evaluate.add_argument("--output", type=Path, required=True)

    diagnostics = commands.add_parser("verify-diagnostics")
    diagnostics.add_argument("--diagnostics", type=Path, required=True)
    diagnostics.add_argument("--cache-dir", type=Path, required=True)

    redaction = commands.add_parser("verify-redaction")
    redaction.add_argument("--native", type=Path, required=True)
    redaction.add_argument("--candidate", type=Path, required=True)
    redaction.add_argument("--workspace", type=Path, required=True)
    redaction.add_argument("--repository", required=True)
    redaction.add_argument("--commit", required=True)

    target = commands.add_parser("verify-target")
    target.add_argument("--workspace", type=Path, required=True)
    target.add_argument("--commit", required=True)

    snapshot = commands.add_parser("prepare-snapshot")
    snapshot.add_argument("--workspace", type=Path, required=True)
    snapshot.add_argument("--commit", required=True)
    snapshot.add_argument("--destination", type=Path, required=True)

    database = commands.add_parser("database")
    database.add_argument("--metadata", action="append", type=Path, required=True)
    database.add_argument("--database-file", action="append", type=Path, required=True)
    database.add_argument("--observed-at", required=True)
    database.add_argument("--output", type=Path, required=True)

    unknown = commands.add_parser("unknown")
    unknown.add_argument("--repository", required=True)
    unknown.add_argument("--commit", required=True)
    unknown.add_argument("--failure-code", choices=sorted(FAILURE_CODES), required=True)
    unknown.add_argument("--completed-at", required=True)
    unknown.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if arguments.command == "evaluate":
        return _evaluate(arguments)
    try:
        if arguments.command == "verify-target":
            verify_target(arguments.workspace, arguments.commit)
        elif arguments.command == "prepare-snapshot":
            prepare_target_snapshot(arguments.workspace, arguments.commit, arguments.destination)
        elif arguments.command == "verify-diagnostics":
            verify_diagnostics(arguments.diagnostics.read_text(encoding="utf-8"), arguments.cache_dir)
        elif arguments.command == "verify-redaction":
            verify_redaction(_load(arguments.native), _load(arguments.candidate),
                             arguments.workspace, arguments.repository, arguments.commit)
        elif arguments.command == "database":
            _write(
                arguments.output,
                database_identity(
                    arguments.metadata,
                    arguments.database_file,
                    arguments.observed_at,
                ),
            )
        else:
            _write(
                arguments.output,
                unknown_result(
                    repository=arguments.repository,
                    commit=arguments.commit,
                    failure_code=arguments.failure_code,
                    completed_at=arguments.completed_at,
                ),
            )
    except (ContractError, OSError, KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        print("repository scan evidence verification failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
