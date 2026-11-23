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
        getCommit: async ({ commit_sha }) => ({
          data: { sha: commit_sha, tree: { sha: commit_sha } },
        }),
        getTree: async ({ repo, tree_sha }) =>
          repo === ".github"
            ? {
                data: change.upstream?.trees[tree_sha],
              }
            : {
                data: {
                  truncated: false,
                  tree: Object.entries(change.manifests || {}).map(([path, entries]) => ({
                    path,
                    sha: entries[tree_sha].sha,
                    mode: change.mode ?? "100644",
                  })),
                },
              },
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
        getBranch: async ({ owner, repo, branch }) => {
          assert.deepEqual(
            { owner, repo, branch },
            { owner: "SecPal", repo: ".github", branch: "main" }
          );
          return { data: change.upstream.branch };
        },
        compareCommitsWithBasehead: async ({ owner, repo, basehead }) => {
          assert.deepEqual({ owner, repo }, { owner: "SecPal", repo: ".github" });
          return { data: change.upstream.comparisons[basehead] };
        },
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
    await new AsyncFunction("github", "context", "core", "require", "fetch", sourceScript)(
      github,
      {
        repo: { owner: "SecPal", repo: "frontend" },
        payload: {
          repository: { default_branch: "main" },
          pull_request: { number: 1, head: { sha: head } },
        },
      },
      { setOutput: (key, value) => Object.assign(output, { [key]: value }) },
      createRequire(import.meta.url),
      change.fetch ?? (() => assert.fail("unexpected network request"))
    );
    return output[change.output ?? (change.classification ? "update-type" : "verified")];
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
  image = "library/composer",
  enforceLine = false
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
    "- package-ecosystem: docker\n  directories: [/, /docker/php-fpm, /docker/nginx, /containers/polyscope-php]\n",
    changes,
    dependencies,
    { DOCKER_RULES: JSON.stringify([{ image, paths, line, suffix, digestRefresh, enforceLine }]) }
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

const phpSuffix = "-fpm-alpine3.24";
const phpPolicyFixture = (candidate, { enforceLine = true, digestRefresh = false } = {}) =>
  dockerFixture(
    ["8.4.27" + phpSuffix, candidate],
    ["docker/php-fpm/Containerfile"],
    "8.4",
    phpSuffix,
    digestRefresh,
    "library/php",
    enforceLine
  );

test("enforced PHP rule accepts future stable patches and preserves explicit digest opt-in", async () => {
  for (const version of ["8.4.28", "8.4.29"]) {
    assert.equal(
      await verifySource(phpPolicyFixture(version + phpSuffix)),
      "version-update:semver-patch"
    );
  }
  const currentTag = "8.4.27" + phpSuffix;
  assert.equal(
    await verifySource(phpPolicyFixture(currentTag, { digestRefresh: true })),
    "digest-refresh"
  );
  assert.equal(await verifySource(phpPolicyFixture(currentTag)), undefined);
});

test("enforced PHP rule rejects prereleases, variant changes, malformed tags, and unsupported lines", async () => {
  for (const [tag, reason] of [
    ...[
      "RC1",
      "rc1",
      ".RC1",
      "-rc.1",
      "alpha1",
      "-BETA.2",
      "a1",
      "-preview",
      "-nightly",
      "-dev",
    ].map((qualifier) => ["8.4.28" + qualifier + phpSuffix, "prerelease"]),
    ["8.6.0RC5" + phpSuffix, "prerelease outside the supported release line"],
    ["8.5.0" + phpSuffix, "outside the supported release line"],
    ["8.4.28-cli-alpine3.24", "invalid runtime tag"],
    ["8.4" + phpSuffix, "invalid runtime tag"],
  ]) {
    const fixture = phpPolicyFixture(tag);
    assert.equal(await verifySource(fixture), undefined, tag);
    assert.match(
      (await verifySource({ ...fixture, output: "policy-rejection" })) ?? "",
      new RegExp(reason),
      tag
    );
  }
});

