# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source-neutral execution of exact accepted-main safety harnesses."""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from . import bootstrap_source_admission as transport
from . import lifecycle_authority as authority


_EVIDENCE_VERSION = re.compile(
    r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})", re.ASCII,
)
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", re.ASCII)
_REGISTERED_VALIDATION_PROVENANCE = "ACCEPTED_RECOVERY_RECORD_EXACT_SOURCE"
_COLLISION_MAX_OBJECTS = 4096
_COLLISION_MAX_OBJECT_BYTES = 1024 * 1024
_COLLISION_MAX_COMMIT_BYTES = 64 * 1024
_COLLISION_MAX_AGGREGATE_BYTES = 16 * 1024 * 1024
_COLLISION_MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
_COLLISION_MAX_HISTORICAL_BYTES = 3 * 1024 * 1024
_COLLISION_MAX_TREE_DEPTH = 64
_COLLISION_MAX_GIT_STATE_FILES = _COLLISION_MAX_OBJECTS + 128
_COLLISION_MAX_GIT_STATE_BYTES = _COLLISION_MAX_AGGREGATE_BYTES * 2
_COLLISION_CURRENT_IDENTITY_FIXTURES = {
    "tests/secpal-pr-review-actions-unit.py": (
        {
            "test_parent2_preservation_cannot_delete_parent1_only_work": 1,
            "test_parent2_preservation_uses_exact_new_attestation_versions": 1,
            "test_ready_integration_accepts_authenticated_current_ready_histories": 1,
            "test_ready_integration_authenticates_exact_parent2_preservation": 2,
            "test_ready_integration_mixes_conflict_and_parent2_preservation": 2,
            "test_ready_integration_v12_delta_uses_registered_item_limit_before_git_work": 2,
        },
    ),
    "tests/secpal-resolve-fixed-threads-unit.py": (
        {
            "test_eligibility_bound_ready_integration_authorizes_exact_thread": 1,
        },
    ),
}

_TWO_PROVENANCE_LAUNCHER = r"""
import importlib.util
import os
from pathlib import Path
import sys

tooling_root = Path(sys.argv[1]).resolve(strict=True)
candidate_root = Path(sys.argv[2]).resolve(strict=True)
candidate_repository = sys.argv[3]
target = sys.argv[4]
entrypoint = sys.argv[5]
if (
    tooling_root == candidate_root
    or tooling_root in candidate_root.parents
    or candidate_root in tooling_root.parents
):
    raise RuntimeError("current-safety tooling and candidate roots are not separated")
expected = (tooling_root / target).resolve(strict=True)
if tooling_root not in expected.parents or not expected.is_file():
    raise RuntimeError("current-safety harness escaped accepted tooling")
stdlib = [value for value in sys.path if value and "site-packages" not in value]
sys.path[:] = [str(tooling_root / "scripts"), *stdlib]
os.environ["SECPAL_CURRENT_SAFETY_TOOLING_ROOT"] = str(tooling_root)
os.environ["SECPAL_CURRENT_SAFETY_CANDIDATE_ROOT"] = str(candidate_root)
os.environ["SECPAL_CURRENT_SAFETY_CANDIDATE_REPOSITORY"] = candidate_repository
sys.argv = [target]
spec = importlib.util.spec_from_file_location(
    "secpal_current_safety_accepted_harness", expected
)
if spec is None or spec.loader is None:
    raise RuntimeError("current-safety harness is unavailable")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
selected = getattr(module, entrypoint, None)
if not callable(selected):
    raise RuntimeError("current-safety harness entrypoint changed")
raise SystemExit(selected([]))
"""


@dataclass(frozen=True)
class CurrentSafetyExecutionRoots:
    """Distinct authenticated roots for tooling authority and candidate source."""

    tooling: Path
    candidate: Path


