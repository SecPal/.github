#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Enforce the closed process-launch surface of the PR review helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import symtable
import sys


@dataclass(frozen=True)
class ProcessCall:
    class_name: str | None
    function_name: str
    executable: str
    arguments: str
    keywords: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DynamicImportCall:
    functions: tuple[str, ...]
    expression: str


@dataclass(frozen=True)
class LoopSite:
    kind: str
    functions: tuple[str, ...]
    iterator: str


@dataclass(frozen=True)
class ClassShape:
    bases: tuple[str, ...]
    keywords: tuple[tuple[str | None, str], ...]
    decorators: tuple[str, ...]


ACTION_CALLS = (
    ProcessCall(
        None,
        "_run_registered_validations",
        "executable",
        "command['argv'][1:]",
        (
            ("check", "False"),
            ("cwd", "working_directory"),
            ("env", "environment"),
            ("stderr", "subprocess.DEVNULL"),
            ("stdin", "subprocess.DEVNULL"),
            ("stdout", "subprocess.DEVNULL"),
            ("timeout", "LOCAL_VALIDATION_TIMEOUT_SECONDS"),
        ),
    ),
    ProcessCall(
        "ActionCommandRunner",
        "run",
        "self.executable_path",
        "arguments[1:]",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("encoding", "'utf-8'"),
            ("env", "evidence.command_environment('gh')"),
            ("errors", "'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "True"),
            ("timeout", "EXTERNAL_COMMAND_TIMEOUT_SECONDS"),
        ),
    ),
    ProcessCall(
        "FastPathGateway",
        "_git",
        "self.git_executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("cwd", "self.repository_root"),
            ("encoding", "'utf-8'"),
            ("env", "evidence.command_environment('git')"),
            ("errors", "'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "True"),
            ("timeout", "EXTERNAL_COMMAND_TIMEOUT_SECONDS"),
        ),
    ),
    ProcessCall(
        None,
        "_run_attestation_git",
        "git_executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("cwd", "repository_root"),
            ("encoding", "None if raw_output else 'utf-8'"),
            ("env", "evidence.command_environment('git')"),
            ("errors", "None if raw_output else 'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "not raw_output"),
            ("timeout", "EXTERNAL_COMMAND_TIMEOUT_SECONDS"),
        ),
    ),
)

EVIDENCE_CALLS = (
    ProcessCall(
        "CommandRunner",
        "run",
        "command",
        "",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("encoding", "'utf-8'"),
            ("env", "environment"),
            ("errors", "'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "True"),
            ("timeout", "self.timeout_seconds"),
        ),
    ),
)

RESOLVER_CALLS = (
    ProcessCall(
        None,
        "_run_gh",
        "executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("encoding", "'utf-8'"),
            ("env", "evidence.command_environment('gh')"),
            ("errors", "'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "True"),
            ("timeout", "30"),
        ),
    ),
    ProcessCall(
        None,
        "_run_git",
        "executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("cwd", "repository_root"),
            ("encoding", "'utf-8'"),
            ("env", "evidence.command_environment('git')"),
            ("errors", "'replace'"),
            ("stdin", "subprocess.DEVNULL"),
            ("text", "True"),
            ("timeout", "30"),
        ),
    ),
)

LATE_DISPOSITION_CALLS = (
    ProcessCall(
        None,
        "_read_global_git_value",
        "executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("env", "environment"),
            ("stdin", "subprocess.DEVNULL"),
            ("timeout", "30"),
        ),
    ),
    ProcessCall(
        None,
        "_run_signature_command_without_input",
        "executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("env", "environment"),
            ("stdin", "subprocess.DEVNULL"),
            ("timeout", "30"),
        ),
    ),
    ProcessCall(
        None,
        "_run_signature_command_with_input",
        "executable",
        "arguments",
        (
            ("capture_output", "True"),
            ("check", "False"),
            ("env", "environment"),
            ("input", "stdin"),
            ("timeout", "30"),
        ),
    ),
)

EXPECTED_CALLS = {
    "secpal-pr-review.py": EVIDENCE_CALLS,
    "secpal-pr-review-actions.py": ACTION_CALLS,
    "fast_path.py": (),
    "follow_up.py": (),
    "secpal-resolve-fixed-threads.py": RESOLVER_CALLS,
    "late_disposition.py": LATE_DISPOSITION_CALLS,
    "secpal-create-late-classification.py": (),
    "secpal-create-late-disposition.py": (),
}

