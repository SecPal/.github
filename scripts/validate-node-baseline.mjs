// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import * as yaml from "js-yaml";

const SETUP_NODE_PREFIX = "actions/setup-node@";
const LOCAL_SETUP_ACTION = "./.github/actions/setup-node-with-deps";
const NODE_COMMAND = /(?:^|[;&|()\s])(?:node|npm|npx|pnpm|yarn)(?=$|\s)/m;
const NODE_DOCUMENTATION_SELECTORS = [
  /\bnode(?:\.js)?(?:\*\*)?[^\n]{0,40}?\bv?(\d+)(?:\.x)?\b/gi,
  /node-version:\s*["']?(\d+)(?:\.x)?/gi,
];

export function parseCanonicalMajor(contents) {
  const value = contents.trim();
  const match = /^(\d+)$/.exec(value);
  if (!match) {
    throw new Error(`.nvmrc must contain one major version, found ${JSON.stringify(value)}`);
  }
  return Number(match[1]);
}

function selectorMajor(selector) {
  const match = /^(\d+)(?:\.x|(?:\.\d+){1,2})?$/.exec(String(selector));
  return match ? Number(match[1]) : null;
}

function workflowCallNodeDefault(workflow) {
  return workflow?.on?.workflow_call?.inputs?.["node-version"]?.default;
}

function selectorIssue(selector, canonicalMajor, location, workflow) {
  if (selector === undefined || selector === null || selector === "") {
    return `${location} must select Node ${canonicalMajor}`;
  }

  if (String(selector).trim() === "${{ inputs.node-version }}") {
    const defaultSelector = workflowCallNodeDefault(workflow);
    if (defaultSelector === undefined) {
      return `${location} references inputs.node-version without a reusable-workflow default`;
    }
    return selectorIssue(defaultSelector, canonicalMajor, `${location} reusable default`, workflow);
  }

  const major = selectorMajor(selector);
  if (major !== canonicalMajor) {
    return `${location} selects ${JSON.stringify(selector)} instead of Node ${canonicalMajor}`;
  }
  return null;
}

function nodeSetupStep(step) {
  const uses = String(step?.uses ?? "");
  return uses.startsWith(SETUP_NODE_PREFIX) || uses === LOCAL_SETUP_ACTION;
}

export function validateWorkflowDocument(workflow, canonicalMajor, source) {
  const errors = [];
  const reusableDefault = workflowCallNodeDefault(workflow);
  if (reusableDefault !== undefined) {
    const issue = selectorIssue(
      reusableDefault,
      canonicalMajor,
      `${source} workflow_call.inputs.node-version.default`,
      workflow
    );
    if (issue) errors.push(issue);
  }

  for (const [jobName, job] of Object.entries(workflow?.jobs ?? {})) {
    const steps = Array.isArray(job?.steps) ? job.steps : [];
    const setupSteps = steps.filter(nodeSetupStep);
    const runsNode = steps.some(
      (step) => typeof step?.run === "string" && NODE_COMMAND.test(step.run)
    );

    if (runsNode && setupSteps.length === 0) {
      errors.push(
        `${source} job ${jobName} executes Node tooling without an explicit Node setup step`
      );
    }

    for (const step of setupSteps) {
      const issue = selectorIssue(
        step?.with?.["node-version"],
        canonicalMajor,
        `${source} job ${jobName} setup step`,
        workflow
      );
      if (issue) errors.push(issue);
    }
  }
  return errors;
}

export function validateCompositeDocument(action, canonicalMajor, source) {
  const errors = [];
  const defaultSelector = action?.inputs?.["node-version"]?.default;
  const defaultIssue = selectorIssue(
    defaultSelector,
    canonicalMajor,
    `${source} inputs.node-version.default`,
    action
  );
  if (defaultIssue) errors.push(defaultIssue);

  for (const [index, step] of (action?.runs?.steps ?? []).entries()) {
    if (!nodeSetupStep(step)) continue;
    const selector = step?.with?.["node-version"];
    if (String(selector).trim() !== "${{ inputs.node-version }}") {
      errors.push(`${source} setup step ${index + 1} must use inputs.node-version`);
    }
  }
  return errors;
}

export function validateDocumentation(contents, source, canonicalMajor) {
  if (source === "CHANGELOG.md" || source.startsWith("docs/audits/")) return [];
  const selectedMajors = new Set(
    NODE_DOCUMENTATION_SELECTORS.flatMap((pattern) =>
      [...contents.matchAll(pattern)].map((match) => Number(match[1]))
    )
  );
  return [...selectedMajors]
    .filter((major) => major !== canonicalMajor)
    .map(
      (major) =>
        `${source} prescribes Node ${major} instead of the canonical Node ${canonicalMajor} baseline`
    );
}

function filesUnder(root, relativeDirectory, extensions) {
  const directory = path.join(root, relativeDirectory);
  if (!fs.existsSync(directory)) return [];
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const relative = path.join(relativeDirectory, entry.name);
    if (entry.isDirectory()) return filesUnder(root, relative, extensions);
    return extensions.has(path.extname(entry.name)) ? [relative] : [];
  });
}

function loadYaml(root, relativePath) {
  return yaml.load(fs.readFileSync(path.join(root, relativePath), "utf8"), {
    schema: yaml.JSON_SCHEMA,
  });
}

export function validateRepository(root) {
  const canonicalMajor = parseCanonicalMajor(fs.readFileSync(path.join(root, ".nvmrc"), "utf8"));
  const errors = [];
  const workflowFiles = filesUnder(root, ".github/workflows", new Set([".yml", ".yaml"]));

  for (const relativePath of workflowFiles) {
    errors.push(
      ...validateWorkflowDocument(loadYaml(root, relativePath), canonicalMajor, relativePath)
    );
  }

  const compositePath = ".github/actions/setup-node-with-deps/action.yml";
  errors.push(
    ...validateCompositeDocument(loadYaml(root, compositePath), canonicalMajor, compositePath)
  );

  const documentationFiles = [
    "README.md",
    "CONTRIBUTING.md",
    "scripts/README.md",
    ".github/workflows/README.md",
    ...filesUnder(root, "docs/scripts", new Set([".md"])),
    ...filesUnder(root, "docs/workflows", new Set([".md"])),
    ...filesUnder(root, ".github/ISSUE_TEMPLATE", new Set([".yml", ".yaml", ".md"])),
  ];
  for (const relativePath of new Set(documentationFiles)) {
    errors.push(
      ...validateDocumentation(
        fs.readFileSync(path.join(root, relativePath), "utf8"),
        relativePath,
        canonicalMajor
      )
    );
  }
  return errors;
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? ".");
  const errors = validateRepository(root);
  if (errors.length > 0) {
    for (const error of errors) console.error(`node-baseline: ${error}`);
    process.exit(1);
  }
  console.log("Node baseline governance is coherent.");
}