def _compatible_evidence_versions(
    occupied_version: str,
    implementation_identity: str,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Admit a derived compatible successor without accepting caller policy."""

    if (
        not isinstance(occupied_version, str)
        or not isinstance(implementation_identity, str)
        or _EVIDENCE_VERSION.fullmatch(occupied_version) is None
        or _EVIDENCE_VERSION.fullmatch(implementation_identity) is None
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation identity is not canonical"
        )
    occupied = tuple(int(part) for part in occupied_version.split("."))
    implementation = tuple(
        int(part) for part in implementation_identity.split(".")
    )
    if occupied[0] != implementation[0] or implementation[1] <= occupied[1]:
        raise authority.LifecycleAuthorityError(
            "collision validation identity is not a later compatible version"
        )
    return occupied, implementation


def _python_byte_offsets(source: bytes, node: ast.AST) -> tuple[int, int]:
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    try:
        return (
            starts[node.lineno - 1] + node.col_offset,
            starts[node.end_lineno - 1] + node.end_col_offset,
        )
    except (AttributeError, IndexError) as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation fixture location is malformed"
        ) from exc


def _literal_is_current_identity(
    node: ast.Constant,
    parents: Mapping[int, ast.AST],
) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.keyword) and parent.arg == "schema_version":
        return True
    if isinstance(parent, ast.Assign) and parent.value is node:
        return any(
            isinstance(target, ast.Subscript)
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "schema_version"
            for target in parent.targets
        )
    descendant: ast.AST = node
    while (ancestor := parents.get(id(descendant))) is not None:
        if isinstance(ancestor, ast.For):
            return (
                isinstance(ancestor.target, ast.Name)
                and ancestor.target.id == "schema_version"
                and any(item is node for item in ast.walk(ancestor.iter))
            )
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            break
        descendant = ancestor
    return False


def _project_collision_current_identity_fixtures(
    relative: str,
    source: bytes,
    *,
    occupied_version: str,
    implementation_identity: str,
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    """Project only the closed current-implementation fixture inventory."""

    _compatible_evidence_versions(occupied_version, implementation_identity)
    expected_profiles = _COLLISION_CURRENT_IDENTITY_FIXTURES.get(relative)
    if expected_profiles is None or not isinstance(source, bytes):
        raise authority.LifecycleAuthorityError(
            "collision validation fixture path is not maintained"
        )
    try:
        module = ast.parse(source.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation fixture source is malformed"
        ) from exc
    all_functions = {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    parents = {
        id(child): node
        for node in ast.walk(module)
        for child in ast.iter_child_nodes(node)
    }
    matching_profiles = [
        profile
        for profile in expected_profiles
        if set(profile) <= set(all_functions)
        and all(
            sum(
                isinstance(node, ast.Constant)
                and node.value == occupied_version
                and _literal_is_current_identity(node, parents)
                for node in ast.walk(all_functions[name])
            ) == count
            for name, count in profile.items()
        )
    ]
    if len(matching_profiles) != 1:
        raise authority.LifecycleAuthorityError(
            "collision validation current-identity fixture inventory drifted"
        )
    expected = matching_profiles[0]
    functions = {name: all_functions[name] for name in expected}
    replacements: list[tuple[int, int]] = []
    old_literal = occupied_version.encode("ascii")
    new_literal = implementation_identity.encode("ascii")
    for name, count in expected.items():
        identities = [
            node
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Constant)
            and node.value == occupied_version
            and _literal_is_current_identity(node, parents)
        ]
        if len(identities) != count:
            raise authority.LifecycleAuthorityError(
                "collision validation current-identity fixture inventory drifted"
            )
        for identity in identities:
            start, end = _python_byte_offsets(source, identity)
            literal = source[start:end]
            if literal not in {
                b'"' + old_literal + b'"',
                b"'" + old_literal + b"'",
            }:
                raise authority.LifecycleAuthorityError(
                    "collision validation identity literal is not canonical"
                )
            replacements.append((start + 1, end - 1))
    if len(replacements) != len(set(replacements)):
        raise authority.LifecycleAuthorityError(
            "collision validation fixture ownership is ambiguous"
        )
    replacements.sort()
    projected = source
    for start, end in reversed(replacements):
        projected = projected[:start] + new_literal + projected[end:]
    return projected, tuple(replacements)


def _project_collision_validation_authority(
    source: bytes,
    *,
    occupied_version: str,
    implementation_identity: str,
) -> bytes:
    """Extend a maintained historical runner guard when that epoch owns one."""

    occupied, _ = _compatible_evidence_versions(
        occupied_version, implementation_identity,
    )
    try:
        module = ast.parse(source.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation authority source is malformed"
        ) from exc
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_verify_integration_tree_delta"
    ]
    if len(functions) != 1:
        raise authority.LifecycleAuthorityError(
            "collision validation authority owner drifted"
        )
    comparisons = [
        node
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotIn)
        and isinstance(node.left, ast.Name)
        and node.left.id == "schema_version"
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Set)
    ]
    if not comparisons:
        return source
    if len(comparisons) != 1:
        raise authority.LifecycleAuthorityError(
            "collision validation authority guard drifted"
        )
    version_set = comparisons[0].comparators[0]
    observed = [
        item.value
        for item in version_set.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    ]
    expected = [f"{occupied[0]}.{minor}" for minor in range(1, occupied[1] + 1)]
    if observed != expected or len(observed) != len(version_set.elts):
        raise authority.LifecycleAuthorityError(
            "collision validation authority version inventory drifted"
        )
    _start, end = _python_byte_offsets(source, version_set)
    if source[end - 1:end] != b"}":
        raise authority.LifecycleAuthorityError(
            "collision validation authority guard is not canonical"
        )
    insertion = b', "' + implementation_identity.encode("ascii") + b'"'
    return source[:end - 1] + insertion + source[end - 1:]


@dataclass(frozen=True)
class HarnessBlobObservation:
    commit_oid: str
    requested_path: str
    tree_entry: bytes


@dataclass(frozen=True)
class HarnessBlobFacts:
    repository_path: str
    mode: str
    object_type: str
    object_oid: str
    size: int | None


@dataclass(frozen=True)
class HarnessBlobBinding:
    commit_oid: str
    repository_path: str
    mode: str
    blob_oid: str
    size: int


def admit_harness_path(relative: str, *, allowed_paths: frozenset[str]) -> str:
    """Admit one literal, profile-owned test harness path."""

    if not isinstance(relative, str):
        raise authority.LifecycleAuthorityError("current safety harness path is unsafe")
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise authority.LifecycleAuthorityError("current safety harness path is unsafe")
    if relative not in allowed_paths or not relative.startswith("tests/"):
        raise authority.LifecycleAuthorityError("current safety harness path is not maintained")
    return relative


def admit_tooling_path(relative: str, *, allowed_paths: frozenset[str]) -> str:
    """Admit one literal profile-owned governance implementation path."""

    if not isinstance(relative, str):
        raise authority.LifecycleAuthorityError("current safety tooling path is unsafe")
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != relative
        or relative not in allowed_paths
        or not (
            relative == "scripts/secpal-pr-review.py"
            or relative == "scripts/secpal-pr-review-actions.py"
            or relative.startswith("scripts/secpal_pr_review/")
        )
    ):
        raise authority.LifecycleAuthorityError(
            "current safety tooling path is not maintained"
        )
    return relative


def _observe_harness_blob(
    repository_root: Path, commit_oid: str, relative: str,
) -> HarnessBlobObservation:
    record = transport._git(
        repository_root,
        ["ls-tree", "-lz", "--full-tree", commit_oid, "--", f":(literal){relative}"],
    ).stdout
    return HarnessBlobObservation(commit_oid, relative, bytes(record))


def _normalize_harness_blob(observation: HarnessBlobObservation) -> HarnessBlobFacts:
    record = observation.tree_entry
    if not record.endswith(b"\0") or record.count(b"\0") != 1:
        raise authority.LifecycleAuthorityError("current safety harness file is unavailable")
    try:
        metadata, separator, observed_path = record[:-1].decode("utf-8", "strict").partition("\t")
    except UnicodeDecodeError as exc:
        raise authority.LifecycleAuthorityError("current safety harness listing is malformed") from exc
    fields = metadata.split()
    if separator != "\t" or len(fields) != 4:
        raise authority.LifecycleAuthorityError("current safety harness listing is malformed")
    try:
        blob_oid = authority._require_oid(fields[2], "current safety harness blob")
    except authority.LifecycleAuthorityError as exc:
        raise authority.LifecycleAuthorityError("current safety harness blob is invalid") from exc
    if fields[3] != "-" and not fields[3].isdecimal():
        raise authority.LifecycleAuthorityError("current safety harness size is invalid")
    return HarnessBlobFacts(
        observed_path, fields[0], fields[1], blob_oid,
        None if fields[3] == "-" else int(fields[3]),
    )


def _admit_harness_blob(
    observation: HarnessBlobObservation,
    facts: HarnessBlobFacts,
    *,
    allowed_paths: frozenset[str],
) -> HarnessBlobBinding:
    commit_oid = authority._require_oid(observation.commit_oid, "current safety harness commit")
    requested = admit_harness_path(observation.requested_path, allowed_paths=allowed_paths)
    if (
        facts.repository_path != requested
        or facts.mode not in {"100644", "100755"}
        or facts.object_type != "blob"
    ):
        raise authority.LifecycleAuthorityError("current safety harness mode is invalid")
    if facts.size is None:
        raise authority.LifecycleAuthorityError("current safety harness size is invalid")
    return HarnessBlobBinding(
        commit_oid, requested, facts.mode, facts.object_oid, facts.size,
    )


def harness_blob(
    repository_root: Path,
    accepted_main: str,
    relative: str,
    *,
    allowed_paths: frozenset[str],
) -> tuple[str, str, int]:
    relative = admit_harness_path(relative, allowed_paths=allowed_paths)
    observation = _observe_harness_blob(repository_root, accepted_main, relative)
    facts = _normalize_harness_blob(observation)
    binding = _admit_harness_blob(observation, facts, allowed_paths=allowed_paths)
    return binding.mode, binding.blob_oid, binding.size


def tooling_blob(
    repository_root: Path,
    accepted_main: str,
    relative: str,
    *,
    allowed_paths: frozenset[str],
) -> tuple[str, str, int]:
    """Bind one regular governance implementation blob from accepted main."""

    relative = admit_tooling_path(relative, allowed_paths=allowed_paths)
    observation = _observe_harness_blob(repository_root, accepted_main, relative)
    facts = _normalize_harness_blob(observation)
    if (
        facts.repository_path != relative
        or facts.mode not in {"100644", "100755"}
        or facts.object_type != "blob"
        or facts.size is None
    ):
        raise authority.LifecycleAuthorityError(
            "current safety tooling blob is invalid"
        )
    return facts.mode, facts.object_oid, facts.size


def build_profile(
    repository_root: Path,
    accepted_main: str,
    *,
    policy: str,
    harness_paths: Sequence[str],
    purpose: str,
    required_invariants: Sequence[str],
    tooling_paths: Sequence[str] = (),
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Bind one closed profile to exact accepted-main harness blobs and commands."""

    allowed = frozenset(harness_paths)
    invariants = list(required_invariants)
    if not allowed or len(allowed) != len(harness_paths):
        raise authority.LifecycleAuthorityError("current safety harness paths are ambiguous")
    if (
        not invariants or invariants != sorted(set(invariants))
        or any(not isinstance(item, str) or not item for item in invariants)
    ):
        raise authority.LifecycleAuthorityError("current safety invariant inventory is malformed")
    if transport._git(repository_root, ["cat-file", "-t", accepted_main]).stdout != b"commit\n":
        raise authority.LifecycleAuthorityError("current safety harness commit is invalid")
    harness = []
    commands = []
    for relative in harness_paths:
        path = admit_harness_path(relative, allowed_paths=allowed)
        mode, blob_oid, size = harness_blob(
            repository_root, accepted_main, path, allowed_paths=allowed,
        )
        harness.append({"path": path, "mode": mode, "blob_oid": blob_oid, "size": size})
        commands.append({"argv": ["python3", path], "working_directory": ".", "purpose": purpose})
    results = [
        {"command_digest": authority.digest_json(command), "exit_status": 0, "successful": True}
        for command in commands
    ]
    profile = {
        "schema_version": "1.0",
        "policy": policy,
        "harness": harness,
        "validation_command_set": commands,
        "validation_command_set_digest": authority.digest_json(commands),
        "timeout_seconds": timeout_seconds,
        "required_invariants": invariants,
        "validation_results": results,
    }
    if tooling_paths:
        tooling_allowed = frozenset(tooling_paths)
        if len(tooling_allowed) != len(tooling_paths):
            raise authority.LifecycleAuthorityError(
                "current safety tooling paths are ambiguous"
            )
        tooling = []
        for relative in tooling_paths:
            path = admit_tooling_path(relative, allowed_paths=tooling_allowed)
            mode, blob_oid, size = tooling_blob(
                repository_root,
                accepted_main,
                path,
                allowed_paths=tooling_allowed,
            )
            tooling.append(
                {"path": path, "mode": mode, "blob_oid": blob_oid, "size": size}
            )
        profile.update(
            execution_model="ACCEPTED_MAIN_TOOLING_WITH_EXACT_CANDIDATE",
            tooling=tooling,
        )
    return profile


def verify_source_bytes(
    source_root: Path,
    tree: str,
    *,
    hash_repository_root: Path | None = None,
    expected_listing: str | None = None,
) -> str:
    """Authenticate regular checked-out bytes against one exact Git tree."""

    listing = (
        transport._git_text(source_root, ["ls-tree", "-rz", "--full-tree", tree])
        if expected_listing is None else expected_listing
    )
    hash_root = hash_repository_root or source_root
    for entry in listing.rstrip("\0").split("\0"):
        metadata, separator, name = entry.partition("\t")
        fields = metadata.split()
        path = source_root / name
        if (
            not separator or len(fields) != 3 or fields[1] != "blob"
            or fields[0] not in {"100644", "100755"} or not name
            or Path(name).is_absolute() or ".." in Path(name).parts
        ):
            raise authority.LifecycleAuthorityError("exact source requires regular immutable bytes")
        for parent in (path, *path.parents):
            if parent == source_root:
                break
            if parent.is_symlink():
                raise authority.LifecycleAuthorityError("exact source bytes contain a symlink")
        try:
            mode = path.stat().st_mode
            matches = (
                stat.S_ISREG(mode)
                and bool(mode & stat.S_IXUSR) == (fields[0] == "100755")
                and transport._git_text(
                    hash_root, ["hash-object", "--no-filters", "--", str(path)]
                ).strip() == fields[2]
            )
        except OSError as exc:
            raise authority.LifecycleAuthorityError("exact source bytes are unavailable") from exc
        if not matches:
            raise authority.LifecycleAuthorityError("validation mutated immutable source bytes")
    return listing


def _verify_harness_file(
    repository_root: Path,
    execution_root: Path,
    relative: str,
    mode: str,
    blob_oid: str,
    size: int,
) -> None:
    destination = execution_root / relative
    for parent in destination.parents:
        if parent == execution_root:
            break
        if parent.is_symlink():
            raise authority.LifecycleAuthorityError("current safety harness path is unsafe")
    try:
        metadata = destination.lstat()
    except OSError as exc:
        raise authority.LifecycleAuthorityError("current safety harness file is unavailable") from exc
    permissions = 0o755 if mode == "100755" else 0o644
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != size
        or stat.S_IMODE(metadata.st_mode) != permissions
    ):
        raise authority.LifecycleAuthorityError("current safety harness mode or size changed")
    actual = transport._git_text(
        repository_root, ["hash-object", "--no-filters", "--", str(destination)],
    ).strip()
    if actual != blob_oid:
        raise authority.LifecycleAuthorityError("current safety harness bytes are not accepted main")


