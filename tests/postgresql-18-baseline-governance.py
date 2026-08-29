#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard the organization-wide PostgreSQL 18 baseline contract."""

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
            "qualified Rocky/RHEL 10.2 PostgreSQL 18 Application Stream",
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
            self.assertNotRegex(
                path.read_text(),
                r"(?i)postgresql\s+(?:16|17)\b",
                str(path.relative_to(REPOSITORY_ROOT)),
            )


if __name__ == "__main__":
    unittest.main()