SAFE_SUBPROCESS_ATTRIBUTES = {
    "CompletedProcess",
    "DEVNULL",
    "TimeoutExpired",
}
SAFE_OS_ATTRIBUTES = {
    "X_OK",
    "access",
    "chmod",
    "close",
    "devnull",
    "environ",
    "fchmod",
    "fdopen",
    "fsync",
    "getuid",
    "path",
    "pathsep",
    "replace",
    "open",
    "fstat",
    "read",
    "write",
    "stat",
    "O_RDONLY",
    "O_WRONLY",
    "O_CREAT",
    "O_EXCL",
    "O_CLOEXEC",
    "O_NOFOLLOW",
    "O_DIRECTORY",
    "unlink",
}
ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "argparse",
    "copy",
    "dataclasses",
    "datetime",
    "errno",
    "functools",
    "hashlib",
    "importlib",
    "json",
    "operator",
    "os",
    "pathlib",
    "pwd",
    "re",
    "secrets",
    "secpal_work_graph",
    "secpal_pr_review",
    "site",
    "stat",
    "subprocess",
    "sys",
    "tempfile",
    "types",
    "typing",
    "urllib",
}
ALLOWED_IMPORTS = {
    "secpal-pr-review.py": {
        "from __future__ import annotations",
        "import argparse",
        "import copy",
        "import hashlib",
        "import json",
        "import os",
        "import re",
        "import stat",
        "import subprocess",
        "import sys",
        "import tempfile",
        "import types",
        "from dataclasses import dataclass",
        "from datetime import datetime",
        "from functools import cache",
        "from pathlib import Path",
        "from typing import Any, Callable, Iterable",
        "from urllib.parse import quote, unquote, urlparse",
    },
    "secpal-pr-review-actions.py": {
        "from __future__ import annotations",
        "import argparse",
        "import copy",
        "import hashlib",
        "import importlib.util",
        "import json",
        "import os",
        "import pwd",
        "import re",
        "import site",
        "import subprocess",
        "import sys",
        "import tempfile",
        "import types",
        "from pathlib import Path",
        "from typing import Any, Iterable",
        "from urllib.parse import quote",
    },
    "fast_path.py": {
        "from __future__ import annotations",
        "import copy",
        "import hashlib",
        "import importlib.util",
        "import json",
        "import os",
        "import re",
        "import sys",
        "import tempfile",
        "from dataclasses import dataclass, field",
        "from pathlib import Path",
        "from typing import Any, Callable, TypeVar",
    },
    "follow_up.py": {
        "from __future__ import annotations",
        "import re",
        "from dataclasses import dataclass",
        "from typing import Any, Callable, Mapping",
        "from secpal_work_graph import github, resolver",
        "from secpal_work_graph.acceptance_criteria import MarkdownParserUnavailable",
    },
    "secpal-resolve-fixed-threads.py": {
        "from __future__ import annotations",
        "import argparse",
        "import hashlib",
        "import importlib.util",
        "import json",
        "import operator",
        "import os",
        "import re",
        "import stat",
        "import subprocess",
        "import sys",
        "from dataclasses import dataclass",
        "from pathlib import Path",
        "from typing import Any, Callable, Sequence",
        "from secpal_pr_review import lifecycle_orchestration as module",
    },
    "late_disposition.py": {
        "from __future__ import annotations",
        "import errno",
        "import hashlib",
        "import json",
        "import os",
        "import pwd",
        "import re",
        "import secrets",
        "import stat",
        "import subprocess",
        "import tempfile",
        "from dataclasses import dataclass",
        "from pathlib import Path",
        "from typing import Any, Sequence",
    },
    "secpal-create-late-disposition.py": {
        "from __future__ import annotations",
        "import argparse",
        "import importlib.util",
        "import json",
        "import sys",
        "from pathlib import Path",
        "from typing import Any, Sequence",
    },
    "secpal-create-late-classification.py": {
        "from __future__ import annotations",
        "import argparse",
        "import importlib.util",
        "import json",
        "import sys",
        "from pathlib import Path",
        "from typing import Any, Sequence",
    },
}
PROHIBITED_IMPORT_ROOTS = {
    "asyncio",
    "commands",
    "concurrent",
    "ctypes",
    "multiprocessing",
    "posix",
    "pty",
    "runpy",
    "time",
}
PROHIBITED_PROCESS_CALL_ATTRIBUTES = {
    "Popen",
    "call",
    "check_call",
    "check_output",
    "execv",
    "execve",
    "fork",
    "forkpty",
    "getoutput",
    "getstatusoutput",
    "popen",
    "posix_spawn",
    "posix_spawnp",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "startfile",
    "system",
}
PROHIBITED_REFLECTION_ATTRIBUTES = {
    "__bases__",
    "__class__",
    "__closure__",
    "__code__",
    "__dict__",
    "__getattribute__",
    "__globals__",
    "__mro__",
    "__subclasses__",
}
SAFE_RUN_TARGETS = {
    "secpal-pr-review.py": {
        "runner.run",
        "self.runner.run",
    },
    "secpal-pr-review-actions.py": {
        "self.github.runner.run",
        "self.runner.run",
    },
}
DIRECT_MODULE_ATTRIBUTES = {
    "secpal-pr-review.py": {
        "stat": {"S_ISDIR", "S_ISLNK", "S_ISREG"},
        "sys": {"stderr", "stdout"},
        "tempfile": {"mkstemp"},
    },
    "secpal-pr-review-actions.py": {
        "importlib": {"util"},
        "pwd": {"getpwuid"},
        "site": {"getusersitepackages"},
        "sys": {"modules", "platform", "stderr", "stdout", "version_info"},
        "tempfile": {"TemporaryDirectory"},
        "types": {"ModuleType"},
    },
    "fast_path.py": {
        "importlib": {"util"},
        "sys": {"modules"},
        "tempfile": {"mkstemp"},
    },
    "follow_up.py": {
        "github": {"GitHubError", "GitHubReadAdapter", "load_snapshot"},
        "resolver": {"ScopeRootUnresolved", "resolve"},
    },
    "secpal-resolve-fixed-threads.py": {
        "importlib": {"util"},
        "operator": {"attrgetter"},
        "sys": {"argv", "modules", "path", "stderr"},
    },
    "late_disposition.py": {
        "errno": {"EINVAL", "ENOTSUP"},
        "pwd": {"getpwuid"},
        "stat": {"S_ISREG"},
        "tempfile": {"TemporaryDirectory"},
    },
    "secpal-create-late-disposition.py": {
        "importlib": {"util"},
        "sys": {"argv", "modules", "stderr"},
    },
    "secpal-create-late-classification.py": {
        "importlib": {"util"},
        "sys": {"argv", "modules", "stderr"},
    },
}
LOADED_MODULE_ATTRIBUTES = {
    "secpal-pr-review-actions.py": {
        "evidence": {
            "BlockedError",
            "CommandPolicyError",
            "CommandRunner",
            "ContractError",
            "TRUSTED_COMMAND_DIRECTORIES",
            "_commit_signature_format",
            "_mark_effective_checks",
            "_normalize_applicable_rules",
            "_normalize_check",
            "command_environment",
            "evaluate_checks",
            "interpret_local_signature",
            "normalize_github_signature",
            "normalize_classic_branch_protection",
            "redact_diagnostic",
            "read_only_rest_endpoint_kind",
            "require_rule_evidence",
            "resolve_trusted_executable",
            "select_effective_check_target",
            "validate_against_authoritative_schema",
            "validate_config",
            "validate_snapshot",
            "verify_local_against_snapshot",
            "verify_snapshot_evidence",
        },
        "fast_path": {
            "BatchRequest",
            "CLASSIFICATION_DISPOSITIONS",
            "DIGEST",
            "IDENTITY",
            "ReadinessState",
            "RecoverableLocalError",
            "SECRET_VALUE",
            "SecurityBlocker",
            "StableFeedbackState",
            "TransientReadFailure",
            "UnknownWriteResult",
            "atomic_write_json",
            "canonical_json_bytes",
            "create_validation_attestation",
            "create_validation_receipt",
            "create_ready_integration_attestation",
            "digest_json",
            "execute_resolution_batch",
            "follow_up",
            "normalize_resolution_eligibility_evidence",
            "normalize_ready_integration_evidence",
            "normalize_ready_integration_prior_authority",
            "normalize_exceptional_recovery_evidence",
            "validate_manual_gate_evidence",
            "verify_commit_signatures",
            "verify_validation_attestation",
        },
        "follow_up": {
            "FollowUpError",
            "parse_follow_up",
        },
    },
    "fast_path.py": {
        "follow_up": {
            "FollowUpError",
            "parse_follow_up",
        },
    },
    "secpal-resolve-fixed-threads.py": {
        "evidence": {
            "CommandPolicyError",
            "ContractError",
            "TRUSTED_COMMAND_DIRECTORIES",
            "TRUSTED_COMMAND_PATH",
            "_commit_signature_format",
            "command_environment",
            "interpret_local_signature",
            "redact_diagnostic",
            "resolve_trusted_executable",
            "validate_against_authoritative_schema",
        },
        "follow_up": {
            "FollowUpError",
            "FollowUpIdentity",
            "LiveFollowUpState",
            "parse_follow_up",
            "read_live_follow_up",
            "verify_live_follow_up",
        },
        "late_disposition": {
            "CLASSIFICATION_KIND",
            "CLASSIFICATION_PURPOSE",
            "CLASSIFICATION_SIGNATURE_NAMESPACE",
            "KIND",
            "IDENTITY",
            "MAXIMUM_ARTIFACT_BYTES",
            "SCHEMA_VERSION",
            "TECHNICAL_BLOCKERS",
            "LateDispositionError",
            "_load_canonical_json",
            "canonical_json_bytes",
            "os_account_home",
            "parse_artifact",
            "parse_classification_artifact",
            "read_signing_configuration",
            "sign_artifact",
            "signer_from_git_verification",
        },
        "lifecycle_orchestration": {
            "LifecycleOrchestrationError",
            "verify_exceptional_recovery_authority",
        },
    },
    "secpal-create-late-disposition.py": {
        "resolver": {
            "ResolutionError",
            "create_late_disposition_artifact",
        },
    },
    "secpal-create-late-classification.py": {
        "resolver": {
            "ResolutionError",
            "create_late_classification_artifact",
        },
    },
}
DYNAMIC_IMPORT_CALLS = {
    "secpal-pr-review-actions.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review_evidence_shared', EVIDENCE_HELPER)",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review.fast_path', FAST_PATH_HELPER)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers", "load"),
            "importlib.util.spec_from_file_location(module_name, path)",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers", "load"),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers", "load"),
            "spec.loader.exec_module(module)",
        ),
    },
    "secpal-resolve-fixed-threads.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review_evidence_shared', EVIDENCE_HELPER)",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review.follow_up', FOLLOW_UP_HELPER)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review.late_disposition', LATE_DISPOSITION_HELPER)",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review.fast_path', FAST_PATH_HELPER)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "spec.loader.exec_module(module)",
        ),
    },
    "fast_path.py": {
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "importlib.util.spec_from_file_location("
            "'secpal_pr_review.follow_up', FOLLOW_UP_HELPER)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "spec.loader.exec_module(module)",
        ),
    },
    "secpal-create-late-disposition.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "importlib.util.spec_from_file_location("
            "'secpal_resolve_fixed_threads_for_late_evidence', RESOLVER)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "spec.loader.exec_module(module)",
        ),
    },
    "secpal-create-late-classification.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "importlib.util.spec_from_file_location("
            "'secpal_resolve_fixed_threads_for_late_classification', RESOLVER)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "importlib.util.module_from_spec(spec)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "spec.loader.exec_module(module)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules.pop(spec.name, None)",
        ),
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules[spec.name]",
        ),
    },
}
SAFE_GETATTR_CALLS = {
    "secpal-pr-review-actions.py": {
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "getattr(loaded, '__file__', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'manual_gate_evidence', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'eligibility_evidence', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'integration_evidence', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'exceptional_recovery_evidence', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'exceptional_recovery_delivery_issue', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'exceptional_recovery_authorization_id', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'delivery_issue', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'integration_authorization_id', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'expected_integration_signer', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'prior_authority', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'prior_authority_tag_ref', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'prior_reviewed_state', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'prior_receipt', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'prior_attestation', None)",
        ),
        DynamicImportCall(
            ("_command_attest_validation",),
            "getattr(arguments, 'expected_prior_authority_signer', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'prior_authority', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'prior_reviewed_state', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'prior_receipt', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'prior_attestation', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'prior_authority_tag_ref', None)",
        ),
        DynamicImportCall(
            ("_verify_ready_integration_prior_authority",),
            "getattr(arguments, 'expected_prior_authority_signer', None)",
        ),
        DynamicImportCall(
            ("_verify_integration_selection",),
            "getattr(arguments, 'delivery_issue', None)",
        ),
        DynamicImportCall(
            ("_verify_integration_selection",),
            "getattr(arguments, 'integration_authorization_id', None)",
        ),
        DynamicImportCall(
            ("_verify_integration_selection",),
            "getattr(arguments, 'expected_integration_signer', None)",
        ),
        DynamicImportCall(
            ("_verify_exceptional_recovery_selection",),
            "getattr(arguments, 'exceptional_recovery_delivery_issue', None)",
        ),
        DynamicImportCall(
            ("_verify_exceptional_recovery_selection",),
            "getattr(arguments, 'exceptional_recovery_authorization_id', None)",
        ),
    },
    "secpal-resolve-fixed-threads.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "getattr(loaded, '__file__', None)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "getattr(loaded, '__file__', None)",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "getattr(loaded, '__file__', None)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "getattr(loaded, '__file__', None)",
        ),
        DynamicImportCall(
            ("_load_lifecycle_orchestration_helper",),
            "getattr(module, '__file__', None)",
        ),
    },
    "fast_path.py": {
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "getattr(loaded, '__file__', None)",
        ),
    },
}
SAFE_SYS_MODULES_CALLS = {
    "secpal-pr-review-actions.py": {
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules.get('secpal_pr_review.fast_path')",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules.get(spec.name)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers",),
            "sys.modules.pop(module_name, None)",
        ),
    },
    "secpal-resolve-fixed-threads.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "sys.modules.get('secpal_pr_review_evidence_shared')",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "sys.modules.get(spec.name)",
        ),
        DynamicImportCall(
            ("_load_evidence_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules.get('secpal_pr_review.follow_up')",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "sys.modules.get('secpal_pr_review.late_disposition')",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules.get('secpal_pr_review.fast_path')",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
    },
    "fast_path.py": {
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules.get('secpal_pr_review.follow_up')",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules.pop(spec.name, None)",
        ),
    },
    "secpal-create-late-disposition.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules.pop(spec.name, None)",
        ),
    },
    "secpal-create-late-classification.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules.pop(spec.name, None)",
        ),
    },
}
SAFE_SYS_MODULES_STORES = {
    "secpal-pr-review-actions.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "sys.modules[spec.name]",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules[spec.name]",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers",),
            "sys.modules[package_name]",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers",),
            "sys.modules[f'{package_name}.fast_path']",
        ),
        DynamicImportCall(
            ("_load_lifecycle_publication_helpers", "load"),
            "sys.modules[module_name]",
        ),
    },
    "secpal-resolve-fixed-threads.py": {
        DynamicImportCall(
            ("_load_evidence_helper",),
            "sys.modules[spec.name]",
        ),
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules[spec.name]",
        ),
        DynamicImportCall(
            ("_load_late_disposition_helper",),
            "sys.modules[spec.name]",
        ),
        DynamicImportCall(
            ("_load_fast_path_helper",),
            "sys.modules[spec.name]",
        ),
    },
    "fast_path.py": {
        DynamicImportCall(
            ("_load_follow_up_helper",),
            "sys.modules[spec.name]",
        ),
    },
    "secpal-create-late-disposition.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules[spec.name]",
        ),
    },
    "secpal-create-late-classification.py": {
        DynamicImportCall(
            ("_load_resolver",),
            "sys.modules[spec.name]",
        ),
    },
}
RESOLVER_TOP_LEVEL_FUNCTIONS = {
    "_body_digest",
    "_canonical_json_bytes",
    "_consume_api_call",
    "_consume_comment",
    "_consume_thread",
    "_digest_json",
    "_graphql",
    "_load_evidence_helper",
    "_load_follow_up_helper",
    "_load_late_disposition_helper",
    "_load_fast_path_helper",
    "_load_lifecycle_orchestration_helper",
    "_late_signing_key",
    "_markdown_parser_environment",
    "_classify_reviewed_target",
    "_matches_late_authorization",
    "_matches_reviewed_target_identity",
    "_read_authenticated_follow_up",
    "_resolve_trusted_markdown_node",
    "_load_repository_entry",
    "_reject_nonfinite_json_constant",
    "_reject_duplicate_json_object",
    "_remote_repository",
    "_reply_state_digest",
    "_run_gh",
    "_run_git",
    "_parse_eligibility_payload",
    "_tracked_follow_ups_from_payload",
    "_tracked_follow_up_disposition_report",
    "_validation_registry_binding",
    "load_repository_limits",
    "load_eligibility_evidence",
    "load_final_feedback_boundary",
    "load_reviewed_state",
    "load_validation_evidence",
    "create_late_disposition_artifact",
    "create_late_classification_artifact",
    "main",
    "parse_args",
    "read_stable_target_thread",
    "read_target_thread",
    "require_expected_target",
    "require_late_target_origin",
    "resolve_threads",
    "resolve_late_disposition_threads",
    "validate_expected_targets",
    "validate_request",
    "verify_local_fix_commit",
    "verify_recovery_bound_source_authority",
    "verify_live_follow_up",
}
RESOLVER_CLASS_SHAPES = {
    "ExpectedThreadState": ClassShape((), (), ("dataclass(frozen=True)",)),
    "EligibilityEvidence": ClassShape((), (), ("dataclass(frozen=True)",)),
    "FinalFeedbackBoundary": ClassShape((), (), ("dataclass(frozen=True)",)),
    "InvocationBudget": ClassShape((), (), ("dataclass",)),
    "ParsedEligibility": ClassShape((), (), ("dataclass(frozen=True)",)),
    "RepositoryLimits": ClassShape((), (), ("dataclass(frozen=True)",)),
    "ReviewedState": ClassShape((), (), ("dataclass(frozen=True)",)),
    "ResolutionError": ClassShape(("RuntimeError",), (), ()),
    "TargetRead": ClassShape((), (), ("dataclass(frozen=True)",)),
    "ThreadCommentState": ClassShape((), (), ("dataclass(frozen=True)",)),
    "ThreadState": ClassShape((), (), ("dataclass(frozen=True)",)),
    "ValidationEvidence": ClassShape((), (), ("dataclass(frozen=True)",)),
}
SAFE_RESOLVER_FUNCTION_REFERENCES = {
    DynamicImportCall(
        ("load_reviewed_state",),
        "_reject_nonfinite_json_constant",
    ),
    DynamicImportCall(
        ("load_reviewed_state",),
        "_reject_duplicate_json_object",
    ),
    DynamicImportCall(
        ("load_validation_evidence",),
        "_reject_nonfinite_json_constant",
    ),
    DynamicImportCall(
        ("load_validation_evidence",),
        "_reject_duplicate_json_object",
    ),
    DynamicImportCall(
        ("load_eligibility_evidence",),
        "_reject_nonfinite_json_constant",
    ),
    DynamicImportCall(
        ("load_eligibility_evidence",),
        "_reject_duplicate_json_object",
    ),
    DynamicImportCall(
        ("verify_recovery_bound_source_authority",),
        "_reject_nonfinite_json_constant",
    ),
    DynamicImportCall(
        ("verify_recovery_bound_source_authority",),
        "_reject_duplicate_json_object",
    ),
    DynamicImportCall(
        ("_parse_eligibility_payload",),
        "_reject_nonfinite_json_constant",
    ),
    DynamicImportCall(
        ("_parse_eligibility_payload",),
        "_reject_duplicate_json_object",
    ),
    DynamicImportCall(
        ("verify_local_fix_commit",),
        "_run_git",
    ),
    DynamicImportCall(
        ("resolve_threads",),
        "_run_gh",
    ),
    DynamicImportCall(
        ("create_late_disposition_artifact",),
        "_run_gh",
    ),
    DynamicImportCall(
        ("create_late_classification_artifact",),
        "_run_gh",
    ),
    DynamicImportCall(
        ("resolve_late_disposition_threads",),
        "_run_gh",
    ),
    DynamicImportCall(
        ("verify_live_follow_up",),
        "_read_authenticated_follow_up",
    ),
    DynamicImportCall(
        ("_read_authenticated_follow_up",),
        "_consume_api_call",
    ),
    DynamicImportCall(
        ("_read_authenticated_follow_up",),
        "_markdown_parser_environment",
    ),
    DynamicImportCall(
        ("_read_authenticated_follow_up",),
        "_resolve_trusted_markdown_node",
    ),
    DynamicImportCall(
        ("resolve_threads",),
        "verify_live_follow_up",
    ),
}
RESOLVER_LOOP_SITES = {
    LoopSite(
        "comprehension",
        ("create_late_classification_artifact",),
        "supplied_blockers",
    ),
    LoopSite(
        "comprehension",
        ("create_late_classification_artifact",),
        "target.thread.comments",
    ),
    LoopSite(
        "for",
        ("_resolve_trusted_markdown_node",),
        "evidence.TRUSTED_COMMAND_DIRECTORIES",
    ),
    LoopSite("for", ("_graphql",), "variables.items()"),
    LoopSite("for", ("load_reviewed_state",), "threads"),
    LoopSite("for", ("load_reviewed_state",), "thread_ids"),
    LoopSite("for", ("load_reviewed_state",), "thread['comments']"),
    LoopSite(
        "for",
        ("_validate_manual_gate_evidence",),
        "enumerate(registered_gates)",
    ),
    LoopSite("for", ("_parse_eligibility_payload",), "threads"),
    LoopSite("for", ("_reject_duplicate_json_object",), "pairs"),
    LoopSite(
        "for",
        ("read_target_thread",),
        "range(budget.maximum_api_calls - budget.api_calls)",
    ),
    LoopSite("for", ("read_target_thread",), "nodes"),
    LoopSite(
        "for",
        ("validate_expected_targets",),
        "expected_targets.items()",
    ),
    LoopSite("for", ("validate_expected_targets",), "target.comments"),
    LoopSite("for", ("resolve_threads",), "thread_ids"),
    LoopSite("for", ("_tracked_follow_up_disposition_report",), "thread_ids"),
    LoopSite("for", ("resolve_threads",), "enumerate(thread_ids)"),
    LoopSite("for", ("resolve_late_disposition_threads",), "thread_ids"),
    LoopSite(
        "for",
        ("resolve_late_disposition_threads",),
        "enumerate(thread_ids)",
    ),
    LoopSite("comprehension", ("_load_repository_entry",), "repositories"),
    LoopSite("comprehension", ("load_reviewed_state",), "feedback.values()"),
    LoopSite("comprehension", ("load_reviewed_state",), "comments.values()"),
    LoopSite(
        "comprehension",
        ("_validate_manual_gate_evidence",),
        "registered_gates",
    ),
    LoopSite(
        "comprehension",
        ("_validation_registry_binding",),
        "focused_validation",
    ),
    LoopSite(
        "comprehension",
        ("_validation_registry_binding",),
        "('maximum_api_calls', 'maximum_items')",
    ),
    LoopSite(
        "comprehension",
        ("validate_expected_targets",),
        "target.comments",
    ),
    LoopSite(
        "comprehension",
        ("_run_gh",),
        "arguments[len(GH_GRAPHQL_PREFIX):]",
    ),
    LoopSite(
        "comprehension",
        ("verify_local_fix_commit",),
        "trailer_output.rstrip('\\n').split('\\x00')",
    ),
    LoopSite(
        "comprehension",
        ("verify_local_fix_commit",),
        "integration_output.rstrip('\\n').split('\\x00')",
    ),
    LoopSite(
        "comprehension",
        ("_parse_eligibility_payload",),
        "finding_ids",
    ),
    LoopSite(
        "comprehension",
        ("load_final_feedback_boundary",),
        "eligibility.thread_ids",
    ),
    LoopSite("comprehension", ("resolve_threads",), "thread_ids"),
    LoopSite("comprehension", ("validate_request",), "thread_ids"),
    LoopSite("comprehension", ("resolve_threads",), "pending"),
    LoopSite("comprehension", ("resolve_threads",), "tracked"),
    LoopSite("comprehension", ("resolve_threads",), "tracked.values()"),
    LoopSite("comprehension", ("resolve_threads",), "remaining_thread_ids"),
    LoopSite(
        "comprehension",
        ("_matches_reviewed_target_identity",),
        "current.comments",
    ),
    LoopSite(
        "comprehension",
        ("_matches_reviewed_target_identity",),
        "reviewed.comments",
    ),
    LoopSite("comprehension", ("_reply_state_digest",), "thread.comments"),
    LoopSite("comprehension", ("_matches_late_authorization",), "thread.comments"),
    LoopSite(
        "comprehension",
        ("create_late_disposition_artifact",),
        "target.thread.comments",
    ),
    LoopSite(
        "comprehension",
        ("resolve_late_disposition_threads",),
        "authorization.threads",
    ),
    LoopSite(
        "comprehension",
        ("resolve_late_disposition_threads",),
        "initial_targets.values()",
    ),
    LoopSite(
        "comprehension",
        ("resolve_late_disposition_threads",),
        "initial_targets.values()",
    ),
    LoopSite(
        "comprehension",
        ("resolve_late_disposition_threads",),
        "thread_ids[index + 1:]",
    ),
    LoopSite("comprehension", ("parse_args",), "late_values"),
    LoopSite(
        "comprehension",
        ("verify_recovery_bound_source_authority",),
        "recovery_inputs",
    ),
    LoopSite("comprehension", ("parse_args",), "recovery_values"),
}