def _create_harness_parent(execution_root: Path, relative: Path) -> Path:
    parent = execution_root
    for part in relative.parent.parts:
        parent /= part
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            parent.mkdir(mode=0o755)
            metadata = parent.lstat()
        except OSError as exc:
            raise authority.LifecycleAuthorityError("current safety harness path is unavailable") from exc
        if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
            raise authority.LifecycleAuthorityError("current safety harness path is unsafe")
    return parent


def _copy_harness_file(
    repository_root: Path,
    accepted_main: str,
    binding: Mapping[str, Any],
    execution_root: Path,
    *,
    allowed_paths: frozenset[str],
    tooling: bool = False,
) -> tuple[str, str, int]:
    admit = admit_tooling_path if tooling else admit_harness_path
    observe = tooling_blob if tooling else harness_blob
    relative = admit(binding.get("path"), allowed_paths=allowed_paths)
    observed = observe(
        repository_root, accepted_main, relative, allowed_paths=allowed_paths,
    )
    expected = (binding.get("mode"), binding.get("blob_oid"), binding.get("size"))
    if observed != expected:
        raise authority.LifecycleAuthorityError("current safety harness binding changed")
    mode, blob_oid, size = observed
    destination = execution_root / relative
    parent = _create_harness_parent(execution_root, Path(relative))
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            executable = transport._resolve_bootstrap_executable("git")
            arguments = ["-C", str(repository_root), "cat-file", "blob", blob_oid]
            try:
                result = subprocess.run(
                    [executable, *arguments],
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                    env=transport._bootstrap_command_environment("git", repository_root),
                    timeout=transport._BOOTSTRAP_COMMAND_TIMEOUT_SECONDS, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise authority.LifecycleAuthorityError(
                    "current safety harness blob is unavailable"
                ) from exc
            if result.returncode != 0:
                raise authority.LifecycleAuthorityError("current safety harness blob is unavailable")
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755 if mode == "100755" else 0o644)
        if temporary.stat().st_size != size:
            raise authority.LifecycleAuthorityError("current safety harness blob size changed")
        actual = transport._git_text(
            repository_root, ["hash-object", "--no-filters", "--", str(temporary)],
        ).strip()
        if actual != blob_oid:
            raise authority.LifecycleAuthorityError("current safety harness blob bytes changed")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    _verify_harness_file(repository_root, execution_root, relative, mode, blob_oid, size)
    return mode, blob_oid, size


def _copy_tooling_file(
    repository_root: Path,
    accepted_main: str,
    binding: Mapping[str, Any],
    execution_root: Path,
    *,
    allowed_paths: frozenset[str],
) -> tuple[str, str, int]:
    return _copy_harness_file(
        repository_root,
        accepted_main,
        binding,
        execution_root,
        allowed_paths=allowed_paths,
        tooling=True,
    )


def _git_blob_oid(source: bytes) -> str:
    header = b"blob " + str(len(source)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + source).hexdigest()


def _collision_listing(listing: str) -> tuple[tuple[str, str, str], ...]:
    entries = []
    for raw in listing.rstrip("\0").split("\0"):
        metadata, separator, relative = raw.partition("\t")
        fields = metadata.split()
        path = Path(relative)
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or not relative
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != relative
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation source listing is malformed"
            )
        entries.append((fields[0], fields[2], relative))
    if not entries or len({item[2] for item in entries}) != len(entries):
        raise authority.LifecycleAuthorityError(
            "collision validation source listing is ambiguous"
        )
    return tuple(entries)


def _collision_projection_bytes(
    relative: str,
    source: bytes,
    *,
    occupied_version: str,
    implementation_identity: str,
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    if relative == "scripts/secpal-pr-review-actions.py":
        return (
            _project_collision_validation_authority(
                source,
                occupied_version=occupied_version,
                implementation_identity=implementation_identity,
            ),
            (),
        )
    if relative in _COLLISION_CURRENT_IDENTITY_FIXTURES:
        return _project_collision_current_identity_fixtures(
            relative,
            source,
            occupied_version=occupied_version,
            implementation_identity=implementation_identity,
        )
    return source, ()


def _materialize_collision_blob(
    root: Path,
    relative: str,
    mode: str,
    source: bytes,
) -> None:
    destination = root / relative
    parent = root
    for part in Path(relative).parent.parts:
        parent /= part
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            parent.mkdir(mode=0o755)
            metadata = parent.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
            raise authority.LifecycleAuthorityError(
                "collision validation harness path is unsafe"
            )
    try:
        destination.write_bytes(source)
        destination.chmod(0o755 if mode == "100755" else 0o644)
    except OSError as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation harness materialization failed"
        ) from exc


