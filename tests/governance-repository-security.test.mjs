// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import * as yaml from "js-yaml";

const trusted = "e89bf9b04bd90bd29b6909994bb7431b56ce5aa2";
const actionDirectory = ".github/actions/trivy-repository-scan";
const workflow = yaml.load(readFileSync(".github/workflows/quality.yml", "utf8"));
const job = workflow.jobs["evidence-architecture"];
const scan = job.steps.find((step) => step.id === "repository-security");
const gate = job.steps.find((step) => step.name === "Require clean repository security");

test("the existing required gate scans the exact source before candidate tooling", () => {
  assert.equal(job.name, "Evidence Architecture PR Gate");
  assert.equal(job.if, undefined);
  assert.equal(job.needs, undefined);
  assert.deepEqual(workflow.permissions, { contents: "read" });
  assert.equal(scan?.uses, "SecPal/.github/" + actionDirectory + "@" + trusted);
  for (const key of ["with", "env", "if", "continue-on-error"]) assert.equal(scan[key], undefined);
  assert.equal(job.steps[0].with.ref, "${{ github.sha }}");
  assert.equal(job.steps[0].with["persist-credentials"], false);
  assert.equal(job.steps.indexOf(scan), 1);
  assert.equal(job.steps.indexOf(gate), 2);
  assert.equal(gate.if, undefined);
  assert.deepEqual(gate.env, {
    SCAN_OUTCOME: "${{ steps.repository-security.outcome }}",
    GATE_STATE: "${{ steps.repository-security.outputs.gate-state }}",
  });
});

test("only successful CLEAN execution admits the required gate", () => {
  for (const outcome of ["success", "failure", "cancelled", "skipped", ""]) {
    for (const state of [
      "CLEAN",
      "ACTIONABLE",
      "REVIEW_REQUIRED",
      "UNKNOWN_STALE",
      "",
      "CLEAN;true",
    ]) {
      const result = spawnSync(
        "bash",
        ["--noprofile", "--norc", "-eo", "pipefail", "-c", gate?.run ?? ""],
        {
          env: { ...process.env, SCAN_OUTCOME: outcome, GATE_STATE: state },
          encoding: "utf8",
        }
      );
      assert.equal(
        result.status === 0,
        outcome === "success" && state === "CLEAN",
        outcome + "/" + state
      );
      assert.equal(result.stdout + result.stderr, "");
    }
  }
});

test("a candidate scanner and policy cannot replace the accepted action runtime", () => {
  assert.equal(scan?.uses, "SecPal/.github/" + actionDirectory + "@" + trusted);
  const root = mkdtempSync(join(tmpdir(), "secpal-self-trust-"));
  const run = (command, args, options = {}) =>
    execFileSync(command, args, { encoding: "utf8", ...options });
  try {
    const accepted = join(root, "accepted");
    const candidate = join(root, "candidate");
    mkdirSync(accepted);
    mkdirSync(join(candidate, "scripts"), { recursive: true });
    mkdirSync(join(candidate, "policies"));
    const archive = execFileSync("git", ["archive", trusted], { maxBuffer: 16 * 1024 * 1024 });
    execFileSync("tar", ["-x", "-C", accepted], { input: archive });
    const sentinel = join(root, "candidate-executed");
    writeFileSync(
      join(candidate, "scripts/secpal-trivy-repository-scan.py"),
      "from pathlib import Path\nPath(" +
        JSON.stringify(sentinel) +
        ").touch()\nraise SystemExit(0)\n"
    );
    writeFileSync(
      join(candidate, "policies/trivy-repository-scan-v1.json"),
      '{"candidate":"untrusted"}\n'
    );
    run("git", ["init", "--quiet", candidate]);
    run("git", ["-C", candidate, "add", "."]);
    run("git", [
      "-C",
      candidate,
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "-c",
      "commit.gpgsign=false",
      "commit",
      "--quiet",
      "-m",
      "Untrusted scanner fixture",
    ]);
    const head = run("git", ["-C", candidate, "rev-parse", "HEAD"]).trim();
    const action = yaml.load(readFileSync(join(accepted, actionDirectory, "action.yml"), "utf8"));
    const step = action.runs.steps.find((item) => item.id === "scan");
    for (const [sha, expectedFailure] of [
      [head, "SCANNER_IDENTITY_FAILURE"],
      ["0".repeat(40), "TARGET_IDENTITY_FAILURE"],
    ]) {
      const runner = join(root, sha);
      mkdirSync(runner);
      const result = spawnSync(
        "bash",
        ["--noprofile", "--norc", "-eo", "pipefail", "-c", step.run],
        {
          cwd: candidate,
          env: {
            ...process.env,
            ...step.env,
            GITHUB_ACTION_PATH: join(accepted, actionDirectory),
            GITHUB_WORKSPACE: candidate,
            GITHUB_SHA: sha,
            GITHUB_REPOSITORY: "SecPal/.github",
            GITHUB_RUN_ID: "1",
            GITHUB_RUN_ATTEMPT: "1",
            RUNNER_OS: "unsupported-fixture",
            RUNNER_ARCH: "X64",
            RUNNER_TEMP: runner,
            GITHUB_OUTPUT: join(runner, "output"),
            GITHUB_STEP_SUMMARY: join(runner, "summary"),
          },
          encoding: "utf8",
        }
      );
      assert.equal(result.status, 0, result.stderr);
      const output = Object.fromEntries(
        readFileSync(join(runner, "output"), "utf8")
          .trim()
          .split("\n")
          .map((line) => {
            const index = line.indexOf("=");
            return [line.slice(0, index), line.slice(index + 1)];
          })
      );
      const evidence = JSON.parse(
        readFileSync(join(output["evidence-path"], "result.json"), "utf8")
      );
      assert.equal(evidence.gate_state, "UNKNOWN_STALE");
      assert.equal(evidence.operation.failure_code, expectedFailure);
      assert.equal(evidence.subject.commit, sha);
      assert.equal(existsSync(sentinel), false, "candidate evaluator executed");
      assert.doesNotMatch(JSON.stringify(evidence), /candidate-executed|untrusted/);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("pin provenance admits accepted governance code, not caller or third-party substitutes", () => {
  const reference = "SecPal/.github/" + actionDirectory + "@";
  for (const [pin, comment, accepted] of [
    [reference + trusted, "main", true],
    [reference + "f".repeat(40), "main", false],
    [reference + "main", "main", false],
    ["other/repository/" + actionDirectory + "@" + trusted, "main", false],
  ]) {
    const result = spawnSync(
      "bash",
      [
        "-c",
        'source tests/android-consumed-workflow-action-pins.sh; is_accepted_action_pin "$1" "$2"',
        "fixture",
        pin,
        comment,
      ],
      {
        env: {
          ...process.env,
          GITHUB_REPOSITORY: "SecPal/.github",
          VERIFY_ACTION_PIN_PROVENANCE: "true",
          SECPAL_BASE_REVISION: trusted,
        },
        encoding: "utf8",
      }
    );
    assert.equal(result.status === 0, accepted, pin);
  }
});
