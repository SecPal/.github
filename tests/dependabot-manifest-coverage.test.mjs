// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const VALIDATOR = path.join(ROOT, "scripts", "secpal-dependabot-manifest-coverage.mjs");
const CATALOG = path.join(ROOT, "policies", "dependabot-manifest-catalog-v1.json");

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

function trustedPolicy(files) {
  return repository(files);
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
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
classifications:
  - directory: terraform
    ecosystem: terraform
    reason: Protected history assigns this complete module to Terraform.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
manifest-exceptions: []
`,
  });
  const { code, report } = run(root, "coverage", ["--trusted-policy-root", baseline]);
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
    "app/package.json": "{}\n",
  });
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: app/package.json
    ecosystem: npm
    reason: Upstream registry access is temporarily unavailable.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
  });
  assert.equal(
    run(root, "coverage", ["--trusted-policy-root", baseline]).report.manifests[0].status,
    "EXCEPTED"
  );
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
    "package.json": "{}\n",
  });
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
no-applicable-manifest:
  reason: This repository is asserted to contain no dependency manifests.
  reviewed-by: "@SecPal/maintainers"
  reviewed-on: "2026-09-02"
`,
  });
  assert.ok(
    run(root, "coverage", ["--trusted-policy-root", baseline]).report.diagnostics.some(
      (item) => item.code === "INVALID_NO_APPLICABLE_MANIFEST_EXCEPTION"
    )
  );
});

test("no-applicable-manifest succeeds only when discovery proves absence", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "README.md": "# Information only\n",
  });
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
no-applicable-manifest:
  reason: This information-only repository has no applicable manifests.
  reviewed-by: "@SecPal/maintainers"
  reviewed-on: "2026-09-02"
`,
  });
  assert.equal(run(root, "coverage", ["--trusted-policy-root", baseline]).report.status, "PASS");
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
  const premature = run(root, "coverage", ["--as-of", "2026-09-01"]);
  assert.ok(premature.report.diagnostics.some((item) => item.code === "CATALOG_NOT_YET_REVIEWED"));
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

test("known supported manifests never disappear from discovery", () => {
  for (const [manifest, content, ecosystem] of [
    ["rust/Cargo.toml", "[package]\nname='example'\nversion='1.0.0'\n", "cargo"],
    ["go/go.mod", "module example.test/project\n\ngo 1.24\n", "gomod"],
    ["ruby/Gemfile", "source 'https://rubygems.org'\n", "bundler"],
    ["java/pom.xml", "<project/>\n", "maven"],
    ["python/constraints.txt", "requests==2.32.5\n", "pip"],
  ]) {
    const root = repository({
      ".github/dependabot.yml": "version: 2\nupdates: []\n",
      [manifest]: content,
    });
    const { report } = run(root);
    assert.equal(report.manifests.length, 1, manifest);
    assert.equal(report.manifests[0].expected_ecosystem, ecosystem, manifest);
    assert.equal(report.manifests[0].status, "UNCOVERED", manifest);
  }
});

test("tracked projects in generic build and vendor directories remain visible", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "build/package.json": "{}\n",
    "vendor/package.json": "{}\n",
  });
  const { report } = run(root);
  assert.deepEqual(
    report.manifests.map((item) => item.manifest_path),
    ["build/package.json", "vendor/package.json"]
  );
  assert.ok(report.manifests.every((item) => item.status === "UNCOVERED"));
});

test("subject-authored review metadata cannot authorize its own exception", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: app/package.json
    ecosystem: npm
    reason: This self-declared exception has no protected-history authority.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
    "app/package.json": "{}\n",
  });
  const { report } = run(root);
  assert.equal(report.manifests[0].status, "UNCOVERED");
  assert.ok(report.diagnostics.some((item) => item.code === "UNTRUSTED_POLICY_INPUT"));
});

test("unused policy can be staged for protected-history review", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: future/package.json
    ecosystem: npm
    reason: This exact policy is staged before the future manifest exists.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
  });
  assert.equal(run(root).report.status, "PASS");
});

test("protected-history exception authority is accepted exactly", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "app/package.json": "{}\n",
  });
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: app/package.json
    ecosystem: npm
    reason: Protected history records this exact temporary exception.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
  });
  const { report } = run(root, "coverage", ["--trusted-policy-root", baseline]);
  assert.equal(report.manifests[0].status, "EXCEPTED");
});

test("review and catalog dates are real and not in the future", () => {
  for (const reviewedOn of ["2026-99-99", "2099-12-31"]) {
    const root = repository({
      ".github/dependabot.yml": "version: 2\nupdates: []\n",
      "app/package.json": "{}\n",
    });
    const baseline = trustedPolicy({
      ".github/dependabot-manifest-exceptions.yml": `version: 1
manifest-exceptions:
  - manifest: app/package.json
    ecosystem: npm
    reason: Invalid review dates must not become trusted policy evidence.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "${reviewedOn}"