def _read_collision_blob(
    root: Path,
    oid: str,
    size: int,
    *,
    kind: str = "blob",
) -> bytes:
    """Stream and rehash one bounded object without output truncation."""

    limit = (
        _COLLISION_MAX_COMMIT_BYTES
        if kind == "commit"
        else _COLLISION_MAX_OBJECT_BYTES
    )
    if (
        not isinstance(oid, str)
        or _GIT_OID.fullmatch(oid) is None
        or kind not in {"blob", "tree", "commit"}
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 <= size <= limit
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation accepted harness binding is malformed"
        )
    executable = transport._resolve_bootstrap_executable("git")
    arguments = ["-C", str(root), "cat-file", kind, oid]
    try:
        with tempfile.TemporaryFile() as output:
            completed = subprocess.run(
                [executable, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=transport._bootstrap_command_environment("git", root),
                timeout=transport._BOOTSTRAP_COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
            output.seek(0)
            source = output.read(size + 1)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation object bytes are unavailable"
        ) from exc
    header = kind.encode("ascii") + b" " + str(len(source)).encode("ascii") + b"\0"
    digest = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
    if (
        completed.returncode != 0
        or len(source) != size
        or digest(header + source).hexdigest() != oid
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation object content-addressed identity changed"
        )
    return source


@contextmanager
def _collision_validation_dependencies(
    root: Path,
) -> Iterator[dict[str, tuple[str, str]]]:
    """Materialize the authenticated lockfile dependency graph outside Git."""

    helper = authority._load_trusted_command_helper()
    try:
        npm = transport._trusted_dependency_executable(helper, "npm")
        node = transport._trusted_dependency_executable(helper, "node")
    except transport.BootstrapSourceAdmissionError as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation dependency executable is unavailable"
        ) from exc
    with tempfile.TemporaryDirectory(
        prefix="secpal-collision-validation-dependencies-"
    ) as directory:
        private = Path(directory)
        private.chmod(0o700)
        acquisition = private / "acquisition"
        home = private / "home"
        cache = private / "cache"
        for path in (acquisition, home, cache):
            path.mkdir(mode=0o700)
        user_config = home / "user.npmrc"
        global_config = home / "global.npmrc"
        for path in (user_config, global_config):
            path.write_text("", encoding="utf-8")
            path.chmod(0o600)
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(root / name, acquisition / name)
        environment = transport._closed_validation_environment(helper, home)
        environment.update({
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_CACHE": str(cache),
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "NPM_CONFIG_GLOBALCONFIG": str(global_config),
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
            "NPM_CONFIG_REPLACE_REGISTRY_HOST": "never",
            "NPM_CONFIG_STRICT_SSL": "true",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "NPM_CONFIG_USERCONFIG": str(user_config),
        })
        arguments = ["ci", "--ignore-scripts", "--no-audit", "--no-fund"]
        try:
            completed = subprocess.run(
                [npm, *arguments],
                cwd=acquisition,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise authority.LifecycleAuthorityError(
                "collision validation dependency acquisition failed"
            ) from exc
        modules = acquisition / "node_modules"
        cli = modules / "markdownlint-cli/markdownlint.js"
        if completed.returncode != 0 or not cli.is_file() or cli.is_symlink():
            raise authority.LifecycleAuthorityError(
                "collision validation dependency acquisition failed"
            )
        shutil.rmtree(modules / ".bin", ignore_errors=True)
        try:
            snapshot = transport._dependency_file_snapshot(modules)
        except transport.BootstrapSourceAdmissionError as exc:
            raise authority.LifecycleAuthorityError(
                "collision validation dependency materialization is unsafe"
            ) from exc
        runtime_modules = root / "node_modules"
        shutil.copytree(modules, runtime_modules)
        runtime: dict[str, tuple[str, str]] = {}
        for path in sorted(runtime_modules.rglob("*")):
            if path.is_dir():
                path.chmod(0o755)
                continue
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            path.chmod(0o755 if mode == "100755" else 0o644)
            runtime[path.relative_to(root).as_posix()] = (
                mode,
                _git_blob_oid(path.read_bytes()),
            )
        executable = runtime_modules / ".bin/markdownlint"
        executable.parent.mkdir(parents=True, mode=0o755)
        wrapper = (
            "#!/bin/sh\nexec "
            + repr(node)
            + " "
            + repr(str(runtime_modules / "markdownlint-cli/markdownlint.js"))
            + ' "$@"\n'
        ).encode("utf-8")
        executable.write_bytes(wrapper)
        executable.chmod(0o755)
        runtime["node_modules/.bin/markdownlint"] = (
            "100755",
            _git_blob_oid(wrapper),
        )
        try:
            yield runtime
        finally:
            try:
                if transport._dependency_file_snapshot(modules) != snapshot:
                    raise authority.LifecycleAuthorityError(
                        "collision validation dependency bytes changed"
                    )
            except transport.BootstrapSourceAdmissionError as exc:
                raise authority.LifecycleAuthorityError(
                    "collision validation dependency bytes changed"
                ) from exc


def _collision_object_bytes(
    root: Path,
    oid: str,
    kind: str,
    verified: dict[str, tuple[str, bytes]],
) -> bytes:
    """Read and rehash one bounded object from the private object database."""

    if _GIT_OID.fullmatch(oid) is None or kind not in {"blob", "tree", "commit"}:
        raise authority.LifecycleAuthorityError(
            "collision object identity is malformed"
        )
    existing = verified.get(oid)
    if existing is not None:
        if existing[0] != kind:
            raise authority.LifecycleAuthorityError(
                "collision object identity changed type"
            )
        return existing[1]
    if len(verified) >= _COLLISION_MAX_OBJECTS:
        raise authority.LifecycleAuthorityError(
            "collision object closure exceeds the object bound"
        )
    size_source = transport._git(root, ["cat-file", "-s", oid]).stdout
    limit = (
        _COLLISION_MAX_COMMIT_BYTES
        if kind == "commit"
        else _COLLISION_MAX_OBJECT_BYTES
    )
    if (
        re.fullmatch(rb"[0-9]+\n", size_source) is None
        or not 0 <= int(size_source) <= limit
    ):
        raise authority.LifecycleAuthorityError(
            "collision object exceeds the size bound"
        )
    raw = _read_collision_blob(root, oid, int(size_source), kind=kind)
    if sum(len(item[1]) for item in verified.values()) + len(raw) > (
        _COLLISION_MAX_AGGREGATE_BYTES
    ):
        raise authority.LifecycleAuthorityError(
            "collision object closure exceeds the aggregate byte bound"
        )
    verified[oid] = (kind, raw)
    return raw


def _verify_collision_tree_closure(
    root: Path,
    tree: str,
    verified: dict[str, tuple[str, bytes]],
) -> None:
    """Rehash one complete bounded tree closure, including its root."""

    pending = [(tree, 0)]
    while pending:
        oid, depth = pending.pop()
        if depth > _COLLISION_MAX_TREE_DEPTH:
            raise authority.LifecycleAuthorityError(
                "collision object closure exceeds the tree-depth bound"
            )
        already_verified = oid in verified
        raw = _collision_object_bytes(root, oid, "tree", verified)
        if already_verified:
            continue
        for mode, _name, child in reversed(
            _collision_tree_entries(raw, len(oid))
        ):
            kind = "tree" if mode == "40000" else "blob"
            if kind == "tree":
                pending.append((child, depth + 1))
            else:
                _collision_object_bytes(root, child, kind, verified)


def _collision_tree_entries(
    raw: bytes, oid_length: int,
) -> tuple[tuple[str, str, str], ...]:
    oid_bytes = 20 if oid_length == 40 else 32
    offset = 0
    entries = []
    names: set[bytes] = set()
    while offset < len(raw):
        delimiter = raw.find(b"\0", offset)
        if delimiter < 0 or delimiter + 1 + oid_bytes > len(raw):
            raise authority.LifecycleAuthorityError(
                "collision tree object is malformed"
            )
        metadata = raw[offset:delimiter].split(b" ", 1)
        if (
            len(metadata) != 2
            or metadata[0] not in {b"40000", b"100644", b"100755"}
            or not metadata[1]
            or b"/" in metadata[1]
            or metadata[1] in {b".", b".."}
            or metadata[1] in names
        ):
            raise authority.LifecycleAuthorityError(
                "collision tree object is malformed"
            )
        names.add(metadata[1])
        try:
            name = metadata[1].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise authority.LifecycleAuthorityError(
                "collision tree object is malformed"
            ) from exc
        child = raw[delimiter + 1:delimiter + 1 + oid_bytes].hex()
        entries.append((metadata[0].decode("ascii"), name, child))
        offset = delimiter + 1 + oid_bytes
    return tuple(entries)


def _verify_collision_tree_inventory(
    root: Path,
    tree: str,
    verified: dict[str, tuple[str, bytes]],
) -> dict[str, str]:
    """Authenticate reachable identities while reading tree objects only."""

    inventory: dict[str, str] = {}
    pending = [(tree, 0)]
    while pending:
        oid, depth = pending.pop()
        if depth > _COLLISION_MAX_TREE_DEPTH:
            raise authority.LifecycleAuthorityError(
                "collision object closure exceeds the tree-depth bound"
            )
        existing = inventory.get(oid)
        if existing is not None:
            if existing != "tree":
                raise authority.LifecycleAuthorityError(
                    "collision object identity changed type"
                )
            continue
        raw = _collision_object_bytes(root, oid, "tree", verified)
        inventory[oid] = "tree"
        for mode, _name, child in reversed(
            _collision_tree_entries(raw, len(oid))
        ):
            kind = "tree" if mode == "40000" else "blob"
            previous = inventory.get(child)
            if previous is not None and previous != kind:
                raise authority.LifecycleAuthorityError(
                    "collision object identity changed type"
                )
            if kind == "tree":
                pending.append((child, depth + 1))
            else:
                inventory[child] = kind
            if len(inventory) > _COLLISION_MAX_OBJECTS:
                raise authority.LifecycleAuthorityError(
                    "collision object closure exceeds the object bound"
                )
    return inventory


def _verify_collision_tree_path(
    root: Path,
    tree: str,
    relative: str,
    verified: dict[str, tuple[str, bytes]],
) -> None:
    """Rehash one exact blob path rooted in an authenticated historical tree."""

    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != relative
        or len(path.parts) > _COLLISION_MAX_TREE_DEPTH
    ):
        raise authority.LifecycleAuthorityError(
            "collision historical path is malformed"
        )
    current = tree
    for index, part in enumerate(path.parts):
        raw = _collision_object_bytes(root, current, "tree", verified)
        matches = [
            (mode, child)
            for mode, name, child in _collision_tree_entries(raw, len(current))
            if name == part
        ]
        if len(matches) != 1:
            raise authority.LifecycleAuthorityError(
                "collision historical path is unavailable"
            )
        mode, child = matches[0]
        final = index == len(path.parts) - 1
        if final:
            if mode not in {"100644", "100755"}:
                raise authority.LifecycleAuthorityError(
                    "collision historical path is not a regular blob"
                )
            _collision_object_bytes(root, child, "blob", verified)
        elif mode != "40000":
            raise authority.LifecycleAuthorityError(
                "collision historical path is malformed"
            )
        current = child


