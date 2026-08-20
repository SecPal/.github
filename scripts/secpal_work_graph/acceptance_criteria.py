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
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

CANONICAL_HEADING = "acceptance criteria"
DECORATIVE_PREFIX = "✅"
DEFAULT_TIMEOUT_SECONDS = 30
DETECTION_BATCH_SIZE = 100

_BRIDGE = Path(__file__).resolve().parent / "markdown_headings.mjs"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class MarkdownParserUnavailable(RuntimeError):
    """The maintained Markdown parser could not be used.

    Detection fails closed: it is never replaced by a textual approximation.
    """


@dataclass(frozen=True)
class StructuralBody:
    """Markdown syntax facts consumed by the work-graph normalizer."""

    has_acceptance_criteria: bool
    relationship_mirrors: tuple[str, ...]


def qualifies(heading_text: str) -> bool:
    """Apply the five normalization steps of section 4.1 to a heading's text."""
    value = heading_text.strip()
    if value.startswith(DECORATIVE_PREFIX):
        value = value[len(DECORATIVE_PREFIX) :].strip()
    if value.endswith(":"):
        value = value[:-1].rstrip()
    return value.translate(_ASCII_LOWER) == CANONICAL_HEADING


def parse(
    bodies: Sequence[str | None],
    *,
    node_executable: str = "node",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[StructuralBody]:
    """Parse structural body facts through the shared Markdown bridge."""
    if not bodies:
        return []
    detected: list[StructuralBody] = []
    for start in range(0, len(bodies), DETECTION_BATCH_SIZE):
        batch = bodies[start : start + DETECTION_BATCH_SIZE]
        payload = json.dumps([body or "" for body in batch])
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
        if not isinstance(parsed, list) or len(parsed) != len(batch):
            raise MarkdownParserUnavailable("Markdown parser returned an unexpected result")
        for item in parsed:
            headings = item.get("headings") if isinstance(item, dict) else None
            mirrors = item.get("relationshipMirrors") if isinstance(item, dict) else None
            if (
                not isinstance(headings, list)
                or any(
                    not isinstance(heading, dict)
                    or not isinstance(heading.get("text"), str)
                    or not isinstance(heading.get("hasContent"), bool)
                    for heading in headings
                )
                or not isinstance(mirrors, list)
                or any(not isinstance(mirror, str) for mirror in mirrors)
            ):
                raise MarkdownParserUnavailable("Markdown parser returned an unexpected result")
            detected.append(
                StructuralBody(
                    has_acceptance_criteria=any(
                        qualifies(heading["text"]) and heading["hasContent"] for heading in headings
                    ),
                    relationship_mirrors=tuple(sorted(set(mirrors))),
                )
            )
    return detected
