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
_COLLISION_CURRENT_IDENTITY_FIXTURES = {
    "tests/secpal-pr-review-actions-unit.py": {
        "test_parent2_preservation_cannot_delete_parent1_only_work": 1,
        "test_parent2_preservation_uses_exact_new_attestation_versions": 1,
        "test_ready_integration_accepts_authenticated_current_ready_histories": 1,
        "test_ready_integration_authenticates_exact_parent2_preservation": 2,
        "test_ready_integration_mixes_conflict_and_parent2_preservation": 2,
        "test_ready_integration_v12_delta_uses_registered_item_limit_before_git_work": 2,
    },
    "tests/secpal-resolve-fixed-threads-unit.py": {
        "test_eligibility_bound_ready_integration_authorizes_exact_thread": 1,
    },
}
_COLLISION_VALIDATION_AUTHORITY_PATH = "scripts/secpal-pr-review-actions.py"


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
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
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
    """Project only the closed current-identity fixture inventory.

    Historical literals, including historical instances of the occupied
    version in the same file, are deliberately outside this AST-owned set.
    """

    _compatible_evidence_versions(occupied_version, implementation_identity)
    expected = _COLLISION_CURRENT_IDENTITY_FIXTURES.get(relative)
    if expected is None or not isinstance(source, bytes):
        raise authority.LifecycleAuthorityError(
            "collision validation fixture path is not maintained"
        )
    try:
        text = source.decode("utf-8", errors="strict")
        module = ast.parse(text)
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise authority.LifecycleAuthorityError(
            "collision validation fixture source is malformed"
        ) from exc
    functions = {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in expected
    }
    if set(functions) != set(expected):
        raise authority.LifecycleAuthorityError(
            "collision validation current-identity fixture inventory drifted"
        )
    parents = {
        id(child): node
        for node in ast.walk(module)
        for child in ast.iter_child_nodes(node)
    }
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
            if literal not in {b'"' + old_literal + b'"', b"'" + old_literal + b"'"}:
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
    """Extend the exact accepted validation guard with the derived identity."""

    occupied, _ = _compatible_evidence_versions(
        occupied_version, implementation_identity,
    )
    if not isinstance(source, bytes):
        raise authority.LifecycleAuthorityError(
            "collision validation authority source is malformed"
        )
    try:
        text = source.decode("utf-8", errors="strict")
        module = ast.parse(text)
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
    start, end = _python_byte_offsets(source, version_set)
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


def build_profile(
    repository_root: Path,
    accepted_main: str,
    *,
    policy: str,
    harness_paths: Sequence[str],
    purpose: str,
    required_invariants: Sequence[str],
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
    return {
        "schema_version": "1.0",
        "policy": policy,
        "harness": harness,
        "validation_command_set": commands,
        "validation_command_set_digest": authority.digest_json(commands),
        "timeout_seconds": timeout_seconds,
        "required_invariants": invariants,
        "validation_results": results,
    }


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
) -> tuple[str, str, int]:
    relative = admit_harness_path(binding.get("path"), allowed_paths=allowed_paths)
    observed = harness_blob(
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


def _collision_projected_bytes(
    relative: str,
    source: bytes,
    *,
    occupied_version: str,
    implementation_identity: str,
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    if relative == _COLLISION_VALIDATION_AUTHORITY_PATH:
        return (
            _project_collision_validation_authority(
                source,
                occupied_version=occupied_version,
                implementation_identity=implementation_identity,
            ),
            (),
        )
    return _project_collision_current_identity_fixtures(
        relative,
        source,
        occupied_version=occupied_version,
        implementation_identity=implementation_identity,
    )


def _git_blob_oid(source: bytes) -> str:
    header = b"blob " + str(len(source)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + source).hexdigest()


def _collision_listing(
    listing: str,
) -> tuple[tuple[str, str, str], ...]:
    entries = []
    for raw in listing.rstrip("\0").split("\0"):
        metadata, separator, relative = raw.partition("\t")
        fields = metadata.split()
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or not relative
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation source listing is malformed"
            )
        admitted = Path(relative)
        if admitted.is_absolute() or ".." in admitted.parts:
            raise authority.LifecycleAuthorityError(
                "collision validation source path is unsafe"
            )
        entries.append((fields[0], fields[2], relative))
    if not entries or len({item[2] for item in entries}) != len(entries):
        raise authority.LifecycleAuthorityError(
            "collision validation source listing is ambiguous"
        )
    return tuple(entries)


def _copy_collision_source(
    source_root: Path,
    execution_root: Path,
    listing: tuple[tuple[str, str, str], ...],
) -> None:
    for mode, _oid, relative in listing:
        source = source_root / relative
        destination = execution_root / relative
        parent = execution_root
        for part in Path(relative).parent.parts:
            parent /= part
            try:
                metadata = parent.lstat()
            except FileNotFoundError:
                parent.mkdir(mode=0o755)
                metadata = parent.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
                raise authority.LifecycleAuthorityError(
                    "collision validation source path is unsafe"
                )
        try:
            metadata = source.lstat()
            if not stat.S_ISREG(metadata.st_mode) or source.is_symlink():
                raise authority.LifecycleAuthorityError(
                    "collision validation source is not a regular file"
                )
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if mode == "100755" else 0o644)
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision validation source copy failed"
            ) from exc


