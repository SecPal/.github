#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard the organization-wide PostgreSQL 18 baseline contract."""

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MAJOR_PATTERN = re.compile(
    r"\b(?:postgres(?:ql)?|pg)[\s_/:=-]*v?(?:16|17)\b",
    re.IGNORECASE,
)
ALLOWED_LEGACY_CONTEXT_PATTERN = re.compile(
    r"\b(?:historical|history|migration(?:-specific)?|negative(?:-test)?|"
    r"unrelated example|immutable release|changelog)\b",
    re.IGNORECASE,
)
ACTIVE_BASELINE_CONTEXT_PATTERN = re.compile(
    r"\b(?:active|baseline|compatibility|current|production|development|ci|"
    r"integration|support(?:ed|ing)?)\b",
    re.IGNORECASE,
)


def active_legacy_references(content: str) -> list[tuple[int, str]]:
    return [
        (line_number, line)
        for line_number, line in enumerate(content.splitlines(), start=1)
        if LEGACY_MAJOR_PATTERN.search(line)
        and (
            ACTIVE_BASELINE_CONTEXT_PATTERN.search(line)
            or not ALLOWED_LEGACY_CONTEXT_PATTERN.search(line)
        )
    ]


class PostgreSQL18BaselineGovernanceTest(unittest.TestCase):
    def test_canonical_guidance_names_the_postgresql_18_contract(self) -> None:
        adr = (REPOSITORY_ROOT / "docs/adr/20260824-postgresql-18-canonical-baseline-adr017.md").read_text()
        normalized_adr = re.sub(r"\s+", " ", adr)

        for requirement in (
            "PostgreSQL 18 is the sole active major",
            "transaction-level advisory locks",
            "row locking",
            "JSONB",
            "UUIDs",
            "relational constraints",
            "transactional integrity",
            "host-native",
            "disposable PostgreSQL 18 containers",
            "bounded CI/integration",
            "qualified Rocky/RHEL 10.2+ PostgreSQL 18 Application Stream",
            "Future major upgrades start from PostgreSQL 18",
        ):
            self.assertIn(requirement, normalized_adr)

    def test_active_templates_name_postgresql_18(self) -> None:
        for relative_path in (
            ".github/ISSUE_TEMPLATE/epic.yml",
            ".github/ISSUE_TEMPLATE/sub-issue.yml",
        ):
            content = (REPOSITORY_ROOT / relative_path).read_text()
            self.assertIn("PostgreSQL 18", content, relative_path)

    def test_github_guidance_has_no_legacy_major_baseline(self) -> None:
        for path in (REPOSITORY_ROOT / ".github").rglob("*"):
            if not path.is_file():
                continue
            self.assertEqual(
                [],
                active_legacy_references(path.read_text()),
                str(path.relative_to(REPOSITORY_ROOT)),
            )

    def test_legacy_major_classifier_rejects_active_guidance(self) -> None:
        for content in (
            "Support PostgreSQL 16 in active development.",
            "Use Postgres 17 for CI.",
            "The production image is postgres:17.",
            "Keep PG16 compatibility.",
            "Historical note: support PostgreSQL 17 in active development.",
        ):
            self.assertTrue(active_legacy_references(content), content)

    def test_legacy_major_classifier_allows_documented_evidence(self) -> None:
        for content in (
            "PostgreSQL 16 is historical evidence only.",
            "Postgres 17 is a migration-specific fixture.",
            "PG16 is an intentionally negative-test example.",
            "PostgreSQL 17 is an unrelated example, not runtime guidance.",
        ):
            self.assertEqual([], active_legacy_references(content), content)


if __name__ == "__main__":
    unittest.main()