class PolicyVisitor(ast.NodeVisitor):
    def __init__(
        self,
        label: str,
        expected_calls: tuple[ProcessCall, ...],
        *,
        bounded_resolver: bool,
    ) -> None:
        self.label = label
        self.source_name = Path(label).name
        self.expected_calls = expected_calls
        self.bounded_resolver = bounded_resolver
        self.findings: list[str] = []
        self.seen_calls: list[ProcessCall] = []
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.parents: dict[ast.AST, ast.AST] = {}
        self.top_level_functions: set[str] = set()
        self.function_calls: dict[str, set[str]] = {}

    def inspect(self, tree: ast.AST) -> list[str]:
        if isinstance(tree, ast.Module):
            self.top_level_functions = {
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
        self.visit(tree)
        recursive_cycle = self._recursive_cycle()
        if recursive_cycle is not None:
            self.findings.append(
                f"{self.label}: recursive resolver call graph is prohibited: "
                f"{' -> '.join(recursive_cycle)}"
            )
        missing = [call for call in self.expected_calls if call not in self.seen_calls]
        for call in missing:
            self.findings.append(
                f"{self.label}: missing allowed subprocess.run in "
                f"{call.class_name + '.' if call.class_name else ''}{call.function_name}"
            )
        return self.findings

    def _recursive_cycle(self) -> list[str] | None:
        if not self.bounded_resolver:
            return None
        visiting: list[str] = []
        visited: set[str] = set()

        def find(function_name: str) -> list[str] | None:
            if function_name in visiting:
                start = visiting.index(function_name)
                return [*visiting[start:], function_name]
            if function_name in visited:
                return None
            visiting.append(function_name)
            for called in sorted(self.function_calls.get(function_name, set())):
                cycle = find(called)
                if cycle is not None:
                    return cycle
            visiting.pop()
            visited.add(function_name)
            return None

        for function_name in sorted(self.top_level_functions):
            cycle = find(function_name)
            if cycle is not None:
                return cycle
        return None

    def finding(self, node: ast.AST, message: str) -> None:
        self.findings.append(
            f"{self.label}:{getattr(node, 'lineno', '?')}: {message}"
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.bounded_resolver:
            observed_shape = ClassShape(
                tuple(ast.unparse(base) for base in node.bases),
                tuple(
                    (keyword.arg, ast.unparse(keyword.value))
                    for keyword in node.keywords
                ),
                tuple(ast.unparse(value) for value in node.decorator_list),
            )
            if (
                self.classes
                or self.functions
                or RESOLVER_CLASS_SHAPES.get(node.name) != observed_shape
            ):
                self.finding(
                    node,
                    "resolver class shape is outside the closed allowlist",
                )
            for statement in node.body:
                safe_docstring = (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
                safe_field = (
                    isinstance(statement, ast.AnnAssign)
                    and isinstance(statement.target, ast.Name)
                    and statement.simple == 1
                    and (
                        statement.value is None
                        or isinstance(statement.value, ast.Constant)
                    )
                )
                if not safe_docstring and not safe_field:
                    self.finding(
                        statement,
                        "resolver class body is outside the data-only allowlist",
                    )
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.bounded_resolver:
            if isinstance(node, ast.AsyncFunctionDef):
                self.finding(node, "async resolver functions are prohibited")
            if node.decorator_list:
                self.finding(
                    node,
                    "decorated resolver functions are prohibited",
                )
            if self.functions:
                self.finding(node, "nested resolver functions are prohibited")
            elif self.classes:
                self.finding(
                    node,
                    "resolver methods are prohibited",
                )
            elif node.name not in RESOLVER_TOP_LEVEL_FUNCTIONS:
                self.finding(
                    node,
                    "resolver function is outside the closed allowlist",
                )
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        allowed_imports = ALLOWED_IMPORTS.get(self.source_name)
        if allowed_imports is not None and ast.unparse(node) not in allowed_imports:
            self.finding(node, "import statement is outside the file allowlist")
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                self.finding(node, f"import is outside the closed allowlist: {root}")
            if root in PROHIBITED_IMPORT_ROOTS:
                self.finding(node, f"prohibited process-capable import: {root}")
            if root in {"os", "subprocess"} and alias.asname is not None:
                self.finding(node, f"{root} must not be aliased")
            if root == "importlib" and alias.name != "importlib.util":
                self.finding(node, "only importlib.util is allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".", 1)[0]
        allowed_imports = ALLOWED_IMPORTS.get(self.source_name)
        if allowed_imports is not None and ast.unparse(node) not in allowed_imports:
            self.finding(node, "import statement is outside the file allowlist")
        if root not in ALLOWED_IMPORT_ROOTS:
            self.finding(node, f"import is outside the closed allowlist: {root}")
        if root in PROHIBITED_IMPORT_ROOTS | {"importlib", "os", "subprocess"}:
            self.finding(node, f"prohibited direct import from {root}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        protected_names = {
            "os",
            "subprocess",
            *DIRECT_MODULE_ATTRIBUTES.get(self.source_name, {}),
            *LOADED_MODULE_ATTRIBUTES.get(self.source_name, {}),
        }
        if node.id in protected_names and isinstance(node.ctx, ast.Load):
            parent = self.parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                self.finding(node, f"bare {node.id} module reference is prohibited")
        if (
            self.bounded_resolver
            and node.id in self.top_level_functions
            and isinstance(node.ctx, ast.Load)
        ):
            parent = self.parents.get(node)
            direct_call = isinstance(parent, ast.Call) and parent.func is node
            reference = DynamicImportCall(tuple(self.functions), node.id)
            if (
                not direct_call
                and reference not in SAFE_RESOLVER_FUNCTION_REFERENCES
            ):
                self.finding(
                    node,
                    "resolver function reference is outside the closed allowlist",
                )
        if node.id in {
            "__builtins__",
            "__import__",
            "breakpoint",
            "compile",
            "eval",
            "exec",
            "globals",
            "locals",
            "vars",
        } and isinstance(node.ctx, ast.Load):
            self.finding(node, f"dynamic execution reference is prohibited: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        direct_modules = DIRECT_MODULE_ATTRIBUTES.get(self.source_name, {})
        loaded_modules = LOADED_MODULE_ATTRIBUTES.get(self.source_name, {})
        if isinstance(node.value, ast.Name) and node.value.id == "subprocess":
            parent = self.parents.get(node)
            if node.attr == "run":
                if not isinstance(parent, ast.Call) or parent.func is not node:
                    self.finding(node, "subprocess.run may only be called directly")
            elif node.attr not in SAFE_SUBPROCESS_ATTRIBUTES:
                self.finding(node, f"prohibited subprocess attribute: {node.attr}")
        elif isinstance(node.value, ast.Name) and node.value.id == "os":
            if node.attr not in SAFE_OS_ATTRIBUTES:
                self.finding(node, f"prohibited os attribute: {node.attr}")
        elif isinstance(node.value, ast.Name) and node.value.id in direct_modules:
            if node.attr not in direct_modules[node.value.id]:
                self.finding(
                    node,
                    f"prohibited {node.value.id} attribute: {node.attr}",
                )
            parent = self.parents.get(node)
            if (
                node.value.id == "importlib"
                and node.attr == "util"
                and (
                    not isinstance(parent, ast.Attribute)
                    or parent.value is not node
                )
            ):
                self.finding(node, "importlib.util may not be aliased")
            if (
                node.value.id == "sys"
                and node.attr == "modules"
            ):
                allowed = False
                if isinstance(parent, ast.Subscript) and parent.value is node:
                    access = DynamicImportCall(
                        tuple(self.functions),
                        ast.unparse(parent),
                    )
                    allowed = (
                        isinstance(parent.ctx, ast.Store)
                        and access
                        in SAFE_SYS_MODULES_STORES.get(self.source_name, set())
                    )
                elif isinstance(parent, ast.Attribute) and parent.value is node:
                    grandparent = self.parents.get(parent)
                    if (
                        isinstance(grandparent, ast.Call)
                        and grandparent.func is parent
                    ):
                        access = DynamicImportCall(
                            tuple(self.functions),
                            ast.unparse(grandparent),
                        )
                        allowed = access in SAFE_SYS_MODULES_CALLS.get(
                            self.source_name,
                            set(),
                        )
                if not allowed:
                    self.finding(
                        node,
                        "sys.modules access is outside the loader allowlist",
                    )
        elif (
            isinstance(node.value, ast.Name)
            and node.value.id in loaded_modules
            and node.attr not in loaded_modules[node.value.id]
        ):
            self.finding(
                node,
                f"prohibited {node.value.id} module attribute: {node.attr}",
            )
        if node.attr == "run":
            parent = self.parents.get(node)
            expression = ast.unparse(node)
            if (
                not isinstance(parent, ast.Call)
                or parent.func is not node
                or (
                    expression != "subprocess.run"
                    and expression
                    not in SAFE_RUN_TARGETS.get(self.source_name, set())
                )
            ):
                self.finding(node, "run reference is outside the closed allowlist")
        if node.attr in PROHIBITED_PROCESS_CALL_ATTRIBUTES:
            self.finding(
                node,
                f"prohibited process-capable attribute: {node.attr}",
            )
        if node.attr in PROHIBITED_REFLECTION_ATTRIBUTES:
            self.finding(
                node,
                f"prohibited reflection attribute: {node.attr}",
            )
        if node.attr == "exec_module":
            parent = self.parents.get(node)
            dynamic_call = (
                DynamicImportCall(tuple(self.functions), ast.unparse(parent))
                if isinstance(parent, ast.Call) and parent.func is node
                else None
            )
            if dynamic_call not in DYNAMIC_IMPORT_CALLS.get(self.source_name, set()):
                self.finding(node, "dynamic loader reference is outside the allowlist")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function_expression = ast.unparse(node.func)
        if (
            self.bounded_resolver
            and len(self.functions) == 1
            and not self.classes
            and isinstance(node.func, ast.Name)
            and node.func.id in self.top_level_functions
        ):
            self.function_calls.setdefault(self.functions[0], set()).add(node.func.id)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
        ):
            call = DynamicImportCall(tuple(self.functions), ast.unparse(node))
            if call not in SAFE_GETATTR_CALLS.get(self.source_name, set()):
                self.finding(node, "getattr call is outside the closed allowlist")
        if (
            self.bounded_resolver
            and isinstance(node.func, ast.Name)
            and node.func.id == "iter"
        ):
            self.finding(node, "resolver iterator construction is prohibited")
        if (
            function_expression.startswith("importlib.")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "exec_module"
            )
        ):
            dynamic_call = DynamicImportCall(
                tuple(self.functions),
                ast.unparse(node),
            )
            if dynamic_call not in DYNAMIC_IMPORT_CALLS.get(self.source_name, set()):
                self.finding(node, "dynamic import is outside the closed allowlist")
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        ):
            self._inspect_process_call(node)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "run":
            if function_expression not in SAFE_RUN_TARGETS.get(
                self.source_name,
                set(),
            ):
                self.finding(node, "run call is outside the closed allowlist")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in PROHIBITED_PROCESS_CALL_ATTRIBUTES
        ):
            self.finding(
                node,
                f"prohibited process-capable call: {node.func.attr}",
            )
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        if self.bounded_resolver:
            self.finding(node, "resolver lambdas are prohibited")
        self.generic_visit(node)

    def _inspect_process_call(self, node: ast.Call) -> None:
        candidates = [
            call
            for call in self.expected_calls
            if self.classes
            == ([call.class_name] if call.class_name is not None else [])
            and self.functions == [call.function_name]
        ]
        if len(candidates) != 1:
            self.finding(node, "subprocess.run is outside the closed allowlist")
            return
        expected = candidates[0]
        if expected in self.seen_calls:
            self.finding(node, "allowed subprocess.run occurs more than once")
            return
        self.seen_calls.append(expected)

        if expected.arguments:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.List):
                self.finding(node, "process argv must be one inline list")
                return
            argv = node.args[0]
            if len(argv.elts) != 2 or not isinstance(argv.elts[1], ast.Starred):
                self.finding(
                    node,
                    "process argv must have one executable and one starred tail",
                )
                return
            if ast.unparse(argv.elts[0]) != expected.executable:
                self.finding(node, "process executable expression changed")
            if ast.unparse(argv.elts[1].value) != expected.arguments:
                self.finding(node, "process argument expression changed")
        elif len(node.args) != 1 or ast.unparse(node.args[0]) != expected.executable:
            self.finding(node, "process argv expression changed")

        if any(keyword.arg is None for keyword in node.keywords):
            self.finding(node, "expanded process keyword arguments are prohibited")
            return
        keywords = tuple(
            sorted(
                (
                    keyword.arg,
                    ast.unparse(keyword.value),
                )
                for keyword in node.keywords
                if keyword.arg is not None
            )
        )
        if keywords != tuple(sorted(expected.keywords)):
            self.finding(node, "process keyword values changed")

    def visit_While(self, node: ast.While) -> None:
        if self.bounded_resolver:
            self.finding(node, "simple resolver loops must be statically bounded")
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        if self.bounded_resolver:
            self.finding(node, "simple resolver must not use async iteration")
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        if self.bounded_resolver:
            self.finding(node, "resolver generators are prohibited")
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        if self.bounded_resolver:
            self.finding(node, "resolver generators are prohibited")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self.bounded_resolver:
            site = LoopSite("for", tuple(self.functions), ast.unparse(node.iter))
            if site not in RESOLVER_LOOP_SITES:
                self.finding(node, "resolver loop is outside the bounded allowlist")
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        if self.bounded_resolver:
            site = LoopSite(
                "comprehension",
                tuple(self.functions),
                ast.unparse(node.iter),
            )
            if site not in RESOLVER_LOOP_SITES:
                self.finding(
                    node,
                    "resolver comprehension is outside the bounded allowlist",
                )
        self.generic_visit(node)


