# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded mechanical renumber evidence; this module grants no authority.

Source topology, protected-main inventory, signatures, lifecycle eligibility and
provider safety must be authenticated by the maintained issuer before these
pure byte comparisons can participate in an Exceptional Continuation.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import io
import re
import tempfile
import tokenize
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import lifecycle_publication as publication
from . import bootstrap_source_admission as bootstrap
from . import exact_source_safety
from .fast_path import digest_json


MAX_BLOB_BYTES = 1024 * 1024
MAX_REPLACEMENTS = 4096
MAX_CHANGED_PATHS = 32
MAX_DELTA_BYTES = 4 * 1024 * 1024
MAX_IMPORTED_OBJECTS = 4096
# The minimal authenticated #786 closure is 10,286,316 bytes. A 16 MiB global
# policy leaves 6,490,900 bytes of fixed headroom while the materially different
# candidate and historical classes remain independently capped below.
MAX_IMPORTED_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_VALIDATION_BYTES = 8 * 1024 * 1024
MAX_HISTORICAL_PREREQUISITE_BYTES = 3 * 1024 * 1024
MAX_IMPORTED_COMMITS = 2048
MAX_COMMIT_DEPTH = 1024
MAX_PARENT_FANOUT = 64
MAX_TREE_DEPTH = 64
MAX_COMMIT_BYTES = 64 * 1024
HISTORY_COMMIT_OBJECTS = "HISTORY_COMMIT_OBJECTS"
STRUCTURAL_TREE_OBJECTS = "STRUCTURAL_TREE_OBJECTS"
OWNER_SOURCE_BLOBS = "OWNER_SOURCE_BLOBS"
DERIVED_RENUMBER_OBJECTS = "DERIVED_RENUMBER_OBJECTS"
CANDIDATE_VALIDATION_TREE_CLOSURE = "CANDIDATE_VALIDATION_TREE_CLOSURE"
ACCEPTED_HARNESS_BLOBS = "ACCEPTED_HARNESS_BLOBS"
VALIDATION_DEPENDENCY_BLOBS = "VALIDATION_DEPENDENCY_BLOBS"
HISTORICAL_PREREQUISITE_TREES = "HISTORICAL_PREREQUISITE_TREES"
OTHER = "OTHER"
IMPORT_CATEGORIES = (
    HISTORY_COMMIT_OBJECTS,
    STRUCTURAL_TREE_OBJECTS,
    OWNER_SOURCE_BLOBS,
    DERIVED_RENUMBER_OBJECTS,
    CANDIDATE_VALIDATION_TREE_CLOSURE,
    ACCEPTED_HARNESS_BLOBS,
    VALIDATION_DEPENDENCY_BLOBS,
    HISTORICAL_PREREQUISITE_TREES,
    OTHER,
)
IMPORT_CATEGORY_BYTE_LIMITS = {
    CANDIDATE_VALIDATION_TREE_CLOSURE: MAX_CANDIDATE_VALIDATION_BYTES,
    HISTORICAL_PREREQUISITE_TREES: MAX_HISTORICAL_PREREQUISITE_BYTES,
}
_VERSION = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})", re.ASCII)
_VERSION_BYTES = frozenset(b"0123456789.")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", re.ASCII)
SOURCE_PATH = "scripts/secpal_pr_review/fast_path.py"
TRUST_REGISTRY_PATH = (
    ".agents/skills/secpal-pr-review/references/repositories.json"
)
TRUST_REGISTRY_SCHEMA_PATH = (
    ".agents/skills/secpal-pr-review/references/repositories.schema.json"
)
COLLISION_AUTHORITY_PATH = "scripts/secpal_pr_review/version_collision.py"
EXACT_SOURCE_SAFETY_PATH = "scripts/secpal_pr_review/exact_source_safety.py"
VALIDATION_ACTIONS_PATH = "scripts/secpal-pr-review-actions.py"
COLLISION_VALIDATION_PROJECTION_PATHS = (
    VALIDATION_ACTIONS_PATH,
    "tests/secpal-pr-review-actions-unit.py",
    "tests/secpal-resolve-fixed-threads-unit.py",
)
COLLISION_VALIDATION_DEPENDENCY_PATHS = ("package.json", "package-lock.json")
COLLISION_VALIDATION_BUNDLE_PATHS = (
    "tests/fixtures/secpal-pr-review-actions/issue771-exact-candidate.bundle",
)
COLLISION_VALIDATION_SNAPSHOT_PATHS = (
    "tests/secpal-pr-review-skill-policy.sh",
)
# Each closed inventory is keyed by the accepted fixture blob identity. The
# bundle list contains exactly its audited external ref-delta bases; reachability
# from its authenticated prerequisite commits is independently verified.
COLLISION_VALIDATION_BUNDLE_BASE_OBJECTS = {
    "56f589c7e9ab6c5e2e6c7fd2db3444a7dd7561e9": (
        ("tree", "43642afd3066209f07912228781e368bbfea17d4"),
        ("tree", "b116142f42dde678905e4ea6b35ad65090333564"),
        ("tree", "9bc987d14d1a9ce7f6e40fa3b0d17e8c523f0a23"),
        ("tree", "ab94780c2df070f759808926bfe5bf3c2ceddfe2"),
        ("tree", "231ee8e47376f09e4b984188aab19b5b76080d9c"),
        ("tree", "a7e256784f302e80cf4f1aab07df4f0698867519"),
        ("tree", "5f14bde41978b9bf9c12a981883d39c8e8657db1"),
        ("tree", "8a893666ee6dc2ea8cb64d6e03ef160af4dfe951"),
        ("tree", "67fadcbe1fa0c67a658129c2825e143ca6f39ba4"),
        ("tree", "9a78b1448d2b7a296dae0e9796e8a7c51969b679"),
        ("blob", "88144c97182c95559e6e0064a7f4f24fb918ffc0"),
        ("blob", "62058f49cbc88320963d362dd1ed11c9bcd2c9dc"),
        ("blob", "660f1c27c5b0ab577a9de71a4bca3a806d736f0d"),
        ("blob", "63e57c2df58a0415691d0d0870fa954b676e5bd3"),
        ("blob", "24f6e6cf116bbb741843d8da3e4a189e16923174"),
        ("blob", "046d34ff115127ef7e3b459ebe7620056738f80f"),
        ("blob", "46e5f260802319bf3ee05d1dbb3c0cda9d9e1639"),
        ("blob", "aedf34c46a49bb589169f2b2a1ac664b4b86bbfc"),
        ("blob", "edb184325addf9da3c2fe279acb8403b914cfeb1"),
        ("blob", "b8a27537f7a5685f2745a03da362008742f260ea"),
        ("blob", "78d379455cf3e4b34d023e67d621e67c20bdc18b"),
        ("blob", "b1dc232e42f9dd6c6dff889d303ff44126acbc3e"),
        ("blob", "3c803689e5f66ba8a16419518c8ae0655b4160d8"),
        ("blob", "810eb90147a30c7e9f35db4386f91a234785e577"),
        ("blob", "36c54529315959d1838fe7b1ce6c51d1f58cd5e2"),
    ),
}
# The accepted snapshot command reads only these baseline paths. Its commit and
# root tree still authenticate their identities; unrelated baseline blobs do not
# become execution or materialization authority.
COLLISION_VALIDATION_SNAPSHOT_PREREQUISITE_PATHS = {
    "ebb541cd2b02fa7da51f3a08b509c76b2b7326d9": (
        "scripts/secpal-pr-review.py",
        "templates/polyscope-codex-AGENTS.md",
        ".github/workflows/copilot-review-memory.yml",
        "scripts/copilot-review-tool.sh",
        "docs/copilot-review-automation.md",
        "AGENTS.md",
    ),
}
FAMILY_KIND = "TWO_PARENT_READY_INTEGRATION"
TRIGGER = "IMMUTABLE_EVIDENCE_VERSION_COLLISION"


class VersionCollisionError(ValueError):
    """A purported version-only source change is not exact and bounded."""


def _version(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise VersionCollisionError("version identity is not canonical major.minor")
    major, minor = value.split(".")
    return int(major), int(minor)


def _text(value: bytes) -> str:
    if not isinstance(value, bytes) or not 0 < len(value) <= MAX_BLOB_BYTES:
        raise VersionCollisionError("changed blob exceeds the bounded text profile")
    try:
        text = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VersionCollisionError("changed blob is not UTF-8") from exc
    if b"\x00" in value:
        raise VersionCollisionError("changed blob contains a NUL byte")
    return text


def _token_at(blob: bytes, token: bytes, offset: int) -> bool:
    end = offset + len(token)
    return (
        blob.startswith(token, offset)
        and (offset == 0 or blob[offset - 1] not in _VERSION_BYTES)
        and (end == len(blob) or blob[end] not in _VERSION_BYTES)
    )


def verify_blob_renumber(
    predecessor: bytes,
    successor: bytes,
    occupied_version: str,
    free_version: str,
) -> tuple[tuple[int, int], ...]:
    """Return exact old/new byte offsets, allowing no other byte difference.

Unchanged occurrences remain untouched. Offsets are paired rather than assumed
equal, so a change in version-token length cannot hide a later textual edit.
The returned positions are evidence only, not authorized replacement positions.
"""

    occupied = _version(occupied_version)
    free = _version(free_version)
    if occupied[0] != free[0] or free <= occupied:
        raise VersionCollisionError("renumber must increase within the compatible major")
    _text(predecessor)
    _text(successor)
    old_token = occupied_version.encode("ascii")
    new_token = free_version.encode("ascii")
    old_offset = 0
    new_offset = 0
    positions: list[tuple[int, int]] = []
    while old_offset < len(predecessor) and new_offset < len(successor):
        if _token_at(predecessor, old_token, old_offset) and _token_at(
            successor, new_token, new_offset
        ):
            if len(positions) >= MAX_REPLACEMENTS:
                raise VersionCollisionError("version replacement count exceeds the bound")
            positions.append((old_offset, new_offset))
            old_offset += len(old_token)
            new_offset += len(new_token)
        elif predecessor[old_offset] == successor[new_offset]:
            old_offset += 1
            new_offset += 1
        else:
            raise VersionCollisionError("source delta contains a non-version byte change")
    if old_offset != len(predecessor) or new_offset != len(successor) or not positions:
        raise VersionCollisionError("source delta is empty or contains an extra byte change")
    return tuple(positions)


def _git(root: Path, arguments: list[str], maximum: int) -> bytes:
    result = publication._run_git(root, arguments)
    if result.returncode != 0 or len(result.stdout) > maximum:
        raise VersionCollisionError("bounded Git source observation failed")
    return result.stdout


def _verify_python_version_tokens(blob: bytes, offsets: tuple[int, ...], version: str) -> None:
    text = _text(blob)
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line.encode("utf-8")))

    def byte_offset(position: tuple[int, int]) -> int:
        row, column = position
        return starts[row - 1] + len(lines[row - 1][:column].encode("utf-8"))

    spans = []
    try:
        interpolated = [
            (starts[node.lineno - 1] + node.col_offset,
             starts[node.end_lineno - 1] + node.end_col_offset)
            for node in ast.walk(ast.parse(text)) if isinstance(node, ast.JoinedStr)
        ]
        if any(start <= offset < end for offset in offsets for start, end in interpolated):
            raise VersionCollisionError("Python version token replacement enters an interpolated string")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in {tokenize.STRING, tokenize.COMMENT}:
                spans.append((byte_offset(token.start), byte_offset(token.end)))
    except (
        tokenize.TokenError,
        IndentationError,
        SyntaxError,
        IndexError,
        RecursionError,
        ValueError,
    ) as exc:
        raise VersionCollisionError("Python version token source is malformed") from exc
    if any(not any(start <= offset and offset + len(version) <= end for start, end in spans) for offset in offsets):
        raise VersionCollisionError("Python version token replacement changes executable syntax")