`,
    });
    assert.equal(
      run(root, "coverage", ["--trusted-policy-root", baseline]).report.diagnostics[0].code,
      "SCHEMA_ERROR"
    );
  }
});

test("target-branch is equivalent only when it names the trusted default branch", () => {
  for (const [target, expected] of [
    [null, "PASS"],
    ["main", "PASS"],
    ["release", "FAIL"],
  ]) {
    const targetLine = target ? `    target-branch: ${target}\n` : "";
    const root = repository({
      ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /
${targetLine}    ${DAILY}
`,
      "package.json": "{}\n",
    });
    assert.equal(
      run(root, "coverage", ["--default-branch", "main"]).report.status,
      expected,
      String(target)
    );
  }
});

test("exclude-paths follow Dependabot file and directory semantics", () => {
  for (const [pattern, manifest, directory, extraFiles = {}] of [
    [".github/workflows", ".github/workflows/quality.yml", "/"],
    ["package.json", "package.json", "/"],
    ["*.json", "packages/app/package.json", "/packages/app"],
    [
      "packages/**",
      "packages/deep/app/package.json",
      "/",
      { "package.json": '{"workspaces":["packages/**"]}\n' },
    ],
  ]) {
    const root = repository({
      ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: ${manifest.includes("workflows") ? "github-actions" : "npm"}
    directory: ${directory}
    exclude-paths: ["${pattern}"]
    ${DAILY}
`,
      [manifest]: manifest.endsWith("package.json") ? "{}\n" : "jobs: {}\n",
      ...extraFiles,
    });
    const { report } = run(root);
    const item = report.manifests.find((candidate) => candidate.manifest_path === manifest);
    assert.equal(item.status, "UNCOVERED", pattern);
    assert.match(item.reason, /excludes this manifest/);
  }
});

test("npm workspace members inherit the configured workspace root", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directory: /
    ${DAILY}
`,
    "package.json": '{"workspaces":["packages/*"]}\n',
    "packages/app/package.json": '{"name":"app"}\n',
  });
  const { report } = run(root);
  assert.equal(report.status, "PASS");
  assert.ok(report.manifests.every((item) => item.coverage_directory === "/"));
});

test("ordinary generic data files are not manifest candidates", () => {
  const root = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "build.yaml": "steps: []\n",
    "modules.toml": "title='documentation'\n",
    "packages.json": "[]\n",
  });
  assert.equal(run(root).report.status, "PASS");
});

test("Terraform and OpenTofu ownership is selected once per module", () => {
  const terraform = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: terraform
    directory: /infra
    ${DAILY}
`,
    "infra/main.tf": "terraform {}\n",
    "infra/versions.tf": "terraform {}\n",
  });
  const baseline = trustedPolicy({
    ".github/dependabot-manifest-exceptions.yml": `version: 1
classifications:
  - directory: infra
    ecosystem: terraform
    reason: Protected history assigns this complete module to Terraform.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
`,
  });
  const terraformReport = run(terraform, "coverage", ["--trusted-policy-root", baseline]).report;
  assert.equal(terraformReport.status, "PASS");
  assert.ok(terraformReport.manifests.every((item) => item.expected_ecosystem === "terraform"));

  const tofu = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: opentofu
    directory: /infra
    ${DAILY}
`,
    "infra/main.tf": "terraform {}\n",
    "infra/main.tofu": "terraform {}\n",
  });
  assert.equal(run(tofu).report.status, "PASS");

  const ambiguous = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "infra/main.tf": "terraform {}\n",
  });
  assert.ok(
    run(ambiguous).report.diagnostics.some(
      (item) => item.code === "AMBIGUOUS_MANIFEST_CLASSIFICATION"
    )
  );

  const contradictory = run(tofu, "coverage", ["--trusted-policy-root", baseline]).report;
  assert.ok(contradictory.diagnostics.some((item) => item.code === "CONTRADICTORY_CLASSIFICATION"));
});

test('documented directories ["**/*"] syntax covers nested manifests', () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directories: ["**/*"]
    ${DAILY}
`,
    "package.json": "{}\n",
    "packages/app/package.json": "{}\n",
    "packages/deep/app/package.json": "{}\n",
  });
  assert.equal(run(root).report.status, "PASS");
});

test("directory scope globs preserve root anchors and segment depth", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: composer
    directories: ["/lib-*"]
    ${DAILY}
  - package-ecosystem: npm
    directories: ["/packages/*"]
    ${DAILY}
  - package-ecosystem: cargo
    directories: ["/crates/**"]
    ${DAILY}
`,
    "apps/lib-tools/composer.json": "{}\n",
    "crates/one/Cargo.toml": "[package]\nname='one'\nversion='1.0.0'\n",
    "crates/one/nested/Cargo.toml": "[package]\nname='nested'\nversion='1.0.0'\n",
    "lib-app/composer.json": "{}\n",
    "lib-tools/composer.json": "{}\n",
    "nested/lib-app/composer.json": "{}\n",
    "packages/app/package.json": "{}\n",
    "packages/deep/app/package.json": "{}\n",
  });
  const { report } = run(root);
  const status = Object.fromEntries(
    report.manifests.map((manifest) => [manifest.manifest_path, manifest.status])
  );
  assert.equal(status["lib-app/composer.json"], "COVERED");
  assert.equal(status["lib-tools/composer.json"], "COVERED");
  assert.equal(status["nested/lib-app/composer.json"], "UNCOVERED");
  assert.equal(status["apps/lib-tools/composer.json"], "UNCOVERED");
  assert.equal(status["packages/app/package.json"], "COVERED");
  assert.equal(status["packages/deep/app/package.json"], "UNCOVERED");
  assert.equal(status["crates/one/Cargo.toml"], "COVERED");
  assert.equal(status["crates/one/nested/Cargo.toml"], "COVERED");

  const recursive = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: npm
    directories: ["/packages/**"]
    ${DAILY}