test("approved Nginx patches pass while both mainline and future stable releases fail the line check", async () => {
  const scenario = (version, path) =>
    dockerFixture(
      ["1.30.7-alpine3.24-slim", version + "-alpine3.24-slim"],
      [path],
      "1.30",
      "-alpine3.24-slim",
      false,
      "library/nginx",
      true
    );
  for (const path of ["docker/nginx/Containerfile", "containers/polyscope-php/Containerfile"]) {
    assert.equal(await verifySource(scenario("1.30.8", path)), "version-update:semver-patch");
    for (const version of ["1.31.10", "1.32.0", "2.0.0"]) {
      const fixture = scenario(version, path);
      assert.equal(await verifySource(fixture), undefined);
      assert.match(
        await verifySource({ ...fixture, output: "policy-rejection" }),
        /outside the supported release line/
      );
    }
  }
});

test("a hard rejection requires an opted-in rule, signed proposal, and current protected base", async () => {
  const tag = "8.4.28RC1" + phpSuffix;
  const unsigned = phpPolicyFixture(tag);
  unsigned.commits[0].commit.verification.verified = false;
  const mismatchedTag = phpPolicyFixture(tag);
  const [file] = mismatchedTag.files;
  const content = mismatchedTag.manifests[file.filename][admissionHead];
  content.content = Buffer.from(
    Buffer.from(content.content, "base64").toString().replace("RC1", "RC2")
  ).toString("base64");
  for (const fixture of [
    phpPolicyFixture(tag, { enforceLine: false }),
    unsigned,
    mismatchedTag,
    { ...phpPolicyFixture(tag), protectedHead: "c".repeat(40) },
    { ...phpPolicyFixture(tag), pr: { user: { login: "developer", type: "User" } } },
  ]) {
    assert.equal(await verifySource({ ...fixture, output: "policy-rejection" }), undefined);
  }
});

