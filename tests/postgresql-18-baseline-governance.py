#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard the organization-wide PostgreSQL 18 baseline contract."""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = REPOSITORY_ROOT / "scripts/preflight.sh"
QUALITY_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/quality.yml"
LEGACY_MAJOR_PATTERN = re.compile(
    r"`?(?:postgres(?:ql)?|pg)[\s_/:=-]*v?(?:16|17)\b"
    r"(?:\s*/\s*(?:(?:postgres(?:ql)?|pg)[\s_/:=-]*v?)?(?:16|17)\b)?`?",
    re.IGNORECASE,
)
SAFE_EVIDENCE_SUFFIXES = frozenset(
    {
        "is historical evidence only",
        "are historical evidence only",
        "is a migration-specific fixture",
        "is an intentionally negative-test example",
        "is an unrelated example, not runtime guidance",
        "is immutable release history only",
        "is changelog history only",
    }
)


def is_bounded_legacy_evidence_statement(line: str) -> bool:
    statement = line.strip()
    for prefix in ("- ", "* ", "+ ", "> "):
        if statement.startswith(prefix):
            statement = statement[len(prefix) :].strip()
            break

    reference = LEGACY_MAJOR_PATTERN.match(statement)
    if reference is None:
        return False

    suffix = statement[reference.end() :].strip()
    if suffix.endswith("."):
        suffix = suffix[:-1].rstrip()
    return suffix.casefold() in SAFE_EVIDENCE_SUFFIXES


def active_legacy_references(content: str) -> list[tuple[int, str]]:
    return [
        (line_number, line)
        for line_number, line in enumerate(content.splitlines(), start=1)
        if LEGACY_MAJOR_PATTERN.search(line) and not is_bounded_legacy_evidence_statement(line)
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
            "Support PostgreSQL 17 in active development.",
            "Support PostgreSQL 16/17 in active development.",
            "Use Postgres 16 for CI.",
            "Use Postgres 17 for CI.",
            "Use Postgres 16/17 for CI.",
            "The production image is postgres:16.",
            "The production image is postgres:17.",
            "Keep PG16 compatibility.",
            "Keep PG17 compatibility.",
            "Keep PG16/PG17 compatibility.",
            "Historical note: support PostgreSQL 17 in active development.",
            "Migration note: use PostgreSQL 17 for the application.",
            "Historical context: deploy postgres:16 for the application.",
        ):
            self.assertTrue(active_legacy_references(content), content)

    def test_legacy_major_classifier_allows_documented_evidence(self) -> None:
        for content in (
            "PostgreSQL 16 is historical evidence only.",
            "Postgres 17 is a migration-specific fixture.",
            "PG16 is an intentionally negative-test example.",
            "PostgreSQL 17 is an unrelated example, not runtime guidance.",
            "PostgreSQL 16 is immutable release history only.",
            "Postgres 17 is changelog history only.",
            "`PostgreSQL 16` is historical evidence only.",
        ):
            self.assertEqual([], active_legacy_references(content), content)

    def test_preflight_enforces_the_governance_test_fail_closed(self) -> None:
        preflight = PREFLIGHT_PATH.read_text()

        self.assertNotRegex(
            preflight,
            r"if \[ -[ef] tests/postgresql-18-baseline-governance\.py \]",
        )
        self.assertEqual(
            1,
            preflight.count("python3 tests/postgresql-18-baseline-governance.py"),
        )
        self.assertEqual(
            2,
            sum(
                line.strip() == "run_postgresql_18_baseline_governance"
                for line in preflight.splitlines()
            ),
        )

    def test_hosted_quality_executes_the_authoritative_preflight_path(self) -> None:
        quality_workflow = QUALITY_WORKFLOW_PATH.read_text()

        self.assertIn(
            "run: ./scripts/preflight.sh --postgresql-baseline-only",
            quality_workflow,
        )

    def test_focused_preflight_fails_when_governance_test_is_absent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="postgresql-baseline-preflight.") as temporary:
            repository = Path(temporary)
            (repository / "scripts").mkdir()
            shutil.copy2(PREFLIGHT_PATH, repository / "scripts/preflight.sh")
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=repository,
                check=True,
            )

            result = subprocess.run(
                ["bash", "scripts/preflight.sh", "--postgresql-baseline-only"],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "PostgreSQL 18 baseline governance regression test failed",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
