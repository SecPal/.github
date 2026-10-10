#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Issue two detached late artifacts for an exact #1048 prerequisite case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


from . import fixed_thread_resolution as resolver


def main(argv: Sequence[str] | None = None) -> int:
    resolver._ensure_exact_prerequisite_helpers()
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
