// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import * as yaml from "js-yaml";
import { createRequire } from "node:module";

const workflow = yaml.load(
  readFileSync(
    new URL("../.github/workflows/reusable-dependabot-auto-merge.yml", import.meta.url),
    "utf8"
  )
);
const check = workflow.jobs["check-eligibility"].steps.find((step) => step.id === "check");
function decision(overrides = {}) {
  const dir = mkdtempSync(join(tmpdir(), "dependabot-boundary-"));
  const output = join(dir, "output");
  try {
    const result = spawnSync("bash", ["-euo", "pipefail", "-c", check.run], {
      encoding: "utf8",
      env: {
        ...process.env,
        GITHUB_OUTPUT: output,
        PHASE: "2",
        PR_TITLE: "chore(deps): bump fixture from 1.2.3 to 1.2.4",
        PR_LABELS: '["dependencies"]',
        METADATA_STEP_OUTCOME: "success",
        DEPENDENCY_NAMES: "fixture",
        DEPENDENCY_GROUP: "",
        MAINTAINER_CHANGES: "false",
        PACKAGE_ECOSYSTEM: "npm_and_yarn",
        UPDATE_TYPE_RAW: "version-update:semver-patch",
        PREVIOUS_VERSION: "1.2.3",
        NEW_VERSION: "1.2.4",
        UPDATED_DEPENDENCIES_JSON: "[]",
        SOURCE_VERIFIED: "true",
        ...overrides,
      },
    });
    assert.equal(result.status, 0, result.stderr);
    return Object.fromEntries(
      readFileSync(output, "utf8")
        .trim()
        .split("\n")
        .map((line) => line.split("="))
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
function eligible(overrides = {}) {
  return decision(overrides)["should-auto-merge"];
}
test("missing labels do not misidentify the Dependabot author and adding the label requalifies", () => {
  assert.equal(decision({ PR_LABELS: "[]" })["update-type"], "missing-dependencies-label");
  assert.equal(eligible({ PR_LABELS: "[]" }), "false");
  assert.equal(eligible({ PR_LABELS: '["dependencies"]' }), "true");
});
for (const kind of ["patch", "minor"]) {
  test(`${kind} with verified metadata is eligible in phase 2`, () => {
    assert.equal(eligible({ UPDATE_TYPE_RAW: `version-update:semver-${kind}` }), "true");
  });
}
for (const [name, overrides] of [
  ["major", { UPDATE_TYPE_RAW: "version-update:semver-major" }],
  ["title cannot replace absent semver metadata", { UPDATE_TYPE_RAW: "" }],
  ["unknown maintainer state", { MAINTAINER_CHANGES: "" }],
  ["maintainer edits", { MAINTAINER_CHANGES: "true" }],
  ["unverified source", { SOURCE_VERIFIED: "false" }],
  ["metadata failed", { METADATA_STEP_OUTCOME: "failure" }],
  ["non-dependencies label substring", { PR_LABELS: '["not-dependencies"]' }],
  [
    "SHA update",
    {
      UPDATE_TYPE_RAW: "",
      PACKAGE_ECOSYSTEM: "github_actions",
      PREVIOUS_VERSION: "123abc",
      NEW_VERSION: "234bcd",
    },
  ],
  ["unknown group", { DEPENDENCY_GROUP: "all", DEPENDENCY_NAMES: "a,b" }],
]) {
  test(`${name} remains manual`, () => assert.equal(eligible(overrides), "false"));
}

const sourceScript = workflow.jobs["check-eligibility"].steps.find((step) => step.id === "source")
  ?.with.script;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
function botCommit(
  message = "Bumps fixture from 1.2.3 to 1.2.4.\n\n---\nupdated-dependencies:\n- dependency-name: fixture\n  update-type: version-update:semver-patch\n...\n",
  login = "dependabot[bot]"
) {
  return {
    sha: "a".repeat(40),
    author: { login },
    committer: { login: "web-flow" },
    commit: { verification: { verified: true }, message },
    parents: [{}],
  };
}
async function verifySource(change = {}) {
  assert.equal(typeof sourceScript, "string");
  const head = "a".repeat(40);
  const pr = {
    number: 1,
    state: "open",
    draft: false,
    user: { login: "dependabot[bot]", type: "Bot" },
    base: { ref: "main", sha: "b".repeat(40) },
    head: { sha: head, repo: { full_name: "SecPal/frontend" } },
    commits: 1,
    changed_files: 2,
    labels: [{ name: "dependencies" }],
    ...change.pr,
  };
  const commits = change.commits || [botCommit()];
  const files = change.files || [{ filename: "package.json" }, { filename: "package-lock.json" }];
  const output = {};
  let reads = 0;
  const github = {
    rest: {
      git: {
        getCommit: async ({ commit_sha }) => ({ data: { tree: { sha: commit_sha } } }),
        getTree: async ({ tree_sha }) => ({
          data: {
            truncated: false,
            tree: Object.entries(change.manifests || {}).map(([path, entries]) => ({
              path,
              sha: entries[tree_sha].sha,
              mode: change.mode ?? "100644",
            })),
          },
        }),
        getRef: async ({ owner, repo, ref }) => ({
          data: {
            object:
              ref === "heads/main"
                ? { type: "commit", sha: change.protectedHead ?? pr.base.sha }
                : change.refs?.[`${owner}/${repo}/${ref}`],
          },
        }),
        getTag: async ({ owner, repo, tag_sha }) => ({
          data: change.tags?.[`${owner}/${repo}/${tag_sha}`],
        }),
      },
      repos: {
        getContent: async ({ ref, path }) => {
          if (change.manifests?.[path]) {
            const manifest = change.manifests[path][ref];
            assert.ok(manifest, "requirements must come from an exact commit");
            return { data: { type: "file", encoding: "base64", ...manifest } };
          }
          if (change.alternateConfig && path.endsWith(".yml")) {
            throw Object.assign(new Error("not found"), { status: 404 });
          }
          assert.equal(ref, pr.base.sha, "configuration must come from the immutable base");
          if (change.configError) throw new Error("configuration unavailable");
          return {
            data: {
              type: "file",
              encoding: "base64",
              content: Buffer.from(
                change.config ??
                  "version: 2\nupdates:\n- package-ecosystem: npm\n  directory: /\n- package-ecosystem: github-actions\n  directory: /\n"
              ).toString("base64"),
            },
          };
        },
      },
      pulls: {
        get: async () => ({ data: ++reads > 1 && change.after ? change.after : pr }),
        listFiles: "files",
        listCommits: "commits",
      },
    },
    paginate: async (endpoint) => (endpoint === "files" ? files : commits),
  };
  const saved = { ...process.env };
  Object.assign(process.env, {
    PACKAGE_ECOSYSTEM: "npm_and_yarn",
    DEPENDENCY_DIRECTORY: "/",
    ALLOWED_ECOSYSTEMS: "npm_and_yarn,github_actions",
    VERIFIED_DEPENDENCIES:
      '[{"dependencyName":"fixture","updateType":"version-update:semver-patch"}]',
    ...change.env,
  });
  try {
    await new AsyncFunction("github", "context", "core", "require", sourceScript)(
      github,
      {
        repo: { owner: "SecPal", repo: "frontend" },
        payload: {
          repository: { default_branch: "main" },
          pull_request: { number: 1, head: { sha: head } },
        },
      },
      { setOutput: (key, value) => Object.assign(output, { [key]: value }) },
      createRequire(import.meta.url)
    );
    return change.classification ? output["update-type"] : output.verified;
  } finally {
    process.env = saved;
  }
}
test("authentic signed bot manifest update passes the source boundary", async () => {
  assert.equal(await verifySource(), "true");
});

const admissionBase = "b".repeat(40);
const admissionHead = "a".repeat(40);
const admissionBlob = "f".repeat(40);

function updateFixture(ecosystem, config, changes, dependencies, env, extra = {}) {
  const signed = dependencies.map(({ dependencyName, newVersion, updateType }) => ({
    "dependency-name": dependencyName,
    "dependency-version": newVersion,
    ...(updateType ? { "update-type": updateType } : {}),
  }));
  const commit = botCommit(`Update.\n\n---\n${yaml.dump({ "updated-dependencies": signed })}...\n`);
  commit.parents = [{ sha: admissionBase }];
  const encoded = (content) => ({
    sha: admissionBlob,
    content: Buffer.from(content).toString("base64"),
  });
  return {
    classification: true,
    pr: { changed_files: changes.length },
    commits: [commit],
    files: changes.map(([filename]) => ({ filename, status: "modified", sha: admissionBlob })),
    manifests: Object.fromEntries(
      changes.map(([name, old, next]) => [
        name,
        {
          [admissionBase]: encoded(old),
          [admissionHead]: encoded(next),
        },
      ])
    ),
    config: `version: 2\nupdates:\n${config}`,
    env: {
      PACKAGE_ECOSYSTEM: ecosystem,
      ALLOWED_ECOSYSTEMS: ecosystem,
      VERIFIED_DEPENDENCIES: JSON.stringify(dependencies),
      ...env,
    },
    ...extra,
  };
}

function preCommitFixture(repo, before, after, oldTag, newTag, extraEdit = "") {
  const name = `https://github.com/${repo}`;
  const config = (rev, edit) =>
    `repos:\n  - repo: ${name}\n    rev: ${rev}\n    hooks:\n      - id: lint\n${edit}  - repo: local\n    hooks:\n      - id: local\n`;
  const refs = {};
  for (const [ref, tag, fallback] of [
    [before, oldTag, admissionBase],
    [after, newTag, admissionHead],
  ]) {
    refs[`${repo}/tags/${tag}`] = {
      type: "commit",
      sha: /^[a-f0-9]{40}/.test(ref) ? ref.slice(0, 40) : fallback,
    };
  }
  return updateFixture(
    "pre_commit",
    "- package-ecosystem: pre-commit\n  directory: /\n",
    [[".pre-commit-config.yaml", config(before, ""), config(after, extraEdit)]],
    [
      {
        dependencyName: name,
        newVersion: newTag.slice(1),
        packageEcosystem: "pre_commit",
        dependencyGroup: "",
      },
    ],
    { PRE_COMMIT_PATH: ".pre-commit-config.yaml" },
    { refs }
  );
}

for (const [repo, initial, replacement, kind] of [
  ["fsfe/reuse-tool", "v6.2.0", "v6.3.0", "minor"],
  ["adrienverge/yamllint", "v1.37.1", "v1.38.0", "minor"],
  ["kjanat/actionlint", "v1.17.0", "v1.17.1", "patch"],
]) {
  test(`authenticates the ${repo} pre-commit ${kind} without a title-derived class`, async () => {
    const [before, after] =
      kind === "patch"
        ? [`${admissionBase} # ${initial}`, `${admissionHead} # ${replacement}`]
        : [initial, replacement];
    const fixture = preCommitFixture(repo, before, after, initial, replacement);
    assert.equal(await verifySource(fixture), `version-update:semver-${kind}`);
    fixture.refs[`${repo}/tags/${replacement}`].sha = admissionBase;
    assert.equal(await verifySource(fixture), undefined);
  });
}

test("pre-commit admission rejects prereleases and hook argument changes", async () => {
  assert.equal(
    await verifySource(
      preCommitFixture("example/hooks", "v1.2.0", "v1.3.0-rc.1", "v1.2.0", "v1.3.0-rc.1")
    ),
    undefined
  );
  assert.equal(
    await verifySource(
      preCommitFixture(
        "example/hooks",
        "v1.2.0",
        "v1.2.1",
        "v1.2.0",
        "v1.2.1",
        "        args: [new]\n"
      )
    ),
    undefined
  );
  assert.equal(
    await verifySource({
      ...preCommitFixture("example/hooks", "v1.2.0", "v1.2.1", "v1.2.0", "v1.2.1"),
      protectedHead: "c".repeat(40),
    }),
    undefined
  );
  assert.equal(
    await verifySource({
      ...preCommitFixture("example/hooks", "v1.2.0", "v1.2.1", "v1.2.0", "v1.2.1"),
      mode: "100755",
    }),
    undefined
  );
});

function dockerFixture(
  tags,
  paths,
  line,
  suffix = "",
  digestRefresh = false,
  image = "library/composer"
) {
  const ref = (tag, digest) =>
    `FROM docker.io/${image}:${tag}@sha256:${digest.repeat(64)} AS base\nRUN true\n`;
  const changes = paths.map((path) => [path, ref(tags[0], "a"), ref(tags[1], "b")]);
  const patch =
    tags[0] === tags[1] ||
    tags[0].split(".").slice(0, 2).join(".") === tags[1].split(".").slice(0, 2).join(".");
  const dependencies = paths.map(() => ({
    dependencyName: image,
    newVersion: tags[1],
    packageEcosystem: "docker",
    dependencyGroup: paths.length > 1 ? "composer-image" : "",
    updateType: `version-update:semver-${patch ? "patch" : "minor"}`,
  }));
  return updateFixture(
    "docker",
    "- package-ecosystem: docker\n  directories: [/, /docker/php-fpm, /docker/nginx]\n",
    changes,
    dependencies,
    { DOCKER_RULES: JSON.stringify([{ image, paths, line, suffix, digestRefresh }]) }
  );
}

test("authenticates a stable PHP patch within the supported image line", async () => {
  const paths = ["docker/php-fpm/Containerfile"];
  assert.equal(
    await verifySource(
      dockerFixture(
        ["8.4.27-fpm-alpine3.24", "8.4.28-fpm-alpine3.24"],
        paths,
        "8.4",
        "-fpm-alpine3.24",
        false,
        "library/php"
      )
    ),
    "version-update:semver-patch"
  );
});

test("authenticates both members of the Composer image group", async () => {
  const paths = ["Containerfile", "docker/php-fpm/Containerfile"];
  const fixture = dockerFixture(["2.10.2", "2.11.1"], paths, "2");
  assert.equal(await verifySource(fixture), "version-update:semver-minor");
  const changed = fixture.manifests[paths[1]][admissionHead];
  changed.content = Buffer.from(
    Buffer.from(changed.content, "base64").toString().replace(/b{64}/, "c".repeat(64))
  ).toString("base64");
  assert.equal(await verifySource(fixture), undefined);
});

test("classifies unchanged FrankenPHP tags as explicit digest refreshes", async () => {
  const tags = ["1.13.5-php8.4.27-alpine", "1.13.5-php8.4.27-alpine"];
  assert.equal(
    await verifySource(
      dockerFixture(
        tags,
        ["Containerfile"],
        "1.13.5",
        "-php8.4.27-alpine",
        true,
        "dunglas/frankenphp"
      )
    ),
    "digest-refresh"
  );
  assert.equal(
    await verifySource(
      dockerFixture(
        tags,
        ["Containerfile"],
        "1.13.5",
        "-php8.4.27-alpine",
        false,
        "dunglas/frankenphp"
      )
    ),
    undefined
  );
  assert.equal(
    eligible({ UPDATE_TYPE_RAW: "digest-refresh", PACKAGE_ECOSYSTEM: "docker", PHASE: "2" }),
    "true"
  );
  assert.equal(
    eligible({ UPDATE_TYPE_RAW: "digest-refresh", PACKAGE_ECOSYSTEM: "docker", PHASE: "1" }),
    "false"
  );
  assert.equal(
    eligible({ UPDATE_TYPE_RAW: "digest-refresh", PACKAGE_ECOSYSTEM: "github_actions" }),
    "false"
  );
});

test("rejects RC image versions and unsupported Nginx lines", async () => {
  assert.equal(
    await verifySource(
      dockerFixture(
        ["8.4.27-fpm-alpine3.24", "8.6.0RC5-fpm-alpine3.24"],
        ["docker/php-fpm/Containerfile"],
        "8.4",
        "-fpm-alpine3.24",
        false,
        "library/php"
      )
    ),
    undefined
  );
  assert.equal(
    await verifySource(
      dockerFixture(
        ["1.30.7-alpine3.24-slim", "1.31.8-alpine3.24-slim"],
        ["docker/nginx/Containerfile"],
        "1.30",
        "-alpine3.24-slim",
        false,
        "library/nginx"
      )
    ),
    undefined
  );
});

const pipPath = "docker/python/opentimestamps-requirements.txt";
const pipBase = "b".repeat(40);
const pipHead = "a".repeat(40);
const pipBlob = "e".repeat(40);
const requirement = (name, version, fill) =>
  `${name}==${version} --hash=sha256:${fill.repeat(64)}\n`;
const pipBefore =
  requirement("opentimestamps", "0.4.5", "a") + requirement("pycryptodomex", "3.23.0", "b");
const pipAfter =
  requirement("opentimestamps", "0.5.0", "c") + requirement("pycryptodomex", "3.23.0", "b");

function pipChange({
  before = pipBefore,
  after = pipAfter,
  version = "0.5.0",
  updateType = "version-update:semver-minor",
  path = pipPath,
  status = "modified",
  blob = pipBlob,
  group = "",
  parent = pipBase,
  secondFile = false,
} = {}) {
  const commit = botCommit(
    `Fixture.\n\n---\nupdated-dependencies:\n- dependency-name: opentimestamps\n  dependency-version: ${version}\n  update-type: ${updateType}\n...\n`
  );
  commit.parents = [{ sha: parent }];
  const files = [{ filename: path, status, sha: blob }];
  if (secondFile)
    files.push({ filename: "docker/python/other-requirements.txt", status, sha: blob });
  return {
    pr: { changed_files: files.length },
    commits: [commit],
    files,
    config: "version: 2\nupdates:\n- package-ecosystem: pip\n  directory: /docker/python\n",
    env: {
      PACKAGE_ECOSYSTEM: "pip",
      ALLOWED_ECOSYSTEMS: "pip",
      PIP_MANIFEST_PATH: pipPath,
      VERIFIED_DEPENDENCIES: JSON.stringify([
        {
          dependencyName: "opentimestamps",
          packageEcosystem: "pip",
          dependencyGroup: group,
          newVersion: version,
          updateType,
        },
      ]),
    },
    manifests: {
      [pipPath]: {
        [pipBase]: { content: Buffer.from(before).toString("base64") },
        [pipHead]: { sha: pipBlob, content: Buffer.from(after).toString("base64") },
      },
    },
  };
}

test("an opted-in signed pip minor changes one hash-locked dependency", async () => {
  assert.equal(await verifySource(pipChange()), "true");
});

test("pip uses canonical names for locked dependencies", async () => {
  const before =
    pipBefore.replace("opentimestamps", "OpenTimestamps") +
    requirement("test-package", "1.2.3", "d");
  const after =
    pipAfter.replace("opentimestamps", "OpenTimestamps") +
    requirement("TEST_package", "1.2.3", "d");
  assert.equal(await verifySource(pipChange({ before, after })), "true");
  assert.equal(
    await verifySource(
      pipChange({ before, after: after + requirement("test.package", "1.2.3", "d") })
    ),
    "false"
  );
});

test("an opted-in signed pip patch changes one hash-locked dependency", async () => {
  const after =
    requirement("opentimestamps", "0.4.6", "c") + requirement("pycryptodomex", "3.23.0", "b");
  assert.equal(
    await verifySource(
      pipChange({ after, version: "0.4.6", updateType: "version-update:semver-patch" })
    ),
    "true"
  );
});

for (const [reason, change] of [
  ["other file", { path: "docker/python/other-requirements.txt" }],
  ["second file", { secondFile: true }],
  ["added file", { status: "added" }],
  ["unbound blob", { blob: "f".repeat(40) }],
  ["stale parent", { parent: "f".repeat(40) }],
  ["grouped change", { group: "python" }],
  ["misclassified update", { updateType: "version-update:semver-patch" }],
  ["signed version mismatch", { version: "0.5.1" }],
  ["unhashed pin", { after: pipAfter.replace(/ --hash=sha256:[a-f]+/, "") }],
  ["unrelated hash change", { after: pipAfter.replace("b".repeat(64), "d".repeat(64)) }],
  ["added dependency", { after: pipAfter + requirement("fixture", "1.2.3", "a") }],
  ["ambiguous continued comment", { after: pipAfter + "# comment\\\nnot-a-requirement\n" }],
  ["encoding override", { after: "# coding: latin1\n" + pipAfter }],
  ["nonstandard line boundary", { after: pipAfter + "# comment\rnot-a-requirement\n" }],
  ["custom package source", { after: pipAfter + "--index-url https://example.com\n" }],
]) {
  test(`pip ${reason} fails source verification`, async () => {
    assert.equal(await verifySource(pipChange(change)), "false");
  });
}
for (const [name, change] of [
  ["foreign PR author", { pr: { user: { login: "attacker", type: "User" } } }],
  [
    "unverified commit signature",
    {
      commits: [
        { ...botCommit(), commit: { ...botCommit().commit, verification: { verified: false } } },
      ],
    },
  ],
  ["maintainer commit", { commits: [botCommit(undefined, "aroviqen")] }],
  [
    "foreign head repository",
    { pr: { head: { sha: "a".repeat(40), repo: { full_name: "attacker/frontend" } } } },
  ],
  [
    "unexpected runtime file",
    { files: [{ filename: "src/App.tsx" }, { filename: "package-lock.json" }] },
  ],
  [
    "rename from unexpected path",
    {
      files: [
        { filename: "package.json", previous_filename: "src/App.tsx" },
        { filename: "package-lock.json" },
      ],
    },
  ],
  ["truncated changed file list", { pr: { changed_files: 3 } }],
  ["unknown ecosystem", { env: { PACKAGE_ECOSYSTEM: "terraform" } }],
  [
    "configured directory traversal",
    { config: "version: 2\nupdates:\n- package-ecosystem: npm\n  directory: /../\n" },
  ],
  ["configuration has no matching ecosystem", { config: "version: 2\nupdates: []\n" }],
  [
    "configuration targets another branch",
    {
      config:
        "version: 2\nupdates:\n- package-ecosystem: npm\n  directory: /\n  target-branch: release\n",
    },
  ],
  [
    "head changed during verification",
    { after: { state: "open", head: { sha: "c".repeat(40) }, base: { sha: "b".repeat(40) } } },
  ],
]) {
  test(`${name} fails source verification`, async () =>
    assert.equal(await verifySource(change), "false"));
}
test("deployment allows verified Actions metadata but excludes infrastructure ecosystems", async () => {
  assert.equal(await verifySource({ env: { ALLOWED_ECOSYSTEMS: "github_actions" } }), "false");
  assert.equal(
    await verifySource({
      env: { ALLOWED_ECOSYSTEMS: "github_actions", PACKAGE_ECOSYSTEM: "github_actions" },
      files: [
        { filename: ".github/workflows/quality.yml" },
        { filename: ".github/workflows/local-integration.yml" },
      ],
    }),
    "true"
  );
});
test("auto-merge enrollment is bound to the verified exact head", () => {
  const step = workflow.jobs["auto-merge"].steps.find((step) => step.name === "Enable auto-merge");
  assert.match(step.env.EXPECTED_HEAD, /pull_request.head.sha/);
  assert.equal(step.if, "steps.enrollment.outputs.required == 'true'");
  for (const command of step.run.split("\n").filter((line) => line.includes("gh pr merge"))) {
    assert.match(command, /--match-head-commit "\$\{EXPECTED_HEAD\}"/);
  }
});

test("multiple bot commits cannot reuse the first commit classification", async () => {
  const commit = botCommit();
  assert.equal(await verifySource({ pr: { commits: 2 }, commits: [commit, commit] }), "false");
});

test("calculated metadata from a mutable title cannot authenticate a SHA update", async () => {
  const commit = botCommit(
    "Bumps fixture from abcdef to bcdefa.\n\n---\nupdated-dependencies:\n- dependency-name: fixture\n  dependency-type: direct:production\n...\n"
  );
  assert.equal(await verifySource({ commits: [commit] }), "false");
});

test("immutable shared workflow pins remain manual even with a claimed patch class", async () => {
  assert.equal(
    await verifySource({
      env: {
        PACKAGE_ECOSYSTEM: "github_actions",
        VERIFIED_DEPENDENCIES:
          '[{"dependencyName":"SecPal/.github/.github/workflows/reusable-test.yml","updateType":"version-update:semver-patch"}]',
      },
      files: [
        { filename: ".github/workflows/quality.yml" },
        { filename: ".github/workflows/lint.yml" },
      ],
    }),
    "false"
  );
});
test("a signed minor class passes the same source boundary", async () => {
  const message =
    "Bumps fixture from 1.2.3 to 1.3.0.\n\n---\nupdated-dependencies:\n- dependency-name: fixture\n  update-type: version-update:semver-minor\n...\n";
  assert.equal(
    await verifySource({
      env: {
        VERIFIED_DEPENDENCIES:
          '[{"dependencyName":"fixture","updateType":"version-update:semver-minor"}]',
      },
      commits: [botCommit(message)],
    }),
    "true"
  );
});

test("deployment's workflow allowlist keeps cloud execution paths manual", async () => {
  const env = {
    ALLOWED_ECOSYSTEMS: "github_actions",
    PACKAGE_ECOSYSTEM: "github_actions",
    WORKFLOW_PATHS: '[".github/workflows/quality.yml",".github/workflows/local-integration.yml"]',
  };
  for (const [path, expected] of [
    ["local-integration", "true"],
    ["cloud-janitor", "false"],
  ]) {
    const files = [".github/workflows/quality.yml", `.github/workflows/${path}.yml`].map(
      (filename) => ({ filename })
    );
    assert.equal(await verifySource({ env, files }), expected);
  }
});

test("queued automation is revoked when eligibility changes, while manual requests survive", async () => {
  assert.equal(workflow["cache-mode"], "none");
  const safety = workflow.jobs["source-safety"];
  assert.ok(safety, "source safety must run before enrollment on every PR head");
  assert.equal(safety.if, "${{ always() }}");
  assert.ok(workflow.jobs["auto-merge"].needs.includes("source-safety"));
  const script = safety.steps[0].with.script;
  const head = "a".repeat(40);
  for (const [eligible, owner, remains, expected, hasLabel = true, mainTarget = true] of [
    ["false", "github-actions[bot]", null, true],
    ["false", "aroviqen", "aroviqen", true],
    ["true", "github-actions[bot]", "github-actions[bot]", true],
    ["false", "github-actions[bot]", "github-actions[bot]", false],
    ["true", "github-actions[bot]", null, true, false],
    ["true", "github-actions[bot]", null, true, true, false],
  ]) {
    let mutations = 0;
    const request = (login) => (login ? { enabled_by: { login }, merge_method: "squash" } : null);
    const pr = {
      head: { sha: head },
      base: { ref: mainTarget ? "main" : "release" },
      state: "open",
      node_id: "PR_1",
      user: { login: "dependabot[bot]" },
      labels: hasLabel ? [{ name: "dependencies" }] : [],
      auto_merge: request(owner),
    };
    const github = {
      rest: {
        pulls: {
          get: async () => ({ data: mutations ? { ...pr, auto_merge: request(remains) } : pr }),
        },
      },
      graphql: async () => {
        mutations++;
      },
    };
    process.env.ELIGIBLE = eligible;
    const run = () =>
      new AsyncFunction("github", "context", script)(github, {
        repo: { owner: "SecPal", repo: "frontend" },
        payload: {
          repository: { default_branch: "main" },
          pull_request: { number: 1, head: { sha: head } },
        },
      });
    if (expected) await run();
    else await assert.rejects(run());
    assert.equal(
      mutations,
      (eligible !== "true" || !hasLabel || !mainTarget) && owner === "github-actions[bot]" ? 1 : 0
    );
  }
  delete process.env.ELIGIBLE;
});

test("caller reconciles label, draft and target changes", () => {
  const caller = yaml.load(readFileSync(".github/workflows/dependabot-auto-merge.yml", "utf8"));
  assert.equal(caller.jobs["auto-merge"].if, undefined);
  assert.equal(caller.jobs["auto-merge"].with.phase, "2");
  assert.equal(caller.jobs["auto-merge"].with["allowed-ecosystems"], "github_actions");
  assert.equal(caller.concurrency["cancel-in-progress"], true);
  assert.equal(caller["cache-mode"], "none");
  assert.deepEqual(caller.permissions, {
    contents: "write",
    "pull-requests": "write",
    checks: "read",
    statuses: "read",
  });
  for (const event of ["labeled", "unlabeled", "edited", "converted_to_draft"]) {
    assert.ok(caller.on.pull_request_target.types.includes(event), `missing ${event}`);
  }
});
test("enrollment requires a successful protected safety check from this same run", () => {
  const step = workflow.jobs["auto-merge"].steps.find((step) => step.name === "Enable auto-merge");
  for (const [checks, expected] of [
    [
      [
        {
          name: "auto-merge / Dependabot Source Safety",
          state: "SUCCESS",
          link: "https://github.com/SecPal/test/actions/runs/41/job/1",
        },
        {
          name: "auto-merge / Dependabot Source Safety",
          state: "SUCCESS",
          link: "https://github.com/SecPal/test/actions/runs/42/job/1",
        },
      ],
      true,
    ],
    [[], false],
    [
      [
        {
          name: "auto-merge / Dependabot Source Safety",
          state: "FAILURE",
          link: "https://github.com/SecPal/test/actions/runs/42/job/1",
        },
      ],
      false,
    ],
    [
      [
        {
          name: "auto-merge / Dependabot Source Safety",
          state: "SUCCESS",
          link: "https://github.com/SecPal/test/actions/runs/41/job/1",
        },
      ],
      false,
    ],
    [
      [
        {
          name: "auto-merge / Dependabot Source Safety",
          state: "SUCCESS",
          link: "https://github.com/SecPal/test/actions/runs/42/job/1",
        },
      ],
      true,
    ],
  ]) {
    const dir = mkdtempSync(join(tmpdir(), "dependabot-enrollment-"));
    try {
      const record = join(dir, "merged");
      writeFileSync(
        join(dir, "gh"),
        '#!/bin/sh\nif [ "$2" = checks ]; then printf "%s" "$CHECKS"; exit 8; fi\nprintf "merge" > "$RECORD"\n',
        { mode: 0o700 }
      );
      const result = spawnSync("bash", ["-c", step.run.replace(/\$\{\{.*?\}\}/g, "fixture")], {
        env: {
          ...process.env,
          PATH: `${dir}:${process.env.PATH}`,
          CHECKS: JSON.stringify(checks),
          RECORD: record,
          GITHUB_SERVER_URL: "https://github.com",
          GITHUB_REPOSITORY: "SecPal/test",
          GITHUB_RUN_ID: "42",
          PR_URL: "https://github.com/SecPal/test/pull/1",
          MERGE_METHOD: "squash",
          EXPECTED_HEAD: "a".repeat(40),
        },
        encoding: "utf8",
      });
      assert.equal(result.status === 0, expected, result.stdout + result.stderr);
      assert.equal(readFileSync(record, { encoding: "utf8", flag: "a+" }) === "merge", expected);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

test("a stale eligible run cannot enroll after the live dependencies label is removed", async () => {
  const step = workflow.jobs["auto-merge"].steps.find((step) => step.id === "enrollment");
  const head = "a".repeat(40);
  for (const labels of [[], [{ name: "dependencies" }]]) {
    const out = {};
    await new AsyncFunction("github", "context", "core", step.with.script)(
      {
        rest: {
          pulls: {
            get: async () => ({
              data: {
                head: { sha: head },
                base: { ref: "main" },
                state: "open",
                draft: false,
                labels,
                auto_merge: null,
              },
            }),
          },
        },
      },
      {
        repo: { owner: "SecPal", repo: ".github" },
        payload: {
          repository: { default_branch: "main" },
          pull_request: { number: 1, head: { sha: head } },
        },
      },
      {
        setOutput: (k, v) => {
          out[k] = v;
        },
      }
    );
    assert.equal(out.required, labels.length ? "true" : "false");
  }
});

test("native required-check lookup has only the necessary read scopes", () => {
  assert.equal(workflow.permissions.checks, "read");
  assert.equal(workflow.permissions.statuses, "read");
  const eligibility = workflow.jobs["check-eligibility"].permissions;
  assert.deepEqual(eligibility, { contents: "read", "pull-requests": "read" });
});

test("callers remaining in phase one still refuse minor enrollment", () => {
  assert.equal(eligible({ PHASE: "1", UPDATE_TYPE_RAW: "version-update:semver-minor" }), "false");
});

// fetch-metadata v3.1.0 interprets the target branch as a directory for these
// real Dependabot PRs: https://github.com/SecPal/frontend/pull/2051 and
// https://github.com/SecPal/api/pull/2646. It is never path authorization.
for (const [name, ecosystem, config, files] of [
  ["frontend #2051", "npm_and_yarn", "npm", ["package.json", "package-lock.json"]],
  ["api #2646", "composer", "composer", ["composer.json", "composer.lock"]],
]) {
  test(`${name}: root manifests are authorized by base config despite /main metadata`, async () => {
    assert.equal(
      await verifySource({
        env: {
          PACKAGE_ECOSYSTEM: ecosystem,
          ALLOWED_ECOSYSTEMS: ecosystem,
          DEPENDENCY_DIRECTORY: "/main",
        },
        config: `version: 2\nupdates:\n- package-ecosystem: ${config}\n  directory: /\n`,
        files: files.map((filename) => ({ filename })),
      }),
      "true"
    );
  });
}
test("a branch-derived directory cannot authorize unconfigured manifest paths", async () => {
  assert.equal(
    await verifySource({
      env: { DEPENDENCY_DIRECTORY: "/main" },
      files: [{ filename: "main/package.json" }, { filename: "main/package-lock.json" }],
    }),
    "false"
  );
});
test("only explicitly configured subdirectories authorize manifests", async () => {
  const config = "version: 2\nupdates:\n- package-ecosystem: npm\n  directories: [/tools, /docs]\n";
  assert.equal(await verifySource({ config }), "false");
  assert.equal(
    await verifySource({
      config,
      files: [{ filename: "tools/package.json" }, { filename: "tools/package-lock.json" }],
    }),
    "true"
  );
});
test("status reporting does not post repeated PR comments", () => {
  assert.doesNotMatch(JSON.stringify(workflow), /issues\.createComment/);
});

test("unavailable base config fails closed", async () => {
  await assert.rejects(verifySource({ configError: true }), /configuration unavailable/);
});

test("the supported dependabot.yaml filename uses the same immutable base", async () => {
  assert.equal(await verifySource({ alternateConfig: true }), "true");
});