def _verify_collision_validation_root(
    root: Path,
    candidate_tree: str,
    production: Mapping[str, tuple[str, str]],
    projection: Mapping[str, tuple[str, str]],
    runtime: Mapping[str, tuple[str, str]],
    object_dependencies: Sequence[Mapping[str, Any]],
    projected_tree: str,
    git_state: tuple[tuple[str, int, int, str], ...],
) -> None:
    expected = {**production, **projection, **runtime}
    if len(expected) != len(production) + len(projection) + len(runtime):
        raise authority.LifecycleAuthorityError(
            "collision validation ownership overlaps"
        )
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path == root / ".git" or root / ".git" in path.parents:
            continue
        if path.is_symlink():
            raise authority.LifecycleAuthorityError(
                "collision validation source contains a symlink"
            )
        if not path.is_dir() and not path.is_file():
            raise authority.LifecycleAuthorityError(
                "collision validation source contains a special file"
            )
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if path.suffix in {".pyc", ".pyo"} and "__pycache__" in path.parts:
                continue
            observed.add(relative)
            binding = expected.get(relative)
            if binding is None:
                raise authority.LifecycleAuthorityError(
                    "collision validation source contains an undeclared file"
                )
            mode, oid = binding
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode)
                != (0o755 if mode == "100755" else 0o644)
                or _git_blob_oid(path.read_bytes()) != oid
            ):
                raise authority.LifecycleAuthorityError(
                    "validation mutated collision source or harness bytes: "
                    + relative
                )
    if observed != set(expected):
        raise authority.LifecycleAuthorityError(
            "collision validation projection is incomplete"
        )
    if transport._git_text(root, ["write-tree"]).strip() != projected_tree:
        raise authority.LifecycleAuthorityError(
            "validation mutated the collision projection index"
        )
    verified_objects: dict[str, tuple[str, bytes]] = {}
    _verify_collision_tree_closure(root, candidate_tree, verified_objects)
    candidate_bytes = sum(len(raw) for _kind, raw in verified_objects.values())
    if candidate_bytes > _COLLISION_MAX_CANDIDATE_BYTES:
        raise authority.LifecycleAuthorityError(
            "collision candidate closure exceeds the byte bound"
        )
    observed_prerequisites: dict[str, str] = {}
    tree_inventories: dict[str, dict[str, str]] = {}
    for dependency in object_dependencies:
        if (
            not isinstance(dependency, Mapping)
            or set(dependency)
            != {
                "path",
                "mode",
                "blob_oid",
                "size",
                "prerequisites",
                "required_objects",
                "required_paths",
            }
        ):
            raise authority.LifecycleAuthorityError(
                "collision object dependency profile is malformed"
            )
        path = dependency.get("path")
        prerequisites = dependency.get("prerequisites")
        required_objects = dependency.get("required_objects")
        required_paths = dependency.get("required_paths")
        if not isinstance(path, str):
            raise authority.LifecycleAuthorityError(
                "collision object dependency profile is malformed"
            )
        dependency_binding = (
            dependency.get("mode"), dependency.get("blob_oid")
        )
        try:
            dependency_size = (root / path).stat().st_size
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision object dependency is unavailable"
            ) from exc
        if (
            path not in production
            or production.get(path) != dependency_binding
            or not isinstance(dependency.get("size"), int)
            or dependency["size"] <= 0
            or dependency_size != dependency["size"]
            or not isinstance(prerequisites, list)
            or not prerequisites
            or not isinstance(required_objects, list)
            or not isinstance(required_paths, list)
        ):
            raise authority.LifecycleAuthorityError(
                "collision object dependency profile is malformed"
            )
        dependency_prerequisites: set[str] = set()
        dependency_trees: dict[str, str] = {}
        for prerequisite in prerequisites:
            if (
                not isinstance(prerequisite, Mapping)
                or set(prerequisite) != {"commit", "tree"}
            ):
                raise authority.LifecycleAuthorityError(
                    "collision object dependency profile is malformed"
                )
            commit = prerequisite.get("commit")
            tree = prerequisite.get("tree")
            if (
                not isinstance(commit, str)
                or _GIT_OID.fullmatch(commit) is None
                or not isinstance(tree, str)
                or _GIT_OID.fullmatch(tree) is None
            ):
                raise authority.LifecycleAuthorityError(
                    "collision object dependency profile is malformed"
                )
            commit_source = _collision_object_bytes(
                root, commit, "commit", verified_objects,
            )
            commit_tree = commit_source.partition(b"\n")[0]
            if (
                commit in dependency_prerequisites
                or (
                    commit in observed_prerequisites
                    and observed_prerequisites[commit] != tree
                )
                or commit_tree != b"tree " + tree.encode("ascii")
            ):
                raise authority.LifecycleAuthorityError(
                    "collision object dependency changed"
                )
            dependency_prerequisites.add(commit)
            observed_prerequisites[commit] = tree
            dependency_trees[commit] = tree

        reachable: dict[str, str] = {}
        observed_required_objects: set[tuple[str, str]] = set()
        if required_objects:
            for tree in dependency_trees.values():
                inventory = tree_inventories.get(tree)
                if inventory is None:
                    inventory = _verify_collision_tree_inventory(
                        root, tree, verified_objects,
                    )
                    tree_inventories[tree] = inventory
                for oid, kind in inventory.items():
                    previous = reachable.get(oid)
                    if previous is not None and previous != kind:
                        raise authority.LifecycleAuthorityError(
                            "collision object dependency changed type"
                        )
                    reachable[oid] = kind
                    if len(reachable) > _COLLISION_MAX_OBJECTS:
                        raise authority.LifecycleAuthorityError(
                            "collision object dependency exceeds the object bound"
                        )
            for requirement in required_objects:
                if (
                    not isinstance(requirement, Mapping)
                    or set(requirement) != {"kind", "oid"}
                    or requirement.get("kind") not in {"tree", "blob"}
                    or not isinstance(requirement.get("oid"), str)
                    or _GIT_OID.fullmatch(requirement["oid"]) is None
                ):
                    raise authority.LifecycleAuthorityError(
                        "collision object dependency profile is malformed"
                    )
                item = (requirement["kind"], requirement["oid"])
                if (
                    item in observed_required_objects
                    or reachable.get(item[1]) != item[0]
                ):
                    raise authority.LifecycleAuthorityError(
                        "collision required object is not uniquely reachable"
                    )
                observed_required_objects.add(item)
                _collision_object_bytes(
                    root, item[1], item[0], verified_objects,
                )

        observed_required_paths: set[tuple[str, str]] = set()
        for requirement in required_paths:
            if (
                not isinstance(requirement, Mapping)
                or set(requirement) != {"commit", "path"}
                or not isinstance(requirement.get("commit"), str)
                or not isinstance(requirement.get("path"), str)
            ):
                raise authority.LifecycleAuthorityError(
                    "collision object dependency profile is malformed"
                )
            item = (requirement["commit"], requirement["path"])
            tree = dependency_trees.get(item[0])
            if tree is None or item in observed_required_paths:
                raise authority.LifecycleAuthorityError(
                    "collision required path has no unique prerequisite"
                )
            observed_required_paths.add(item)
            _verify_collision_tree_path(
                root, tree, item[1], verified_objects,
            )
        if (
            sum(len(raw) for _kind, raw in verified_objects.values())
            - candidate_bytes
            > _COLLISION_MAX_HISTORICAL_BYTES
        ):
            raise authority.LifecycleAuthorityError(
                "collision historical closure exceeds the byte bound"
            )
    _require_collision_git_state(root, git_state)