def _verify_python_test_renumber(
    predecessor: bytes,
    successor: bytes,
    positions: tuple[tuple[int, int], ...],
    occupied_version: str,
    free_version: str,
) -> None:
    """Admit only comment text; test execution and comparisons remain immutable."""

    def safe_spans(blob: bytes) -> tuple[tuple[int, int], ...]:
        text = _text(blob)
        lines = text.splitlines(keepends=True)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line.encode("utf-8")))

        def byte_offset(position: tuple[int, int]) -> int:
            row, column = position
            return starts[row - 1] + len(
                lines[row - 1][:column].encode("utf-8")
            )

        try:
            return tuple(
                (byte_offset(token.start), byte_offset(token.end))
                for token in tokenize.generate_tokens(io.StringIO(text).readline)
                if token.type == tokenize.COMMENT
            )
        except (
            tokenize.TokenError,
            IndentationError,
            SyntaxError,
            IndexError,
            RecursionError,
            ValueError,
        ) as exc:
            raise VersionCollisionError(
                "Python test version token source is malformed"
            ) from exc

    predecessor_spans = safe_spans(predecessor)
    successor_spans = safe_spans(successor)
    if any(
        not any(
            start <= old_offset
            and old_offset + len(occupied_version) <= end
            for start, end in predecessor_spans
        )
        or not any(
            start <= new_offset
            and new_offset + len(free_version) <= end
            for start, end in successor_spans
        )
        for old_offset, new_offset in positions
    ):
        raise VersionCollisionError(
            "Python test version token is not a provably inert expectation"
        )


def _oid(value: str) -> str:
    if not isinstance(value, str) or _OID.fullmatch(value) is None:
        raise VersionCollisionError("source object identity is malformed")
    return value


def _path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 1024
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise VersionCollisionError("changed path is outside the bounded path profile")
    return value


def verify_tree_renumber(
    repository_root: Path,
    predecessor_tree: str,
    resulting_tree: str,
    *,
    occupied_version: str,
    free_version: str,
    source_scope: frozenset[str],
    authorized_paths: tuple[str, ...],
) -> dict[str, Any]:
    """Derive raw Git delta evidence, without authenticating caller constraints.

The issuer must independently derive source_scope, verify signed exact path
authorization, and authenticate both trees. Passing this function alone never
proves a collision or authorizes a lifecycle transition.
"""

    if (
        not isinstance(source_scope, frozenset)
        or not isinstance(authorized_paths, tuple)
        or not 0 < len(authorized_paths) <= MAX_CHANGED_PATHS
    ):
        raise VersionCollisionError("changed path authorization is not bounded")
    paths = tuple(_path(path) for path in authorized_paths)
    if paths != tuple(sorted(set(paths))) or not set(paths) <= source_scope:
        raise VersionCollisionError("changed path authorization differs from delivery scope")
    predecessor_tree = _oid(predecessor_tree)
    resulting_tree = _oid(resulting_tree)
    for tree in (predecessor_tree, resulting_tree):
        if _git(repository_root, ["cat-file", "-t", tree], 16) != b"tree\n":
            raise VersionCollisionError("source tree identity is not a tree")
    raw = _git(
        repository_root,
        ["diff-tree", "--no-commit-id", "--raw", "-z", "-r", "--no-renames",
         "--no-abbrev", "--no-ext-diff", "--no-textconv", predecessor_tree, resulting_tree, "--"],
        MAX_CHANGED_PATHS * 2048,
    )
    fields = raw.split(b"\x00")
    if fields[-1] != b"" or not 0 < len(fields) - 1 <= MAX_CHANGED_PATHS * 2 or len(fields) % 2 != 1:
        raise VersionCollisionError("raw tree delta is empty, malformed or excessive")
    records: list[tuple[str, str, str, str]] = []
    try:
        for offset in range(0, len(fields) - 1, 2):
            metadata = fields[offset].decode("ascii").split(" ")
            if len(metadata) != 5:
                raise VersionCollisionError("raw tree delta metadata is malformed")
            old_mode, new_mode, old_blob, new_blob, status = metadata
            if (
                old_mode not in {":100644", ":100755"}
                or old_mode[1:] != new_mode
                or status != "M"
                or old_blob == new_blob
            ):
                raise VersionCollisionError("tree delta adds, deletes, renames or changes mode/type")
            path = _path(fields[offset + 1].decode("utf-8", errors="strict"))
            records.append((path, new_mode, _oid(old_blob), _oid(new_blob)))
    except UnicodeDecodeError as exc:
        raise VersionCollisionError("raw tree delta is not bounded UTF-8 text") from exc
    if tuple(sorted(record[0] for record in records)) != paths:
        raise VersionCollisionError("actual changed paths differ from exact authorization")
    changes = []
    total_bytes = 0
    total_replacements = 0
    for path, mode, old_blob, new_blob in sorted(records):
        blobs = []
        for blob in (old_blob, new_blob):
            raw_size = _git(repository_root, ["cat-file", "-s", blob], 32)
            if re.fullmatch(rb"[0-9]+\n", raw_size) is None:
                raise VersionCollisionError("changed blob size is malformed")
            size = int(raw_size)
            total_bytes += size
            if not 0 < size <= MAX_BLOB_BYTES or total_bytes > MAX_DELTA_BYTES:
                raise VersionCollisionError("source delta byte count exceeds the bound")
            data = _git(repository_root, ["cat-file", "blob", blob], MAX_BLOB_BYTES)
            if len(data) != size:
                raise VersionCollisionError("changed blob size differs from observed object")
            blobs.append(data)
        positions = verify_blob_renumber(blobs[0], blobs[1], occupied_version, free_version)
        if path.startswith("tests/") and not path.endswith(".py"):
            raise VersionCollisionError(
                "test version token source has no provably inert profile"
            )
        if path.endswith(".py"):
            _verify_python_version_tokens(blobs[0], tuple(pair[0] for pair in positions), occupied_version)
            _verify_python_version_tokens(blobs[1], tuple(pair[1] for pair in positions), free_version)
            if path.startswith("tests/"):
                _verify_python_test_renumber(
                    blobs[0], blobs[1], positions, occupied_version, free_version,
                )
        total_replacements += len(positions)
        if total_replacements > MAX_REPLACEMENTS:
            raise VersionCollisionError("source delta token count exceeds the bound")
        changes.append({
            "path": path, "mode": mode, "predecessor_blob": old_blob,
            "resulting_blob": new_blob,
            "replacement_offsets": [list(pair) for pair in positions],
        })
    evidence = {
        "predecessor_tree": predecessor_tree,
        "resulting_tree": resulting_tree,
        "occupied_version": occupied_version,
        "free_version": free_version,
        "changed_paths": list(paths),
        "changes": changes,
    }
    return {**evidence, "source_delta_digest": digest_json(evidence)}


