# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source-neutral execution of exact accepted-main safety harnesses."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from . import bootstrap_source_admission as transport
from . import lifecycle_authority as authority


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
    if observed != results:
        if (
            not reports or any(not isinstance(item, str) or item not in invariants for item in reports)
            or reports != sorted(set(reports))
        ):
            raise authority.LifecycleAuthorityError("current safety failure report invalid")
        raise authority.LifecycleAuthorityError("current safety assertions failed: " + ", ".join(reports))
    if reports != list(invariants):
        raise authority.LifecycleAuthorityError("current safety invariant coverage incomplete")