def _collision_git_state(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    """Hash the complete bounded private Git state used by validation."""

    git_root = root / ".git"
    try:
        if git_root.resolve(strict=True) != git_root or not git_root.is_dir():
            raise authority.LifecycleAuthorityError(
                "collision private Git state is unavailable"
            )
    except (OSError, RuntimeError) as exc:
        raise authority.LifecycleAuthorityError(
            "collision private Git state is unavailable"
        ) from exc
    state: list[tuple[str, int, int, str]] = []
    aggregate = 0
    for path in sorted(git_root.rglob("*")):
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision private Git state is unavailable"
            ) from exc
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise authority.LifecycleAuthorityError(
                "collision private Git state contains a special file"
            )
        if len(state) >= _COLLISION_MAX_GIT_STATE_FILES:
            raise authority.LifecycleAuthorityError(
                "collision private Git state exceeds the file bound"
            )
        aggregate += metadata.st_size
        if aggregate > _COLLISION_MAX_GIT_STATE_BYTES:
            raise authority.LifecycleAuthorityError(
                "collision private Git state exceeds the byte bound"
            )
        try:
            raw = path.read_bytes()
            after = path.lstat()
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision private Git state is unavailable"
            ) from exc
        if (
            len(raw) != metadata.st_size
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
            or after.st_mode != metadata.st_mode
        ):
            raise authority.LifecycleAuthorityError(
                "collision private Git state changed while observed"
            )
        state.append((
            path.relative_to(git_root).as_posix(),
            stat.S_IMODE(metadata.st_mode),
            len(raw),
            hashlib.sha256(raw).hexdigest(),
        ))
    return tuple(state)


def _require_collision_git_state(
    root: Path,
    expected: tuple[tuple[str, int, int, str], ...],
) -> None:
    if _collision_git_state(root) != expected:
        raise authority.LifecycleAuthorityError(
            "validation mutated collision private Git state"
        )


@contextmanager
def collision_validation_root(
    root: Path,
    *,
    profile: Mapping[str, Any],
    expected_profile: Mapping[str, Any],
) -> Iterator[tuple[Path, Any]]:
    """Construct one closed candidate root from an isolated authenticated DB."""

    if dict(profile) != dict(expected_profile):
        raise authority.LifecycleAuthorityError(
            "collision validation profile or command set drifted"
        )
    candidate_tree = profile.get("candidate_tree")
    predecessor = profile.get("candidate_predecessor_head")
    occupied = profile.get("occupied_version")
    implementation = profile.get("implementation_identity")
    sources = profile.get("validation_projection_sources")
    object_dependencies = profile.get("validation_object_dependencies")
    if (
        not isinstance(candidate_tree, str)
        or not isinstance(predecessor, str)
        or not isinstance(sources, list)
        or not sources
        or not isinstance(object_dependencies, list)
        or not object_dependencies
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation projection profile is malformed"
        )
    root = root.resolve(strict=True)
    listing = _collision_listing(
        transport._git_text(root, ["ls-tree", "-rz", "--full-tree", candidate_tree])
    )
    projection_paths = tuple(
        item.get("path") for item in sources if isinstance(item, Mapping)
    )
    if (
        len(projection_paths) != len(sources)
        or len(set(projection_paths)) != len(sources)
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation projection inventory is malformed"
        )
    production = {
        relative: (mode, oid)
        for mode, oid, relative in listing
        if relative not in projection_paths
    }
    transport._git(root, ["update-ref", "--no-deref", "HEAD", predecessor])
    transport._git(root, ["read-tree", "--empty"])
    index = b"".join(
        f"{mode} {oid}\t{relative}\0".encode("utf-8")
        for relative, (mode, oid) in production.items()
    )
    transport._git(
        root, ["update-index", "-z", "--index-info"], input_bytes=index,
    )
    transport._git(root, ["checkout-index", "--all", "--force"])
    for relative, (mode, _oid) in production.items():
        try:
            (root / relative).chmod(0o755 if mode == "100755" else 0o644)
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision candidate materialization failed"
            ) from exc
    projection: dict[str, tuple[str, str]] = {}
    for item in sources:
        relative = item["path"]
        mode = item.get("mode")
        source_oid = item.get("candidate_blob_oid")
        raw = _read_collision_blob(root, source_oid, item.get("candidate_size"))
        projected, offsets = _collision_projection_bytes(
            relative,
            raw,
            occupied_version=occupied,
            implementation_identity=implementation,
        )
        projected_oid = _git_blob_oid(projected)
        if (
            projected_oid != item.get("projected_blob_oid")
            or len(projected) != item.get("projected_size")
            or [list(offset) for offset in offsets]
            != item.get("current_identity_offsets")
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation authenticated projection changed"
            )
        _materialize_collision_blob(root, relative, mode, projected)
        projection[relative] = (mode, projected_oid)
    transport._git(root, ["add", "--all", "--"])
    projected_tree = transport._git_text(root, ["write-tree"]).strip()
    with _collision_validation_dependencies(root) as runtime:
        git_state = _collision_git_state(root)

        def verify() -> None:
            _verify_collision_validation_root(
                root,
                candidate_tree,
                production,
                projection,
                runtime,
                object_dependencies,
                projected_tree,
                git_state,
            )

        verify()
        try:
            yield root, verify
        finally:
            verify()