class _SourceDeclarations:
    def __init__(self, source: bytes):
        try:
            self.text = _text(source)
            self.module = ast.parse(self.text)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise VersionCollisionError("version authority source is malformed") from exc
        self.assignments: dict[str, list[ast.expr]] = {}
        for node in self.module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assignments.setdefault(target.id, []).append(node.value)
        protected = frozenset({
            "READY_INTEGRATION_KIND",
            "READY_INTEGRATION_KEYS",
            "READY_INTEGRATION_V12_KEYS",
            "READY_INTEGRATION_KEYS_BY_VERSION",
            "READY_INTEGRATION_ATTESTATION_BY_VERSION",
        })
        owner_functions = frozenset({
            "normalize_ready_integration_evidence",
            "create_ready_integration_attestation",
        })
        mutable_tables = frozenset({
            "READY_INTEGRATION_KEYS_BY_VERSION",
            "READY_INTEGRATION_ATTESTATION_BY_VERSION",
        })
        reserved = protected | owner_functions | {"frozenset"}
        declared_targets = {
            id(target)
            for node in self.module.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name) and target.id in protected
        }
        declared_functions = {
            id(node)
            for node in self.module.body
            if isinstance(node, ast.FunctionDef)
            and node.name in owner_functions
        }
        if any(
            node.decorator_list
            for node in self.module.body
            if isinstance(node, ast.FunctionDef)
            and node.name in owner_functions
        ):
            raise VersionCollisionError(
                "version declaration is mutated or shadowed"
            )
        parents = {
            id(child): node
            for node in ast.walk(self.module)
            for child in ast.iter_child_nodes(node)
        }

        def rooted_in_protected(node: ast.AST) -> bool:
            while isinstance(node, (ast.Attribute, ast.Subscript)):
                node = node.value
            return isinstance(node, ast.Name) and node.id in protected

        for node in ast.walk(self.module):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in reserved
            ):
                raise VersionCollisionError(
                    "version declaration is mutated or shadowed"
                )
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id in mutable_tables
            ):
                parent = parents.get(id(node))
                direct_get = (
                    isinstance(parent, ast.Attribute)
                    and parent.value is node
                    and parent.attr == "get"
                    and isinstance(parents.get(id(parent)), ast.Call)
                    and parents[id(parent)].func is parent
                )
                direct_item = (
                    isinstance(parent, ast.Subscript)
                    and parent.value is node
                    and isinstance(parent.ctx, ast.Load)
                )
                if not direct_get and not direct_item:
                    raise VersionCollisionError(
                        "version declaration is mutated or shadowed"
                    )
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and node.id in reserved
                and id(node) not in declared_targets
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if isinstance(node, ast.arg) and node.arg in reserved:
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name in reserved
                and id(node) not in declared_functions
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                (alias.asname or alias.name.split(".")[0]) in reserved
                for alias in node.names
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, ast.ExceptHandler)
                and node.name in reserved
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, (ast.Attribute, ast.Subscript))
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and (
                    rooted_in_protected(node)
                    or (
                        isinstance(node, ast.Attribute)
                        and node.attr in reserved
                    )
                    or (
                        isinstance(node, ast.Subscript)
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "__builtins__"
                    )
                )
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                and isinstance(node.value, ast.Name)
                and node.value.id in protected
            ):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                if any(
                    not isinstance(target, ast.Name) or target.id not in protected
                    for target in targets
                ):
                    raise VersionCollisionError("version declaration is ambiguously aliased")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {
                    "exec", "eval", "globals", "locals", "vars", "setattr", "delattr",
                }
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if isinstance(node, ast.Call) and any(
                any(
                    isinstance(descendant, ast.Name)
                    and descendant.id in protected
                    for descendant in ast.walk(argument)
                )
                for argument in (
                    *node.args,
                    *(keyword.value for keyword in node.keywords),
                )
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in protected
                and node.func.attr in {
                    "add", "append", "clear", "discard", "extend", "insert",
                    "pop", "remove", "setdefault", "sort", "update",
                }
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in {"globals", "locals", "vars"}
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in protected
            ):
                raise VersionCollisionError("version declaration is mutated or shadowed")

    def declaration(self, name: str, depth: int = 0) -> Any:
        values = self.assignments.get(name, [])
        if len(values) != 1 or depth > 16:
            raise VersionCollisionError("version declaration is absent, repeated or recursive")
        return self.literal(values[0], depth + 1)

    def literal(self, node: ast.expr, depth: int = 0) -> Any:
        if depth > 16:
            raise VersionCollisionError("version declaration nesting exceeds the bound")
        if isinstance(node, ast.Constant) and type(node.value) in {str, bool}:
            return node.value
        if isinstance(node, ast.Name):
            return self.declaration(node.id, depth + 1)
        if isinstance(node, ast.Tuple):
            return tuple(self.literal(item, depth + 1) for item in node.elts)
        if isinstance(node, ast.Set):
            values = [self.literal(item, depth + 1) for item in node.elts]
            if any(not isinstance(value, str) for value in values) or len(set(values)) != len(values):
                raise VersionCollisionError("version field declaration is ambiguous")
            return frozenset(values)
        if isinstance(node, ast.Dict):
            result = {}
            for key, value in zip(node.keys, node.values):
                if key is None:
                    raise VersionCollisionError("version mapping expansion is forbidden")
                parsed_key = self.literal(key, depth + 1)
                if parsed_key in result:
                    raise VersionCollisionError("version mapping repeats an identity")
                result[parsed_key] = self.literal(value, depth + 1)
            return result
        if (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset" and len(node.args) == 1 and not node.keywords
        ):
            value = self.literal(node.args[0], depth + 1)
            if isinstance(value, frozenset):
                return value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self.literal(node.left, depth + 1)
            right = self.literal(node.right, depth + 1)
            if isinstance(left, frozenset) and isinstance(right, frozenset):
                return left | right
        raise VersionCollisionError("version declaration is not a closed literal expression")

    def function(self, name: str) -> ast.FunctionDef:
        functions = [node for node in self.module.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(functions) != 1:
            raise VersionCollisionError("version authority function is absent or ambiguous")
        return functions[0]


def _assigned_expression(function: ast.FunctionDef, name: str) -> ast.expr:
    values = [node.value for node in function.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise VersionCollisionError("version dispatch is absent or ambiguous")
    return values[0]


def _expression_is(node: ast.expr, expected: str) -> bool:
    return ast.dump(node) == ast.dump(ast.parse(expected, mode="eval").body)


def _mapped_limit_identity(
    normalizer: ast.FunctionDef, occupied: str
) -> ast.Constant | None:
    """Return the sole maintained mapped-version limit gate identity.

    The field and attestation tables are the primary mapped dispatch.  The real
    v1.2 owner additionally applies the registered finite item limit only to
    that version.  Admit exactly that maintained guard, rather than treating an
    arbitrary comparison containing the version string as ownership.
    """

    identities = [
        node
        for node in ast.walk(normalizer)
        if isinstance(node, ast.Constant) and node.value == occupied
    ]
    if not identities:
        return None
    if len(identities) != 1:
        raise VersionCollisionError(
            "candidate version identity uses unsupported custom dispatch"
        )
    template = ast.parse(
        f'''if schema_version == "{occupied}":
    limits = registry.get("limits") if isinstance(registry, dict) else None
    maximum_items = limits.get("maximum_items") if isinstance(limits, dict) else None
    if (
        isinstance(maximum_items, bool)
        or not isinstance(maximum_items, int)
        or maximum_items < 1
    ):
        raise SecurityBlocker("registered integration item limit is invalid")
    if isinstance(raw_delta, list) and len(raw_delta) > maximum_items:
        raise SecurityBlocker("Ready integration delta exceeds the registered item limit")
'''
    ).body[0]
    matching = [
        statement
        for statement in normalizer.body
        if isinstance(statement, ast.If)
        and ast.dump(statement, include_attributes=False)
        == ast.dump(template, include_attributes=False)
    ]
    if len(matching) != 1:
        raise VersionCollisionError(
            "candidate version identity uses unsupported custom dispatch"
        )
    return identities[0]


def _owner_replacement_offsets(source: bytes, occupied: str) -> tuple[int, ...]:
    """Derive the complete maintained implementation-owner token set."""

    declarations = _SourceDeclarations(source)
    inventory = inventory_from_source(source)
    if occupied not in inventory["versions"]:
        raise VersionCollisionError("candidate version identity is not maintained")
    identities: list[ast.Constant] = []
    mapped = all(
        len(declarations.assignments.get(name, [])) == 1
        and isinstance(declarations.assignments[name][0], ast.Dict)
        for name in (
            "READY_INTEGRATION_KEYS_BY_VERSION",
            "READY_INTEGRATION_ATTESTATION_BY_VERSION",
        )
    )
    normalizer = declarations.function("normalize_ready_integration_evidence")
    if mapped:
        for name in (
            "READY_INTEGRATION_KEYS_BY_VERSION",
            "READY_INTEGRATION_ATTESTATION_BY_VERSION",
        ):
            table = declarations.assignments[name][0]
            for key in table.keys:
                identity = key.elts[0] if isinstance(key, ast.Tuple) and key.elts else key
                if isinstance(identity, ast.Constant) and identity.value == occupied:
                    identities.append(identity)
        if len(identities) != 3:
            raise VersionCollisionError("candidate version identity keys are incomplete")
        limit_identity = _mapped_limit_identity(normalizer, occupied)
        if limit_identity is not None:
            identities.append(limit_identity)
    else:
        comparisons = [
            node
            for node in ast.walk(normalizer)
            if isinstance(node, ast.Compare)
            and _expression_is(node, f'schema_version == "{occupied}"')
        ]
        if len(comparisons) != 3:
            raise VersionCollisionError("candidate version identity dispatch is incomplete")
        identities.extend(comparison.comparators[0] for comparison in comparisons)
        guards = [
            node
            for node in ast.walk(normalizer)
            if isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotIn)
            and _expression_is(node.left, "schema_version")
            and isinstance(node.comparators[0], ast.Set)
        ]
        guard_identities = [
            item
            for guard in guards
            for item in guard.comparators[0].elts
            if isinstance(item, ast.Constant) and item.value == occupied
        ]
        fields = _assigned_expression(
            declarations.function("create_ready_integration_attestation"), "fields"
        )
        schema_values = [
            value
            for key, value in zip(fields.keys, fields.values)
            if isinstance(key, ast.Constant) and key.value == "schema_version"
        ] if isinstance(fields, ast.Dict) else []
        attestation_identities = [
            value.body
            for value in schema_values
            if isinstance(value, ast.IfExp)
            and _expression_is(value.test, "eligibility_bound")
            and isinstance(value.body, ast.Constant)
            and value.body.value == occupied
        ]
        if len(guard_identities) != 1 or len(attestation_identities) != 1:
            raise VersionCollisionError("candidate version identity dispatch is incomplete")
        identities.extend((*guard_identities, *attestation_identities))
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    positions = []
    for identity in identities:
        start = starts[identity.lineno - 1] + identity.col_offset
        end = starts[identity.end_lineno - 1] + identity.end_col_offset
        if source[start:end] not in {f'"{occupied}"'.encode(), f"'{occupied}'".encode()}:
            raise VersionCollisionError("candidate version identity literal is not canonical")
        positions.append(start + 1)
    positions = sorted(positions)
    if len(positions) != len(set(positions)):
        raise VersionCollisionError("candidate version identity positions are ambiguous")
    return tuple(positions)


def _derive_owner_renumber(
    source: bytes,
    occupied: str,
    free: str,
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    """Replace only the independently derived implementation-owner tokens."""

    old_token = occupied.encode("ascii")
    new_token = free.encode("ascii")
    offsets = _owner_replacement_offsets(source, occupied)
    pieces: list[bytes] = []
    pairs: list[tuple[int, int]] = []
    old_end = 0
    new_end = 0
    for old_offset in offsets:
        if old_offset < old_end or not _token_at(source, old_token, old_offset):
            raise VersionCollisionError(
                "candidate version identity literal is not canonical"
            )
        prefix = source[old_end:old_offset]
        pieces.extend((prefix, new_token))
        new_offset = new_end + len(prefix)
        pairs.append((old_offset, new_offset))
        old_end = old_offset + len(old_token)
        new_end = new_offset + len(new_token)
    pieces.append(source[old_end:])
    successor = b"".join(pieces)
    if verify_blob_renumber(source, successor, occupied, free) != tuple(pairs):
        raise VersionCollisionError(
            "derived owner renumber differs from its exact byte replacement set"
        )
    return successor, tuple(pairs)


def _verify_owner_renumber(source: bytes, occupied: str, delta: dict[str, Any]) -> None:
    positions = _owner_replacement_offsets(source, occupied)
    owner = [change for change in delta["changes"] if change["path"] == SOURCE_PATH]
    if len(owner) != 1 or [pair[0] for pair in owner[0]["replacement_offsets"]] != list(positions):
        raise VersionCollisionError("source version identity positions differ from the complete owning dispatch")
    if any(change["path"] != SOURCE_PATH and not (
        change["path"].startswith("tests/") or change["path"].endswith(".md")
    ) for change in delta["changes"]):
        raise VersionCollisionError("version identity edit extends outside its implementation, tests or documentation")


def inventory_from_source(source: bytes) -> dict[str, Any]:
    """Parse the maintained Ready-integration declaration forms without execution.

Field and attestation mappings are observable immutable schema semantics. The
implementation digest additionally binds both complete owning functions; a
different implementation alone is deliberately insufficient collision proof.
This parser is observation/normalization, not protected-main authentication.
"""

    try:
        declarations = _SourceDeclarations(source)
        kind = declarations.declaration("READY_INTEGRATION_KIND")
        if kind != FAMILY_KIND:
            raise VersionCollisionError("version evidence family is unsupported")
        normalizer = declarations.function("normalize_ready_integration_evidence")
        attestation = declarations.function("create_ready_integration_attestation")
        dispatches = [node for node in normalizer.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "expected_keys" for target in node.targets)]
        dispatch = _assigned_expression(normalizer, "expected_keys") if dispatches else ast.Constant(None)
        legacy = (
            not dispatches
            and sum(isinstance(node, ast.Compare) and _expression_is(node, 'value.get("schema_version") != "1.1"')
                    for node in ast.walk(normalizer)) == 1
            and sum(isinstance(node, ast.Compare) and _expression_is(node, 'set(value) != READY_INTEGRATION_KEYS')
                    for node in ast.walk(normalizer)) == 1
        )
        if _expression_is(dispatch, "READY_INTEGRATION_KEYS_BY_VERSION.get(schema_version)"):
            version_fields = declarations.declaration("READY_INTEGRATION_KEYS_BY_VERSION")
            mapping = declarations.declaration("READY_INTEGRATION_ATTESTATION_BY_VERSION")
            mapping_use = [node.value for node in attestation.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Tuple) for target in node.targets)]
            if len(mapping_use) != 1 or not _expression_is(
                mapping_use[0], 'READY_INTEGRATION_ATTESTATION_BY_VERSION[(normalized["schema_version"], eligibility_bound)]'
            ):
                raise VersionCollisionError("attestation version mapping is not the selected authority")
        elif legacy or _expression_is(dispatch, 'READY_INTEGRATION_V12_KEYS if schema_version == "1.2" else READY_INTEGRATION_KEYS'):
            version_fields = {"1.1": declarations.declaration("READY_INTEGRATION_KEYS")}
            if not legacy:
                version_fields["1.2"] = declarations.declaration("READY_INTEGRATION_V12_KEYS")
            guards = [node for node in ast.walk(normalizer) if isinstance(node, ast.Compare)
                      and _expression_is(node, 'schema_version not in {"1.1", "1.2"}')]
            if not legacy and len(guards) != 1:
                raise VersionCollisionError("accepted version inventory dispatch changed")
            fields = _assigned_expression(attestation, "fields")
            if not isinstance(fields, ast.Dict):
                raise VersionCollisionError("attestation mapping is not a literal dictionary")
            selected = {key.value: value for key, value in zip(fields.keys, fields.values)
                        if isinstance(key, ast.Constant) and key.value in {"schema_version", "kind"}}
            if set(selected) != {"schema_version", "kind"}:
                raise VersionCollisionError("attestation identity is incomplete")
            mapping = {}
            for bound in (False, True):
                identity = []
                for field in ("schema_version", "kind"):
                    value = selected[field]
                    if not isinstance(value, ast.IfExp) or not _expression_is(value.test, "eligibility_bound"):
                        raise VersionCollisionError("attestation selection has unsupported semantics")
                    identity.append(declarations.literal(value.body if bound else value.orelse))
                for version in version_fields:
                    mapping[(version, bound)] = tuple(identity)
        else:
            raise VersionCollisionError("version dispatch has unsupported semantics")
        if not isinstance(version_fields, dict) or not 0 < len(version_fields) <= 64 or not isinstance(mapping, dict):
            raise VersionCollisionError("version inventory is not bounded")
        expected_keys = {(version, bound) for version in version_fields for bound in (False, True)}
        if set(mapping) != expected_keys:
            raise VersionCollisionError("attestation inventory differs from evidence inventory")
        versions = {}
        for version in sorted(version_fields, key=_version):
            fields = version_fields[version]
            if not isinstance(fields, frozenset) or not {"kind", "schema_version"} <= fields or len(fields) > 128:
                raise VersionCollisionError("immutable version fields are malformed")
            attestations = []
            for bound in (False, True):
                identity = mapping[(version, bound)]
                if not isinstance(identity, tuple) or len(identity) != 2 or not all(isinstance(item, str) for item in identity):
                    raise VersionCollisionError("immutable attestation mapping is malformed")
                _version(identity[0])
                attestations.append({"eligibility_bound": bound, "version": identity[0], "kind": identity[1]})
            versions[version] = {"fields": sorted(fields), "attestations": attestations}
        implementation = [ast.dump(function, include_attributes=False) for function in (normalizer, attestation)]
        return {"kind": kind, "versions": versions, "implementation_digest": digest_json(implementation)}
    except (TypeError, KeyError, RecursionError, UnicodeError) as exc:
        raise VersionCollisionError("immutable version inventory is malformed") from exc


