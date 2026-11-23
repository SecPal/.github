# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
from datetime import date
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
monitor = runpy.run_path(str(ROOT / "scripts/secpal-runtime-upgrades.py"))
PHP_SUPPORT = monitor["PHP_SUPPORT"]
PHP_RELEASE = monitor["PHP_RELEASE"]
NGINX_DOWNLOADS = monitor["NGINX_DOWNLOADS"]
IMAGES = monitor["IMAGES"]


def php_row(line, security_until):
    return (f'<tr class="stable"><td><a href="/downloads.php?version={line}">{line}</a></td>'
            f'<td>20 Nov 2025</td><td>31 Dec 2027</td><td>{security_until}</td></tr>')


def php_release(version, sha="a" * 64):
    return json.dumps({version: {"tags": ["security"], "source": [
        {"filename": f"php-{version}.tar.gz", "sha256": sha},
    ]}})


def nginx_row(channel, version):
    filename = f"/download/nginx-{version}.tar.gz"
    return (f"<h4>{channel} version</h4><table><tr>"
            f'<td><a href="{filename}">nginx</a><a href="{filename}.asc">pgp</a></td>'
            "</tr></table>")


def image(tag, arch="amd64, arm64v8"):
    return f"Tags: {tag}, latest\nArchitectures: {arch}\nGitCommit: {'c' * 40}\n"


class RuntimeUpgradeTests(unittest.TestCase):
    def sources(self):
        return {
            PHP_SUPPORT: ("<h3>Currently Supported Versions</h3><table>"
                          + "".join(php_row(line, "31 Dec 2030") for line in ("8.4", "8.5", "8.6", "9.0"))
                          + "</table><table><tr class='stable'>Unrelated legend</tr></table>"),
            PHP_RELEASE + "8.5": php_release("8.5.14"),
            PHP_RELEASE + "8.6": php_release("8.6.1"),
            PHP_RELEASE + "9.0": php_release("9.0.0"),
            NGINX_DOWNLOADS: nginx_row("Mainline", "1.33.2") + nginx_row("Stable", "1.32.1"),
            monitor["NGINX_ADVISORIES"]: (
                "<li><p>CVE-2040-12345<br>Not vulnerable: 1.33.2+, 1.30.8+<br>Vulnerable: 1.21.0-1.33.1</p></li>"
                "<li><p>CVE-2040-12346<br>Not vulnerable: 1.33.2+<br>Vulnerable: 1.21.0-1.33.1</p></li>"
                "<li><p>CVE-2040-12347<br>Not vulnerable: 1.33.2+<br>Vulnerable: 1.2.0-1.20.1</p></li>"
            ),
            IMAGES + "php": image("8.5.14-fpm-alpine3.24") + "\n" + image("8.6.1-fpm-trixie", "amd64"),
            IMAGES + "nginx": image("1.32.1-alpine3.24-slim"),
        }

    def collect(self, sources):
        with TemporaryDirectory() as root:
            fixture = Path(root) / "Containerfile"
            fixture.write_text(
                f"FROM docker.io/library/php:8.4.28-fpm-alpine3.24@sha256:{'a' * 64} AS php\n"
                f"FROM docker.io/library/nginx:1.30.7-alpine3.24-slim@sha256:{'b' * 64} AS preview-nginx\n"
            )
            return monitor["collect"](fixture, sources.__getitem__, date(2026, 11, 23))

    def test_discovers_each_new_supported_branch_and_both_nginx_channels(self):
        found = self.collect(self.sources())
        self.assertEqual([row["version"] for row in found], ["8.5.14", "8.6.1", "9.0.0", "1.33.2", "1.32.1"])
        self.assertEqual(found[0]["source_sha256"], "a" * 64)
        self.assertEqual(found[0]["support"], "Active until 31 Dec 2027; security until 31 Dec 2030")
        self.assertTrue(monitor["ready"](found[0]))
        self.assertFalse(monitor["ready"](found[1]))
        self.assertEqual(found[2]["variants"], [])
        self.assertEqual(found[3]["channel"], "mainline")
        self.assertIn("CVE-2040-12345 is also fixed by approved-line 1.30.8", found[3]["security"])
        self.assertEqual(found[3]["candidate_only"], ["CVE-2040-12346"])
        self.assertEqual(found[4]["channel"], "stable")
        self.assertTrue(monitor["ready"](found[4]))

    def test_patch_noise_dedupes_while_variant_readiness_and_channels_signal(self):
        sources = self.sources()
        older = self.collect(sources)
        sources[PHP_RELEASE + "8.5"] = php_release("8.5.15")
        sources[IMAGES + "php"] = sources[IMAGES + "php"].replace("8.5.14", "8.5.15")
        latest = self.collect(sources)
        key = monitor["key"]
        self.assertEqual(key(older[0]), key(latest[0]))
        sources[IMAGES + "php"] += "\n" + image("8.6.1-fpm-alpine3.24")
        self.assertNotEqual(key(older[1]), key(self.collect(sources)[1]))
        self.assertNotEqual(key(older[3]), key({**older[3], "channel": "stable"}))
        report = monitor["render"](latest)
        self.assertIn("migration85.php", report)
        self.assertIn("security_advisories.html", report)
        self.assertIn("No advertised exact variant", report)
        self.assertNotIn("CLEAN", report)

    def test_fails_closed_when_official_release_evidence_is_incomplete(self):
        for source, value in [
            (PHP_RELEASE + "8.5", php_release("8.6.0")),
            (PHP_RELEASE + "8.5", php_release("8.5.14", "unverified")),
            (NGINX_DOWNLOADS, nginx_row("Mainline", "1.33.2")),
            (IMAGES + "php", "unexpected upstream format"),
        ]:
            sources = self.sources()
            sources[source] = value
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.collect(sources)
