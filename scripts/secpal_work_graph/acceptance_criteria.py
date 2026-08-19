# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Structural acceptance-criteria detection.

Implements the "structurally complete" definition of
docs/work-graph-contract.md section 4.1. The Markdown primitive is provided by
the repository's `markdown-it` parser; only the canonical normalization
procedure is applied here.
"""

from __future__ import annotations

import json
import string
import subprocess
from pathlib import Path
from typing import Sequence

CANONICAL_HEADING = "acceptance criteria"
DECORATIVE_PREFIX = "✅"
DEFAULT_TIMEOUT_SECONDS = 30

_BRIDGE = Path(__file__).resolve().parent / "markdown_headings.mjs"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class MarkdownParserUnavailable(RuntimeError):
    """The maintained Markdown parser could not be used.

    Detection fails closed: it is never replaced by a textual approximation.
    """


def qualifies(heading_text: str) -> bool:
    """Apply the five normalization steps of section 4.1 to a heading's text."""
    value = heading_text.strip()
    if value.startswith(DECORATIVE_PREFIX):
        value = value[len(DECORATIVE_PREFIX) :].strip()
    if value.endswith(":"):
        value = value[:-1].rstrip()
    return value.translate(_ASCII_LOWER) == CANONICAL_HEADING


def detect(
    bodies: Sequence[str | None],
    *,
    node_executable: str = "node",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[bool]:
    """Return, per body, whether it structurally carries acceptance criteria."""
    if not bodies:
        return []
    payload = json.dumps([body or "" for body in bodies])
    try:
        completed = subprocess.run(
            [node_executable, str(_BRIDGE)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=str(_REPOSITORY_ROOT),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MarkdownParserUnavailable(f"cannot run the Markdown parser: {error}") from error
    if completed.returncode != 0:
        raise MarkdownParserUnavailable(completed.stderr.strip() or "Markdown parsing failed")
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MarkdownParserUnavailable(f"unreadable Markdown parser output: {error}") from error
    if not isinstance(parsed, list) or len(parsed) != len(bodies):
        raise MarkdownParserUnavailable("Markdown parser returned an unexpected result")
    return [
        any(qualifies(heading["text"]) and heading["hasContent"] for heading in headings)
        for headings in parsed
    ]
