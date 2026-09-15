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
import subprocess
import sys
import tempfile


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
QUALIFICATION_TERMS = (
    'readonly QUALIFIED_ROCKY_MINOR="10.2"',
    "administrator_path_admitted", "effective_quadlet_service_admitted",
    "least_authority_process_admitted", "SELINUX_ISOLATION_INVARIANT_OWNER",
    "QUADLET_AUTHORITY_INVARIANT_OWNER",
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
        qualification = REQUIRED_FILES[3].read_text(encoding="utf-8")
        json.loads(schema)
        ast.parse(validator)
        quadlet_paths = sorted(Path("config/production/quadlet").glob("*"))
        quadlets = "\n".join(
            path.read_text(encoding="utf-8")
            for path in quadlet_paths
            if path.is_file()
        )
        quadlets_valid = bool(quadlet_paths) and all(
            path.is_file() and not path.is_symlink() and path.stat().st_size > 0
            for path in quadlet_paths
        )
        semantic_probe = """
import copy
import importlib.util
from pathlib import Path

path = Path('scripts/validate-production-contract.py')
spec = importlib.util.spec_from_file_location('registered_contract', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
inventory = {'host': {'hostname': 'secpal-host.example.invalid',
                      'architecture': 'amd64'}}
facts = {'hostname': 'secpal-host.example.invalid', 'architecture': 'amd64',
         'os': {'version_id': '10.2'},
         'cpu': {'admission_method': 'glibc-loader-hwcaps',
                 'x86_64_level': 'x86-64-v3'}}
module.validate_platform_facts(inventory, facts)
bad = copy.deepcopy(facts)
bad['os']['version_id'] = '10.1'
try:
    module.validate_platform_facts(inventory, bad)
except module.ContractViolation:
    pass
else:
    raise SystemExit(1)
selinux = {'workload': {'process_mcs': 's0:c1,c2',
                        'storage_mcs': 's0:c1,c2',
                        'cross_boundary_process_mcs': 's0:c3,c4'}}
module.validate_selinux_facts(selinux)
bad_selinux = copy.deepcopy(selinux)
bad_selinux['workload']['cross_boundary_process_mcs'] = 's0:c1,c2'
try:
    module.validate_selinux_facts(bad_selinux)
except module.ContractViolation:
    pass
else:
    raise SystemExit(1)
"""
        semantic = subprocess.run(
            [sys.executable, "-c", semantic_probe],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=30, check=False,
        )
        syntax = subprocess.run(
            ["bash", "-n", str(REQUIRED_FILES[3])],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        help_result = subprocess.run(
            ["bash", str(REQUIRED_FILES[3]), "--help"],
            stdin=subprocess.DEVNULL, capture_output=True,
            timeout=10, check=False,
        )
        with tempfile.TemporaryDirectory(
            prefix="secpal-registered-safety-"
        ) as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}\n", encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable, str(REQUIRED_FILES[2]),
                    "--inventory", str(invalid), "--host-facts", str(invalid),
                    "--synthetic",
                ],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30, check=False,
            )
    except (
        OSError, UnicodeError, ValueError, SyntaxError,
        subprocess.SubprocessError,
    ):
        print(json.dumps(["registered_validation"]))
        return 1
    if (
        any(term not in document for term in DOCUMENT_TERMS)
        or any(term not in schema for term in SCHEMA_TERMS)
        or any(term not in validator for term in VALIDATOR_TERMS)
        or any(term not in qualification for term in QUALIFICATION_TERMS)
        or not quadlets_valid
        or any(term in quadlets for term in FORBIDDEN_QUADLET_TERMS)
        or FORBIDDEN_ACTIVE_CONTRACT.search(schema + "\n" + validator)
        or "docker_engine_version" in schema
        or semantic.returncode != 0
        or syntax.returncode != 0
        or help_result.returncode != 0
        or not help_result.stdout.startswith(b"Usage:")
        or rejected.returncode == 0
    ):
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