def _candidate_listing_without_harness(listing: str) -> str:
    entries = [
        item for item in listing.rstrip("\0").split("\0")
        if not item.partition("\t")[2].startswith("tests/")
    ]
    return "\0".join(entries) + ("\0" if entries else "")


def _registered_candidate_validation(
    source_root: Path,
    value: Any,
    *,
    candidate_repository: str | None,
) -> tuple[str, tuple[Mapping[str, Any], ...]]:
    """Authenticate one closed accepted-policy inventory from the exact candidate."""

    if (
        not isinstance(value, Mapping)
        or set(value) != {"provenance", "repository", "head_sha", "tree_sha", "files"}
        or value.get("provenance") != _REGISTERED_VALIDATION_PROVENANCE
        or value.get("repository") != candidate_repository
        or not isinstance(candidate_repository, str)
        or re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", candidate_repository
        ) is None
        or not isinstance(value.get("head_sha"), str)
        or _GIT_OID.fullmatch(value["head_sha"]) is None
        or not isinstance(value.get("tree_sha"), str)
        or _GIT_OID.fullmatch(value["tree_sha"]) is None
        or not isinstance(value.get("files"), list)
        or not value["files"]
    ):
        raise authority.LifecycleAuthorityError(
            "registered candidate validation provenance is malformed"
        )
    head = value["head_sha"]
    tree = value["tree_sha"]
    if (
        transport._git_text(source_root, ["rev-parse", "HEAD"]).strip() != head
        or transport._git_text(source_root, ["rev-parse", "HEAD^{tree}"]).strip()
        != tree
    ):
        raise authority.LifecycleAuthorityError(
            "registered candidate validation source identity changed"
        )
    files = tuple(value["files"])
    if any(
        not isinstance(item, Mapping)
        or set(item) != {"path", "mode", "blob_oid", "size"}
        or not isinstance(item.get("path"), str)
        or item.get("mode") not in {"100644", "100755"}
        or not isinstance(item.get("blob_oid"), str)
        or _GIT_OID.fullmatch(item["blob_oid"]) is None
        or type(item.get("size")) is not int
        or item["size"] < 0
        for item in files
    ):
        raise authority.LifecycleAuthorityError(
            "registered candidate validation inventory is malformed"
        )
    paths = tuple(item["path"] for item in files)
    allowed = frozenset(paths)
    if len(allowed) != len(paths):
        raise authority.LifecycleAuthorityError(
            "registered candidate validation inventory is ambiguous"
        )
    for item in files:
        path = admit_harness_path(item["path"], allowed_paths=allowed)
        if not path.startswith("tests/"):
            raise authority.LifecycleAuthorityError(
                "registered candidate validation path is outside tests"
            )
        observed = harness_blob(
            source_root, head, path, allowed_paths=allowed,
        )
        if observed != (item["mode"], item["blob_oid"], item["size"]):
            raise authority.LifecycleAuthorityError(
                "registered candidate validation binding changed"
            )
    return head, files


def _verify_execution_root(
    repository_root: Path,
    root: Path,
    tree: str,
    candidate_listing: str,
    bindings: Mapping[str, tuple[str, str, int]],
) -> None:
    expected = {
        item.partition("\t")[2] for item in candidate_listing.rstrip("\0").split("\0") if item
    }
    if expected.intersection(bindings):
        raise authority.LifecycleAuthorityError("candidate production and harness ownership overlap")
    expected.update(bindings)
    directories = {
        parent.as_posix() for relative in expected for parent in Path(relative).parents
        if parent != Path(".")
    }
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise authority.LifecycleAuthorityError("current safety source contains symlink")
        if path.is_dir():
            if path.relative_to(root).as_posix() not in directories:
                raise authority.LifecycleAuthorityError(
                    "current safety source contains undeclared directory: "
                    + path.relative_to(root).as_posix()
                )
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
            raise authority.LifecycleAuthorityError("current safety source contains bytecode")
        observed.add(relative)
    if observed != expected:
        raise authority.LifecycleAuthorityError("current safety source contains undeclared files")
    verify_source_bytes(
        root, tree, hash_repository_root=repository_root, expected_listing=candidate_listing,
    )
    for relative, binding in bindings.items():
        _verify_harness_file(repository_root, root, relative, *binding)


def _verify_root_separation(tooling_root: Path, candidate_root: Path) -> None:
    try:
        tooling = tooling_root.resolve(strict=True)
        candidate = candidate_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise authority.LifecycleAuthorityError(
            "current safety execution root is unavailable"
        ) from exc
    if (
        tooling == candidate
        or tooling in candidate.parents
        or candidate in tooling.parents
        or tooling_root.is_symlink()
        or candidate_root.is_symlink()
    ):
        raise authority.LifecycleAuthorityError(
            "current safety tooling and candidate roots must be distinct"
        )


def _reject_candidate_import_authority(
    listing: str, *, candidate_repository: str,
) -> None:
    """Reject candidate-controlled Python startup and foreign issuer surfaces."""

    paths = {
        item.partition("\t")[2]
        for item in listing.rstrip("\0").split("\0")
        if item
    }
    startup = {
        path
        for path in paths
        if Path(path).name in {"sitecustomize.py", "usercustomize.py"}
        or Path(path).suffix == ".pth"
    }
    foreign_governance = {
        path
        for path in paths
        if path == "secpal_pr_review.py"
        or path.startswith("secpal_pr_review/")
        or path == "scripts/secpal-pr-review-actions.py"
        or path == "scripts/secpal-pr-review.py"
        or path.startswith("scripts/secpal_pr_review/")
    }
    if startup or (
        candidate_repository != "SecPal/.github" and foreign_governance
    ):
        raise authority.LifecycleAuthorityError(
            "candidate source contains forbidden Python import authority"
        )


def _verify_tooling_root(
    repository_root: Path,
    root: Path,
    bindings: Mapping[str, tuple[str, str, int]],
) -> None:
    expected = set(bindings)
    directories = {
        parent.as_posix()
        for relative in expected
        for parent in Path(relative).parents
        if parent != Path(".")
    }
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise authority.LifecycleAuthorityError(
                "current safety tooling contains symlink"
            )
        if path.is_dir():
            if path.relative_to(root).as_posix() not in directories:
                raise authority.LifecycleAuthorityError(
                    "current safety tooling contains undeclared directory"
                )
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
            raise authority.LifecycleAuthorityError(
                "current safety tooling contains bytecode"
            )
        observed.add(relative)
    if observed != expected:
        raise authority.LifecycleAuthorityError(
            "current safety tooling contains undeclared files"
        )
    for relative, binding in bindings.items():
        _verify_harness_file(repository_root, root, relative, *binding)


