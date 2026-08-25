# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Pure policy and exact plans for graph-first replanning.

The canonical semantics remain in ``docs/work-graph-contract.md``. This module
turns an explicit human/agent classification into a finite operation; it does
not infer judgment classifications from prose or review metadata.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .model import Node, Snapshot, parse_node_key

SCHEMA = "secpal-work-graph-replan/v1"
RECOVERY_SCHEMA = "secpal-work-graph-replan-recovery/v1"
AGGREGATE = "@aggregate"

CLASSIFICATION_ACTIONS = MappingProxyType(
    {
        "IN_CONTRACT_DEFECT": "KEEP_IN_CURRENT_CONTRACT",
        "MISSING_PREREQUISITE": "INSERT_PREREQUISITE",
        "NEW_RESPONSIBILITY": "CREATE_OWNED_SIBLING",
        "PROMOTE_TO_SUB_EPIC": "PROMOTE_TO_SUB_EPIC",
        "NON_BLOCKING_FOLLOWUP": "CREATE_OWNED_FOLLOWUP",
        "INVALID_FINDING": "REJECT_WITH_EVIDENCE",
    }
)
TIMINGS = frozenset({"BEFORE_FREEZE", "AFTER_FREEZE"})
RISK_CLASSES = frozenset(
    {"P1", "P2", "P3", "INFORMATIONAL", "SECURITY", "AUTHENTICATION", "INTEGRITY", "FAIL_OPEN"}
)
NON_BLOCKING_FORBIDDEN_RISKS = frozenset(
    {"P1", "P2", "SECURITY", "AUTHENTICATION", "INTEGRITY", "FAIL_OPEN"}
)
ALIAS = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
TRUSTED_GIT_DIRECTORIES = tuple(
    Path(value)
    for value in ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin", "/opt/local/bin")
)
GIT_ENVIRONMENT_OVERRIDES = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_EXEC_PATH",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)
SAFE_GIT_CONFIG = (
    ("core.fsmonitor", "false"),
    ("gpg.program", "gpg"),
    ("gpg.openpgp.program", "gpg"),
    ("gpg.ssh.program", "ssh-keygen"),
    ("gpg.x509.program", "gpgsm"),
)


class PlanError(ValueError):
    """The requested semantic operation violates the replanning contract."""


class StalePlanError(PlanError):
    """The actor or exact canonical graph snapshot changed before mutation."""


@dataclass(frozen=True)
class Classification:
    name: str
    action: str
    technically_blocking: bool
    mechanically_blocking: bool
    timing: str
    risk: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    kind: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class Plan:
    actor: str
    classification: Classification
    current_issue: str
    owner: str | None
    snapshot_digest: str
    steps: tuple[Step, ...]
    request: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", MappingProxyType(dict(self.request)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "actor": self.actor,
            "classification": {
                "name": self.classification.name,
                "action": self.classification.action,
                "technically_blocking": self.classification.technically_blocking,
                "mechanically_blocking": self.classification.mechanically_blocking,
                "timing": self.classification.timing,
                "risk": list(self.classification.risk),
            },
            "current_issue": self.current_issue,
            "owner": self.owner,
            "snapshot_digest": self.snapshot_digest,
            "request": dict(self.request),
            "steps": [
                {"kind": step.kind, "arguments": dict(step.arguments)} for step in self.steps
            ],
        }


@dataclass(frozen=True)
class CreatedIssueIdentity:
    """Canonical identity returned by one successful create mutation."""

    key: str
    node_id: str
    repository_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "node_id": self.node_id,
            "repository_id": self.repository_id,
        }


def content_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def plan_digest(plan: Plan) -> str:
    payload = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def created_issue_body(plan: Plan, step_index: int) -> str:
    """Return the exact planned body for one create step."""

    step = plan.steps[step_index]
    if step.kind != "CREATE_ISSUE":
        raise PlanError("created issue content requested for a non-create step")
    return str(step.arguments["body"])


def _document_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def recovery_document_digest(value: Mapping[str, Any]) -> str:
    """Return the canonical digest of recovery fields excluding the digest itself."""

    return _document_digest({key: item for key, item in value.items() if key != "journal_digest"})


class RecoverySigner(Protocol):
    def sign(self, digest: str) -> Mapping[str, str]: ...

    def verify(self, authentication: Any, digest: str) -> None: ...


