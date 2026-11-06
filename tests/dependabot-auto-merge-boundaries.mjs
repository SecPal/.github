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
function eligible(overrides = {}) {
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
    )["should-auto-merge"];
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
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
    ...change.pr,
  };
  const commits = change.commits || [botCommit()];
  const files = change.files || [{ filename: "package.json" }, { filename: "package-lock.json" }];
  const output = {};
  let reads = 0;
  const github = {
    rest: {
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
        payload: { pull_request: { number: 1, head: { sha: head } } },
      },
      { setOutput: (key, value) => Object.assign(output, { [key]: value }) },
      createRequire(import.meta.url)
    );
    return output.verified;
  } finally {
    process.env = saved;
  }
}
test("authentic signed bot manifest update passes the source boundary", async () => {
  assert.equal(await verifySource(), "true");
});
for (const [name, change] of [
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
  ["directory traversal", { env: { DEPENDENCY_DIRECTORY: "/../" } }],
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
  for (const [eligible, owner, remains, expected, hasLabel = true] of [
    ["false", "github-actions[bot]", null, true],
    ["false", "aroviqen", "aroviqen", true],
    ["true", "github-actions[bot]", "github-actions[bot]", true],
    ["false", "github-actions[bot]", "github-actions[bot]", false],
    ["true", "github-actions[bot]", null, true, false],
  ]) {
    let mutations = 0;
    const request = (login) => (login ? { enabled_by: { login }, merge_method: "squash" } : null);
    const pr = {
      head: { sha: head },
      base: { ref: "main" },
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
        payload: { pull_request: { number: 1, head: { sha: head } } },
      });
    if (expected) await run();
    else await assert.rejects(run());
    assert.equal(
      mutations,
      (eligible !== "true" || !hasLabel) && owner === "github-actions[bot]" ? 1 : 0
    );
  }
  delete process.env.ELIGIBLE;
});

test("caller reconciles label, draft and target changes", () => {
  const caller = yaml.load(readFileSync(".github/workflows/dependabot-auto-merge.yml", "utf8"));
  for (const event of ["labeled", "unlabeled", "edited", "converted_to_draft"]) {
    assert.ok(caller.on.pull_request_target.types.includes(event), `missing ${event}`);
  }
});
test("enrollment requires a successful protected safety check from this same run", () => {
  const step = workflow.jobs["auto-merge"].steps.find((step) => step.name === "Enable auto-merge");
  for (const [checks, expected] of [
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
        payload: { pull_request: { number: 1, head: { sha: head } } },
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
