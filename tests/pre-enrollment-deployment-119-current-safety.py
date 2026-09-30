# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main current safety for deployment #119's exact parked workload tree."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


INVARIANTS = [
    "current_tree_exact", "historical_bytes_unavailable",
    "registered_validation", "source_history",
]
COLLECTOR = Path("scripts/ci-cloud/collect-workload-evidence.py")
ASSEMBLER = Path("scripts/ci-cloud/assemble-evidence.py")
VALIDATOR = Path("scripts/ci-cloud/validate-evidence.py")
SCHEMA = Path("schemas/ci-cloud-evidence.schema.json")
RUNTIME = Path("scripts/integration_runtime_contract.py")
TEST = Path("tests/ci-cloud-workload-evidence.py")
PODMAN_FIXTURE = Path("tests/fixtures/podman-5.4.2-rootless-userns.json")
WORKFLOW = Path(".github/workflows/cloud-conformance.yml")
RUNNER = Path("scripts/ci-cloud/run-remote-conformance.sh")
DOCUMENT = Path("docs/ci-cloud-conformance.md")
ROLES = (
    "secrets-init", "postgres", "migrate", "api", "worker-general",
    "worker-hash-chain", "scheduler", "frontend", "gateway",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("workload module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _rejects(collector, valid: dict, change, invariant: str) -> bool:
    changed = copy.deepcopy(valid)
    change(changed)
    return invariant in collector.workload_admission_failures(changed)


def _closed_scope_schema(schema: object) -> bool:
    if not isinstance(schema, dict):
        return False
    definitions = schema.get("$defs")
    workload = (
        definitions.get("workloadEvidence")
        if isinstance(definitions, dict) else None
    )
    if not isinstance(workload, dict):
        return False
    properties = workload.get("properties")
    required = workload.get("required")
    return (
        workload.get("additionalProperties") is False
        and isinstance(properties, dict)
        and isinstance(required, list)
        and {"claim_scope", "database_scope"} <= set(required)
        and properties.get("claim_scope")
        == {"const": "disposable-rootless-application-integration"}
        and properties.get("database_scope")
        == {"const": "disposable-postgresql-18-fixture"}
    )


def _semantic_safety() -> bool:
    collector = _load(COLLECTOR, "accepted_deployment_119_collector")
    runtime = _load(RUNTIME, "accepted_deployment_119_runtime")
    fixture = _load(TEST, "accepted_deployment_119_fixture")
    valid = fixture.valid_observations()
    if (
        tuple(collector.ROLES) != ROLES
        or tuple(collector.ROLE_CONTRACTS) != ROLES
        or collector.CI_UID != 20000
        or collector.API_DIGEST != runtime.API_DIGEST
        or collector.FRONTEND_DIGEST != runtime.FRONTEND_DIGEST
        or collector.POSTGRES_DIGEST != runtime.POSTGRES_FIXTURE.image.rsplit("@", 1)[1]
        or runtime.POSTGRES_FIXTURE.major != 18
        or not runtime.POSTGRES_FIXTURE.image.startswith(
            "docker.io/library/postgres@sha256:"
        )
        or valid["claim_scope"] != "disposable-rootless-application-integration"
        or valid["database_scope"] != "disposable-postgresql-18-fixture"
        or valid["target_sha"] != "a" * 40
        or valid["result"] != "passed"
        or collector.workload_admission_failures(valid)
        or len(valid["live"]["containers"]) != len(ROLES)
        or [item["role"] for item in valid["live"]["containers"]] != list(ROLES)
        or valid["post_cleanup"]["containers"] != []
    ):
        return False
    migration = collector.ROLE_CONTRACTS["migrate"]
    secrets_init = collector.ROLE_CONTRACTS["secrets-init"]
    if (
        migration.entrypoint != (
            "/bin/bash", "/run/secpal/container-entrypoint.sh"
        )
        or migration.command != ("php", "artisan", "migrate", "--force")
        or secrets_init.entrypoint != (
            "/bin/bash", "/run/secpal/init-local-secrets.sh"
        )
        or secrets_init.command != ()
    ):
        return False
    checks = (
        (lambda item: item["live"].__setitem__("target_sha", "b" * 40),
         "WORKLOAD_TARGET_BINDING"),
        (lambda item: item["live"]["containers"][3].__setitem__("rootless", False),
         "WORKLOAD_ROOTLESS"),
        (lambda item: item["live"]["containers"][3].__setitem__("network_mode", "host"),
         "WORKLOAD_HOST_NETWORK"),
        (lambda item: item["live"].__setitem__("podman_api", True),
         "WORKLOAD_PODMAN_API_DISABLED"),
        (lambda item: item["live"]["containers"][3].__setitem__(
            "effective_process_label", ""
        ), "WORKLOAD_SELINUX_ISOLATION"),
        (lambda item: item["live"]["containers"][3].__setitem__(
            "effective_seccomp_mode", 0
        ), "WORKLOAD_SECCOMP_ISOLATION"),
        (lambda item: item["live"]["containers"][3].__setitem__(
            "image", "localhost/secpal-ci-api:latest"
        ), "WORKLOAD_IMAGE_PROVENANCE"),
        (lambda item: item["live"]["containers"][3].__setitem__("role", "valkey"),
         "WORKLOAD_CONTAINER_SET"),
        (lambda item: item["live"]["containers"].append(
            copy.deepcopy(item["live"]["containers"][4])
        ), "WORKLOAD_CONTAINER_SET"),
        (lambda item: item["live"]["containers"].__delitem__(6),
         "WORKLOAD_SINGLETON_ROLES"),
        (lambda item: item["post_cleanup"].__setitem__(
            "migration_invocation_count", 2
        ), "WORKLOAD_MIGRATION"),
        (lambda item: item["live"]["containers"][3].__setitem__(
            "remote_api_environment", True
        ), "WORKLOAD_PODMAN_API_DISABLED"),
        (lambda item: item["live"]["containers"][3].__setitem__(
            "auto_update", "registry"
        ), "WORKLOAD_AUTO_UPDATE_DISABLED"),
        (lambda item: item["live"]["containers"][3]["mounts"].append({
            "source": "/run/podman/podman.sock",
            "destination": "/run/podman/podman.sock",
            "options": ["rw"],
        }), "WORKLOAD_PODMAN_API_DISABLED"),
        (lambda item: item["live"]["containers"][3]["published_ports"].append({
            "host_ip": "0.0.0.0", "host_port": 8080,
            "container_port": 8080, "protocol": "tcp",
        }), "WORKLOAD_PUBLISHED_PORTS"),
        (lambda item: item["post_cleanup"]["containers"].append(
            copy.deepcopy(item["live"]["containers"][3])
        ), "WORKLOAD_CLEANUP_ABSENCE"),
    )
    if any(not _rejects(collector, valid, change, invariant)
           for change, invariant in checks):
        return False
    gateway = next(item for item in valid["live"]["containers"]
                   if item["role"] == "gateway")
    installed = next(item["image"] for item in valid["live"]["installed_units"]
                     if item["name"].endswith("-gateway.container"))
    if (
        not collector.expected_image_identity(valid["instance"], "gateway", gateway, installed)
        or collector.expected_image_identity(
            valid["instance"], "gateway", gateway,
            installed.replace(gateway["image_digest"], "sha256:" + "f" * 64),
        )
    ):
        return False
    result = subprocess.run(
        [sys.executable, "-m", "unittest", TEST.as_posix()],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=90, check=False,
    )
    match = re.search(rb"Ran ([1-9][0-9]*) tests? in ", result.stderr)
    return (result.returncode == 0 and match is not None
            and int(match.group(1)) >= 100)


def _static_safety() -> bool:
    required = (COLLECTOR, ASSEMBLER, VALIDATOR, SCHEMA, RUNTIME,
                TEST, PODMAN_FIXTURE, WORKFLOW, RUNNER, DOCUMENT)
    if any(not path.is_file() or path.is_symlink() for path in required):
        return False
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    document = DOCUMENT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    collector = COLLECTOR.read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    if (
        not _closed_scope_schema(schema)
        or "Rocky Linux 10.2" not in document
        or "SELinux" not in document
        or "Quadlet" not in document
        or "PostgreSQL 18" not in document
        or "disposable" not in document
        or "It does not prove native production PostgreSQL" not in document
        or "workload evidence is Rocky Linux 10.2+" not in document
        or "It cannot pass on the" not in document
        or "obsolete Debian/AppArmor execution path" not in document
        or "target_sha" not in collector
        or "WORKLOAD_CLEANUP_ABSENCE" not in collector
        or "WORKLOAD_SELINUX_ISOLATION" not in collector
        or "WORKLOAD_IMAGE_PROVENANCE" not in collector
        or "WORKLOAD_PODMAN_API_DISABLED" not in collector
        or "WORKLOAD_TARGET_BINDING" not in collector
        or "disposable-postgresql-18-fixture" not in validator
        or any(term not in runner for term in (
            '[[ "$actual_sha" == "$target_sha" ]]',
            "run_target_prepare_start",
            "collect_workload_live",
            "run_target_cleanup",
            "collect_workload_post_cleanup",
            "post-cleanup",
        ))
        or not re.search(
            r'if \[\[ "\$SECPAL_DEBIAN_CONFORMANCE_RETIRED" == true \]\]; then'
            r'[\s\S]*?exit 1\s*fi', workflow,
        )
        or workflow.index("SECPAL_DEBIAN_CONFORMANCE_RETIRED")
        > workflow.index("debian-13-x64")
    ):
        return False
    return True


def main(arguments: list[str]) -> int:
    try:
        safe = not arguments and _static_safety() and _semantic_safety()
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            ImportError, SyntaxError, subprocess.SubprocessError):
        safe = False
    print(json.dumps(INVARIANTS if safe else ["registered_validation"]))
    return 0 if safe else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
