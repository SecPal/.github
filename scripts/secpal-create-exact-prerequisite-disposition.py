#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Issue two detached late artifacts for an exact #1048 prerequisite case."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence


RESOLVER = Path(__file__).resolve().with_name("secpal-resolve-fixed-threads.py")
sys.path.insert(0, str(RESOLVER.parent.parent))


def _load_resolver() -> Any:
    spec = importlib.util.spec_from_file_location(
        "secpal_resolve_fixed_threads_for_exact_prerequisite", RESOLVER
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", required=True,
        choices=tuple(resolver.exact_prerequisite.CASES),
    )
    parser.add_argument("--classification-output", required=True, type=Path)
    parser.add_argument(
        "--classification-signature-output", required=True, type=Path
    )
    parser.add_argument("--disposition-output", required=True, type=Path)
    parser.add_argument("--disposition-signature-output", required=True, type=Path)
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = resolver.create_exact_prerequisite_late_evidence(
            arguments.case,
            classification_output=arguments.classification_output,
            classification_signature_output=(
                arguments.classification_signature_output
            ),
            disposition_output=arguments.disposition_output,
            disposition_signature_output=arguments.disposition_signature_output,
        )
    except resolver.ResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