def _derive_collision_identity(
    baseline: dict[str, Any],
    accepted: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive the sole compatible collision result before observing a successor."""

    if any(item.get("kind") != FAMILY_KIND for item in (baseline, accepted, candidate)):
        raise VersionCollisionError("collision evidence family changed")
    introduced = set(candidate["versions"]) - set(baseline["versions"])
    if len(introduced) != 1:
        raise VersionCollisionError("candidate does not introduce exactly one immutable version")
    occupied = next(iter(introduced))
    prior_semantic = candidate["versions"][occupied]
    accepted_semantic = accepted["versions"].get(occupied)
    if accepted_semantic is None or accepted_semantic == prior_semantic:
        raise VersionCollisionError("accepted main has no different semantic at the candidate version")
    if {key: value for key, value in candidate["versions"].items() if key != occupied} != baseline["versions"]:
        raise VersionCollisionError("candidate changes an existing immutable schema mapping")
    major, minor = _version(occupied)
    free = f"{major}.{minor + 1}"
    while free in accepted["versions"] or free in candidate["versions"]:
        minor += 1
        free = f"{major}.{minor + 1}"
    _version(free)
    expected = {key: copy.deepcopy(value) for key, value in candidate["versions"].items() if key != occupied}
    expected[free] = copy.deepcopy(prior_semantic)
    return ({
        "version_family": FAMILY_KIND,
        "occupied_version": occupied,
        "free_version": free,
        "candidate_semantic": copy.deepcopy(prior_semantic),
        "accepted_semantic": copy.deepcopy(accepted_semantic),
        "inventory": copy.deepcopy(accepted),
        "inventory_digest": digest_json(accepted),
    }, expected)


def derive_collision(
    baseline: dict[str, Any], accepted: dict[str, Any],
    candidate: dict[str, Any], successor: dict[str, Any],
) -> dict[str, Any]:
    """Admit an observed immutable schema collision; these arguments are not authority."""

    collision, expected = _derive_collision_identity(
        baseline, accepted, candidate,
    )
    if successor.get("kind") != FAMILY_KIND or successor["versions"] != expected:
        raise VersionCollisionError("successor skips lowest-free identity or changes immutable mappings")
    return collision


@dataclass(frozen=True)
class _CollisionSeal:
    digest: str


@dataclass(frozen=True)
class VerifiedVersionCollision:
    projection: bytes
    _seal: _CollisionSeal

    def to_dict(self) -> dict[str, Any]:
        from . import lifecycle_authority as authority

        if not isinstance(self._seal, _CollisionSeal) or hashlib.sha256(self.projection).hexdigest() != self._seal.digest:
            raise VersionCollisionError("collision result has no intact verifier seal")
        result = authority.loads_closed_json(self.projection)
        if authority.canonical_json_bytes(result) != self.projection:
            raise VersionCollisionError("collision result is not canonical")
        return result


@dataclass(frozen=True)
class CollisionValidationExecution:
    collision: VerifiedVersionCollision
    repository_entry: dict[str, Any]
    registry_binding: dict[str, Any]
    execution_root: Path
    verify_execution_root: Any
    object_accounting: dict[str, Any]


def _read_bounded_blob(root: Path, treeish: str, path: str) -> bytes:
    path = _path(path)
    entry = _git(root, ["ls-tree", "-z", _oid(treeish), "--", path], 2048)
    parts = entry.split(b"\t")
    if len(parts) != 2 or parts[1] != path.encode() + b"\x00":
        raise VersionCollisionError("authenticated source blob is missing")
    metadata = parts[0].decode("ascii").split(" ")
    if len(metadata) != 3 or metadata[:2] != ["100644", "blob"]:
        raise VersionCollisionError("authenticated source is not a regular blob")
    blob = _oid(metadata[2])
    size = _git(root, ["cat-file", "-s", blob], 32)
    if re.fullmatch(rb"[0-9]+\n", size) is None or not 0 < int(size) <= MAX_BLOB_BYTES:
        raise VersionCollisionError("authenticated source exceeds the bound")
    return _git(root, ["cat-file", "blob", blob], MAX_BLOB_BYTES)


def _authenticated_blob(
    root: Path,
    treeish: str,
    path: str,
) -> tuple[str, str, int, bytes]:
    """Read one exact regular blob together with its immutable Git binding."""

    path = _path(path)
    entry = _git(root, ["ls-tree", "-z", _oid(treeish), "--", path], 2048)
    metadata, separator, observed = entry.rstrip(b"\x00").partition(b"\t")
    try:
        fields = metadata.decode("ascii", errors="strict").split()
    except UnicodeDecodeError as exc:
        raise VersionCollisionError(
            "authenticated validation source listing is malformed"
        ) from exc
    if (
        separator != b"\t"
        or observed != path.encode("utf-8")
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
    ):
        raise VersionCollisionError(
            "authenticated validation source is unavailable"
        )
    oid = _oid(fields[2])
    size_raw = _git(root, ["cat-file", "-s", oid], 32)
    if re.fullmatch(rb"[0-9]+\n", size_raw) is None:
        raise VersionCollisionError(
            "authenticated validation source size is malformed"
        )
    size = int(size_raw)
    if not 0 < size <= MAX_BLOB_BYTES:
        raise VersionCollisionError(
            "authenticated validation source exceeds the bound"
        )
    source = _git(root, ["cat-file", "blob", oid], MAX_BLOB_BYTES)
    if len(source) != size:
        raise VersionCollisionError(
            "authenticated validation source size changed"
        )
    return fields[0], oid, size, source


def _tree_regular_blob_paths(
    root: Path,
    treeish: str,
    prefix: str | None = None,
) -> tuple[str, ...]:
    if prefix is not None:
        prefix = _path(prefix)
    arguments = ["ls-tree", "-rz", "--full-tree", _oid(treeish)]
    if prefix is not None:
        arguments.extend(("--", prefix))
    listing = _git(
        root,
        arguments,
        MAX_DELTA_BYTES,
    )
    paths = []
    for entry in listing.rstrip(b"\x00").split(b"\x00"):
        metadata, separator, raw_path = entry.partition(b"\t")
        try:
            fields = metadata.decode("ascii", errors="strict").split()
            path = _path(raw_path.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, VersionCollisionError) as exc:
            raise VersionCollisionError(
                "accepted validation harness inventory is malformed"
            ) from exc
        if (
            separator != b"\t"
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or (prefix is not None and not path.startswith(prefix + "/"))
        ):
            raise VersionCollisionError(
                "accepted validation harness inventory is malformed"
            )
        paths.append(path)
    if not paths or len(paths) != len(set(paths)):
        raise VersionCollisionError(
            "accepted validation harness inventory is ambiguous"
        )
    return tuple(sorted(paths))


def _collision_validation_command_paths(commands: Any) -> frozenset[str]:
    """Derive every direct repository path in the registered command set."""

    paths: set[str] = set()
    if not isinstance(commands, list) or not commands:
        raise VersionCollisionError(
            "collision validation command set is unavailable"
        )
    for command in commands:
        argv = command.get("argv") if isinstance(command, dict) else None
        if not isinstance(argv, list) or not argv:
            raise VersionCollisionError(
                "collision validation command set is malformed"
            )
        if len(argv) == 4 and argv[:3] == ["python3", "-m", "unittest"]:
            paths.add(_path(argv[3]))
        elif isinstance(argv[0], str) and argv[0].startswith("./"):
            paths.add(_path(argv[0][2:]))
    return frozenset(paths)


def _bundle_prerequisites(source: bytes) -> tuple[str, ...]:
    """Return commit prerequisites from one bounded, authenticated v2 bundle."""

    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_BLOB_BYTES:
        raise VersionCollisionError(
            "accepted validation bundle exceeds the bound"
        )
    header, separator, pack = source.partition(b"\n\nPACK")
    if separator != b"\n\nPACK" or not pack:
        raise VersionCollisionError("accepted validation bundle is malformed")
    try:
        lines = header.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise VersionCollisionError(
            "accepted validation bundle header is malformed"
        ) from exc
    if not lines or lines[0] != "# v2 git bundle":
        raise VersionCollisionError("accepted validation bundle is malformed")
    prerequisites = []
    references = []
    reference_phase = False
    for line in lines[1:]:
        identity, space, description = line.partition(" ")
        if not space or not description or any(ord(character) < 32 for character in line):
            raise VersionCollisionError(
                "accepted validation bundle header is malformed"
            )
        if identity.startswith("-") and not reference_phase:
            prerequisites.append(_oid(identity[1:]))
        elif (
            not identity.startswith("-")
            and description.startswith("refs/heads/")
            and ".." not in description
        ):
            reference_phase = True
            references.append((_oid(identity), description))
        else:
            raise VersionCollisionError(
                "accepted validation bundle header is malformed"
            )
    if (
        not prerequisites
        or not references
        or len(prerequisites) != len(set(prerequisites))
        or len(references) != len(set(references))
        or len(prerequisites) > MAX_PARENT_FANOUT
        or len(references) > MAX_PARENT_FANOUT
    ):
        raise VersionCollisionError(
            "accepted validation bundle inventory is ambiguous"
        )
    return tuple(prerequisites)


def _validation_object_prerequisites(
    path: str,
    source: bytes,
) -> tuple[str, ...]:
    """Derive only maintained historical object prerequisites."""

    if path in COLLISION_VALIDATION_BUNDLE_PATHS:
        return _bundle_prerequisites(source)
    if path == "tests/secpal-pr-review-skill-policy.sh":
        matches = re.findall(
            rb'^P21_BASELINE="([0-9a-f]{40})"$', source, re.MULTILINE
        )
        if len(matches) == 1:
            return (_oid(matches[0].decode("ascii")),)
    raise VersionCollisionError(
        "accepted validation object prerequisite owner drifted"
    )


def _validation_object_requirements(
    path: str,
    blob_oid: str,
    source: bytes,
) -> tuple[
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
]:
    """Bind exact execution requirements to one authenticated fixture blob."""

    prerequisites = _validation_object_prerequisites(path, source)
    if path in COLLISION_VALIDATION_BUNDLE_PATHS:
        required_objects = COLLISION_VALIDATION_BUNDLE_BASE_OBJECTS.get(
            _oid(blob_oid)
        )
        if required_objects is None:
            raise VersionCollisionError(
                "accepted validation bundle object requirements are unavailable"
            )
        return prerequisites, required_objects, ()
    required_paths = COLLISION_VALIDATION_SNAPSHOT_PREREQUISITE_PATHS.get(
        _oid(blob_oid)
    )
    if required_paths is None or len(prerequisites) != 1:
        raise VersionCollisionError(
            "accepted validation snapshot requirements are unavailable"
        )
    return (
        prerequisites,
        (),
        tuple((prerequisites[0], path) for path in required_paths),
    )


def _collision_validation_authority(
    root: Path,
    collision: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive the registry, commands, and narrow projection from trusted roots."""

    from . import fast_path
    from . import lifecycle_authority as authority

    required = {
        "repository",
        "predecessor_head",
        "predecessor_tree",
        "resulting_tree",
        "protected_main",
        "delivery_scope_base",
        "occupied_version",
        "free_version",
        "delta",
    }
    if not isinstance(collision, dict) or not required <= set(collision):
        raise VersionCollisionError(
            "collision validation authority is incomplete"
        )
    repository = collision["repository"]
    predecessor = _oid(collision["predecessor_head"])
    predecessor_tree = _oid(collision["predecessor_tree"])
    resulting_tree = _oid(collision["resulting_tree"])
    protected_main = _oid(collision["protected_main"])
    validation_epoch = _oid(collision["delivery_scope_base"])
    occupied = collision["occupied_version"]
    implementation = collision["free_version"]
    if repository != "SecPal/.github":
        raise VersionCollisionError(
            "collision validation repository is unsupported"
        )
    if collision["delta"].get("changed_paths") != [SOURCE_PATH]:
        raise VersionCollisionError(
            "collision candidate changes validation or non-owner bytes"
        )

    registry_source = _authenticated_blob(root, validation_epoch, TRUST_REGISTRY_PATH)
    schema_source = _authenticated_blob(
        root, validation_epoch, TRUST_REGISTRY_SCHEMA_PATH
    )
    for candidate_identity in (predecessor_tree, resulting_tree):
        if (
            _authenticated_blob(root, candidate_identity, TRUST_REGISTRY_PATH)
            != registry_source
            or _authenticated_blob(
                root, candidate_identity, TRUST_REGISTRY_SCHEMA_PATH
            )
            != schema_source
        ):
            raise VersionCollisionError(
                "candidate registry authority differs from the accepted epoch"
            )
    try:
        registry = authority.loads_closed_json(registry_source[3])
        schema = schema_source[3].decode("utf-8", errors="strict")
        validated_registry = fast_path.validate_repository_registry_structure(
            registry,
            authoritative_schema_raw=schema,
        )
    except (
        UnicodeDecodeError,
        authority.LifecycleAuthorityError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise VersionCollisionError(
            "accepted collision validation registry is invalid"
        ) from exc
    entries = [
        entry
        for entry in validated_registry.get("repositories", [])
        if isinstance(entry, dict) and entry.get("repository") == repository
    ]
    if len(entries) != 1:
        raise VersionCollisionError(
            "accepted collision validation registry has no unique repository"
        )
    entry = entries[0]
    binding = fast_path.validation_registry_projection(entry)
    commands = binding["validation"]

    candidate_paths = frozenset(_tree_regular_blob_paths(root, resulting_tree))
    selected_paths = _collision_validation_command_paths(commands)
    if (
        not selected_paths <= candidate_paths
        or not set(COLLISION_VALIDATION_PROJECTION_PATHS) <= candidate_paths
        or not set(COLLISION_VALIDATION_PROJECTION_PATHS[1:]) <= selected_paths
    ):
        raise VersionCollisionError(
            "registered collision validation escapes the authenticated candidate"
        )
    projection_sources = []
    for path in COLLISION_VALIDATION_PROJECTION_PATHS:
        predecessor_source = _authenticated_blob(root, predecessor_tree, path)
        candidate_source = _authenticated_blob(root, resulting_tree, path)
        if predecessor_source != candidate_source:
            raise VersionCollisionError(
                "collision candidate changes validation projection bytes: " + path
            )
        mode, oid, size, source = candidate_source
        try:
            projected, offsets = (
                exact_source_safety._collision_projection_bytes(
                    path,
                    source,
                    occupied_version=occupied,
                    implementation_identity=implementation,
                )
            )
        except authority.LifecycleAuthorityError as exc:
            raise VersionCollisionError(
                "accepted collision validation projection cannot be derived: "
                + path
            ) from exc
        projection_sources.append({
            "path": path,
            "mode": mode,
            "candidate_blob_oid": oid,
            "candidate_size": size,
            "projected_blob_oid": _git_object_oid("blob", projected, len(oid)),
            "projected_size": len(projected),
            "current_identity_offsets": [list(item) for item in offsets],
        })

    dependencies = []
    for path in COLLISION_VALIDATION_DEPENDENCY_PATHS:
        accepted = _authenticated_blob(root, validation_epoch, path)
        predecessor_dependency = _authenticated_blob(root, predecessor_tree, path)
        candidate = _authenticated_blob(root, resulting_tree, path)
        if predecessor_dependency != accepted or candidate != accepted:
            raise VersionCollisionError(
                "candidate validation dependency differs from accepted main"
            )
        dependencies.append({
            "path": path,
            "mode": accepted[0],
            "blob_oid": accepted[1],
            "size": accepted[2],
        })

    object_dependencies = []
    for path in (
        *COLLISION_VALIDATION_BUNDLE_PATHS,
        *COLLISION_VALIDATION_SNAPSHOT_PATHS,
    ):
        accepted = _authenticated_blob(root, validation_epoch, path)
        predecessor_fixture = _authenticated_blob(root, predecessor_tree, path)
        candidate_fixture = _authenticated_blob(root, resulting_tree, path)
        if predecessor_fixture != accepted or candidate_fixture != accepted:
            raise VersionCollisionError(
                "candidate object fixture differs from accepted main"
            )
        prerequisites, required_objects, required_paths = (
            _validation_object_requirements(path, accepted[1], accepted[3])
        )
        prerequisite_trees = []
        for commit in prerequisites:
            try:
                tree, _parents = fast_path._commit_topology(
                    _git(root, ["cat-file", "commit", commit], MAX_COMMIT_BYTES)
                    .decode("utf-8", errors="strict")
                )
            except (UnicodeDecodeError, fast_path.SecurityBlocker) as exc:
                raise VersionCollisionError(
                    "accepted validation prerequisite tree is malformed"
                ) from exc
            prerequisite_trees.append({"commit": commit, "tree": tree})
        object_dependencies.append({
            "path": path,
            "mode": accepted[0],
            "blob_oid": accepted[1],
            "size": accepted[2],
            "prerequisites": prerequisite_trees,
            "required_objects": [
                {"kind": kind, "oid": oid}
                for kind, oid in required_objects
            ],
            "required_paths": [
                {"commit": commit, "path": required_path}
                for commit, required_path in required_paths
            ],
        })

    issuer_sources = []
    for path in (
        COLLISION_AUTHORITY_PATH,
        EXACT_SOURCE_SAFETY_PATH,
        VALIDATION_ACTIONS_PATH,
    ):
        mode, oid, size, _source = _authenticated_blob(
            root, protected_main, path,
        )
        issuer_sources.append({
            "path": path,
            "mode": mode,
            "blob_oid": oid,
            "size": size,
        })
    profile = {
        "schema_version": "1.0",
        "policy": "IMMUTABLE_EVIDENCE_VERSION_COLLISION_COMPLETE_VALIDATION",
        "accepted_main": protected_main,
        "validation_epoch": validation_epoch,
        "accepted_main_sources": issuer_sources,
        "candidate_predecessor_head": predecessor,
        "candidate_predecessor_tree": predecessor_tree,
        "candidate_tree": resulting_tree,
        "candidate_test_delta": [],
        "collision_digest": digest_json(
            validation_collision_projection(collision)
        ),
        "occupied_version": occupied,
        "implementation_identity": implementation,
        "registry": {
            "source_commit": validation_epoch,
            "path": TRUST_REGISTRY_PATH,
            "mode": registry_source[0],
            "blob_oid": registry_source[1],
            "size": registry_source[2],
            "schema_path": TRUST_REGISTRY_SCHEMA_PATH,
            "schema_mode": schema_source[0],
            "schema_blob_oid": schema_source[1],
            "schema_size": schema_source[2],
        },
        "validation_dependencies": dependencies,
        "validation_object_dependencies": object_dependencies,
        "validation_object_dependencies_digest": digest_json(
            object_dependencies
        ),
        "validation_command_set": copy.deepcopy(commands),
        "validation_command_set_digest": digest_json(commands),
        "validation_projection_sources": projection_sources,
        "validation_projection_digest": digest_json(projection_sources),
    }
    return entry, {
        **binding,
        "collision_validation_authority": profile,
    }


def _read_source(root: Path, commit: str) -> bytes:
    return _read_bounded_blob(root, commit, SOURCE_PATH)


def _read_authenticated_registry(root: Path, protected_main: str) -> bytes:
    """Read the fixed registry blob already imported from accepted main."""

    return _read_bounded_blob(root, protected_main, TRUST_REGISTRY_PATH)


def _changed_paths(root: Path, before: str, after: str, limit: int) -> tuple[str, ...]:
    raw = _git(root, ["diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
                      "--no-renames", _oid(before), _oid(after), "--"], limit * 1025)
    if not raw or not raw.endswith(b"\x00"):
        raise VersionCollisionError("source scope has no exact changed paths")
    try:
        paths = tuple(sorted(_path(value.decode("utf-8")) for value in raw[:-1].split(b"\x00")))
    except UnicodeError as exc:
        raise VersionCollisionError("source scope is not UTF-8") from exc
    if len(paths) > limit or len(set(paths)) != len(paths):
        raise VersionCollisionError("source scope is excessive or ambiguous")
    return paths


def _derive_collision_from_git(
    root: Path, *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_head: str, protected_main: str,
) -> dict[str, Any]:
    from . import lifecycle_orchestration as orchestration

    if repository != "SecPal/.github" or any(type(value) is not int or value <= 0 for value in (delivery_issue, pull_request)):
        raise VersionCollisionError("collision repository or delivery identity is unsupported")
    resulting_tree = orchestration._immutable_commit_tree(root, repository, resulting_head)
    parents = _git(root, ["rev-list", "--parents", "-n", "1", _oid(resulting_head)], 256).decode("ascii").split()
    if parents != [resulting_head, predecessor_head]:
        raise VersionCollisionError("collision successor is not an exact single-parent commit")
    return {**_derive_collision_tree(
        root, repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
        predecessor_head=predecessor_head, resulting_tree=resulting_tree, protected_main=protected_main,
    ), "resulting_head": resulting_head}


def _derive_collision_tree(
    root: Path, *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_tree: str, protected_main: str,
) -> dict[str, Any]:
    from . import lifecycle_orchestration as orchestration

    if repository != "SecPal/.github" or any(type(value) is not int or value <= 0 for value in (delivery_issue, pull_request)):
        raise VersionCollisionError("collision repository or delivery identity is unsupported")
    trees = {head: orchestration._immutable_commit_tree(root, repository, head)
             for head in (predecessor_head, protected_main)}
    if _git(root, ["cat-file", "-t", _oid(resulting_tree)], 16) != b"tree\n":
        raise VersionCollisionError("collision result is not a tree")
    bases = _git(root, ["merge-base", "--all", _oid(protected_main), _oid(predecessor_head)], 256).decode("ascii").split()
    if len(bases) != 1:
        raise VersionCollisionError("delivery source scope has no unique merge base")
    base = _oid(bases[0])
    scope = _changed_paths(root, base, predecessor_head, 4096)
    changed = _changed_paths(root, trees[predecessor_head], resulting_tree, MAX_CHANGED_PATHS)
    sources = {head: _read_source(root, head) for head in (base, protected_main, predecessor_head, resulting_tree)}
    inventory = {head: inventory_from_source(source) for head, source in sources.items()}
    collision = derive_collision(inventory[base], inventory[protected_main], inventory[predecessor_head], inventory[resulting_tree])
    delta = verify_tree_renumber(
        root, trees[predecessor_head], resulting_tree,
        occupied_version=collision["occupied_version"], free_version=collision["free_version"],
        source_scope=frozenset(scope), authorized_paths=changed,
    )
    _verify_owner_renumber(sources[predecessor_head], collision["occupied_version"], delta)
    return {
        "trigger": TRIGGER, "repository": repository, "delivery_issue": delivery_issue,
        "pull_request": pull_request, "predecessor_head": predecessor_head,
        "predecessor_tree": trees[predecessor_head],
        "resulting_tree": resulting_tree, "protected_main": protected_main,
        "protected_main_tree": trees[protected_main], "delivery_scope_base": base,
        "delivery_scope": list(scope), "delivery_scope_digest": digest_json(list(scope)),
        **collision, "delta": delta,
    }


def _observe_main() -> str:
    return bootstrap._normalize_protected_main(bootstrap._observe_protected_main()).head_sha


def _source_repository_state(
    root: Path,
) -> tuple[bytes, tuple[int, bytes], tuple[int, bytes], bytes]:
    """Snapshot bounded semantic refs around authenticated source reads."""

    refs = _git(
        root,
        [
            "for-each-ref",
            "--sort=refname",
            "--format=%(refname)%00%(objectname)%00%(symref)",
        ],
        MAX_BLOB_BYTES,
    )
    symbolic = publication._run_git(root, ["symbolic-ref", "-q", "HEAD"])
    head = publication._run_git(root, ["rev-parse", "--verify", "HEAD"])
    if (
        symbolic.returncode not in {0, 1}
        or len(symbolic.stdout) > 4096
        or head.returncode not in {0, 128}
        or len(head.stdout) > 4096
    ):
        raise VersionCollisionError("source repository state is malformed")
    return (
        refs,
        (symbolic.returncode, symbolic.stdout),
        (head.returncode, head.stdout),
        _git(root, ["count-objects", "-v"], 4096),
    )


class _BoundedObjectImporter:
    def __init__(self, source: Path, destination: Path):
        self.source = source
        self.destination = destination
        self.imported: set[str] = set()
        self.objects: dict[str, bytes] = {}
        self.object_kinds: dict[str, str] = {}
        self.source_objects: dict[str, tuple[str, bytes]] = {}
        self.histories: set[str] = set()
        self.commit_trees: dict[str, str] = {}
        self.complete_trees: set[str] = set()
        self.total_bytes = 0
        self._object_memberships: dict[str, set[str]] = {}
        self._object_references: dict[str, int] = {}
        self._physical_attribution: dict[str, str] = {}
        self._physical_bytes_by_category = {
            category: 0 for category in IMPORT_CATEGORIES
        }
        self._historical_phase_start_bytes: int | None = None

    def _record_reference(self, oid: str, category: str) -> None:
        if category not in IMPORT_CATEGORIES:
            raise VersionCollisionError(
                "source object accounting category is unsupported"
            )
        self._object_memberships.setdefault(oid, set()).add(category)
        self._object_references[oid] = self._object_references.get(oid, 0) + 1

    def _check_physical_capacity(self, size: int, category: str) -> None:
        if self.total_bytes + size > MAX_IMPORTED_BYTES:
            raise VersionCollisionError(
                "source object closure exceeds the byte bound"
            )
        category_limit = IMPORT_CATEGORY_BYTE_LIMITS.get(category)
        if (
            category_limit is not None
            and self._physical_bytes_by_category[category] + size
            > category_limit
        ):
            raise VersionCollisionError(
                "source object closure exceeds the "
                + category.lower().replace("_", "-")
                + " byte bound"
            )

    def _record_physical_import(
        self, oid: str, kind: str, raw: bytes, category: str,
    ) -> None:
        self.imported.add(oid)
        self.objects[oid] = raw
        self.object_kinds[oid] = kind
        self.total_bytes += len(raw)
        self._physical_attribution[oid] = category
        self._physical_bytes_by_category[category] += len(raw)

    def accounting(self) -> dict[str, Any]:
        """Return ephemeral OID-deduplicated diagnostics with fixed attribution.

        The first category in the closed acquisition order that physically
        materializes an OID owns its sole byte charge. Later categories retain
        semantic membership without another physical charge.
        """

        bytes_by_category = {category: 0 for category in IMPORT_CATEGORIES}
        objects_by_category = {category: 0 for category in IMPORT_CATEGORIES}
        semantic_objects_by_category = {
            category: 0 for category in IMPORT_CATEGORIES
        }
        semantic_bytes_by_category = {
            category: 0 for category in IMPORT_CATEGORIES
        }
        object_memberships = []
        for oid, raw in sorted(self.objects.items()):
            memberships = self._object_memberships.get(oid, {OTHER})
            ordered = [
                category for category in IMPORT_CATEGORIES
                if category in memberships
            ]
            attributed = self._physical_attribution[oid]
            bytes_by_category[attributed] += len(raw)
            objects_by_category[attributed] += 1
            for category in ordered:
                semantic_objects_by_category[category] += 1
                semantic_bytes_by_category[category] += len(raw)
            object_memberships.append({
                "oid": oid,
                "kind": self.object_kinds[oid],
                "bytes": len(raw),
                "memberships": ordered,
                "attributed_category": attributed,
                "references": self._object_references.get(oid, 0),
            })
        historical_bytes = bytes_by_category[HISTORICAL_PREREQUISITE_TREES]
        historical_start = self._historical_phase_start_bytes
        return {
            "physical_byte_attribution_rule": (
                "FIRST_PHYSICAL_MATERIALIZATION_IN_CLOSED_IMPORT_ORDER"
            ),
            "total_unique_objects": len(self.objects),
            "total_unique_bytes": sum(len(raw) for raw in self.objects.values()),
            "source_bytes_before_historical_prerequisites": (
                None
                if historical_start is None
                else historical_start
                - bytes_by_category[DERIVED_RENUMBER_OBJECTS]
            ),
            "unique_bytes_before_historical_prerequisites": historical_start,
            "bytes_required_by_historical_prerequisites": historical_bytes,
            "final_minimal_required_bytes": sum(
                len(raw) for raw in self.objects.values()
            ),
            "bytes_by_category": bytes_by_category,
            "objects_by_category": objects_by_category,
            "semantic_objects_by_category": semantic_objects_by_category,
            "semantic_bytes_by_category": semantic_bytes_by_category,
            "duplicate_oid_references": sum(
                max(0, item["references"] - 1)
                for item in object_memberships
            ),
            "object_memberships": object_memberships,
        }

    @staticmethod
    def _tree_entries(raw: bytes) -> tuple[tuple[bytes, bytes, str], ...]:
        entries = []
        offset = 0
        while offset < len(raw):
            delimiter = raw.find(b"\x00", offset)
            if delimiter < 0 or delimiter + 21 > len(raw):
                raise VersionCollisionError("source tree entry is malformed")
            metadata = raw[offset:delimiter].split(b" ", 1)
            if (
                len(metadata) != 2
                or metadata[0]
                not in {b"40000", b"100644", b"100755", b"120000", b"160000"}
                or not metadata[1]
                or b"/" in metadata[1]
                or metadata[1] in {b".", b".."}
            ):
                raise VersionCollisionError("source tree object mode or name is malformed")
            entries.append(
                (metadata[0], metadata[1], raw[delimiter + 1:delimiter + 21].hex())
            )
            offset = delimiter + 21
        return tuple(entries)

    def _transfer_tree_children(
        self,
        oid: str,
        raw: bytes,
        depth: int,
        *,
        import_blobs: bool,
        category: str,
    ) -> None:
        for mode, _name, child in self._tree_entries(raw):
            if mode == b"40000":
                self.transfer(
                    child,
                    "tree",
                    depth + 1,
                    import_blobs=import_blobs,
                    category=category,
                )
            elif mode != b"160000" and import_blobs:
                self.transfer(
                    child, "blob", depth + 1, category=category,
                )
        if import_blobs:
            self.complete_trees.add(oid)

    def transfer(
        self,
        oid: str,
        kind: str,
        depth: int = 0,
        *,
        import_blobs: bool = True,
        category: str = OTHER,
    ) -> bytes:
        oid = _oid(oid)
        self._record_reference(oid, category)
        if depth > MAX_TREE_DEPTH:
            raise VersionCollisionError("source object closure exceeds the bound")
        if oid in self.objects:
            raw = self.objects[oid]
            if self.object_kinds[oid] != kind:
                raise VersionCollisionError(
                    "source object identity changed type"
                )
            if kind == "tree" and import_blobs and oid not in self.complete_trees:
                self._transfer_tree_children(
                    oid,
                    raw,
                    depth,
                    import_blobs=True,
                    category=category,
                )
            return raw
        if len(self.imported) >= MAX_IMPORTED_OBJECTS:
            raise VersionCollisionError("source object closure exceeds the bound")
        raw = self._read_source_object(oid, kind)
        self._check_physical_capacity(len(raw), category)
        written = publication._run_git(
            self.destination, ["hash-object", "-w", "-t", kind, "--stdin"], input_bytes=raw,
        )
        if written.returncode != 0 or written.stdout != (oid + "\n").encode("ascii"):
            raise VersionCollisionError("verified source object import failed")
        self._record_physical_import(oid, kind, raw, category)
        self.source_objects[oid] = (kind, raw)
        if kind == "tree":
            self._transfer_tree_children(
                oid,
                raw,
                depth,
                import_blobs=import_blobs,
                category=category,
            )
        return raw

    def _read_source_object(self, oid: str, kind: str) -> bytes:
        size = _git(self.source, ["cat-file", "-s", oid], 32)
        limit = MAX_COMMIT_BYTES if kind == "commit" else MAX_BLOB_BYTES
        if re.fullmatch(rb"[0-9]+\n", size) is None or not 0 <= int(size) <= limit:
            raise VersionCollisionError("source object exceeds the bound")
        raw = _git(self.source, ["cat-file", kind, oid], limit)
        header = kind.encode("ascii") + b" " + str(len(raw)).encode("ascii") + b"\x00"
        digest = (
            hashlib.sha1(header + raw).hexdigest()
            if len(oid) == 40
            else hashlib.sha256(header + raw).hexdigest()
        )
        if digest != oid:
            raise VersionCollisionError(
                "source object hash differs from its claimed identity"
            )
        return raw

    def verify_source_objects_unchanged(self) -> None:
        """Re-read every bounded source object that granted authority."""

        for oid, (kind, expected) in sorted(self.source_objects.items()):
            try:
                observed = self._read_source_object(oid, kind)
            except VersionCollisionError as exc:
                raise VersionCollisionError(
                    "source object bytes changed during collision authentication"
                ) from exc
            if observed != expected:
                raise VersionCollisionError(
                    "source object bytes changed during collision authentication"
                )

    def transfer_path(
        self, tree: str, path: str, *, category: str = OTHER,
    ) -> str:
        """Transfer the exact blob named by one already bounded tree path."""

        tree = _oid(tree)
        encoded_parts = _path(path).encode("utf-8").split(b"/")
        current = tree
        for index, part in enumerate(encoded_parts):
            raw = self.transfer(
                current, "tree", import_blobs=False, category=category,
            )
            matches = [
                (mode, child)
                for mode, name, child in self._tree_entries(raw)
                if name == part
            ]
            if len(matches) != 1:
                raise VersionCollisionError("required source tree path is unavailable")
            mode, child = matches[0]
            final = index == len(encoded_parts) - 1
            if final:
                if mode not in {b"100644", b"100755"}:
                    raise VersionCollisionError(
                        "required source tree path is not a regular blob"
                    )
                self.transfer(child, "blob", category=category)
                return child
            if mode != b"40000":
                raise VersionCollisionError("required source tree path is malformed")
            current = child
        raise VersionCollisionError("required source tree path is unavailable")

    def transfer_tree_inventory(
        self, tree: str, *, category: str,
    ) -> dict[str, str]:
        """Authenticate tree reachability without materializing every blob."""

        inventory: dict[str, str] = {}
        pending = [(_oid(tree), 0)]
        while pending:
            oid, depth = pending.pop()
            if depth > MAX_TREE_DEPTH:
                raise VersionCollisionError(
                    "source object closure exceeds the bound"
                )
            existing = inventory.get(oid)
            if existing is not None:
                if existing != "tree":
                    raise VersionCollisionError(
                        "source object identity changed type"
                    )
                continue
            raw = self.transfer(
                oid,
                "tree",
                depth,
                import_blobs=False,
                category=category,
            )
            inventory[oid] = "tree"
            for mode, _name, child in reversed(self._tree_entries(raw)):
                if mode == b"40000":
                    kind = "tree"
                    pending.append((child, depth + 1))
                elif mode in {b"100644", b"100755"}:
                    kind = "blob"
                else:
                    raise VersionCollisionError(
                        "historical prerequisite contains a forbidden object type"
                    )
                previous = inventory.get(child)
                if previous is not None and previous != kind:
                    raise VersionCollisionError(
                        "source object identity changed type"
                    )
                if kind == "blob":
                    inventory[child] = kind
                if len(inventory) > MAX_IMPORTED_OBJECTS:
                    raise VersionCollisionError(
                        "historical prerequisite inventory exceeds the object bound"
                    )
        return inventory

    def commit(self, oid: str) -> tuple[str, tuple[str, ...]]:
        from . import fast_path

        try:
            return fast_path._commit_topology(
                self.transfer(
                    oid, "commit", category=HISTORY_COMMIT_OBJECTS,
                ).decode("utf-8", errors="strict")
            )
        except (UnicodeError, fast_path.SecurityBlocker) as exc:
            raise VersionCollisionError("source commit headers are malformed") from exc

    def history(self, head: str) -> str:
        """Import one complete, finite raw-parent closure without trusting source ancestry."""

        head = _oid(head)
        if len(head) != 40:
            raise VersionCollisionError(
                "GitHub collision history requires SHA-1 commit identities"
            )
        pending = [(head, 0)]
        while pending:
            commit_oid, depth = pending.pop()
            if depth > MAX_COMMIT_DEPTH:
                raise VersionCollisionError(
                    "source commit history depth exceeds the bound"
                )
            if commit_oid in self.histories:
                continue
            if len(self.histories) >= MAX_IMPORTED_COMMITS:
                raise VersionCollisionError(
                    "source commit history count exceeds the bound"
                )
            tree, parents = self.commit(commit_oid)
            if len(parents) > MAX_PARENT_FANOUT:
                raise VersionCollisionError(
                    "source commit parent fanout exceeds the bound"
                )
            self.histories.add(commit_oid)
            self.commit_trees[commit_oid] = tree
            pending.extend((parent, depth + 1) for parent in reversed(parents))
        return self.commit_trees[head]

    def import_histories_and_merge_base(self, left: str, right: str) -> str:
        """Import both raw histories and recompute their unique base in isolation."""

        left = _oid(left)
        right = _oid(right)
        self.history(left)
        self.history(right)
        observed = publication._run_git(
            self.destination, ["merge-base", "--all", left, right]
        )
        if observed.returncode not in {0, 1} or len(observed.stdout) > 256:
            raise VersionCollisionError(
                "imported histories have no unique merge base"
            )
        try:
            bases = observed.stdout.decode("ascii", errors="strict").split()
        except UnicodeDecodeError as exc:
            raise VersionCollisionError(
                "imported histories have no unique merge base"
            ) from exc
        if len(bases) != 1 or _oid(bases[0]) not in self.histories:
            raise VersionCollisionError(
                "imported histories have no unique merge base"
            )
        base = bases[0]
        for head in (left, right):
            ancestry = publication._run_git(
                self.destination, ["merge-base", "--is-ancestor", base, head]
            )
            if ancestry.returncode != 0:
                raise VersionCollisionError(
                    "imported merge base is unreachable from a source head"
                )
        return base

    def materialize_derived(
        self,
        kind: str,
        oid: str,
        raw: bytes,
    ) -> None:
        """Write one independently reconstructed object into the isolated DB."""

        oid = _oid(oid)
        self._record_reference(oid, DERIVED_RENUMBER_OBJECTS)
        if kind not in {"blob", "tree"}:
            raise VersionCollisionError("derived object type is unsupported")
        limit = MAX_BLOB_BYTES
        if len(raw) > limit:
            raise VersionCollisionError("derived object exceeds the bound")
        if _git_object_oid(kind, raw, len(oid)) != oid:
            raise VersionCollisionError(
                "derived object hash differs from its recomputed identity"
            )
        if kind == "tree":
            self._tree_entries(raw)
        if oid in self.objects:
            if self.object_kinds[oid] != kind or self.objects[oid] != raw:
                raise VersionCollisionError(
                    "derived object collides with authenticated source bytes"
                )
            return
        if len(self.imported) >= MAX_IMPORTED_OBJECTS:
            raise VersionCollisionError("source object closure exceeds the bound")
        self._check_physical_capacity(len(raw), DERIVED_RENUMBER_OBJECTS)
        written = publication._run_git(
            self.destination,
            ["hash-object", "-w", "-t", kind, "--stdin"],
            input_bytes=raw,
        )
        if written.returncode != 0 or written.stdout != (oid + "\n").encode(
            "ascii"
        ):
            raise VersionCollisionError("verified derived object import failed")
        self._record_physical_import(
            oid, kind, raw, DERIVED_RENUMBER_OBJECTS,
        )


def _transfer_validation_object_requirements(
    importer: _BoundedObjectImporter,
    prerequisites: tuple[str, ...],
    required_objects: tuple[tuple[str, str], ...],
    required_paths: tuple[tuple[str, str], ...],
) -> None:
    """Acquire only execution-consumed objects from authenticated prerequisites."""

    if importer._historical_phase_start_bytes is None:
        importer._historical_phase_start_bytes = importer.total_bytes
    if (
        not prerequisites
        or len(prerequisites) != len(set(prerequisites))
        or len(required_objects) != len(set(required_objects))
        or len(required_paths) != len(set(required_paths))
    ):
        raise VersionCollisionError(
            "validation prerequisite requirements are ambiguous"
        )
    prerequisite_trees = {}
    for commit in prerequisites:
        if commit not in importer.commit_trees:
            raise VersionCollisionError(
                "validation prerequisite is outside authenticated history"
            )
        importer.transfer(
            commit, "commit", category=HISTORICAL_PREREQUISITE_TREES,
        )
        prerequisite_trees[commit] = importer.commit_trees[commit]

    reachable: dict[str, str] = {}
    if required_objects:
        for tree in prerequisite_trees.values():
            for oid, kind in importer.transfer_tree_inventory(
                tree, category=HISTORICAL_PREREQUISITE_TREES,
            ).items():
                previous = reachable.get(oid)
                if previous is not None and previous != kind:
                    raise VersionCollisionError(
                        "historical prerequisite object changed type"
                    )
                reachable[oid] = kind
                if len(reachable) > MAX_IMPORTED_OBJECTS:
                    raise VersionCollisionError(
                        "historical prerequisite inventory exceeds the object bound"
                    )
        for kind, oid in required_objects:
            if kind not in {"tree", "blob"} or reachable.get(_oid(oid)) != kind:
                raise VersionCollisionError(
                    "validation bundle base is outside authenticated prerequisites"
                )
            importer.transfer(
                oid, kind, category=HISTORICAL_PREREQUISITE_TREES,
            )

    for commit, path in required_paths:
        tree = prerequisite_trees.get(_oid(commit))
        if tree is None:
            raise VersionCollisionError(
                "validation snapshot path has no authenticated prerequisite"
            )
        importer.transfer_path(
            tree, path, category=HISTORICAL_PREREQUISITE_TREES,
        )


def _git_object_oid(kind: str, raw: bytes, oid_length: int) -> str:
    if kind not in {"blob", "tree"} or oid_length not in {40, 64}:
        raise VersionCollisionError("derived object identity profile is unsupported")
    header = kind.encode("ascii") + b" " + str(len(raw)).encode("ascii") + b"\x00"
    digest = hashlib.sha1 if oid_length == 40 else hashlib.sha256
    return digest(header + raw).hexdigest()


def _plan_collision_tree_reconstruction(
    importer: _BoundedObjectImporter,
    predecessor_tree: str,
    successor_source: bytes,
) -> tuple[str, tuple[tuple[str, str, bytes], ...]]:
    """Rebuild only the fixed implementation-owner path without writing it."""

    predecessor_tree = _oid(predecessor_tree)
    parts = SOURCE_PATH.encode("utf-8").split(b"/")
    if not parts or len(parts) > MAX_TREE_DEPTH:
        raise VersionCollisionError("implementation owner path exceeds the bound")
    current = predecessor_tree
    frames: list[tuple[bytes, tuple[tuple[bytes, bytes, str], ...], int]] = []
    for index, part in enumerate(parts):
        raw = importer.transfer(
            current,
            "tree",
            index,
            import_blobs=False,
            category=STRUCTURAL_TREE_OBJECTS,
        )
        entries = importer._tree_entries(raw)
        matches = [
            position
            for position, (_mode, name, _child) in enumerate(entries)
            if name == part
        ]
        if len(matches) != 1:
            raise VersionCollisionError("implementation owner path is unavailable")
        position = matches[0]
        mode, _name, child = entries[position]
        final = index == len(parts) - 1
        if final:
            if mode != b"100644":
                raise VersionCollisionError(
                    "implementation owner is not a regular source blob"
                )
        elif mode != b"40000":
            raise VersionCollisionError("implementation owner path is malformed")
        frames.append((raw, entries, position))
        current = child

    objects: list[tuple[str, str, bytes]] = []
    child_oid = _git_object_oid("blob", successor_source, len(predecessor_tree))
    objects.append(("blob", child_oid, successor_source))
    for _raw, entries, position in reversed(frames):
        rebuilt = b"".join(
            mode
            + b" "
            + name
            + b"\x00"
            + bytes.fromhex(child_oid if entry_index == position else oid)
            for entry_index, (mode, name, oid) in enumerate(entries)
        )
        child_oid = _git_object_oid("tree", rebuilt, len(predecessor_tree))
        objects.append(("tree", child_oid, rebuilt))
    return child_oid, tuple(objects)


def _import_successor(
    source: Path, destination: Path, head: str | None, predecessor: str, *, resulting_tree: str | None = None,
    importer: _BoundedObjectImporter | None = None,
    import_tree: bool = True,
) -> str:
    from . import fast_path

    _oid(predecessor)
    if (head is None) == (resulting_tree is None):
        raise VersionCollisionError("source import requires exactly one commit or tree")
    selected = _oid(head if head is not None else resulting_tree)
    if len(selected) != 40 or len(predecessor) != 40:
        raise VersionCollisionError("GitHub collision source requires SHA-1 object identities")
    importer = importer or _BoundedObjectImporter(source, destination)

    if resulting_tree is not None:
        if import_tree:
            importer.transfer(resulting_tree, "tree")
        return resulting_tree
    commit = importer.transfer(selected, "commit", category=OTHER)
    try:
        tree, parents = fast_path._commit_topology(commit.decode("utf-8", errors="strict"))
    except (UnicodeError, fast_path.SecurityBlocker) as exc:
        raise VersionCollisionError("successor commit headers are malformed") from exc
    if parents != (predecessor,):
        raise VersionCollisionError("successor requires the exact single predecessor parent")
    if import_tree:
        importer.transfer(tree, "tree")
    return tree


@contextmanager
def _authenticated_source_checkout(
    source: Path, predecessor: str, resulting: str | None, *, resulting_tree: str | None = None,
    accepted_main: str | None = None, include_validation_authority: bool = False,
) -> Iterator[tuple[Path, str, _BoundedObjectImporter]]:
    from . import lifecycle_authority as authority

    if (resulting is None) == (resulting_tree is None):
        raise VersionCollisionError(
            "source authentication requires exactly one commit or expected tree"
        )
    main = (
        _authenticate_installed_collision_issuer()
        if accepted_main is None
        else _oid(accepted_main)
    )
    source = source.resolve(strict=True)
    source_repository_state = _source_repository_state(source)
    with tempfile.TemporaryDirectory(prefix="secpal-collision-source-") as directory:
        root = Path(directory)
        _git(root, ["init", "--quiet"], 4096)
        _git(
            root,
            ["remote", "add", "origin", "https://github.com/SecPal/.github.git"],
            4096,
        )
        importer = _BoundedObjectImporter(source, root)
        importer.history(main)
        protected_main_history = frozenset(importer.histories)
        base = importer.import_histories_and_merge_base(main, predecessor)
        trees = {
            head: importer.commit_trees[head]
            for head in (main, predecessor)
        }
        base_tree = importer.commit_trees[base]
        for tree in {*trees.values(), base_tree}:
            importer.transfer(
                tree,
                "tree",
                import_blobs=False,
                category=STRUCTURAL_TREE_OBJECTS,
            )
        scope_paths = _changed_paths(root, base, predecessor, 4096)
        if SOURCE_PATH not in scope_paths:
            raise VersionCollisionError(
                "collision owner is outside the authenticated delivery scope"
            )
        for tree in (base_tree, trees[main], trees[predecessor]):
            importer.transfer_path(tree, SOURCE_PATH, category=OWNER_SOURCE_BLOBS)
        sources = {
            head: _read_source(root, head)
            for head in (base, main, predecessor)
        }
        inventories = {
            head: inventory_from_source(blob)
            for head, blob in sources.items()
        }
        collision, _expected_inventory = _derive_collision_identity(
            inventories[base], inventories[main], inventories[predecessor]
        )
        successor_source, _replacement_offsets = _derive_owner_renumber(
            sources[predecessor],
            collision["occupied_version"],
            collision["free_version"],
        )
        successor_inventory = inventory_from_source(successor_source)
        derive_collision(
            inventories[base],
            inventories[main],
            inventories[predecessor],
            successor_inventory,
        )
        recomputed_tree, derived_objects = _plan_collision_tree_reconstruction(
            importer,
            trees[predecessor],
            successor_source,
        )
        expected_tree = (
            _import_successor(
                source,
                root,
                resulting,
                predecessor,
                importer=importer,
                import_tree=False,
            )
            if resulting is not None
            else _oid(resulting_tree)
        )
        if recomputed_tree != expected_tree:
            raise VersionCollisionError(
                "recomputed collision tree differs from the expected result"
            )
        for kind, oid, raw in derived_objects:
            importer.materialize_derived(kind, oid, raw)
        changed_paths = _changed_paths(
            root,
            trees[predecessor],
            recomputed_tree,
            MAX_CHANGED_PATHS,
        )
        if changed_paths != (SOURCE_PATH,):
            raise VersionCollisionError(
                "derived collision tree differs outside its implementation owner"
            )
        installed = Path(__file__).resolve().parents[2]
        registry_path = authority._TRUST_REGISTRY.relative_to(installed).as_posix()
        if registry_path != TRUST_REGISTRY_PATH:
            raise VersionCollisionError(
                "accepted trust registry path differs from the collision profile"
            )
        importer.transfer_path(trees[main], TRUST_REGISTRY_PATH, category=OTHER)
        if include_validation_authority:
            importer.transfer(
                recomputed_tree,
                "tree",
                category=CANDIDATE_VALIDATION_TREE_CLOSURE,
            )
            accepted_paths = (
                (TRUST_REGISTRY_PATH, OTHER),
                (TRUST_REGISTRY_SCHEMA_PATH, OTHER),
                *(
                    (path, VALIDATION_DEPENDENCY_BLOBS)
                    for path in COLLISION_VALIDATION_DEPENDENCY_PATHS
                ),
                *(
                    (path, VALIDATION_DEPENDENCY_BLOBS)
                    for path in COLLISION_VALIDATION_BUNDLE_PATHS
                ),
                *(
                    (path, VALIDATION_DEPENDENCY_BLOBS)
                    for path in COLLISION_VALIDATION_SNAPSHOT_PATHS
                ),
            )
            for path, category in accepted_paths:
                importer.transfer_path(base_tree, path, category=category)
                importer.transfer_path(
                    trees[predecessor], path, category=category,
                )
            for path in COLLISION_VALIDATION_PROJECTION_PATHS:
                importer.transfer_path(
                    trees[predecessor], path, category=ACCEPTED_HARNESS_BLOBS,
                )
            for path in (
                COLLISION_AUTHORITY_PATH,
                EXACT_SOURCE_SAFETY_PATH,
                VALIDATION_ACTIONS_PATH,
            ):
                importer.transfer_path(
                    trees[main], path, category=ACCEPTED_HARNESS_BLOBS,
                )
            for path in (
                *COLLISION_VALIDATION_BUNDLE_PATHS,
                *COLLISION_VALIDATION_SNAPSHOT_PATHS,
            ):
                accepted_fixture = _authenticated_blob(root, base_tree, path)
                if (
                    _authenticated_blob(root, trees[predecessor], path)
                    != accepted_fixture
                    or _authenticated_blob(root, recomputed_tree, path)
                    != accepted_fixture
                ):
                    raise VersionCollisionError(
                        "candidate object fixture differs from accepted main"
                    )
                requirements = _validation_object_requirements(
                    path, accepted_fixture[1], accepted_fixture[3]
                )
                for prerequisite in requirements[0]:
                    if prerequisite not in protected_main_history:
                        raise VersionCollisionError(
                            "validation bundle prerequisite is outside protected-main history"
                        )
                _transfer_validation_object_requirements(
                    importer, *requirements,
                )
        for path in changed_paths:
            importer.transfer_path(
                trees[predecessor], path, category=OWNER_SOURCE_BLOBS,
            )
            importer.transfer_path(
                recomputed_tree, path, category=OWNER_SOURCE_BLOBS,
            )
        if not set(changed_paths) <= set(scope_paths):
            raise VersionCollisionError(
                "collision renumber extends outside the authenticated delivery scope"
            )
        policy = authority._load_lifecycle_trust_policy("SecPal/.github")
        allowed = root / ".git" / "allowed-signers"
        allowed.write_text("".join(
            f"{identity} {key}\n" for identity in sorted(policy.transition_signer_identities)
            for key in policy.signers[identity].ssh_public_keys
        ), encoding="utf-8")
        _git(root, ["config", "gpg.ssh.allowedSignersFile", str(allowed)], 4096)
        try:
            yield root, main, importer
        finally:
            importer.verify_source_objects_unchanged()
            if _source_repository_state(source) != source_repository_state:
                raise VersionCollisionError(
                    "source repository changed during collision authentication"
                )
            if _observe_main() != main:
                raise VersionCollisionError(
                    "protected main drifted during collision authentication"
                )


def _seal_collision(result: dict[str, Any]) -> VerifiedVersionCollision:
    from . import lifecycle_authority as authority

    raw = authority.canonical_json_bytes(result)
    return VerifiedVersionCollision(raw, _CollisionSeal(hashlib.sha256(raw).hexdigest()))


def authenticate_collision_source(
    *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_head: str, repository_root: Path,
) -> VerifiedVersionCollision:
    """Observe protected main and immutable source through fixed maintained boundaries."""

    _validate_public_collision_request(
        repository,
        delivery_issue,
        pull_request,
        predecessor_head,
        resulting_head,
        repository_root,
    )
    main = _authenticate_installed_collision_issuer()
    _require_current_collision_predecessor(
        repository, delivery_issue, pull_request, predecessor_head,
    )
    with _authenticated_source_checkout(
        repository_root,
        predecessor_head,
        resulting_head,
        accepted_main=main,
    ) as (root, main, _importer):
        return _seal_collision(_derive_collision_from_git(
            root, repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
            predecessor_head=predecessor_head, resulting_head=resulting_head, protected_main=main,
        ))


def prepare_collision_tree(
    *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_tree: str, repository_root: Path,
) -> VerifiedVersionCollision:
    """Read-only validation preparation; absence of a resulting head prevents publication."""

    _validate_public_collision_request(
        repository,
        delivery_issue,
        pull_request,
        predecessor_head,
        resulting_tree,
        repository_root,
    )
    main = _authenticate_installed_collision_issuer()
    _require_current_collision_predecessor(
        repository, delivery_issue, pull_request, predecessor_head,
    )
    with _authenticated_source_checkout(
        repository_root,
        predecessor_head,
        None,
        resulting_tree=resulting_tree,
        accepted_main=main,
    ) as (root, main, _importer):
        return _seal_collision(_derive_collision_tree(
            root, repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
            predecessor_head=predecessor_head, resulting_tree=resulting_tree, protected_main=main,
        ))


@contextmanager
def collision_complete_validation(
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_head: str,
    resulting_tree: str,
    repository_root: Path,
) -> Iterator[CollisionValidationExecution]:
    """Construct the sole accepted-main ordinary validation environment."""

    _validate_public_collision_request(
        repository,
        delivery_issue,
        pull_request,
        predecessor_head,
        resulting_tree,
        repository_root,
    )
    main = _authenticate_installed_collision_issuer()
    _require_current_collision_predecessor(
        repository, delivery_issue, pull_request, predecessor_head,
    )
    with _authenticated_source_checkout(
        repository_root,
        predecessor_head,
        None,
        resulting_tree=resulting_tree,
        accepted_main=main,
        include_validation_authority=True,
    ) as (root, main, importer):
        collision = _derive_collision_tree(
            root,
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            predecessor_head=predecessor_head,
            resulting_tree=resulting_tree,
            protected_main=main,
        )
        entry, binding = _collision_validation_authority(root, collision)
        profile = binding["collision_validation_authority"]
        try:
            with exact_source_safety.collision_validation_root(
                root,
                profile=profile,
                expected_profile=profile,
            ) as (execution_root, verify_execution_root):
                yield CollisionValidationExecution(
                    collision=_seal_collision(collision),
                    repository_entry=copy.deepcopy(entry),
                    registry_binding=copy.deepcopy(binding),
                    execution_root=execution_root,
                    verify_execution_root=verify_execution_root,
                    object_accounting=importer.accounting(),
                )
        finally:
            _require_accepted_issuer(main)


def collision_validation_binding_for_commit(
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_head: str,
    resulting_head: str,
    repository_root: Path,
) -> tuple[VerifiedVersionCollision, dict[str, Any]]:
    """Recompute the receipt authority for one signed collision candidate."""

    _validate_public_collision_request(
        repository,
        delivery_issue,
        pull_request,
        predecessor_head,
        resulting_head,
        repository_root,
    )
    main = _authenticate_installed_collision_issuer()
    _require_current_collision_predecessor(
        repository, delivery_issue, pull_request, predecessor_head,
    )
    with _authenticated_source_checkout(
        repository_root,
        predecessor_head,
        resulting_head,
        accepted_main=main,
        include_validation_authority=True,
    ) as (root, main, _importer):
        collision = _derive_collision_from_git(
            root,
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            predecessor_head=predecessor_head,
            resulting_head=resulting_head,
            protected_main=main,
        )
        _entry, binding = _collision_validation_authority(root, collision)
        _require_accepted_issuer(main)
        return _seal_collision(collision), binding


def _validate_public_collision_request(
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor: str,
    result: str,
    repository_root: Path,
) -> None:
    if (
        repository != "SecPal/.github"
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (delivery_issue, pull_request)
        )
        or not isinstance(repository_root, Path)
        or len(_oid(predecessor)) != 40
        or len(_oid(result)) != 40
    ):
        raise VersionCollisionError(
            "collision request identity is outside the maintained profile"
        )


def _authenticate_installed_collision_issuer() -> str:
    """Bind installed collision and policy sources before authority consumption."""

    main = _observe_main()
    _require_accepted_issuer(main)
    return main


def _require_accepted_issuer(main: str) -> None:
    from . import lifecycle_authority as authority

    root = Path(__file__).resolve().parents[2]
    head = _git(root, ["rev-parse", "HEAD"], 128).decode("ascii").strip()
    status = _git(root, ["status", "--porcelain=v1", "--untracked-files=normal"], MAX_DELTA_BYTES)
    if head != main or status:
        raise VersionCollisionError("collision issuer is not exact clean accepted-main tooling")
    try:
        exact_source_safety.verify_source_bytes(root, main)
    except authority.LifecycleAuthorityError as exc:
        raise VersionCollisionError(
            "collision issuer has substituted accepted-main source bytes"
        ) from exc


def _require_current_collision_predecessor(
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_head: str,
) -> Any:
    from . import lifecycle_authority as authority

    try:
        observed = publication.verify_current_lifecycle_authority(
            repository, delivery_issue
        )
        lifecycle = observed.lifecycle
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise VersionCollisionError(
            "collision CURRENT lifecycle authority is unavailable"
        ) from exc
    if (
        lifecycle.repository != repository
        or lifecycle.delivery_issue != delivery_issue
        or lifecycle.pull_request != pull_request
        or lifecycle.head_sha != _oid(predecessor_head)
        or state["ready"] is not True
        or state["draft"] is not False
        or state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        or state["exceptional_recovery_count"] != authority.MAX_EXCEPTIONAL_RECOVERIES
        or state["exceptional_continuation_count"] != 0
        or state["cycle_3_absent"] is not True
    ):
        raise VersionCollisionError(
            "collision predecessor differs from exact exhausted Ready CURRENT"
        )
    return observed


def validation_collision_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Exclude only the not-yet-created commit identity to avoid a receipt cycle."""

    return {key: copy.deepcopy(item) for key, item in value.items() if key != "resulting_head"}