def _verify_collision_validation_root(
    root: Path,
    listing: tuple[tuple[str, str, str], ...],
    projected: Mapping[str, tuple[str, int]],
    runtime: Mapping[str, tuple[str, str]],
    projected_tree: str,
) -> None:
    expected_paths = {item[2] for item in listing}
    tracked = transport._git_text(root, ["ls-files", "-z"]).rstrip("\0").split("\0")
    if set(tracked) != expected_paths or len(tracked) != len(expected_paths):
        raise authority.LifecycleAuthorityError(
            "collision validation projection is incomplete"
        )
    expected_by_path = {
        relative: (mode, oid) for mode, oid, relative in listing
    }
    for relative, binding in projected.items():
        if relative not in expected_by_path:
            raise authority.LifecycleAuthorityError(
                "collision validation projection path is untracked"
            )
        expected_by_path[relative] = (expected_by_path[relative][0], binding[0])
    for relative, binding in runtime.items():
        if relative in expected_by_path:
            raise authority.LifecycleAuthorityError(
                "collision validation runtime overlaps source"
            )
        expected_by_path[relative] = binding
    for relative, (mode, oid) in expected_by_path.items():
        path = root / relative
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise authority.LifecycleAuthorityError(
                    "collision validation source contains a symlink"
                )
        try:
            metadata = path.lstat()
            actual = _git_blob_oid(path.read_bytes())
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision validation source is unavailable"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode)
            != (0o755 if mode == "100755" else 0o644)
            or actual != oid
        ):
            raise authority.LifecycleAuthorityError(
                "validation mutated collision source or harness bytes"
            )
    if transport._git_text(root, ["write-tree"]).strip() != projected_tree:
        raise authority.LifecycleAuthorityError(
            "validation mutated the collision projection index"
        )
    for path in root.rglob("*"):
        if path == root / ".git" or root / ".git" in path.parents:
            continue
        if path.is_symlink():
            raise authority.LifecycleAuthorityError(
                "collision validation source contains a symlink"
            )
        if path.is_file() and path.relative_to(root).as_posix() not in expected_by_path:
            if path.suffix not in {".pyc", ".pyo"} or "__pycache__" not in path.parts:
                raise authority.LifecycleAuthorityError(
                    "collision validation source contains an undeclared file"
                )


@contextmanager
def _collision_validation_dependencies(
    root: Path,
) -> Iterator[dict[str, tuple[str, str]]]:
    """Materialize the lockfile-pinned Markdown validator outside source."""

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
                mode, _git_blob_oid(path.read_bytes()),
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
            "100755", _git_blob_oid(wrapper),
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


