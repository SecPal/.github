// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  parseCanonicalMajor,
  validateCompositeDocument,
  validateDocumentation,
  validateRepository,
  validateWorkflowDocument,
} from "../scripts/validate-node-baseline.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CANONICAL_MAJOR = parseCanonicalMajor(fs.readFileSync(path.join(ROOT, ".nvmrc"), "utf8"));
const CANONICAL_DIAGNOSTIC = new RegExp(`Node ${CANONICAL_MAJOR}`);

function directWorkflow(selector = `${CANONICAL_MAJOR}.x`) {
  return {
    on: { pull_request: {} },
    jobs: {
      validate: {
        steps: [
          {
            uses: "actions/setup-node@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            with: { "node-version": selector },
          },
          { run: "npm ci\nnode --test" },
        ],
      },
    },
  };
}

function reusableWorkflow(defaultSelector = String(CANONICAL_MAJOR)) {
  return {
    on: {
      workflow_call: {
        inputs: { "node-version": { default: defaultSelector } },
      },
    },
    jobs: {
      lint: {
        steps: [
          {
            uses: "actions/setup-node@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            with: { "node-version": "${{ inputs.node-version }}" },
          },
          { run: "npx markdownlint README.md" },
        ],
      },
    },
  };
}

test("active repository selectors and documentation agree with .nvmrc", () => {
  assert.deepEqual(validateRepository(ROOT), []);
});

test("workflow discovery is independent of job count and ordering", () => {
  const workflow = directWorkflow();
  workflow.jobs.additional = {
    steps: [
      {
        uses: "actions/setup-node@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        with: { "node-version": String(CANONICAL_MAJOR) },
      },
      { run: "npm test" },
    ],
  };
  workflow.jobs = {
    additional: workflow.jobs.additional,
    validate: workflow.jobs.validate,
  };
  assert.deepEqual(validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml"), []);
});

test("reusable workflow default rejects the historical major", () => {
  const errors = validateWorkflowDocument(reusableWorkflow("22"), CANONICAL_MAJOR, "fixture.yml");
  assert.match(errors.join("\n"), /default/);
  assert.match(errors.join("\n"), CANONICAL_DIAGNOSTIC);
});

test("direct setup rejects the historical major", () => {
  const errors = validateWorkflowDocument(directWorkflow("22.x"), CANONICAL_MAJOR, "fixture.yml");
  assert.match(errors.join("\n"), /setup step/);
  assert.match(errors.join("\n"), CANONICAL_DIAGNOSTIC);
});

test("Node execution requires an explicit qualified setup", () => {
  const workflow = directWorkflow();
  delete workflow.jobs.validate.steps[0].with["node-version"];
  assert.match(
    validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml").join("\n"),
    new RegExp(`must select Node ${CANONICAL_MAJOR}`)
  );

  workflow.jobs.validate.steps.shift();
  assert.match(
    validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml").join("\n"),
    /without an explicit Node setup step/
  );
});

test("input-driven Node commands require an explicit qualified setup", () => {
  const workflow = reusableWorkflow();
  workflow.on.workflow_call.inputs["install-command"] = { default: "npm ci" };
  workflow.jobs.lint.steps = [
    {
      env: { INSTALL_CMD: "${{ inputs.install-command }}" },
      run: "$INSTALL_CMD",
    },
  ];

  assert.match(
    validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml").join("\n"),
    /without an explicit Node setup step/
  );
});

test("Node setup must precede Node commands", () => {
  const workflow = directWorkflow();
  workflow.jobs.validate.steps.reverse();

  assert.match(
    validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml").join("\n"),
    /before its Node tooling command/
  );
});

test("local setup action may use its validated default selector", () => {
  const workflow = {
    jobs: {
      validate: {
        steps: [{ uses: "./.github/actions/setup-node-with-deps" }],
      },
    },
  };

  assert.deepEqual(
    validateWorkflowDocument(workflow, CANONICAL_MAJOR, "fixture.yml", {
      localSetupDefault: `${CANONICAL_MAJOR}.x`,
    }),
    []
  );
});

test("composite action default agrees with the canonical major", () => {
  const action = {
    inputs: { "node-version": { default: "22.x" } },
    runs: {
      steps: [
        {
          uses: "actions/setup-node@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          with: { "node-version": "${{ inputs.node-version }}" },
        },
      ],
    },
  };
  assert.match(
    validateCompositeDocument(action, CANONICAL_MAJOR, "action.yml").join("\n"),
    new RegExp(`default.*Node ${CANONICAL_MAJOR}`)
  );
});

test("composite action requires setup before installing Node dependencies", () => {
  const action = {
    inputs: { "node-version": { default: `${CANONICAL_MAJOR}.x` } },
    runs: { steps: [{ run: "npm ci" }] },
  };
  assert.match(
    validateCompositeDocument(action, CANONICAL_MAJOR, "action.yml").join("\n"),
    /without an explicit Node setup step/
  );

  action.runs.steps.push({
    uses: "actions/setup-node@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    with: { "node-version": "${{ inputs.node-version }}" },
  });
  assert.match(
    validateCompositeDocument(action, CANONICAL_MAJOR, "action.yml").join("\n"),
    /before its Node tooling command/
  );
});

test("active documentation must agree while historical evidence remains allowed", () => {
  assert.match(
    validateDocumentation("Install Node.js 22.x.", "README.md", CANONICAL_MAJOR).join("\n"),
    CANONICAL_DIAGNOSTIC
  );
  assert.deepEqual(
    validateDocumentation(
      "The project previously used Node.js 22.x.",
      "CHANGELOG.md",
      CANONICAL_MAJOR
    ),
    []
  );
  assert.deepEqual(
    validateDocumentation("Node.js 22 was observed.", "docs/audits/old.md", CANONICAL_MAJOR),
    []
  );
});
