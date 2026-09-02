// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const VALIDATOR = path.join(ROOT, "scripts", "secpal-dependabot-manifest-coverage.mjs");

function repository(files) {
  const root = mkdtempSync(path.join(tmpdir(), "dependabot-coverage-"));
  execFileSync("git", ["init", "--quiet", root]);
  for (const [name, content] of Object.entries(files)) {
    const target = path.join(root, name);
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, content);
  }
  execFileSync("git", ["-C", root, "add", "."]);
  return root;
}

function run(root, assertion = "coverage", extra = []) {
  const result = spawnSync(
    "node",
    [
      VALIDATOR,
      assertion,
      "--root",
      root,
      "--repository",
      "SecPal/example",
      "--as-of",
      "2026-09-02",
      "--format",
      "json",
      ...extra,
    ],
    { encoding: "utf8" }
  );
  assert.equal(result.signal, null, result.stderr);
  return { code: result.status, report: JSON.parse(result.stdout) };
}

const DAILY = `schedule:
      interval: daily
      time: "04:00"
      timezone: Europe/Berlin`;

test("Containerfile is covered only by docker in its directory", () => {
  const root = repository({
    "image/Containerfile": "FROM alpine:3.22\n",
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: docker
    directory: /image
    schedule:
      interval: daily
      time: "04:00"
      timezone: Europe/Berlin
`,
  });

  const output = execFileSync(
    "node",
    [
      VALIDATOR,
      "coverage",
      "--root",
      root,
      "--repository",
      "SecPal/example",
      "--as-of",
      "2026-09-02",
      "--format",
      "json",
    ],
    { encoding: "utf8" }
  );
  const report = JSON.parse(output);
  assert.equal(report.status, "PASS");
  assert.deepEqual(report.manifests, [
    {
      coverage_directory: "/image",
      expected_ecosystem: "docker",
      manifest_path: "image/Containerfile",
      matched_configuration: ["updates[0]:docker:/image"],
      reason: "exact ecosystem and directory match",
      status: "COVERED",
    },
  ]);
});

test("the current SecPal ecosystems and manifest forms are data-driven", () => {
  const root = repository({
    ".github/workflows/quality.yml": "jobs: {}\n",
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    ${DAILY}
  - package-ecosystem: npm
    directory: /web
    ${DAILY}
  - package-ecosystem: composer
    directory: /php
    ${DAILY}
  - package-ecosystem: pip
    directory: /python
    ${DAILY}
  - package-ecosystem: gradle
    directory: /android
    ${DAILY}
  - package-ecosystem: pre-commit
    directory: /
    ${DAILY}
  - package-ecosystem: terraform
    directory: /terraform
    ${DAILY}
  - package-ecosystem: opentofu
    directory: /tofu
    ${DAILY}
  - package-ecosystem: docker
    directories: [/image, /nested/image]
    ${DAILY}
  - package-ecosystem: docker-compose
    directory: /compose
    ${DAILY}
`,
    ".github/dependabot-manifest-exceptions.yml": `version: 1
classifications:
  - manifest: terraform/main.tf
    ecosystem: terraform
    reason: Terraform owns this reviewed HCL module.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
manifest-exceptions: []
`,
    ".pre-commit-config.yaml": "repos: []\n",
    "android/build.gradle.kts": "plugins {}\n",
    "compose/docker-compose.prod.yaml": "services: {}\n",
    "image/Dockerfile": "FROM alpine:3.22\n",
    "nested/image/Containerfile.dev": "FROM alpine:3.22\n",
    "php/composer.json": "{}\n",
    "python/Pipfile": "[packages]\n",
    "python/pyproject.toml": "[project]\ndependencies=[]\n",
    "python/requirements-dev.in": "pytest==8.4.2\n",
    "terraform/main.tf": "terraform {}\n",
    "tofu/main.tofu": "terraform {}\n",
    "web/package.json": "{}\n",
  });
  const { code, report } = run(root);
  assert.equal(code, 0);
  assert.equal(report.status, "PASS");
  assert.equal(report.manifests.length, 13);
  assert.deepEqual([...new Set(report.manifests.map((item) => item.expected_ecosystem))].sort(), [
    "composer",
    "docker",
    "docker-compose",
    "github-actions",
    "gradle",
    "npm",
    "opentofu",
    "pip",
    "pre-commit",
    "terraform",
  ]);
});