@contextmanager
def collision_validation_root(
    repository_root: Path,
    *,
    source_root: Path,
    profile: Mapping[str, Any],
    expected_profile: Mapping[str, Any],
) -> Iterator[Path]:
    """Build the dedicated immutable-collision Complete Validation root."""

    if dict(profile) != dict(expected_profile):
        raise authority.LifecycleAuthorityError(
            "collision validation profile or command set drifted"
        )
    candidate_tree = profile.get("candidate_tree")
    predecessor = profile.get("candidate_predecessor_head")
    accepted_main = profile.get("accepted_main")
    occupied = profile.get("occupied_version")
    implementation = profile.get("implementation_identity")
    sources = profile.get("projected_sources")
    dependencies = profile.get("validation_dependencies")
    if (
        not isinstance(candidate_tree, str)
        or not isinstance(predecessor, str)
        or not isinstance(accepted_main, str)
        or not isinstance(sources, list)
        or not isinstance(dependencies, list)
        or tuple(
            item.get("path")
            for item in dependencies
            if isinstance(item, Mapping)
        )
        != ("package.json", "package-lock.json")
        or tuple(
            item.get("path") for item in sources if isinstance(item, Mapping)
        )
        != (
            _COLLISION_VALIDATION_AUTHORITY_PATH,
            *tuple(_COLLISION_CURRENT_IDENTITY_FIXTURES),
        )
    ):
        raise authority.LifecycleAuthorityError(
            "collision validation profile is malformed"
        )
    source_root = source_root.resolve(strict=True)
    repository_root = repository_root.resolve(strict=True)
    if source_root == repository_root:
        raise authority.LifecycleAuthorityError(
            "collision candidate must be distinct from accepted-main authority"
        )
    head = transport._git_text(source_root, ["rev-parse", "HEAD"]).strip()
    tree = transport._git_text(source_root, ["write-tree"]).strip()
    if head != predecessor or tree != candidate_tree:
        raise authority.LifecycleAuthorityError(
            "collision validation candidate head or tree changed"
        )
    source_status = transport._git_text(
        source_root, ["status", "--porcelain=v2", "--untracked-files=all"],
    )
    listing_raw = verify_source_bytes(source_root, candidate_tree)
    listing = _collision_listing(listing_raw)
    source_by_path = {relative: (mode, oid) for mode, oid, relative in listing}
    for item in dependencies:
        binding = source_by_path.get(item["path"])
        try:
            size = (source_root / item["path"]).stat().st_size
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "collision validation dependency source is unavailable"
            ) from exc
        if (
            binding != (item.get("mode"), item.get("blob_oid"))
            or size != item.get("size")
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation dependency authority changed"
            )
    projection_bindings: dict[str, tuple[str, int]] = {}
    projection_bytes: dict[str, bytes] = {}
    for item in sources:
        relative = item["path"]
        binding = source_by_path.get(relative)
        if (
            binding is None
            or binding[0] != item.get("mode")
            or binding[1] != item.get("candidate_blob_oid")
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation candidate harness binding changed"
            )
        raw = (source_root / relative).read_bytes()
        if len(raw) != item.get("candidate_size"):
            raise authority.LifecycleAuthorityError(
                "collision validation candidate harness size changed"
            )
        projected_bytes, offsets = _collision_projected_bytes(
            relative,
            raw,
            occupied_version=occupied,
            implementation_identity=implementation,
        )
        if (
            _git_blob_oid(projected_bytes) != item.get("projected_blob_oid")
            or len(projected_bytes) != item.get("projected_size")
            or [list(offset) for offset in offsets]
            != item.get("current_identity_offsets")
        ):
            raise authority.LifecycleAuthorityError(
                "collision validation accepted projection changed"
            )
        projection_bytes[relative] = projected_bytes
        projection_bindings[relative] = (
            item["projected_blob_oid"], item["projected_size"],
        )
    with tempfile.TemporaryDirectory(
        prefix="secpal-collision-complete-validation-"
    ) as directory:
        root = Path(directory) / "source"
        root.mkdir(mode=0o700)
        transport._git(root, ["init", "--quiet"])
        transport._git(root, ["remote", "add", "candidate", str(source_root)])
        transport._git(root, ["remote", "add", "authority", str(repository_root)])
        transport._git(root, [
            "fetch", "--quiet", "--no-tags", "--depth=2048",
            "authority", accepted_main,
        ])
        transport._git(root, [
            "fetch", "--quiet", "--no-tags", "--depth=2048",
            "candidate", predecessor,
        ])
        transport._git(root, ["checkout", "--quiet", "--detach", "FETCH_HEAD"])
        _copy_collision_source(source_root, root, listing)
        for relative, projected_bytes in projection_bytes.items():
            destination = root / relative
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", dir=destination.parent,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(projected_bytes)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.chmod(destination.stat().st_mode & 0o777)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        transport._git(root, ["add", "--all", "--"])
        projected_tree = transport._git_text(root, ["write-tree"]).strip()
        with _collision_validation_dependencies(root) as runtime:
            _verify_collision_validation_root(
                root, listing, projection_bindings, runtime, projected_tree,
            )
            try:
                yield root
            finally:
                _verify_collision_validation_root(
                    root, listing, projection_bindings, runtime, projected_tree,
                )
                if (
                    transport._git_text(source_root, ["rev-parse", "HEAD"]).strip()
                    != head
                    or transport._git_text(source_root, ["write-tree"]).strip()
                    != candidate_tree
                    or transport._git_text(
                        source_root,
                        ["status", "--porcelain=v2", "--untracked-files=all"],
                    )
                    != source_status
                ):
                    raise authority.LifecycleAuthorityError(
                        "validation mutated the exact collision candidate"
                    )
                verify_source_bytes(
                    source_root, candidate_tree, expected_listing=listing_raw,
                )


def _candidate_listing_without_harness(listing: str) -> str:
    entries = [
        item for item in listing.rstrip("\0").split("\0")
        if not item.partition("\t")[2].startswith("tests/")
    ]
    return "\0".join(entries) + ("\0" if entries else "")


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


@contextmanager
def execution_root(
    repository_root: Path,
    accepted_main: str,
    *,
    source_root: Path,
    profile: Mapping[str, Any],
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
        except OSError as exc:
            raise authority.LifecycleAuthorityError("current safety harness preparation failed") from exc
        _verify_execution_root(repository_root, root, tree, candidate_listing, bindings)
        try:
            yield root
        finally:
            _verify_execution_root(repository_root, root, tree, candidate_listing, bindings)
            verify_source_bytes(source_root, tree, expected_listing=listing)


def run_profile(
    root: Path,
    profile: Mapping[str, Any],
    *,
    expected_profile: Mapping[str, Any],
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
            result = transport._run_isolated_python(
                transport._isolated_python_command(
                    transport._ISOLATED_SOURCE_LAUNCHER,
                    "ENTRYPOINT", str(root), command["argv"][1], "main",
                ),
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
