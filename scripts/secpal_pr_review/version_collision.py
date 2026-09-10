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
from .fast_path import digest_json


MAX_BLOB_BYTES = 1024 * 1024
MAX_REPLACEMENTS = 4096
MAX_CHANGED_PATHS = 32
MAX_DELTA_BYTES = 4 * 1024 * 1024
MAX_IMPORTED_OBJECTS = 4096
MAX_IMPORTED_BYTES = 8 * 1024 * 1024
_VERSION = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})", re.ASCII)
_VERSION_BYTES = frozenset(b"0123456789.")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", re.ASCII)
_INERT_TEST_ASSERTIONS = frozenset(
    {
        "assertCountEqual",
        "assertDictEqual",
        "assertEqual",
        "assertIn",
        "assertListEqual",
        "assertMultiLineEqual",
        "assertNotEqual",
        "assertNotIn",
        "assertNotRegex",
        "assertRegex",
        "assertSequenceEqual",
        "assertSetEqual",
        "assertTupleEqual",
    }
)
SOURCE_PATH = "scripts/secpal_pr_review/fast_path.py"
FAMILY_KIND = "TWO_PARENT_READY_INTEGRATION"
TRIGGER = "IMMUTABLE_EVIDENCE_VERSION_COLLISION"


class VersionCollisionError(ValueError):
    """A purported version-only source change is not exact and bounded."""


def _version(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise VersionCollisionError("version identity is not canonical major.minor")
    major, minor = value.split(".")
    return int(major), int(minor)


def _text(value: bytes) -> None:
    if not isinstance(value, bytes) or not 0 < len(value) <= MAX_BLOB_BYTES:
        raise VersionCollisionError("changed blob exceeds the bounded text profile")
    try:
        value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VersionCollisionError("changed blob is not UTF-8") from exc
    if b"\x00" in value:
        raise VersionCollisionError("changed blob contains a NUL byte")


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
    lines = blob.decode("utf-8", errors="strict").splitlines(keepends=True)
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
            for node in ast.walk(ast.parse(blob.decode("utf-8", errors="strict"))) if isinstance(node, ast.JoinedStr)
        ]
        if any(start <= offset < end for offset in offsets for start, end in interpolated):
            raise VersionCollisionError("Python version token replacement enters an interpolated string")
        for token in tokenize.generate_tokens(io.StringIO(blob.decode("utf-8")).readline):
            if token.type in {tokenize.STRING, tokenize.COMMENT}:
                spans.append((byte_offset(token.start), byte_offset(token.end)))
    except (tokenize.TokenError, IndentationError, SyntaxError, IndexError) as exc:
        raise VersionCollisionError("Python version token source is malformed") from exc
    if any(not any(start <= offset and offset + len(version) <= end for start, end in spans) for offset in offsets):
        raise VersionCollisionError("Python version token replacement changes executable syntax")