test("directories globs use directory matching, not filesystem prefixes", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directories: ["/packages/*"]
    ${DAILY}
`,
    "packages/app/package.json": "{}\n",
  });
  assert.equal(run(root).report.status, "PASS");
});

for (const [name, config, expectedReason] of [
  [
    "correct ecosystem in wrong directory",
    `  - package-ecosystem: npm\n    directory: /tools\n    ${DAILY}`,
    "expected ecosystem is configured only for an unrelated directory",
  ],
  [
    "wrong ecosystem in correct directory",
    `  - package-ecosystem: github-actions\n    directory: /frontend\n    ${DAILY}`,
    "manifest directory is configured only for an unrelated ecosystem",
  ],
  [
    "unrelated parent directory",
    `  - package-ecosystem: npm\n    directory: /\n    ${DAILY}`,
    "expected ecosystem is configured only for an unrelated directory",
  ],
]) {
  test(name, () => {
    const root = repository({
      ".github/dependabot.yml": `version: 2\nupdates:\n${config}\n`,
      "frontend/package.json": "{}\n",
    });
    const { code, report } = run(root);
    assert.equal(code, 1);
    assert.equal(report.manifests[0].status, "UNCOVERED");
    assert.equal(report.manifests[0].reason, expectedReason);
  });
}

test("commented-out configuration is not coverage", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates: []
# - package-ecosystem: npm
#   directory: /app
`,
    "app/package.json": "{}\n",
  });
  assert.equal(run(root).report.manifests[0].status, "UNCOVERED");
});

test("malformed YAML and duplicate scopes fail structurally", () => {
  const malformed = repository({
    ".github/dependabot.yml": "version: 2\nupdates: [\n",
  });
  assert.equal(run(malformed).report.diagnostics[0].code, "MALFORMED_YAML");

  const duplicate = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /app
    ${DAILY}
  - package-ecosystem: npm
    directory: /app
    ${DAILY}
`,
    "app/package.json": "{}\n",
  });
  assert.equal(run(duplicate).report.diagnostics[0].code, "DUPLICATE_CONFIGURATION");
});

test("overlapping directory entries are ambiguous for the actual manifest", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directories: ["/packages/*"]
    ${DAILY}
  - package-ecosystem: npm
    directory: /packages/app
    ${DAILY}
`,
    "packages/app/package.json": "{}\n",
  });
  assert.equal(run(root).report.manifests[0].status, "AMBIGUOUS");
});