test("authenticates an alias-free Caddy digest refresh without accepting an alias change", async () => {
  const path = "containers/phase-b-gateway/Containerfile";
  const image = "library/caddy";
  const tag = "2.11.9-alpine";
  const base = (digest) => `FROM docker.io/${image}:${tag}@sha256:${digest.repeat(64)}`;
  const scenario = (alias = "") =>
    updateFixture(
      "docker",
      "- package-ecosystem: docker\n  directory: /containers/phase-b-gateway\n",
      [[path, `${base("a")}\nUSER 1000\n`, `${base("b")}${alias}\nUSER 1000\n`]],
      [
        {
          dependencyName: image,
          newVersion: tag,
          packageEcosystem: "docker",
          dependencyGroup: "",
          updateType: "version-update:semver-patch",
        },
      ],
      {
        DOCKER_RULES: JSON.stringify([
          { image, paths: [path], line: "2.11", suffix: "-alpine", digestRefresh: true },
        ]),
      }
    );
  assert.equal(await verifySource(scenario()), "digest-refresh");
  assert.equal(await verifySource(scenario(" AS alternate")), undefined);
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

test("classifies unchanged official PHP tags as explicit digest refreshes", async () => {
  const tags = ["8.4.28-fpm-alpine3.24", "8.4.28-fpm-alpine3.24"];
  assert.equal(
    await verifySource(
      dockerFixture(tags, ["Containerfile"], "8.4", "-fpm-alpine3.24", true, "library/php")
    ),
    "digest-refresh"
  );
  assert.equal(
    await verifySource(
      dockerFixture(tags, ["Containerfile"], "8.4", "-fpm-alpine3.24", false, "library/php")
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

const deploymentPins = {
  "requirements/build/requirements.txt": "shellcheck-py==0.11.0.1\n",
  "requirements/integration/requirements.txt": "-r ../quality/requirements.txt\npsycopg==3.3.6\n",
  "requirements/qualification/requirements.txt": "-r ../schema/requirements.txt\nPyYAML==6.0.2\n",
  "requirements/quality/requirements.txt":
    "-r ../qualification/requirements.txt\nreuse==6.1.2\nboolean.py==5.0\n",
  "requirements/schema/requirements.txt":
    'jsonschema==4.25.1\ntyping-extensions==4.16.0; python_version < "3.13"\n',
};

function deploymentPipChange({
  group = "",
  before = deploymentPins,
  after = "PyYAML==6.0.3",
  version = "6.0.3",
  dependencyName = "pyyaml",
  oldPin = "PyYAML==6.0.2",
  path = "requirements/qualification/requirements.txt",
} = {}) {
  const paths = Object.keys(before);
  const config = [
    "- package-ecosystem: pip",
    "  directories:",
    ...paths.map((path) => `    - /${path.split("/").slice(0, -1).join("/")}`),
    "  groups:",
    "    deployment-python:",
    "      group-by: dependency-name",
    "",
  ].join("\n");
  const fixture = updateFixture(
    "pip",
    config,
    [[path, before[path], before[path].replace(oldPin, after)]],
    [
      {
        dependencyName,
        newVersion: version,
        packageEcosystem: "pip",
        dependencyGroup: group,
        updateType: "version-update:semver-patch",
      },
    ],
    { PIP_PLAIN_MANIFEST_PATHS: JSON.stringify(paths) }
  );
  for (const manifest of paths) {
    if (manifest === path) continue;
    const unchanged = {
      sha: "c".repeat(40),
      content: Buffer.from(before[manifest]).toString("base64"),
    };
    fixture.manifests[manifest] = { [admissionBase]: unchanged, [admissionHead]: unchanged };
  }
  fixture.manifests[path][admissionBase].sha = "c".repeat(40);
  return fixture;
}

test("authenticates an exact Deployment pip update to an included canonical pin", async () => {
  for (const group of ["", "deployment-python"]) {
    assert.equal(await verifySource(deploymentPipChange({ group })), "version-update:semver-patch");
  }
});

test("Deployment pip qualifies stable two-component pins without confusing version aliases", async () => {
  const change = {
    path: "requirements/quality/requirements.txt",
    dependencyName: "boolean-py",
    oldPin: "boolean.py==5.0",
  };
  assert.equal(
    await verifySource(
      deploymentPipChange({
        ...change,
        version: "5.0.1",
        after: "boolean.py==5.0.1",
      })
    ),
    "version-update:semver-patch"
  );
  assert.equal(
    await verifySource(
      deploymentPipChange({
        ...change,
        version: "5.0.0",
        after: "boolean.py==5.0.0",
      })
    ),
    undefined
  );
});

test("Deployment pip classifies four-component stable patches without allowing downgrades", async () => {
  const change = {
    path: "requirements/build/requirements.txt",
    dependencyName: "shellcheck-py",
    oldPin: "shellcheck-py==0.11.0.1",
  };
  for (const version of ["0.11.0.2", "0.11.1", "0.11.1.0"]) {
    const fixture = deploymentPipChange({ ...change, version, after: `shellcheck-py==${version}` });
    assert.equal(await verifySource(fixture), "version-update:semver-patch");
  }
  for (const version of ["0.11.0", "0.11.0.0", "0.11.0.2.1", "0.11.0.2rc1"]) {
    const fixture = deploymentPipChange({ ...change, version, after: `shellcheck-py==${version}` });
    assert.equal(await verifySource(fixture), undefined);
  }
});

test("Deployment pip admission rejects changes beyond the single canonical stable pin", async () => {
  for (const change of [
    { group: "unaccepted" },
    { after: "PyYAML==6.0.4" },
    { after: "PyYAML==6.0.3rc1", version: "6.0.3rc1" },
    { after: "PyYAML==7.0.0", version: "7.0.0" },
    { after: "pyyaml==6.0.3" },
    { after: "PyYAML==6.0.3\n-r ../integration/requirements.txt" },
    { after: 'PyYAML==6.0.3; python_version < "3.13"' },
    {
      before: {
        ...deploymentPins,
        "requirements/build/requirements.txt": "py_yaml==6.0.2\npyyaml==6.0.2\n",
      },
    },
    {
      before: {
        ...deploymentPins,
        "requirements/schema/requirements.txt": "-r ../integration/requirements.txt\n",
      },
    },
    {
      before: {
        ...deploymentPins,
        "requirements/schema/requirements.txt": "-r ../other/requirements.txt\n",
      },
    },
  ]) {
    assert.equal(await verifySource(deploymentPipChange(change)), undefined);
  }
});

test("an independently verified one-package pip group is eligible", () => {
  assert.equal(
    eligible({
      PACKAGE_ECOSYSTEM: "pip",
      DEPENDENCY_GROUP: "deployment-python",
      SOURCE_UPDATE_TYPE: "version-update:semver-minor",
      UPDATE_TYPE_RAW: "version-update:semver-minor",
    }),
    "true"
  );
});

const wrapperPath = "android/gradle/wrapper/gradle-wrapper.properties";
const checksumBefore = "b".repeat(64);
const checksumAfter = "c".repeat(64);
const wrapper = (version, checksum) =>
  `distributionUrl=https\\://services.gradle.org/distributions/gradle-${version}-all.zip\n` +
  `distributionSha256Sum=${checksum}\nvalidateDistributionUrl=true\n`;

function gradleWrapper({ next = wrapper("9.9.2", checksumAfter), path = wrapperPath } = {}) {
  return updateFixture(
    "gradle",
    "- package-ecosystem: gradle\n  directory: /android\n",
    [[path, wrapper("9.9.1", checksumBefore), next]],
    [
      {
        dependencyName: "gradle-wrapper",
        newVersion: "9.9.2",
        packageEcosystem: "gradle",
        dependencyGroup: "",
        updateType: "version-update:semver-patch",
      },
    ],
    { GRADLE_WRAPPER_PATH: wrapperPath },
    {
      fetch: async (url, options) => {
        assert.equal(options.redirect, "error");
        const published = {
          "https://downloads.gradle.org/distributions/gradle-9.9.1-all.zip.sha256": checksumBefore,
          "https://downloads.gradle.org/distributions/gradle-9.9.2-all.zip.sha256": checksumAfter,
        }[url];
        assert.ok(published);
        return { ok: true, text: async () => published + "\n" };
      },
    }
  );
}

const sharedCaller = ".github/workflows/quality.yml";
const scannerAction = ".github/actions/trivy-repository-scan";
const scannerSources = [
  ["scripts/secpal-trivy-repository-scan.py", "93849ae528f9a43e24e24d6db9bca52bff1263a5"],
  ["policies/trivy-repository-scan-v1.json", "e735fd4c17d63d3ccdb4932c7eddae861cd4495d"],
  ["policies/trivy-repository-scan-ignore-v1.yaml", "2b0cecf85eaab8dcb8a4f7d0da5b7f776023ef6b"],
  ["policies/trivy-repository-secret-v1.yaml", "11600a6f598c88150e061b1e198b8cc4cbe97adf"],
];

function sharedPin({ dependency = scannerAction, alter = (data) => data, duplicateRef } = {}) {
  const full = `SecPal/.github/${dependency}`;
  const oldRef = "1".repeat(40),
    nextRef = "2".repeat(40);
  const isReusableWorkflow = dependency.startsWith(".github/workflows/");
  const content = (ref) =>
    `jobs:\n  quality:\n${isReusableWorkflow ? "    uses:" : "    steps:\n      - uses:"} ${full}@${ref} # main\n`;
  const oldTree = {
    truncated: false,
    tree: [
      {
        path: `${scannerAction}/action.yml`,
        sha: "f51119d1a316f9226df9f79dae76e0710118afbe",
        mode: "100644",
      },
      ...scannerSources.map(([path, sha]) => ({ path, sha, mode: "100644" })),
    ],
  };
  if (isReusableWorkflow) {
    const blob = spawnSync(
      "git",
      ["rev-parse", `618d818048480b4386cdf82a8cbbc5195351faf1:${dependency}`],
      { encoding: "utf8" }
    );
    assert.equal(blob.status, 0, blob.stderr);
    oldTree.tree = [{ path: dependency, sha: blob.stdout.trim(), mode: "100644" }];
  }
  const duplicate = duplicateRef ? `      - uses: ${full}@${duplicateRef} # main\n` : "";
  const nextTree = structuredClone(oldTree);
  nextTree.tree.push({ path: "docs/changelog.md", sha: "4".repeat(40), mode: "100644" });
  return updateFixture(
    "github_actions",
    "- package-ecosystem: github-actions\n  directory: /\n",
    [[sharedCaller, content(oldRef) + duplicate, alter(content(nextRef) + duplicate)]],
    [
      {
        dependencyName: full,
        newVersion: nextRef,
        prevVersion: oldRef,
        packageEcosystem: "github_actions",
        dependencyGroup: "",
      },
    ],
    { SHARED_SHA_WORKFLOW_PATHS: JSON.stringify([sharedCaller]) },
    {
      upstream: {
        branch: { name: "main", protected: true, commit: { sha: nextRef } },
        comparisons: {
          [`${oldRef}...${nextRef}`]: { status: "ahead", merge_base_commit: { sha: oldRef } },
        },
        trees: { [oldRef]: oldTree, [nextRef]: nextTree },
      },
    }
  );
}

test("a signed Android Gradle wrapper patch matches both official checksums", async () => {
  assert.equal(await verifySource(gradleWrapper()), "version-update:semver-patch");
});

test("Android wrapper admission rejects missing or incorrect checksums and out-of-scope edits", async () => {
  for (const change of [
    { next: wrapper("9.9.2", "") },
    { next: wrapper("9.9.2", checksumBefore) },
    { next: wrapper("9.9.2", checksumAfter).replace("true", "false") },
    { next: wrapper("9.9.2", checksumAfter).replace("services.gradle.org", "example.org") },
    { next: wrapper("9.9.2", checksumAfter) + `distributionSha256Sum=${checksumBefore}\n` },
    { path: "android/build.gradle" },
  ]) {
    assert.equal(await verifySource(gradleWrapper(change)), undefined);
  }
  assert.equal(
    await verifySource({ ...gradleWrapper(), fetch: async () => ({ ok: false }) }),
    undefined
  );
});

test("a signed immutable shared pin can advance across unrelated upstream changes", async () => {
  assert.equal(await verifySource(sharedPin()), "shared-sha-no-op");
  assert.equal(
    eligible({
      PACKAGE_ECOSYSTEM: "github_actions",
      SOURCE_UPDATE_TYPE: "shared-sha-no-op",
      UPDATE_TYPE_RAW: "shared-sha-no-op",
      DEPENDENCY_GROUP: "shared-workflow-pins",
    }),
    "true"
  );
});

for (const dependency of [
  ".github/workflows/reusable-check-conflict-markers.yml",
  ".github/workflows/reusable-pr-size.yml",
]) {
  test(`authenticates the reviewed ${dependency} blob and rejects a changed workflow`, async () => {
    const fixture = sharedPin({ dependency });
    assert.equal(await verifySource(fixture), "shared-sha-no-op");
    fixture.upstream.trees["2".repeat(40)].tree[0].sha = "7".repeat(40);
    assert.equal(await verifySource(fixture), undefined);
  });
}

test("a refreshed signed shared pin can retain an equivalent ancestor in its metadata", async () => {
  const fixture = sharedPin();
  const oldRef = "1".repeat(40);
  const newRef = "2".repeat(40);
  const retainedRef = "9".repeat(40);
  fixture.commits[0].commit.message = fixture.commits[0].commit.message.replace(
    newRef,
    retainedRef
  );
  const dependencies = JSON.parse(fixture.env.VERIFIED_DEPENDENCIES);
  dependencies[0].newVersion = retainedRef;
  fixture.env.VERIFIED_DEPENDENCIES = JSON.stringify(dependencies);
  fixture.upstream.trees[retainedRef] = structuredClone(fixture.upstream.trees[newRef]);
  fixture.upstream.comparisons[`${oldRef}...${retainedRef}`] = {
    status: "ahead",
    merge_base_commit: { sha: oldRef },
  };
  fixture.upstream.comparisons[`${retainedRef}...${newRef}`] = {
    status: "ahead",
    merge_base_commit: { sha: retainedRef },
  };
  assert.equal(await verifySource(fixture), "shared-sha-no-op");

  const unrelated = structuredClone(fixture);
  delete unrelated.upstream.comparisons[`${retainedRef}...${newRef}`];
  assert.equal(await verifySource(unrelated), undefined);
  fixture.upstream.trees[retainedRef].tree[1].sha = "6".repeat(40);
  assert.equal(await verifySource(fixture), undefined);
});

test("shared SHA admission rejects a stale duplicate use and permits an already-current one", async () => {
  assert.equal(await verifySource(sharedPin({ duplicateRef: "1".repeat(40) })), undefined);
  assert.equal(await verifySource(sharedPin({ duplicateRef: "2".repeat(40) })), "shared-sha-no-op");
});

test("shared SHA admission rejects transitive changes, missing ancestry, policy pins and extra caller edits", async () => {
  for (const fixture of [
    sharedPin({ dependency: ".github/workflows/reusable-dependabot-auto-merge.yml" }),
    sharedPin({ alter: (content) => content + "# Extra caller change\n" }),
    sharedPin({ alter: (content) => content.replace("# main", "# different") }),
    { ...sharedPin(), protectedHead: "5".repeat(40) },
  ]) {
    assert.equal(await verifySource(fixture), undefined);
  }
  for (const mutate of [
    (fixture) => {
      fixture.upstream.branch.protected = false;
    },
    (fixture) => {
      fixture.upstream.comparisons = {};
    },
    (fixture) => {
      fixture.upstream.trees["2".repeat(40)].tree[1].sha = "7".repeat(40);
    },
    (fixture) => {
      fixture.upstream.trees["2".repeat(40)].tree[0].mode = "120000";
    },
    (fixture) => {
      fixture.upstream.trees["2".repeat(40)].tree.push({
        path: `${scannerAction}/action.yaml`,
        sha: "8".repeat(40),
        mode: "100644",
      });
    },
    (fixture) => {
      fixture.env.SHARED_SHA_WORKFLOW_PATHS = "[]";
    },
    (fixture) => {
      fixture.env.WORKFLOW_PATHS = '[".github/workflows/local.yml"]';
    },
  ]) {
    const fixture = sharedPin();
    mutate(fixture);
    assert.equal(await verifySource(fixture), undefined);
  }
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
  assert.equal(
    caller.jobs["auto-merge"].with["allowed-ecosystems"],
    "github_actions,pre_commit,docker"
  );
  assert.equal(caller.jobs["auto-merge"].with["pre-commit-path"], ".pre-commit-config.yaml");
  assert.deepEqual(JSON.parse(caller.jobs["auto-merge"].with["shared-sha-workflow-paths"]), [
    ".github/workflows/daily-repository-security.yml",
    ".github/workflows/quality.yml",
  ]);
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
test("enrollment requires a successful protected safety check from this run and head", () => {
  const step = workflow.jobs["auto-merge"].steps.find((step) => step.name === "Enable auto-merge");
  const head = "a".repeat(40);
  const completed = {
    name: "auto-merge / Dependabot Source Safety",
    status: "COMPLETED",
    conclusion: "SUCCESS",
    detailsUrl: "https://github.com/SecPal/test/actions/runs/42/job/1",
    isRequired: true,
  };
  const otherRun = {
    ...completed,
    detailsUrl: "https://github.com/SecPal/test/actions/runs/41/job/1",
  };
  const page = (nodes, { headRefOid = head, oid = head } = {}) => ({
    data: {
      repository: {
        pullRequest: {
          headRefOid,
          commits: { nodes: [{ commit: { oid, statusCheckRollup: { contexts: { nodes } } } }] },
        },
      },
    },
  });

  for (const [pages, expected, lookupExit = 0] of [
    [[page([completed])], true],
    [[page([otherRun]), page([completed])], true],
    [[page([])], false],
    [[page([otherRun])], false],
    [[page([completed, completed])], false],
    [[page([{ ...completed, isRequired: false }])], false],
    [[page([{ ...completed, conclusion: "FAILURE" }])], false],
    [[page([{ ...completed, status: "IN_PROGRESS", conclusion: null }])], false],
    [[page([completed], { headRefOid: "b".repeat(40) })], false],
    [[page([completed], { oid: "b".repeat(40) })], false],
    [[page([completed])], false, 4],
  ]) {
    const dir = mkdtempSync(join(tmpdir(), "dependabot-enrollment-"));
    try {
      const record = join(dir, "merged");
      writeFileSync(
        join(dir, "gh"),
        [
          "#!/bin/sh",
          'case "$1:$2" in',
          "  api:graphql)",
          '    case " $* " in *" --slurp "*) ;; *) exit 2 ;; esac',
          '    case " $* " in',
          '      *" --paginate "*\'after: $endCursor\'*) printf "%s" "$CHECKS" ;;',
          '      *) printf "%s" "$FIRST_PAGE" ;;',
          "    esac",
          '    exit "$LOOKUP_EXIT" ;;',
          "  pr:checks) exit 4 ;;",
          '  pr:merge) printf "merge" > "$RECORD" ;;',
          "  *) exit 1 ;;",
          "esac",
        ].join("\n"),
        { mode: 0o700 }
      );
      const result = spawnSync("bash", ["-c", step.run.replace(/\$\{\{.*?\}\}/g, "fixture")], {
        env: {
          ...process.env,
          PATH: `${dir}:${process.env.PATH}`,
          CHECKS: JSON.stringify(pages),
          FIRST_PAGE: JSON.stringify(pages.slice(0, 1)),
          LOOKUP_EXIT: String(lookupExit),
          RECORD: record,
          GITHUB_SERVER_URL: "https://github.com",
          GITHUB_REPOSITORY: "SecPal/test",
          GITHUB_RUN_ID: "42",
          PR_URL: "https://github.com/SecPal/test/pull/1",
          PR_NUMBER: "1",
          MERGE_METHOD: "squash",
          EXPECTED_HEAD: head,
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

test("the required source-safety check blocks the verified policy rejection", async () => {
  const safety = workflow.jobs["source-safety"];
  assert.match(safety.steps[0].env.POLICY_REJECTION ?? "", /policy-rejection/);
  const script = safety.steps[0].with.script;
  const head = "a".repeat(40);
  const pr = {
    head: { sha: head },
    base: { ref: "main" },
    state: "open",
    user: { login: "dependabot[bot]" },
    labels: [{ name: "dependencies" }],
    auto_merge: null,
  };
  const policyRejection = "Docker image library/php uses a prerelease";
  const github = {
    rest: { pulls: { get: async () => ({ data: pr }) } },
    graphql: async () => assert.fail("a policy rejection does not close or edit the PR"),
  };
  const run = () =>
    new AsyncFunction("github", "context", script)(github, {
      repo: { owner: "SecPal", repo: "frontend" },
      payload: { pull_request: { number: 1, head: { sha: head } } },
    });
  process.env.POLICY_REJECTION = policyRejection;
  try {
    await assert.rejects(run(), new RegExp(policyRejection));
    pr.head.sha = "b".repeat(40);
    await assert.rejects(run(), /enrollment identity is unavailable or changed/);
  } finally {
    delete process.env.POLICY_REJECTION;
  }
});
