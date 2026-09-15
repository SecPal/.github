# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main safety assertions for the registered immutable delivery tree.

The exact-source runner removes candidate-owned tests before executing this file.
Assertion authority therefore remains on accepted central main while the parked
registered-repository production bytes remain the system under test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys


INVARIANTS = [
    "current_tree_exact",
    "historical_bytes_unavailable",
    "registered_validation",
    "source_history",
]
REQUIRED_FILES = (
    Path("docs/architecture/production-host.md"),
    Path("schemas/production-host-facts.schema.json"),
    Path("scripts/validate-production-contract.py"),
    Path("scripts/qualify-production-host.sh"),
)
DOCUMENT_TERMS = (
    "Rocky Linux 10.2", "SELinux Enforcing", "x86-64-v3", "aarch64",
    "container-selinux", "container_t", "container_file_t", ":Z",
    "rootless Podman", "native Quadlet", "Netavark", "Aardvark DNS",
    "cgroup v2", "crun", "seccomp", "digest-only", "Pull=never",
)
SCHEMA_TERMS = (
    '"evidence_class"', '"rocky-native"', '"const": "rocky"',
    '"container_policy_package"', '"process_mcs"',
    '"cross_boundary_access_denied"', '"avc_denial_observed"',
    '"persistent_labels"', '"privileged"', '"seccomp_enabled"',
    '"digest_only_images"', '"podman_socket_mounted"',
    '"docker_socket_mounted"', '"installed_nevras"',
)
VALIDATOR_TERMS = (
    'QUALIFIED_ROCKY_MINORS = frozenset({"10.2"})',
    "glibc-loader-hwcaps", "rocky-aarch64-native", "validate_selinux_facts",
)
FORBIDDEN_QUADLET_TERMS = (
    "label=disable", "Network=host", "Privileged=true", "AutoUpdate=registry",
)
FORBIDDEN_ACTIVE_CONTRACT = re.compile(
    r"const.*debian|debian_release_suites|trixie|debian-archive|"
    r"apparmor.*required|AppArmor enabled|unattended-upgrades",
    re.IGNORECASE,
)


def main(arguments: list[str]) -> int:
    if arguments or any(not path.is_file() for path in REQUIRED_FILES):
        print(json.dumps(["registered_validation"]))
        return 1
    try:
        document = REQUIRED_FILES[0].read_text(encoding="utf-8")
        schema = REQUIRED_FILES[1].read_text(encoding="utf-8")
        validator = REQUIRED_FILES[2].read_text(encoding="utf-8")
        json.loads(schema)
        ast.parse(validator)
        quadlet_paths = sorted(Path("config/production/quadlet").glob("*"))
        quadlets = "\n".join(
            path.read_text(encoding="utf-8")
            for path in quadlet_paths
            if path.is_file()
        )
    except (OSError, UnicodeError, ValueError):
        print(json.dumps(["registered_validation"]))
        return 1
    if (
        any(term not in document for term in DOCUMENT_TERMS)
        or any(term not in schema for term in SCHEMA_TERMS)
        or any(term not in validator for term in VALIDATOR_TERMS)
        or not quadlet_paths
        or any(term in quadlets for term in FORBIDDEN_QUADLET_TERMS)
        or FORBIDDEN_ACTIVE_CONTRACT.search(schema + "\n" + validator)
        or "docker_engine_version" in schema
    ):
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