@contextmanager
def two_provenance_execution_roots(
    repository_root: Path,
    accepted_main: str,
    *,
    source_root: Path,
    candidate_repository: str,
    profile: Mapping[str, Any],
) -> Iterator[CurrentSafetyExecutionRoots]:
    """Materialize accepted tooling separately from immutable candidate source."""

    source_root = source_root.resolve(strict=True)
    repository_root = repository_root.resolve(strict=True)
    if not isinstance(profile, Mapping):
        raise authority.LifecycleAuthorityError(
            "current safety two-provenance profile is malformed"
        )
    if (
        not isinstance(candidate_repository, str)
        or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", candidate_repository)
        is None
    ):
        raise authority.LifecycleAuthorityError(
            "current safety candidate repository is malformed"
        )
    harness = profile.get("harness")
    tooling = profile.get("tooling")
    if (
        profile.get("execution_model")
        != "ACCEPTED_MAIN_TOOLING_WITH_EXACT_CANDIDATE"
        or not isinstance(harness, list)
        or not harness
        or not isinstance(tooling, list)
        or not tooling
        or any(not isinstance(item, Mapping) for item in [*harness, *tooling])
    ):
        raise authority.LifecycleAuthorityError(
            "current safety two-provenance profile is malformed"
        )
    harness_paths = tuple(item.get("path") for item in harness)
    tooling_paths = tuple(item.get("path") for item in tooling)
    harness_allowed = frozenset(harness_paths)
    tooling_allowed = frozenset(tooling_paths)
    if (
        len(harness_allowed) != len(harness_paths)
        or len(tooling_allowed) != len(tooling_paths)
        or harness_allowed.intersection(tooling_allowed)
    ):
        raise authority.LifecycleAuthorityError(
            "current safety two-provenance inventory is ambiguous"
        )
    tree = transport._git_text(source_root, ["rev-parse", "HEAD^{tree}"]).strip()
    listing = verify_source_bytes(source_root, tree)
    _reject_candidate_import_authority(
        listing, candidate_repository=candidate_repository,
    )
    candidate_listing = _candidate_listing_without_harness(listing)
    with tempfile.TemporaryDirectory(
        prefix="secpal-two-provenance-current-safety-"
    ) as directory:
        private = Path(directory)
        private.chmod(0o700)
        candidate_root = private / "candidate"
        tooling_root = private / "tooling"
        tooling_root.mkdir(mode=0o700)
        try:
            shutil.copytree(
                source_root,
                candidate_root,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git"),
            )
            tests_root = candidate_root / "tests"
            if tests_root.exists():
                shutil.rmtree(tests_root)
            bindings: dict[str, tuple[str, str, int]] = {}
            for item in harness:
                bindings[item["path"]] = _copy_harness_file(
                    repository_root,
                    accepted_main,
                    item,
                    tooling_root,
                    allowed_paths=harness_allowed,
                )
            for item in tooling:
                bindings[item["path"]] = _copy_tooling_file(
                    repository_root,
                    accepted_main,
                    item,
                    tooling_root,
                    allowed_paths=tooling_allowed,
                )
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "current safety two-provenance preparation failed"
            ) from exc
        _verify_root_separation(tooling_root, candidate_root)
        _verify_execution_root(
            repository_root, candidate_root, tree, candidate_listing, {},
        )
        _verify_tooling_root(repository_root, tooling_root, bindings)
        roots = CurrentSafetyExecutionRoots(tooling_root, candidate_root)
        try:
            yield roots
        finally:
            _verify_root_separation(tooling_root, candidate_root)
            _verify_execution_root(
                repository_root, candidate_root, tree, candidate_listing, {},
            )
            _verify_tooling_root(repository_root, tooling_root, bindings)
            verify_source_bytes(source_root, tree, expected_listing=listing)


@contextmanager
def execution_root(
    repository_root: Path,
    accepted_main: str,
    *,
    source_root: Path,
    profile: Mapping[str, Any],
    candidate_repository: str | None = None,
) -> Iterator[Path]:
    """Build a disposable exact candidate with only profile harness bytes overlaid."""

    source_root = source_root.resolve(strict=True)
    repository_root = repository_root.resolve(strict=True)
    harness = profile.get("harness") if isinstance(profile, Mapping) else None
    if not isinstance(harness, list) or not harness:
        raise authority.LifecycleAuthorityError("current safety profile harness is malformed")
    paths = tuple(item.get("path") for item in harness if isinstance(item, Mapping))
    if len(paths) != len(harness):
        raise authority.LifecycleAuthorityError("current safety profile harness is malformed")
    allowed = frozenset(paths)
    if len(allowed) != len(paths):
        raise authority.LifecycleAuthorityError("current safety harness paths are ambiguous")
    tree = transport._git_text(source_root, ["rev-parse", "HEAD^{tree}"]).strip()
    listing = verify_source_bytes(source_root, tree)
    candidate_listing = _candidate_listing_without_harness(listing)
    registered_value = profile.get("registered_candidate_validation")
    registered_head: str | None = None
    registered_files: tuple[Mapping[str, Any], ...] = ()
    if registered_value is not None:
        registered_head, registered_files = _registered_candidate_validation(
            source_root,
            registered_value,
            candidate_repository=candidate_repository,
        )
    registered_allowed = frozenset(item["path"] for item in registered_files)
    if allowed.intersection(registered_allowed):
        raise authority.LifecycleAuthorityError(
            "accepted harness and registered candidate validation overlap"
        )
    with tempfile.TemporaryDirectory(prefix="secpal-exact-source-safety-") as directory:
        root = Path(directory) / "source"
        try:
            shutil.copytree(source_root, root, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            tests_root = root / "tests"
            if tests_root.exists():
                shutil.rmtree(tests_root)
            bindings = {
                item["path"]: _copy_harness_file(
                    repository_root, accepted_main, item, root, allowed_paths=allowed,
                )
                for item in harness
            }
            if registered_head is not None:
                for item in registered_files:
                    bindings[item["path"]] = _copy_harness_file(
                        source_root,
                        registered_head,
                        item,
                        root,
                        allowed_paths=registered_allowed,
                    )
        except OSError as exc:
            raise authority.LifecycleAuthorityError("current safety harness preparation failed") from exc
        _verify_execution_root(repository_root, root, tree, candidate_listing, bindings)
        try:
            yield root
        finally:
            _verify_execution_root(repository_root, root, tree, candidate_listing, bindings)
            verify_source_bytes(source_root, tree, expected_listing=listing)
            if registered_value is not None:
                _registered_candidate_validation(
                    source_root,
                    registered_value,
                    candidate_repository=candidate_repository,
                )


def run_profile(
    root: Path,
    profile: Mapping[str, Any],
    *,
    expected_profile: Mapping[str, Any],
    candidate_root: Path | None = None,
    candidate_repository: str | None = None,
) -> None:
    """Execute the exact closed profile through the isolated Python boundary."""

    if dict(profile) != dict(expected_profile):
        raise authority.LifecycleAuthorityError("current safety profile or command drift")
    commands = profile.get("validation_command_set")
    results = profile.get("validation_results")
    invariants = profile.get("required_invariants")
    if not isinstance(commands, list) or not commands or not isinstance(results, list):
        raise authority.LifecycleAuthorityError("current safety profile command set is malformed")
    observed = []
    reports = []
    with tempfile.TemporaryDirectory(prefix="secpal-current-safety-home-") as home:
        environment = transport._closed_validation_environment(
            authority._load_trusted_command_helper(), Path(home),
        )
        for command in commands:
            if "tooling" in profile:
                if candidate_root is None or candidate_repository is None:
                    raise authority.LifecycleAuthorityError(
                        "current safety candidate execution boundary is missing"
                    )
                _verify_root_separation(root, candidate_root)
                isolated_command = transport._isolated_python_command(
                    _TWO_PROVENANCE_LAUNCHER,
                    str(root),
                    str(candidate_root),
                    candidate_repository,
                    command["argv"][1],
                    "main",
                )
            else:
                isolated_command = transport._isolated_python_command(
                    transport._ISOLATED_SOURCE_LAUNCHER,
                    "ENTRYPOINT", str(root), command["argv"][1], "main",
                )
            result = transport._run_isolated_python(
                isolated_command,
                cwd=root, timeout=profile["timeout_seconds"], env=environment,
            )
            observed.append({
                "command_digest": authority.digest_json(command),
                "exit_status": result.returncode,
                "successful": result.returncode == 0,
            })
            try:
                report = authority.loads_closed_json(result.stdout)
            except authority.LifecycleAuthorityError as exc:
                raise authority.LifecycleAuthorityError("current safety failure report invalid") from exc
            reports.extend(report if isinstance(report, list) else [])
    if any(not isinstance(item, str) or item not in invariants for item in reports):
        raise authority.LifecycleAuthorityError("current safety failure report invalid")
    covered_invariants = sorted(set(reports))
    if observed != results:
        if not reports:
            raise authority.LifecycleAuthorityError("current safety failure report invalid")
        raise authority.LifecycleAuthorityError("current safety assertions failed: " + ", ".join(reports))
    if covered_invariants != list(invariants):
        raise authority.LifecycleAuthorityError("current safety invariant coverage incomplete")
