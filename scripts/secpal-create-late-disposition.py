#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Create detached signed evidence for exact post-push review disposition."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence


RESOLVER = Path(__file__).resolve().with_name("secpal-resolve-fixed-threads.py")


def _load_resolver() -> Any:
    spec = importlib.util.spec_from_file_location(
        "secpal_resolve_fixed_threads_for_late_evidence", RESOLVER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("maintained fixed-thread resolver is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


resolver = _load_resolver()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--delivery-issue", required=True, type=int)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--final-reviewed-state", required=True)
    parser.add_argument("--expected-final-reviewed-state-digest", required=True)
    parser.add_argument("--final-validation-evidence", required=True)
    parser.add_argument("--final-eligibility-evidence", required=True)
    parser.add_argument("--classification-evidence", required=True)
    parser.add_argument("--classification-signature", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--signature-output", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = resolver.create_late_disposition_artifact(
            arguments.repo,
            arguments.delivery_issue,
            arguments.pr,
            arguments.expected_head,
            repository_root=arguments.repo_root,
            final_reviewed_state_path=arguments.final_reviewed_state,
            expected_final_reviewed_state_digest=(
                arguments.expected_final_reviewed_state_digest
            ),
            final_validation_evidence_path=arguments.final_validation_evidence,
            final_eligibility_evidence_path=(
                arguments.final_eligibility_evidence
            ),
            classification_evidence_path=arguments.classification_evidence,
            classification_signature_path=arguments.classification_signature,
            output_path=arguments.output,
            signature_output_path=arguments.signature_output,
        )
    except resolver.ResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