def inspect_source(
    source: str,
    label: str,
    expected_calls: tuple[ProcessCall, ...],
    *,
    bounded_resolver: bool = False,
) -> list[str]:
    tree = ast.parse(source, filename=label)
    findings = PolicyVisitor(
        label,
        expected_calls,
        bounded_resolver=bounded_resolver,
    ).inspect(tree)
    if bounded_resolver:
        tables = [symtable.symtable(source, label, "exec")]
        while tables:
            table = tables.pop()
            tables.extend(table.get_children())
            for identifier in table.get_identifiers():
                symbol = table.lookup(identifier)
                if symbol.is_parameter() and (
                    symbol.is_assigned() or symbol.is_imported()
                ):
                    findings.append(
                        f"{label}:{table.get_lineno()}: "
                        f"resolver function parameters are immutable: {identifier}"
                    )
    return findings


def self_test() -> None:
    safe_call = ProcessCall(
        None,
        "safe_runner",
        "executable",
        "arguments",
        (("check", "False"),),
    )
    safe = (
        "import subprocess\n"
        "def safe_runner(executable, arguments):\n"
        "    return subprocess.run([executable, *arguments], check=False)\n"
    )
    if inspect_source(safe, "safe-fixture", (safe_call,)):
        raise SystemExit("static policy safe fixture was rejected")

    legacy_tree = ast.parse("def resolve_threads():\n    pass\n")
    legacy_function = legacy_tree.body[0]
    if hasattr(legacy_function, "type_params"):
        del legacy_function.type_params
    legacy_findings = PolicyVisitor(
        "secpal-resolve-fixed-threads.py",
        (),
        bounded_resolver=True,
    ).inspect(legacy_tree)
    if legacy_findings:
        raise SystemExit(
            "static policy rejected a pre-PEP-695 function AST: "
            f"{legacy_findings}"
        )

    unsafe: dict[str, tuple[str, tuple[ProcessCall, ...]]] = {
        "shell-dispatch-through-env": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    return subprocess.run(\n"
                "        ['/usr/bin/env', 'bash', '-c', *arguments], check=False\n"
                "    )\n"
            ),
            (safe_call,),
        ),
        "variable-array-gh-merge-authority": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    argv = [executable, 'pr', 'merge', *arguments]\n"
                "    return subprocess.run(argv, check=False)\n"
            ),
            (safe_call,),
        ),
        "aliased-run": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    runner = subprocess.run\n"
                "    return runner([executable, *arguments], check=False)\n"
            ),
            (safe_call,),
        ),
        "nested-allowlist-name": (
            (
                "import subprocess\n"
                "def outer():\n"
                "    def safe_runner(executable, arguments):\n"
                "        return subprocess.run([executable, *arguments], check=False)\n"
            ),
            (safe_call,),
        ),
        "changed-process-keyword-value": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    return subprocess.run([executable, *arguments], check=True)\n"
            ),
            (safe_call,),
        ),
        "blocking-wait": (
            "from time import sleep\nsleep(1)\n",
            (),
        ),
        "alternate-process-api": (
            "import os\nos.system(command)\n",
            (),
        ),
        "indirect-process-module": (
            (
                "def unsafe_runner(arguments):\n"
                "    return evidence.subprocess.run(arguments, check=False)\n"
            ),
            (),
        ),
        "dynamic-process-module": (
            (
                "import importlib.util\n"
                "spec = importlib.util.spec_from_file_location('unsafe', path)\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(module)\n"
            ),
            (),
        ),
        "process-capable-library": (
            "import webbrowser\nwebbrowser.open(url)\n",
            (),
        ),
        "builtin-namespace-loader": (
            (
                "builtins = globals()['__builtins__']\n"
                "loader = builtins['__import__']\n"
                "loader('os')\n"
            ),
            (),
        ),
    }
    for name, (source, expected) in unsafe.items():
        if not inspect_source(source, name, expected):
            raise SystemExit(f"static policy negative fixture was not detected: {name}")

    unbounded_resolver_loops = {
        "attribute-call-iterator": (
            "import itertools\n"
            "for _item in itertools.count():\n"
            "    pass\n"
        ),
        "precomputed-infinite-iterator": (
            "import itertools\n"
            "forever = itertools.count()\n"
            "for _item in forever:\n"
            "    pass\n"
        ),
        "precomputed-callable-sentinel": (
            "forever = iter(int, 1)\n"
            "for _item in forever:\n"
            "    pass\n"
        ),
    }
    for name, source in unbounded_resolver_loops.items():
        if not inspect_source(source, name, (), bounded_resolver=True):
            raise SystemExit(
                f"static policy unbounded-loop fixture was not detected: {name}"
            )

    resolver_specific_unsafe = {
        "allowed-name-rebound-to-infinite-iterator": (
            "def resolve_threads():\n"
            "    thread_ids = iter(int, 1)\n"
            "    for thread_id in thread_ids:\n"
            "        pass\n"
        ),
        "validated-parameter-rebound-to-file-iterator": (
            "def resolve_threads(thread_ids):\n"
            "    thread_ids = open('/dev/zero')\n"
            "    for thread_id in thread_ids:\n"
            "        pass\n"
        ),
        "validated-parameter-rebound-by-pattern": (
            "def resolve_threads(thread_ids):\n"
            "    match open('/dev/zero'):\n"
            "        case thread_ids:\n"
            "            pass\n"
            "    for thread_id in thread_ids:\n"
            "        pass\n"
        ),
        "resolver-import-expansion": "import site\n",
        "aliased-dynamic-loader": (
            "import importlib.util\n"
            "util = importlib.util\n"
            "spec = util.spec_from_file_location('unsafe', path)\n"
            "loader = spec.loader.exec_module\n"
            "loader(module)\n"
        ),
        "aliased-getattr-process-loader": (
            "ev = evidence\n"
            "process_module = getattr(ev, 'subprocess')\n"
            "launch = getattr(process_module, 'run')\n"
            "launch(arguments)\n"
        ),
        "direct-recursion": (
            "def resolve_threads():\n"
            "    return resolve_threads()\n"
        ),
        "mutual-recursion": (
            "def resolve_threads():\n"
            "    return read_target_thread()\n"
            "def read_target_thread():\n"
            "    return resolve_threads()\n"
        ),
        "method-recursion": (
            "@dataclass\n"
            "class InvocationBudget:\n"
            "    def consume_api_call(self):\n"
            "        return self.consume_api_call()\n"
        ),
        "method-alias-recursion": (
            "@dataclass\n"
            "class InvocationBudget:\n"
            "    def consume_api_call(self):\n"
            "        callback = self.consume_api_call\n"
            "        return callback()\n"
        ),
        "method-type-dispatch-recursion": (
            "@dataclass\n"
            "class InvocationBudget:\n"
            "    def consume_api_call(self):\n"
            "        return type(self).consume_api_call(self)\n"
        ),
        "inherited-dispatch-surface": (
            "@dataclass\n"
            "class InvocationBudget(Path):\n"
            "    maximum_api_calls: int\n"
        ),
        "metaclass-dispatch-surface": (
            "@dataclass\n"
            "class InvocationBudget(metaclass=type):\n"
            "    maximum_api_calls: int\n"
        ),
        "executable-class-body": (
            "@dataclass\n"
            "class InvocationBudget:\n"
            "    callback = resolve_threads()\n"
        ),
        "decorated-function-dispatch": (
            "@dataclass\n"
            "def resolve_threads():\n"
            "    pass\n"
        ),
        "async-function-dispatch": (
            "async def resolve_threads():\n"
            "    pass\n"
        ),
        "top-level-alias-recursion": (
            "def resolve_threads():\n"
            "    callback = resolve_threads\n"
            "    return callback()\n"
        ),
        "nested-function-recursion": (
            "def resolve_threads():\n"
            "    def poll():\n"
            "        return poll()\n"
            "    return poll()\n"
        ),
        "lambda-recursion": (
            "def resolve_threads():\n"
            "    poll = lambda: poll()\n"
            "    return poll()\n"
        ),
    }
    resolver_specific_messages = {
        "direct-recursion": "recursive resolver call graph is prohibited",
        "mutual-recursion": "recursive resolver call graph is prohibited",
        "method-recursion": "resolver methods are prohibited",
        "method-alias-recursion": "resolver methods are prohibited",
        "method-type-dispatch-recursion": "resolver methods are prohibited",
        "inherited-dispatch-surface": (
            "resolver class shape is outside the closed allowlist"
        ),
        "metaclass-dispatch-surface": (
            "resolver class shape is outside the closed allowlist"
        ),
        "executable-class-body": (
            "resolver class body is outside the data-only allowlist"
        ),
        "decorated-function-dispatch": (
            "decorated resolver functions are prohibited"
        ),
        "async-function-dispatch": "async resolver functions are prohibited",
        "top-level-alias-recursion": (
            "resolver function reference is outside the closed allowlist"
        ),
        "nested-function-recursion": "nested resolver functions are prohibited",
        "lambda-recursion": "resolver lambdas are prohibited",
        "validated-parameter-rebound-to-file-iterator": (
            "resolver function parameters are immutable"
        ),
        "validated-parameter-rebound-by-pattern": (
            "resolver function parameters are immutable"
        ),
    }
    for name, source in resolver_specific_unsafe.items():
        findings = inspect_source(
            source,
            "secpal-resolve-fixed-threads.py",
            (),
            bounded_resolver=True,
        )
        if not findings:
            raise SystemExit(
                f"static policy resolver fixture was not detected: {name}"
            )
        expected_message = resolver_specific_messages.get(name)
        if expected_message is not None and not any(
            expected_message in finding for finding in findings
        ):
            raise SystemExit(
                "static policy resolver fixture was detected for the wrong reason: "
                f"{name}: {findings}"
            )

    source_specific_unsafe = (
        (
            "secpal-pr-review.py",
            "import sys\nlauncher = sys.modules['subprocess'].run\nlauncher(argv)\n",
        ),
        (
            "secpal-pr-review-actions.py",
            (
                "import sys\n"
                "sys.modules['subprocess'].__dict__['run'](argv, shell=True)\n"
            ),
        ),
        (
            "secpal-pr-review-actions.py",
            (
                "import sys\n"
                "def _load_fast_path_helper():\n"
                "    module_name = 'subprocess'\n"
                "    return sys.modules.get(module_name).__dict__['run'](\n"
                "        argv, shell=True\n"
                "    )\n"
            ),
        ),
        (
            "secpal-pr-review-actions.py",
            (
                "module_alias = evidence\n"
                "module_alias.__dict__['subprocess'].run(argv, shell=True)\n"
            ),
        ),
        (
            "secpal-resolve-fixed-threads.py",
            (
                "import sys\n"
                "sys.modules['os'].__dict__['spawnv'](mode, path, argv)\n"
            ),
        ),
        (
            "secpal-pr-review-actions.py",
            "import site\nsite.addsitedir(path)\n",
        ),
    )
    for label, source in source_specific_unsafe:
        if not inspect_source(source, label, ()):
            raise SystemExit(
                f"static policy source-specific fixture was not detected: {label}"
            )


def main(argv: list[str]) -> int:
    if len(argv) != 9:
        raise SystemExit(
            "usage: secpal-pr-review-static-policy.py "
            "EVIDENCE ACTIONS FAST_PATH SIMPLE_RESOLVER FOLLOW_UP "
            "LATE_DISPOSITION LATE_CLASSIFICATION_CREATOR LATE_CREATOR"
        )
    self_test()
    findings: list[str] = []
    for value in argv[1:]:
        path = Path(value)
        expected = EXPECTED_CALLS.get(path.name)
        if expected is None:
            raise SystemExit(f"no static policy registered for {path.name}")
        findings.extend(
            inspect_source(
                path.read_text(encoding="utf-8"),
                str(path),
                expected,
                bounded_resolver=path.name == "secpal-resolve-fixed-threads.py",
            )
        )
    if findings:
        raise SystemExit("\n".join(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