class GitRecoverySigner:
    """Authenticate recovery state with the user's configured Git signing key."""

    def __init__(self, repository_root: Path, git_executable: str) -> None:
        self.repository_root = repository_root
        self.git_executable = git_executable

    @classmethod
    def discover(cls, directory: Path) -> GitRecoverySigner:
        executable = next(
            (
                candidate.resolve()
                for parent in TRUSTED_GIT_DIRECTORIES
                for candidate in (parent / "git",)
                if candidate.is_file() and os.access(candidate, os.X_OK)
            ),
            None,
        )
        if executable is None:
            raise PlanError("git is required to authenticate recovery evidence")
        environment = cls._environment()
        result = subprocess.run(
            [str(executable), "-C", str(directory), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise PlanError("recovery evidence must be created inside a Git worktree")
        return cls(Path(result.stdout.strip()).resolve(), str(executable))

    @staticmethod
    def _environment() -> dict[str, str]:
        environment = os.environ.copy()
        for key in GIT_ENVIRONMENT_OVERRIDES:
            environment.pop(key, None)
        for key in tuple(environment):
            if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
                environment.pop(key, None)
            if key.startswith("GIT_TRACE"):
                environment.pop(key, None)
        environment["PATH"] = os.pathsep.join(str(path) for path in TRUSTED_GIT_DIRECTORIES)
        environment["GIT_PAGER"] = "cat"
        environment["GIT_NO_LAZY_FETCH"] = "1"
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        environment["GIT_CONFIG_COUNT"] = str(len(SAFE_GIT_CONFIG))
        for index, (key, value) in enumerate(SAFE_GIT_CONFIG):
            environment[f"GIT_CONFIG_KEY_{index}"] = key
            environment[f"GIT_CONFIG_VALUE_{index}"] = value
        return environment

    def _run(self, arguments: list[str], *, input_text: str | None = None) -> str:
        result = subprocess.run(
            [self.git_executable, "-C", str(self.repository_root), *arguments],
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
            env=self._environment(),
            timeout=30,
        )
        if result.returncode != 0:
            raise StalePlanError("Git could not authenticate recovery evidence")
        return result.stdout

    def sign(self, digest: str) -> Mapping[str, str]:
        tree = self._run(["rev-parse", "HEAD^{tree}"]).strip()
        message = f"Authenticate work-graph recovery\n\n{digest}\n"
        commit_oid = self._run(["commit-tree", "-S", tree], input_text=message).strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_oid):
            raise StalePlanError("Git returned an invalid recovery attestation identity")
        return {"kind": "git-signed-commit", "commit_oid": commit_oid}

    def verify(self, authentication: Any, digest: str) -> None:
        if (
            not isinstance(authentication, Mapping)
            or set(authentication) != {"kind", "commit_oid"}
            or authentication.get("kind") != "git-signed-commit"
            or not isinstance(authentication.get("commit_oid"), str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", authentication["commit_oid"])
        ):
            raise StalePlanError("recovery authentication is malformed")
        commit_oid = str(authentication["commit_oid"])
        self._run(["verify-commit", commit_oid])
        message = self._run(["show", "-s", "--format=%B", commit_oid]).strip()
        expected = f"Authenticate work-graph recovery\n\n{digest}"
        if message != expected:
            raise StalePlanError("recovery authentication binds different evidence")

    def recovery_path(self, operation_digest: str) -> Path:
        value = self._run(
            ["rev-parse", "--git-path", f"secpal-work-graph-replan/{operation_digest}.json"]
        ).strip()
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.repository_root / path).resolve()


class RecoveryJournal:
    """Durable, plan-bound evidence for one non-transactional operation."""

    def __init__(self, path: Path, plan: Plan, signer: RecoverySigner) -> None:
        self.path = path
        self.plan = plan
        self.signer = signer

    @classmethod
    def for_plan(cls, plan: Plan, signer: GitRecoverySigner) -> RecoveryJournal:
        return cls(signer.recovery_path(plan_digest(plan)), plan, signer)

    def _fields(self) -> dict[str, Any]:
        return {
            "schema": RECOVERY_SCHEMA,
            "plan_digest": plan_digest(self.plan),
            "actor": self.plan.actor,
            "current_issue": self.plan.current_issue,
            "snapshot_digest": self.plan.snapshot_digest,
            "outcome": "NO_WRITES",
            "next_step": 0,
            "attempting_step": None,
            "created": {},
        }

    def _write(self, fields: Mapping[str, Any], *, exclusive: bool = False) -> None:
        document = dict(fields)
        document["journal_digest"] = _document_digest(document)
        document["authentication"] = dict(self.signer.sign(document["journal_digest"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if exclusive:
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError as exc:
                raise StalePlanError(
                    "recovery state already exists; use bounded recovery instead of replay"
                ) from exc
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._fsync_parent()
            return
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self._fsync_parent()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _fsync_parent(self) -> None:
        descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def start(self) -> None:
        self._write(self._fields(), exclusive=True)

    @contextmanager
    def lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StalePlanError("another process owns this recovery operation") from exc
            yield
        finally:
            os.close(descriptor)

    def load(self) -> dict[str, Any]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StalePlanError("recovery evidence is missing or unreadable") from exc
        if not isinstance(document, dict):
            raise StalePlanError("recovery evidence is malformed")
        authentication = document.pop("authentication", None)
        digest = document.pop("journal_digest", None)
        if digest != _document_digest(document):
            raise StalePlanError("recovery evidence digest is invalid")
        if not isinstance(digest, str):
            raise StalePlanError("recovery evidence digest is malformed")
        self.signer.verify(authentication, digest)
        expected = self._fields()
        if set(document) != set(expected):
            raise StalePlanError("recovery evidence contains unknown or missing fields")
        for field in ("schema", "plan_digest", "actor", "current_issue", "snapshot_digest"):
            if document.get(field) != expected[field]:
                raise StalePlanError("recovery evidence is bound to a different operation")
        next_step = document.get("next_step")
        attempting = document.get("attempting_step")
        created = document.get("created")
        if (
            type(next_step) is not int
            or not 0 <= next_step <= len(self.plan.steps)
            or (attempting is not None and (type(attempting) is not int or attempting != next_step))
            or not isinstance(created, dict)
            or document.get("outcome")
            not in {"NO_WRITES", "KNOWN_WRITES", "UNKNOWN_MUTATION_OUTCOME", "COMPLETE"}
        ):
            raise StalePlanError("recovery evidence has an invalid state")
        expected_outcome = (
            "UNKNOWN_MUTATION_OUTCOME"
            if attempting is not None
            else "NO_WRITES"
            if next_step == 0
            else "COMPLETE"
            if next_step == len(self.plan.steps)
            else "KNOWN_WRITES"
        )
        expected_aliases = {
            str(step.arguments["alias"])
            for step in self.plan.steps[:next_step]
            if step.kind == "CREATE_ISSUE"
        }
        if document["outcome"] != expected_outcome or set(created) != expected_aliases:
            raise StalePlanError("recovery evidence does not match the applied step prefix")
        return {
            **document,
            "journal_digest": digest,
            "authentication": authentication,
        }

    def begin_step(self, step_index: int) -> None:
        document = self.load()
        if document["next_step"] != step_index or document["attempting_step"] is not None:
            raise StalePlanError("recovery step does not match the exact mutation sequence")
        document.pop("journal_digest")
        document.pop("authentication")
        document["attempting_step"] = step_index
        document["outcome"] = "UNKNOWN_MUTATION_OUTCOME"
        self._write(document)

    def cancel_unattempted_step(self, step_index: int) -> None:
        document = self.load()
        if document["attempting_step"] != step_index:
            raise StalePlanError("recovery attempt state changed unexpectedly")
        document.pop("journal_digest")
        document.pop("authentication")
        document["attempting_step"] = None
        document["outcome"] = "KNOWN_WRITES" if document["next_step"] else "NO_WRITES"
        self._write(document)

    def complete_step(
        self, step_index: int, created: CreatedIssueIdentity | None
    ) -> None:
        document = self.load()
        if document["attempting_step"] != step_index or document["next_step"] != step_index:
            raise StalePlanError("recovery completion does not match the attempted mutation")
        document.pop("journal_digest")
        document.pop("authentication")
        if created is not None:
            alias = str(self.plan.steps[step_index].arguments["alias"])
            document["created"][alias] = created.to_dict()
        document["next_step"] = step_index + 1
        document["attempting_step"] = None
        document["outcome"] = (
            "COMPLETE" if document["next_step"] == len(self.plan.steps) else "KNOWN_WRITES"
        )
        self._write(document)


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PlanError(f"{field} must be a boolean")
    return value


def classify(value: Mapping[str, Any]) -> Classification:
    """Validate explicit judgment facts without collapsing the two blockers."""

    if not isinstance(value, Mapping):
        raise PlanError("finding classification must be an object")
    if set(value) != {
        "classification",
        "technically_blocking",
        "mechanically_blocking",
        "timing",
        "risk",
    }:
        raise PlanError("finding classification contains unknown or missing fields")
    name = value.get("classification")
    if name not in CLASSIFICATION_ACTIONS:
        raise PlanError("unsupported finding classification")
    timing = value.get("timing")
    if timing not in TIMINGS:
        raise PlanError("finding timing must be BEFORE_FREEZE or AFTER_FREEZE")
    raw_risk = value.get("risk")
    if not isinstance(raw_risk, list) or any(item not in RISK_CLASSES for item in raw_risk):
        raise PlanError("finding risk contains an unsupported value")
    risk = tuple(dict.fromkeys(raw_risk))
    technical = _strict_bool(value.get("technically_blocking"), "technically_blocking")
    mechanical = _strict_bool(value.get("mechanically_blocking"), "mechanically_blocking")

    high_risk = NON_BLOCKING_FORBIDDEN_RISKS.intersection(risk)
    if high_risk and not technical:
        raise PlanError(
            "P1/P2 and security, authentication, integrity, or fail-open findings "
            "must remain technically blocking"
        )
    if name == "NON_BLOCKING_FOLLOWUP":
        if timing != "AFTER_FREEZE":
            raise PlanError("non-blocking follow-up is only valid after the evidence freeze")
        if technical:
            raise PlanError("a technically blocking finding cannot use the non-blocking path")
        forbidden = NON_BLOCKING_FORBIDDEN_RISKS.intersection(risk)
        if forbidden:
            raise PlanError(
                "high-risk findings cannot use the non-blocking path: " + ", ".join(sorted(forbidden))
            )
    if name in {"NEW_RESPONSIBILITY", "INVALID_FINDING"} and technical:
        raise PlanError(f"{name} cannot be a technical blocker of the current contract")

    return Classification(name, CLASSIFICATION_ACTIONS[name], technical, mechanical, timing, risk)


def validate_request(request: Mapping[str, Any]) -> Classification:
    if not isinstance(request, Mapping):
        raise PlanError("replanning request must be an object")
    if set(request) != {"current_issue", "finding", "operation"}:
        raise PlanError("replanning request contains unknown or missing fields")
    current = request.get("current_issue")
    if not isinstance(current, str) or "#" not in current:
        raise PlanError("current_issue must be repository-qualified")
    classification = classify(request.get("finding"))
    operation = request.get("operation")
    if not isinstance(operation, Mapping):
        raise PlanError("operation must be an object")
    if operation.get("kind") != classification.action:
        if classification.name == "IN_CONTRACT_DEFECT":
            raise PlanError("an in-contract defect must stay in the current contract")
        raise PlanError(
            f"{classification.name} requires {classification.action}, not {operation.get('kind')}"
        )
    return classification


def _node_fingerprint(node: Node) -> dict[str, Any]:
    return {
        "key": node.key,
        "node_id": node.node_id,
        "repository_id": node.repository_id,
        "title": node.title,
        "body_digest": node.body_digest,
        "state": node.state,
        "state_reason": node.state_reason,
        "parent": node.parent,
        "parent_observable": node.parent_observable,
        "children": list(node.children),
        "children_observable": node.children_observable,
        "blocked_by": list(node.blocked_by),
        "dependencies_observable": node.dependencies_observable,
        "blocking": list(node.blocking),
        "blocking_observable": node.blocking_observable,
        "has_acceptance_criteria": node.has_acceptance_criteria,
        "resolved": node.resolved,
    }


def snapshot_digest(snapshot: Snapshot) -> str:
    document = [_node_fingerprint(snapshot.nodes[key]) for key in sorted(snapshot.nodes)]
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _issue_spec(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"alias", "repository", "title", "body"}:
        raise PlanError("new issue must contain exactly alias, repository, title, and body")
    result = {name: value.get(name) for name in ("alias", "repository", "title", "body")}
    if not all(isinstance(item, str) and item.strip() for item in result.values()):
        raise PlanError("new issue fields must be non-empty strings")
    if not ALIAS.fullmatch(result["alias"]):
        raise PlanError("new issue alias is malformed")
    try:
        parse_node_key(f"{result['repository']}#1")
    except ValueError as exc:
        raise PlanError("new issue repository must be owner/name")
    return result


def _exact_operation(operation: Mapping[str, Any], fields: set[str]) -> None:
    if set(operation) != fields:
        raise PlanError("operation contains unknown or missing fields for its classification")


def _step(kind: str, **arguments: Any) -> Step:
    return Step(kind, arguments)


def _placements(value: Any, expected: tuple[str, ...], aliases: set[str], label: str) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise PlanError(f"{label} must place every existing relationship exactly once")
    result: dict[str, list[str]] = {}
    allowed = aliases | {AGGREGATE}
    for edge in expected:
        targets = value.get(edge)
        if (
            not isinstance(targets, list)
            or not targets
            or len(targets) != len(set(targets))
            or any(target not in allowed for target in targets)
        ):
            raise PlanError(f"{label} contains an invalid placement for {edge}")
        result[edge] = list(targets)
    return result


def build_plan(snapshot: Snapshot, request: Mapping[str, Any], *, actor: str) -> Plan:
    """Compile one semantic operation into an inspectable, bounded step list."""

    classification = validate_request(request)
    if not isinstance(actor, str) or not actor.strip():
        raise PlanError("authenticated actor identity is required")
    current_key = str(request["current_issue"])
    current = snapshot.get(current_key)
    if current is None or not current.resolved or not current.is_open:
        raise PlanError("current issue is missing or closed")
    if current.children:
        raise PlanError("the current delivery contract must still be a leaf")
    if not (
        current.parent_observable
        and current.children_observable
        and current.dependencies_observable
    ):
        raise PlanError("current issue graph state is incomplete")
    operation = request["operation"]
    owner = current.parent
    plan_owner = owner
    steps: list[Step] = []

    if classification.action in {"KEEP_IN_CURRENT_CONTRACT", "REJECT_WITH_EVIDENCE"}:
        _exact_operation(operation, {"kind"})
    elif classification.action in {"CREATE_OWNED_SIBLING", "CREATE_OWNED_FOLLOWUP"}:
        owner_node = snapshot.get(owner) if owner else None
        if owner is None:
            _exact_operation(operation, {"kind", "epic", "issue"})
            epic = _issue_spec(operation.get("epic"))
            plan_owner = "@" + epic["alias"]
            steps.append(_step("CREATE_ISSUE", parent=None, **epic))
            steps.append(_step("ADD_SUB_ISSUE", parent=plan_owner, child=current_key))
            owner = plan_owner
        elif owner_node is None or not owner_node.is_open:
            raise PlanError("new responsibility requires an open owning epic or sub-epic")
        else:
            _exact_operation(operation, {"kind", "issue"})
        spec = _issue_spec(operation.get("issue"))
        if owner.startswith("@") and spec["alias"] == owner[1:]:
            raise PlanError("new issue and root epic aliases must be distinct")
        steps.append(_step("CREATE_ISSUE", parent=owner, **spec))
        steps.append(_step("REPRIORITIZE_SUB_ISSUE", parent=owner, child="@" + spec["alias"], after=current_key))
    elif classification.action == "INSERT_PREREQUISITE":
        existing = operation.get("existing_issue")
        created = operation.get("issue")
        if (existing is None) == (created is None):
            raise PlanError("prerequisite must name exactly one existing or new issue")
        if existing is not None:
            _exact_operation(operation, {"kind", "existing_issue", "move_current_blockers"})
            existing_node = snapshot.get(existing) if isinstance(existing, str) else None
            if (
                existing_node is None
                or not existing_node.is_open
                or not existing_node.has_acceptance_criteria
            ):
                raise PlanError("existing prerequisite is absent from the verified snapshot")
            prerequisite = existing
        else:
            owner_node = snapshot.get(owner) if owner else None
            if owner is None:
                _exact_operation(operation, {"kind", "epic", "issue", "move_current_blockers"})
                epic = _issue_spec(operation.get("epic"))
                plan_owner = "@" + epic["alias"]
                steps.append(_step("CREATE_ISSUE", parent=None, **epic))
                steps.append(_step("ADD_SUB_ISSUE", parent=plan_owner, child=current_key))
                owner = plan_owner
            elif owner_node is None or not owner_node.is_open:
                raise PlanError("a new prerequisite requires an open owning epic or sub-epic")
            else:
                _exact_operation(operation, {"kind", "issue", "move_current_blockers"})
            spec = _issue_spec(created)
            if owner.startswith("@") and spec["alias"] == owner[1:]:
                raise PlanError("new prerequisite and root epic aliases must be distinct")
            prerequisite = "@" + spec["alias"]
            steps.append(_step("CREATE_ISSUE", parent=owner, **spec))
            steps.append(_step("REPRIORITIZE_SUB_ISSUE", parent=owner, child=prerequisite, before=current_key))
        if prerequisite in current.blocked_by:
            raise PlanError("current issue already has that prerequisite")
        moved = operation.get("move_current_blockers")
        if not isinstance(moved, list) or len(moved) != len(set(moved)):
            raise PlanError("move_current_blockers must be a unique list")
        if any(blocker not in current.blocked_by for blocker in moved):
            raise PlanError("only an exact current blocker may be rewired")
        for blocker in moved:
            steps.append(_step("ADD_BLOCKED_BY", blocked=prerequisite, blocker=blocker))
        steps.append(_step("ADD_BLOCKED_BY", blocked=current_key, blocker=prerequisite))
        for blocker in moved:
            steps.append(_step("REMOVE_BLOCKED_BY", blocked=current_key, blocker=blocker))
    else:
        _exact_operation(
            operation,
            {"kind", "children", "blocked_by_placement", "blocking_placement"},
        )
        if not current.blocking_observable:
            raise PlanError("promotion requires complete reverse dependency state")
        raw_children = operation.get("children")
        if not isinstance(raw_children, list):
            raise PlanError("promotion children must be a list")
        specs = [_issue_spec(item) for item in raw_children]
        aliases = {spec["alias"] for spec in specs}
        if len(aliases) != len(specs):
            raise PlanError("promotion child aliases must be unique")
        blocked_by = _placements(
            operation.get("blocked_by_placement"), current.blocked_by, aliases, "blocked_by_placement"
        )
        blocking = _placements(
            operation.get("blocking_placement"), current.blocking, aliases, "blocking_placement"
        )
        if len(specs) < 2:
            raise PlanError("promotion requires at least two independently deliverable child contracts")
        for spec in specs:
            steps.append(_step("CREATE_ISSUE", parent=current_key, **spec))
        for blocker, targets in blocked_by.items():
            for target in targets:
                if target != AGGREGATE:
                    steps.append(_step("ADD_BLOCKED_BY", blocked="@" + target, blocker=blocker))
            if AGGREGATE not in targets:
                steps.append(_step("REMOVE_BLOCKED_BY", blocked=current_key, blocker=blocker))
        for dependent, targets in blocking.items():
            for target in targets:
                if target != AGGREGATE:
                    steps.append(_step("ADD_BLOCKED_BY", blocked=dependent, blocker="@" + target))
            if AGGREGATE not in targets:
                steps.append(_step("REMOVE_BLOCKED_BY", blocked=dependent, blocker=current_key))

    plan = Plan(
        actor=actor,
        classification=classification,
        current_issue=current_key,
        owner=plan_owner,
        snapshot_digest=snapshot_digest(snapshot),
        steps=tuple(steps),
        request=request,
    )
    _validate_simulated_plan(snapshot, plan)
    return plan


def _validate_simulated_plan(snapshot: Snapshot, plan: Plan) -> None:
    """Run the canonical validator over the exact planned graph before writes."""

    from . import resolver

    nodes = dict(snapshot.nodes)
    aliases: dict[str, str] = {}
    next_number = 900_000_000

    def resolve_key(reference: str) -> str:
        if reference.startswith("@"):
            return aliases[reference[1:]]
        return reference

    affected = {plan.current_issue}
    for step in plan.steps:
        arguments = step.arguments
        if step.kind == "CREATE_ISSUE":
            while f"{arguments['repository']}#{next_number}" in nodes:
                next_number += 1
            key = f"{arguments['repository']}#{next_number}"
            next_number += 1
            aliases[str(arguments["alias"])] = key
            parent = arguments["parent"]
            parent = resolve_key(parent) if isinstance(parent, str) else None
            repository, number = key.rsplit("#", 1)
            nodes[key] = Node(
                repository=repository,
                number=int(number),
                state="open",
                parent=parent,
                node_id="SIMULATED",
                repository_id="SIMULATED",
                has_acceptance_criteria=True,
                blocking_observable=True,
            )
            if parent:
                owner = nodes[parent]
                nodes[parent] = replace(owner, children=owner.children + (key,))
                affected.add(parent)
            affected.add(key)
        elif step.kind == "ADD_SUB_ISSUE":
            parent = resolve_key(str(arguments["parent"]))
            child = resolve_key(str(arguments["child"]))
            owner, member = nodes[parent], nodes[child]
            if member.parent is not None:
                raise PlanError("planned containment would replace an existing parent")
            nodes[parent] = replace(owner, children=owner.children + (child,))
            nodes[child] = replace(member, parent=parent)
            affected.update((parent, child))
        elif step.kind == "REPRIORITIZE_SUB_ISSUE":
            parent = resolve_key(str(arguments["parent"]))
            child = resolve_key(str(arguments["child"]))
            owner = nodes[parent]
            children = list(owner.children)
            children.remove(child)
            anchor_name = "before" if "before" in arguments else "after"
            anchor = resolve_key(str(arguments[anchor_name]))
            position = children.index(anchor)
            children.insert(position if anchor_name == "before" else position + 1, child)
            nodes[parent] = replace(owner, children=tuple(children))
            affected.add(parent)
        elif step.kind in {"ADD_BLOCKED_BY", "REMOVE_BLOCKED_BY"}:
            blocked = resolve_key(str(arguments["blocked"]))
            blocker = resolve_key(str(arguments["blocker"]))
            blocked_node, blocker_node = nodes[blocked], nodes[blocker]
            if not blocked_node.dependencies_observable or not blocker_node.blocking_observable:
                raise PlanError("planned dependency state is incomplete")
            if blocker_node.blocking_count != len(blocker_node.blocking):
                raise PlanError("planned reverse dependency count is inconsistent")
            blocked_by, blocking = list(blocked_node.blocked_by), list(blocker_node.blocking)
            if step.kind == "ADD_BLOCKED_BY":
                if blocker in blocked_by or blocked in blocking:
                    raise PlanError("planned dependency already exists")
                blocked_by.append(blocker)
                blocking.append(blocked)
            else:
                if blocker not in blocked_by:
                    raise PlanError("planned dependency removal is stale")
                blocked_by.remove(blocker)
                if blocked not in blocking:
                    raise PlanError("planned reverse dependency removal is stale")
                blocking.remove(blocked)
            nodes[blocked] = replace(blocked_node, blocked_by=tuple(blocked_by))
            nodes[blocker] = replace(
                blocker_node,
                blocking=tuple(blocking),
                blocking_count=len(blocking),
            )
            affected.update((blocked, blocker))

        simulated = Snapshot(nodes)
        roots = set(affected)
        if plan.owner:
            roots.add(resolve_key(plan.owner))
        for root in roots:
            result = resolver.resolve(simulated, root)
            if not result.complete or result.structurally_malformed:
                raise PlanError("planned graph does not pass canonical structural validation")


class RecordingWriter:
    """Hermetic writer used by policy tests and callers composing dry runs."""

    def __init__(self) -> None:
        self.calls: list[Step] = []

    def apply(
        self,
        step: Step,
        aliases: Mapping[str, CreatedIssueIdentity],
        *,
        plan: Plan,
        step_index: int,
    ) -> CreatedIssueIdentity | None:
        self.calls.append(step)
        if step.kind == "CREATE_ISSUE":
            return CreatedIssueIdentity(
                key=f"created/{step.arguments['alias']}#1",
                node_id=f"CREATED_{step_index}",
                repository_id="CREATED_REPOSITORY",
            )
        return None


def _identities(document: Mapping[str, Any]) -> dict[str, CreatedIssueIdentity]:
    identities: dict[str, CreatedIssueIdentity] = {}
    for alias, value in document.items():
        if not isinstance(alias, str) or not isinstance(value, Mapping):
            raise StalePlanError("recovery created identity is malformed")
        if set(value) != {"key", "node_id", "repository_id"}:
            raise StalePlanError("recovery created identity has unknown or missing fields")
        try:
            identity = CreatedIssueIdentity(
                key=str(value["key"]),
                node_id=str(value["node_id"]),
                repository_id=str(value["repository_id"]),
            )
            parse_node_key(identity.key)
        except (KeyError, ValueError) as exc:
            raise StalePlanError("recovery created identity is malformed") from exc
        if not identity.node_id or not identity.repository_id:
            raise StalePlanError("recovery created identity is incomplete")
        identities[alias] = identity
    return identities


def recovery_identities(evidence: Mapping[str, Any]) -> dict[str, CreatedIssueIdentity]:
    created = evidence.get("created")
    if not isinstance(created, Mapping):
        raise StalePlanError("recovery created identities are missing")
    identities = _identities(created)
    if len({item.key for item in identities.values()}) != len(identities) or len(
        {item.node_id for item in identities.values()}
    ) != len(identities):
        raise StalePlanError("recovery created identities are not unique")
    return identities


def apply_plan(
    plan: Plan,
    snapshot: Snapshot,
    *,
    actor: str,
    writer: Any,
    recovery: RecoveryJournal | None = None,
    resume: bool = False,
    recovery_locked: bool = False,
) -> dict[str, CreatedIssueIdentity]:
    """Apply only after exact actor and graph preconditions still match."""

    lock = (
        nullcontext()
        if recovery is None or recovery_locked
        else recovery.lock()
    )
    with lock:
        if actor != plan.actor:
            raise StalePlanError("authenticated actor changed before mutation")
        if snapshot_digest(snapshot) != plan.snapshot_digest:
            raise StalePlanError("canonical graph drift detected before mutation")
        prepare = getattr(writer, "prepare", None)
        if prepare is not None:
            prepare(plan, snapshot)
        if recovery is None and plan.steps and hasattr(writer, "mutation_index"):
            raise PlanError("mutating replanning requires durable recovery evidence")
        if recovery is not None:
            if resume:
                evidence = recovery.load()
                if evidence["attempting_step"] is not None:
                    raise StalePlanError(
                        "recovery has an unknown mutation outcome; inspect GitHub state manually"
                    )
                aliases = recovery_identities(evidence)
                start_step = int(evidence["next_step"])
            else:
                recovery.start()
                aliases = {}
                start_step = 0
        else:
            aliases = {}
            start_step = 0
        restore = getattr(writer, "restore_created", None)
        if restore is not None:
            restore(aliases)
        for step_index, step in enumerate(plan.steps[start_step:], start=start_step):
            if recovery is not None:
                recovery.begin_step(step_index)
            mutation_index = getattr(writer, "mutation_index", None)
            try:
                created = writer.apply(step, aliases, plan=plan, step_index=step_index)
            except Exception:
                if recovery is not None and getattr(writer, "mutation_index", None) == mutation_index:
                    recovery.cancel_unattempted_step(step_index)
                raise
            if step.kind == "CREATE_ISSUE":
                if not isinstance(created, CreatedIssueIdentity):
                    raise PlanError("issue creation did not return a canonical identity")
                aliases[str(step.arguments["alias"])] = created
            if recovery is not None:
                recovery.complete_step(step_index, created)
        return aliases


def rebuild_plan(document: Mapping[str, Any], snapshot: Snapshot, *, actor: str) -> Plan:
    """Recompile an untrusted serialized plan and require byte-semantic equality."""

    if not isinstance(document, Mapping) or document.get("schema") != SCHEMA:
        raise PlanError("unsupported replanning plan schema")
    expected_actor = document.get("actor")
    if expected_actor != actor:
        raise StalePlanError("authenticated actor changed before mutation")
    request = document.get("request")
    rebuilt = build_plan(snapshot, request, actor=actor)
    if rebuilt.to_dict() != dict(document):
        raise StalePlanError("serialized plan differs from the verified canonical plan")
    return rebuilt


def _resolve(reference: str, aliases: Mapping[str, CreatedIssueIdentity]) -> str:
    if reference.startswith("@"):
        alias = reference[1:]
        if alias not in aliases:
            raise PlanError(f"mutation result omitted alias {alias}")
        return aliases[alias].key
    return reference


def verify_applied(
    plan: Plan,
    snapshot: Snapshot,
    aliases: Mapping[str, CreatedIssueIdentity],
    *,
    step_limit: int | None = None,
) -> None:
    """Prove every intended relationship and the absence of every removed edge."""

    # Replay the plan over its authenticated pre-state. The final comparison
    # below rejects any concurrent or accidental relationship change outside
    # the exact emitted steps.
    before_nodes = plan.request.get("_snapshot_nodes")
    if before_nodes is not None:
        raise PlanError("request must not carry private snapshot state")

    steps = plan.steps if step_limit is None else plan.steps[:step_limit]
    for step_index, step in enumerate(steps):
        arguments = step.arguments
        if step.kind == "CREATE_ISSUE":
            created = snapshot.get(_resolve("@" + str(arguments["alias"]), aliases))
            expected_parent = arguments["parent"]
            if isinstance(expected_parent, str):
                expected_parent = _resolve(expected_parent, aliases)
            identity = aliases[str(arguments["alias"])]
            expected_repository, _ = parse_node_key(identity.key)
            expected_children: list[str] = []
            expected_blocked_by: set[str] = set()
            expected_blocking: set[str] = set()
            for relationship in steps:
                relationship_arguments = relationship.arguments
                if relationship.kind == "CREATE_ISSUE":
                    relationship_parent = relationship_arguments["parent"]
                    if (
                        isinstance(relationship_parent, str)
                        and _resolve(relationship_parent, aliases) == identity.key
                    ):
                        expected_children.append(
                            _resolve(
                                "@" + str(relationship_arguments["alias"]), aliases
                            )
                        )
                elif relationship.kind == "ADD_SUB_ISSUE" and _resolve(
                    str(relationship_arguments["parent"]), aliases
                ) == identity.key:
                    expected_children.append(
                        _resolve(str(relationship_arguments["child"]), aliases)
                    )
                elif relationship.kind == "REPRIORITIZE_SUB_ISSUE" and _resolve(
                    str(relationship_arguments["parent"]), aliases
                ) == identity.key:
                    child = _resolve(str(relationship_arguments["child"]), aliases)
                    expected_children.remove(child)
                    anchor_name = "before" if "before" in relationship_arguments else "after"
                    anchor = _resolve(str(relationship_arguments[anchor_name]), aliases)
                    position = expected_children.index(anchor)
                    expected_children.insert(
                        position if anchor_name == "before" else position + 1, child
                    )
                elif relationship.kind in {"ADD_BLOCKED_BY", "REMOVE_BLOCKED_BY"}:
                    blocked = _resolve(str(relationship_arguments["blocked"]), aliases)
                    blocker = _resolve(str(relationship_arguments["blocker"]), aliases)
                    target = (
                        expected_blocked_by
                        if blocked == identity.key
                        else expected_blocking
                        if blocker == identity.key
                        else None
                    )
                    if target is not None:
                        if relationship.kind == "ADD_BLOCKED_BY":
                            target.add(blocker if blocked == identity.key else blocked)
                        else:
                            target.discard(blocker if blocked == identity.key else blocked)
            if (
                created is None
                or created.node_id != identity.node_id
                or created.repository_id != identity.repository_id
                or expected_repository != arguments["repository"]
                or created.title != arguments["title"]
                or created.body_digest != content_digest(created_issue_body(plan, step_index))
                or not created.is_open
                or created.state_reason is not None
                or created.parent != expected_parent
                or not created.parent_observable
                or not created.children_observable
                or not created.dependencies_observable
                or not created.blocking_observable
                or created.children != tuple(expected_children)
                or set(created.blocked_by) != expected_blocked_by
                or set(created.blocking) != expected_blocking
                or created.blocking_count != len(expected_blocking)
            ):
                raise PlanError("created issue differs from its exact planned postcondition")
        elif step.kind == "ADD_SUB_ISSUE":
            parent = snapshot.get(_resolve(str(arguments["parent"]), aliases))
            child = snapshot.get(_resolve(str(arguments["child"]), aliases))
            if parent is None or child is None or child.parent != parent.key or child.key not in parent.children:
                raise PlanError("intended containment relationship is absent after mutation")
        elif step.kind == "ADD_BLOCKED_BY":
            blocked = snapshot.get(_resolve(str(arguments["blocked"]), aliases))
            blocker = _resolve(str(arguments["blocker"]), aliases)
            if blocked is None or blocker not in blocked.blocked_by:
                raise PlanError("intended dependency is absent after mutation")
        elif step.kind == "REMOVE_BLOCKED_BY":
            blocked = snapshot.get(_resolve(str(arguments["blocked"]), aliases))
            blocker = _resolve(str(arguments["blocker"]), aliases)
            if blocked is None or blocker in blocked.blocked_by:
                raise PlanError("removed dependency remains after mutation")
        elif step.kind == "REPRIORITIZE_SUB_ISSUE":
            parent = snapshot.get(_resolve(str(arguments["parent"]), aliases))
            child = _resolve(str(arguments["child"]), aliases)
            anchor_name = "before" if "before" in arguments else "after"
            anchor = _resolve(str(arguments[anchor_name]), aliases)
            if parent is None or child not in parent.children or anchor not in parent.children:
                raise PlanError("sub-issue ordering target is absent after mutation")
            child_position = parent.children.index(child)
            anchor_position = parent.children.index(anchor)
            if (anchor_name == "before" and child_position >= anchor_position) or (
                anchor_name == "after" and child_position <= anchor_position
            ):
                raise PlanError("sub-issue ordering was not applied")


def verify_unchanged_relationships(
    plan: Plan,
    before: Snapshot,
    after: Snapshot,
    aliases: Mapping[str, CreatedIssueIdentity],
    *,
    step_limit: int | None = None,
) -> None:
    """Reject unrelated state, hierarchy, ordering, or dependency changes."""

    expected_children = {key: list(node.children) for key, node in before.nodes.items()}
    expected_blocked_by = {key: list(node.blocked_by) for key, node in before.nodes.items()}
    expected_blocking = {key: list(node.blocking) for key, node in before.nodes.items()}
    expected_parent = {key: node.parent for key, node in before.nodes.items()}

    for alias, identity in aliases.items():
        key = identity.key
        expected_children[key] = []
        expected_blocked_by[key] = []
        expected_blocking[key] = []
        expected_parent[key] = None

    steps = plan.steps if step_limit is None else plan.steps[:step_limit]
    for step in steps:
        arguments = step.arguments
        if step.kind == "CREATE_ISSUE":
            created = _resolve("@" + str(arguments["alias"]), aliases)
            parent = arguments["parent"]
            if isinstance(parent, str):
                parent = _resolve(parent, aliases)
                expected_children[parent].append(created)
                expected_parent[created] = parent
        elif step.kind == "ADD_SUB_ISSUE":
            parent = _resolve(str(arguments["parent"]), aliases)
            child = _resolve(str(arguments["child"]), aliases)
            expected_children[parent].append(child)
            expected_parent[child] = parent
        elif step.kind == "REPRIORITIZE_SUB_ISSUE":
            parent = _resolve(str(arguments["parent"]), aliases)
            children = expected_children[parent]
            child = _resolve(str(arguments["child"]), aliases)
            children.remove(child)
            anchor_name = "before" if "before" in arguments else "after"
            anchor = _resolve(str(arguments[anchor_name]), aliases)
            anchor_position = children.index(anchor)
            children.insert(anchor_position if anchor_name == "before" else anchor_position + 1, child)
        elif step.kind in {"ADD_BLOCKED_BY", "REMOVE_BLOCKED_BY"}:
            blocked = _resolve(str(arguments["blocked"]), aliases)
            blocker = _resolve(str(arguments["blocker"]), aliases)
            if step.kind == "ADD_BLOCKED_BY":
                expected_blocked_by[blocked].append(blocker)
                expected_blocking[blocker].append(blocked)
            else:
                expected_blocked_by[blocked].remove(blocker)
                expected_blocking[blocker].remove(blocked)

    expected_keys = set(before.nodes) | {identity.key for identity in aliases.values()}
    if set(after.nodes) != expected_keys:
        raise PlanError("post-mutation scope contains an unplanned issue identity")

    for key, old in before.nodes.items():
        live = after.get(key)
        if live is None:
            raise PlanError(f"pre-existing issue {key} disappeared during mutation")
        immutable = (old.state, old.state_reason, expected_parent[key], old.title, old.body_digest)
        if (live.state, live.state_reason, live.parent, live.title, live.body_digest) != immutable:
            raise PlanError(f"unrelated issue state, content, or parent changed for {key}")
        if (
            not live.parent_observable
            or not live.children_observable
            or not live.dependencies_observable
            or (old.blocking_observable and not live.blocking_observable)
        ):
            raise PlanError(f"post-mutation relationship state is incomplete for {key}")
        if tuple(expected_children[key]) != live.children:
            raise PlanError(f"unplanned child relationship or order change for {key}")
        if set(expected_blocked_by[key]) != set(live.blocked_by):
            raise PlanError(f"unplanned blocked-by relationship change for {key}")
        if old.blocking_observable and set(expected_blocking[key]) != set(live.blocking):
            raise PlanError(f"unplanned blocking relationship change for {key}")
        if old.blocking_observable and live.blocking_count != len(expected_blocking[key]):
            raise PlanError(f"unplanned blocking relationship count change for {key}")
    for step_index, step in enumerate(steps):
        if step.kind != "CREATE_ISSUE":
            continue
        alias = str(step.arguments["alias"])
        identity = aliases[alias]
        key = identity.key
        live = after.get(key)
        repository, _ = parse_node_key(key)
        if live is None:
            raise PlanError(f"created issue {key} is absent after mutation")
        if (
            live.node_id != identity.node_id
            or live.repository_id != identity.repository_id
            or repository != step.arguments["repository"]
            or live.title != step.arguments["title"]
            or live.body_digest != content_digest(created_issue_body(plan, step_index))
            or not live.is_open
            or live.state_reason is not None
            or live.parent != expected_parent[key]
            or tuple(expected_children[key]) != live.children
            or set(expected_blocked_by[key]) != set(live.blocked_by)
            or set(expected_blocking[key]) != set(live.blocking)
            or live.blocking_count != len(expected_blocking[key])
            or not live.parent_observable
            or not live.children_observable
            or not live.dependencies_observable
            or not live.blocking_observable
        ):
            raise PlanError(f"created issue {key} differs from the exact planned graph")