test("Containerfile cannot be covered by an unrelated ecosystem", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: github-actions
    directory: /image
    ${DAILY}
`,
    "image/Containerfile": "FROM alpine:3.22\n",
  });
  const item = run(root).report.manifests[0];
  assert.equal(item.expected_ecosystem, "docker");
  assert.equal(item.status, "UNCOVERED");
});

test("an exact reviewed manifest exception succeeds", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: app/package.json
    ecosystem: npm
    reason: Upstream registry access is temporarily unavailable.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
    "app/package.json": "{}\n",
  });
  assert.equal(run(root).report.manifests[0].status, "EXCEPTED");
});

for (const [name, manifest, ecosystem] of [
  ["wrong exception path", "other/package.json", "npm"],
  ["wrong exception ecosystem", "app/package.json", "composer"],
]) {
  test(name, () => {
    const root = repository({
      ".github/dependabot.yml": "version: 2\nupdates: []\n",
      ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: "${manifest}"
    ecosystem: ${ecosystem}
    reason: This deliberately mismatched record must not suppress coverage.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
      "app/package.json": "{}\n",
    });
    assert.equal(run(root).report.manifests[0].status, "UNCOVERED");
  });
}

test("wildcard suppression and non-normalized paths are rejected", () => {
  for (const manifest of ["*/package.json", "app/../package.json"]) {
    const root = repository({
      ".github/dependabot.yml": "version: 2\nupdates: []\n",
      ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: "${manifest}"
    ecosystem: npm
    reason: This broad record is intentionally invalid for regression proof.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
    });
    assert.equal(run(root).report.diagnostics[0].code, "PATH_ERROR");
  }
});

test("no-applicable-manifest cannot hide a discovered manifest", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    ".github/dependabot-manifest-exceptions.yml": `version: 1
no-applicable-manifest:
  reason: This repository is asserted to contain no dependency manifests.
  reviewed-by: "@SecPal/maintainers"
  reviewed-on: "2026-09-02"
`,
    "package.json": "{}\n",
  });
  assert.ok(
    run(root).report.diagnostics.some(
      (item) => item.code === "INVALID_NO_APPLICABLE_MANIFEST_EXCEPTION"
    )
  );
});

test("no-applicable-manifest succeeds only when discovery proves absence", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    ".github/dependabot-manifest-exceptions.yml": `version: 1
no-applicable-manifest:
  reason: This information-only repository has no applicable manifests.
  reviewed-by: "@SecPal/maintainers"
  reviewed-on: "2026-09-02"
`,
    "README.md": "# Information only\n",
  });
  assert.equal(run(root).report.status, "PASS");
});

test("untracked exception input cannot affect the result", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "package.json": "{}\n",
  });
  writeFileSync(
    path.join(root, ".github/dependabot-manifest-exceptions.yml"),
    `version: 1
manifest-exceptions:
  - manifest: package.json
    ecosystem: npm
    reason: This untracked record must never become review authority.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`
  );
  assert.equal(run(root).report.diagnostics[0].code, "UNTRACKED_POLICY_INPUT");
});

test("unknown manifest candidates and stale knowledge fail closed", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "dependencies.future": "future-package == 1\n",
  });
  assert.equal(run(root).report.diagnostics[0].code, "UNCLASSIFIED_MANIFEST_CANDIDATE");
  const stale = run(root, "coverage", ["--as-of", "2026-12-02"]);
  assert.ok(stale.report.diagnostics.some((item) => item.code === "CATALOG_STALE"));
});

test("tracked manifest symlinks fail closed", () => {
  const root = mkdtempSync(path.join(tmpdir(), "dependabot-coverage-"));
  execFileSync("git", ["init", "--quiet", root]);
  mkdirSync(path.join(root, ".github"), { recursive: true });
  writeFileSync(path.join(root, ".github/dependabot.yml"), "version: 2\nupdates: []\n");
  writeFileSync(path.join(root, "real.json"), "{}\n");
  symlinkSync("real.json", path.join(root, "package.json"));
  execFileSync("git", ["-C", root, "add", "."]);
  assert.equal(run(root).report.diagnostics[0].code, "UNSAFE_SYMLINK");
});

test("coverage and cadence are independent assertions", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      time: "04:00"
      timezone: Europe/Berlin
`,
    "package.json": "{}\n",
  });
  assert.equal(run(root, "coverage").report.status, "PASS");
  assert.equal(run(root, "cadence").report.diagnostics[0].code, "CADENCE_POLICY_MISMATCH");
});

test("equivalent input produces byte-stable JSON", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /
    ${DAILY}
`,
    "package.json": "{}\n",
  });
  const first = run(root).report;
  const second = run(root).report;
  assert.equal(JSON.stringify(first), JSON.stringify(second));
});

for (const [name, schedule, status] of [
  [
    "daily 04:00 Europe/Berlin",
    { interval: "daily", time: "04:00", timezone: "Europe/Berlin" },
    "PASS",
  ],
  ["weekly", { interval: "weekly", time: "04:00", timezone: "Europe/Berlin" }, "FAIL"],
  ["wrong time", { interval: "daily", time: "05:00", timezone: "Europe/Berlin" }, "FAIL"],
  ["wrong timezone", { interval: "daily", time: "04:00", timezone: "UTC" }, "FAIL"],
]) {
  test(`cadence: ${name}`, () => {
    const root = repository({
      ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: ${schedule.interval}
      time: "${schedule.time}"
      timezone: ${schedule.timezone}
`,
    });
    assert.equal(run(root, "cadence").report.status, status);
  });
}