`,
    "packages/app/package.json": "{}\n",
    "packages/deep/app/package.json": "{}\n",
  });
  assert.equal(run(recursive).report.status, "PASS");
});

test("secure readers bind validation and reads to one file descriptor", () => {
  const source = readFileSync(VALIDATOR, "utf8");
  assert.match(source, /constants\.O_RDONLY \| constants\.O_NOFOLLOW \| constants\.O_NONBLOCK/);
  assert.match(source, /fstatSync\(descriptor\)/);
  assert.match(source, /readSync\(descriptor,/);
  assert.doesNotMatch(source, /readFileSync\(absolute/);

  const optional = repository({ README: "no Dependabot configuration\n" });
  assert.equal(run(optional).report.status, "PASS");

  const missingPolicy = path.join(optional, "missing-policy.json");
  assert.equal(
    run(optional, "coverage", ["--policy", missingPolicy]).report.diagnostics[0].code,
    "POLICY_ERROR"
  );

  const symlinked = repository({
    ".github/dependabot-source.yml": "version: 2\nupdates: []\n",
  });
  symlinkSync("dependabot-source.yml", path.join(symlinked, ".github/dependabot.yml"));
  execFileSync("git", ["-C", symlinked, "add", ".github/dependabot.yml"]);
  assert.equal(run(symlinked).report.diagnostics[0].code, "FILE_ERROR");

  const nonRegular = repository({
    ".github/dependabot.yml/placeholder": "tracked directory entry\n",
  });
  assert.equal(run(nonRegular).report.diagnostics[0].code, "FILE_ERROR");

  const oversizedYaml = repository({
    ".github/dependabot.yml": `#${"x".repeat(1024 * 1024)}\n`,
  });
  assert.equal(run(oversizedYaml).report.diagnostics[0].code, "FILE_ERROR");

  const oversizedTrackedText = repository({
    ".github/dependabot.yml": "version: 2\nupdates: []\n",
    "package.json": `{"padding":"${"x".repeat(2 * 1024 * 1024)}"}\n`,
  });
  assert.equal(run(oversizedTrackedText).report.diagnostics[0].code, "FILE_ERROR");
});

test("secure tracked reads retain content-qualified discovery", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
updates:
  - package-ecosystem: docker
    directory: /deploy
    ${DAILY}
  - package-ecosystem: pip
    directory: /python
    ${DAILY}
`,
    "deploy/config.yaml": "title: ordinary data\n",
    "deploy/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\n",
    "python/constraints.txt": "requests==2.32.5\n",
  });
  const { report } = run(root);
  assert.equal(report.status, "PASS");
  assert.deepEqual(
    report.manifests.map((manifest) => manifest.manifest_path),
    ["deploy/deployment.yaml", "python/constraints.txt"]
  );
});

test("multi-ecosystem entries require non-empty patterns", () => {
  const root = repository({
    ".github/dependabot.yml": `version: 2
multi-ecosystem-groups:
  infrastructure:
    schedule:
      interval: daily
      time: "04:00"
      timezone: Europe/Berlin
updates:
  - package-ecosystem: docker
    directory: /
    multi-ecosystem-group: infrastructure
`,
    Dockerfile: "FROM alpine:3.22\n",
  });
  assert.equal(run(root).report.diagnostics[0].code, "CONFIG_SCHEMA_ERROR");
});

test("catalog discovery dispositions and rule provenance are complete", () => {
  const original = JSON.parse(readFileSync(CATALOG, "utf8"));
  for (const mutate of [
    (policy) => delete policy.discovery_dispositions[policy.supported_config_ecosystems[0]],
    (policy) => delete policy.manifest_rules[0].source_paths,
    (policy) => (policy.reviewed_on = "2026-99-99"),
  ]) {
    const policy = structuredClone(original);
    mutate(policy);
    const root = repository({
      ".github/dependabot.yml": "version: 2\nupdates: []\n",
      "policy.json": `${JSON.stringify(policy)}\n`,
    });
    assert.equal(
      run(root, "coverage", ["--policy", path.join(root, "policy.json")]).report.diagnostics[0]
        .code,
      "POLICY_ERROR"
    );
  }
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