def _verify_python_test_version_tokens(
    blob: bytes, offsets: tuple[int, ...], version: str,
) -> None:
    """Admit only comments and structurally inert unittest expectations."""

    text = blob.decode("utf-8", errors="strict")
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line.encode("utf-8")))

    def byte_offset(position: tuple[int, int]) -> int:
        row, column = position
        return starts[row - 1] + len(lines[row - 1][:column].encode("utf-8"))

    try:
        module = ast.parse(text)
        comments = [
            (byte_offset(token.start), byte_offset(token.end))
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError, IndexError) as exc:
        raise VersionCollisionError("Python test version token source is malformed") from exc

    parents = {
        child: parent
        for parent in ast.walk(module)
        for child in ast.iter_child_nodes(parent)
    }

    imported_testcase_names = {
        alias.asname or alias.name
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module == "unittest"
        for alias in node.names
        if alias.name == "TestCase"
    }
    imported_unittest_names = {
        alias.asname or alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "unittest"
    }

    def testcase_class(node: ast.ClassDef) -> bool:
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in imported_testcase_names:
                return True
            if (
                isinstance(base, ast.Attribute)
                and base.attr == "TestCase"
                and isinstance(base.value, ast.Name)
                and base.value.id in imported_unittest_names
            ):
                return True
        return False

    def assignment_targets(node: ast.AST) -> tuple[ast.AST, ...]:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            return tuple(targets)
        return ()

    def inert_expectation(node: ast.Constant) -> bool:
        current: ast.AST = node
        while isinstance(parents.get(current), (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            current = parents[current]
        call = parents.get(current)
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Attribute)
            or call.func.attr not in _INERT_TEST_ASSERTIONS
            or not isinstance(call.func.value, ast.Name)
            or call.func.value.id != "self"
            or not isinstance(parents.get(call), ast.Expr)
        ):
            return False
        statement = parents[call]
        function = parents.get(statement)
        if (
            not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
            or not function.name.startswith("test_")
            or not function.args.args
            or function.args.args[0].arg != "self"
        ):
            return False
        owner = parents.get(function)
        if not isinstance(owner, ast.ClassDef) or not testcase_class(owner):
            return False
        forbidden_methods = {call.func.attr, "__getattr__", "__getattribute__"}
        if any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name in forbidden_methods
            for item in owner.body
        ):
            return False
        return not any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == call.func.attr
            for item in ast.walk(function)
            for target in assignment_targets(item)
        )

    safe_spans = list(comments)
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and hasattr(node, "end_lineno")
            and inert_expectation(node)
        ):
            safe_spans.append(
                (
                    starts[node.lineno - 1] + node.col_offset,
                    starts[node.end_lineno - 1] + node.end_col_offset,
                )
            )
    if any(
        not any(start <= offset and offset + len(version) <= end for start, end in safe_spans)
        for offset in offsets
    ):
        raise VersionCollisionError(
            "Python test version token is not a structurally inert expectation"
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
                "test version token source has no structurally inert profile"
            )
        if path.endswith(".py"):
            _verify_python_version_tokens(blobs[0], tuple(pair[0] for pair in positions), occupied_version)
            _verify_python_version_tokens(blobs[1], tuple(pair[1] for pair in positions), free_version)
            if path.startswith("tests/"):
                _verify_python_test_version_tokens(
                    blobs[0], tuple(pair[0] for pair in positions), occupied_version,
                )
                _verify_python_test_version_tokens(
                    blobs[1], tuple(pair[1] for pair in positions), free_version,
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
        _text(source)
        try:
            self.module = ast.parse(source.decode("utf-8"))
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise VersionCollisionError("version authority source is malformed") from exc
        self.assignments: dict[str, list[ast.expr]] = {}
        for node in self.module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assignments.setdefault(target.id, []).append(node.value)

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


def _verify_owner_renumber(source: bytes, occupied: str, delta: dict[str, Any]) -> None:
    declarations = _SourceDeclarations(source)
    identities: list[ast.Constant] = []
    for name in ("READY_INTEGRATION_KEYS_BY_VERSION", "READY_INTEGRATION_ATTESTATION_BY_VERSION"):
        assigned = declarations.assignments.get(name, [])
        if len(assigned) != 1 or not isinstance(assigned[0], ast.Dict):
            raise VersionCollisionError("candidate version identity table is not explicit")
        for key in assigned[0].keys:
            identity = key.elts[0] if isinstance(key, ast.Tuple) and key.elts else key
            if isinstance(identity, ast.Constant) and identity.value == occupied:
                identities.append(identity)
    if len(identities) != 3:
        raise VersionCollisionError("candidate version identity keys are incomplete")
    identities.extend(node for node in ast.walk(declarations.function("normalize_ready_integration_evidence"))
                      if isinstance(node, ast.Constant) and node.value == occupied)
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
    owner = [change for change in delta["changes"] if change["path"] == SOURCE_PATH]
    if len(owner) != 1 or [pair[0] for pair in owner[0]["replacement_offsets"]] != sorted(set(positions)):
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


def derive_collision(
    baseline: dict[str, Any], accepted: dict[str, Any],
    candidate: dict[str, Any], successor: dict[str, Any],
) -> dict[str, Any]:
    """Admit an observed immutable schema collision; these arguments are not authority."""

    if any(item.get("kind") != FAMILY_KIND for item in (baseline, accepted, candidate, successor)):
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
    if successor["versions"] != expected:
        raise VersionCollisionError("successor skips lowest-free identity or changes immutable mappings")
    return {
        "version_family": FAMILY_KIND,
        "occupied_version": occupied,
        "free_version": free,
        "candidate_semantic": copy.deepcopy(prior_semantic),
        "accepted_semantic": copy.deepcopy(accepted_semantic),
        "inventory": copy.deepcopy(accepted),
        "inventory_digest": digest_json(accepted),
    }


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


def _read_source(root: Path, commit: str) -> bytes:
    entry = _git(root, ["ls-tree", "-z", _oid(commit), "--", SOURCE_PATH], 2048)
    parts = entry.split(b"\t")
    if len(parts) != 2 or parts[1] != SOURCE_PATH.encode() + b"\x00":
        raise VersionCollisionError("version authority source is missing")
    metadata = parts[0].decode("ascii").split(" ")
    if len(metadata) != 3 or metadata[:2] != ["100644", "blob"]:
        raise VersionCollisionError("version authority source is not a regular blob")
    blob = _oid(metadata[2])
    size = _git(root, ["cat-file", "-s", blob], 32)
    if re.fullmatch(rb"[0-9]+\n", size) is None or not 0 < int(size) <= MAX_BLOB_BYTES:
        raise VersionCollisionError("version authority source exceeds the bound")
    return _git(root, ["cat-file", "blob", blob], MAX_BLOB_BYTES)


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


def _import_successor(
    source: Path, destination: Path, head: str | None, predecessor: str, *, resulting_tree: str | None = None,
) -> None:
    from . import fast_path

    _oid(predecessor)
    if (head is None) == (resulting_tree is None):
        raise VersionCollisionError("source import requires exactly one commit or tree")
    selected = _oid(head if head is not None else resulting_tree)
    if len(selected) != 40 or len(predecessor) != 40:
        raise VersionCollisionError("GitHub collision source requires SHA-1 object identities")
    imported: set[str] = set()
    total_bytes = 0

    def transfer(oid: str, kind: str, depth: int) -> bytes | None:
        nonlocal total_bytes
        _oid(oid)
        if oid in imported:
            return None
        if depth > 64 or len(imported) >= MAX_IMPORTED_OBJECTS:
            raise VersionCollisionError("source object closure exceeds the bound")
        imported.add(oid)
        if kind != "commit" and publication._run_git(destination, ["cat-file", "-e", oid]).returncode == 0:
            return None
        size = _git(source, ["cat-file", "-s", oid], 32)
        limit = 65536 if kind == "commit" else MAX_BLOB_BYTES
        if re.fullmatch(rb"[0-9]+\n", size) is None or not 0 <= int(size) <= limit:
            raise VersionCollisionError("source object exceeds the bound")
        raw = _git(source, ["cat-file", kind, oid], limit)
        header = kind.encode("ascii") + b" " + str(len(raw)).encode("ascii") + b"\x00"
        if hashlib.sha1(header + raw).hexdigest() != oid:
            raise VersionCollisionError("source object hash differs from its claimed identity")
        total_bytes += len(raw)
        if total_bytes > MAX_IMPORTED_BYTES:
            raise VersionCollisionError("source object closure exceeds the byte bound")
        written = publication._run_git(destination, ["hash-object", "-w", "-t", kind, "--stdin"], input_bytes=raw)
        if written.returncode != 0 or written.stdout != (oid + "\n").encode("ascii"):
            raise VersionCollisionError("verified source object import failed")
        if kind == "tree":
            offset = 0
            while offset < len(raw):
                delimiter = raw.find(b"\x00", offset)
                if delimiter < 0 or delimiter + 21 > len(raw):
                    raise VersionCollisionError("source tree entry is malformed")
                metadata = raw[offset:delimiter].split(b" ", 1)
                if len(metadata) != 2 or metadata[0] not in {b"40000", b"100644", b"100755", b"120000", b"160000"}:
                    raise VersionCollisionError("source tree object mode is malformed")
                child = raw[delimiter + 1:delimiter + 21].hex()
                if metadata[0] != b"160000":
                    transfer(child, "tree" if metadata[0] == b"40000" else "blob", depth + 1)
                offset = delimiter + 21
        return raw

    if resulting_tree is not None:
        transfer(resulting_tree, "tree", 0)
        return
    commit = transfer(selected, "commit", 0)
    if commit is None:
        raise VersionCollisionError("successor commit is absent")
    try:
        tree, parents = fast_path._commit_topology(commit.decode("utf-8", errors="strict"))
    except (UnicodeError, fast_path.SecurityBlocker) as exc:
        raise VersionCollisionError("successor commit headers are malformed") from exc
    if parents != (predecessor,):
        raise VersionCollisionError("successor requires the exact single predecessor parent")
    transfer(tree, "tree", 0)


@contextmanager
def _authenticated_source_checkout(
    source: Path, predecessor: str, resulting: str | None, *, resulting_tree: str | None = None,
) -> Iterator[tuple[Path, str]]:
    from . import lifecycle_authority as authority

    main = _observe_main()
    _require_accepted_issuer(main)
    with tempfile.TemporaryDirectory(prefix="secpal-collision-source-") as directory:
        root = Path(directory)
        _git(root, ["init", "--quiet"], 4096)
        _git(root, ["remote", "add", "origin", "https://github.com/SecPal/.github.git"], 4096)
        _git(root, ["-c", "fetch.fsckObjects=true", "fetch", "--no-tags", "origin", _oid(main), _oid(predecessor)], 4096)
        _import_successor(source.resolve(strict=True), root, resulting, predecessor, resulting_tree=resulting_tree)
        policy = authority._load_lifecycle_trust_policy("SecPal/.github")
        allowed = root / "allowed-signers"
        allowed.write_text("".join(
            f"{identity} {key}\n" for identity in sorted(policy.transition_signer_identities)
            for key in policy.signers[identity].ssh_public_keys
        ), encoding="utf-8")
        _git(root, ["config", "gpg.ssh.allowedSignersFile", str(allowed)], 4096)
        yield root, main
        if _observe_main() != main:
            raise VersionCollisionError("protected main drifted during collision authentication")


def _seal_collision(result: dict[str, Any]) -> VerifiedVersionCollision:
    from . import lifecycle_authority as authority

    raw = authority.canonical_json_bytes(result)
    return VerifiedVersionCollision(raw, _CollisionSeal(hashlib.sha256(raw).hexdigest()))


def authenticate_collision_source(
    *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_head: str, repository_root: Path,
) -> VerifiedVersionCollision:
    """Observe protected main and immutable source through fixed maintained boundaries."""

    with _authenticated_source_checkout(repository_root, predecessor_head, resulting_head) as (root, main):
        return _seal_collision(_derive_collision_from_git(
            root, repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
            predecessor_head=predecessor_head, resulting_head=resulting_head, protected_main=main,
        ))


def prepare_collision_tree(
    *, repository: str, delivery_issue: int, pull_request: int,
    predecessor_head: str, resulting_tree: str, repository_root: Path,
) -> VerifiedVersionCollision:
    """Read-only validation preparation; absence of a resulting head prevents publication."""

    with _authenticated_source_checkout(
        repository_root, predecessor_head, None, resulting_tree=resulting_tree,
    ) as (root, main):
        return _seal_collision(_derive_collision_tree(
            root, repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
            predecessor_head=predecessor_head, resulting_tree=resulting_tree, protected_main=main,
        ))


def _require_accepted_issuer(main: str) -> None:
    root = Path(__file__).resolve().parents[2]
    head = _git(root, ["rev-parse", "HEAD"], 128).decode("ascii").strip()
    status = _git(root, ["status", "--porcelain=v1", "--untracked-files=normal"], MAX_DELTA_BYTES)
    if head != main or status:
        raise VersionCollisionError("collision issuer is not exact clean accepted-main tooling")


def validation_collision_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Exclude only the not-yet-created commit identity to avoid a receipt cycle."""

    return {key: copy.deepcopy(item) for key, item in value.items() if key != "resulting_head"}
