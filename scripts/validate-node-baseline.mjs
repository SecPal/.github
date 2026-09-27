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

function resolveWorkflowInputs(value, workflow) {
  if (typeof value !== "string") return value;
  return value.replace(/\$\{\{\s*inputs\.([A-Za-z0-9_-]+)\s*}}/g, (expression, inputName) => {
    const defaultValue = workflow?.on?.workflow_call?.inputs?.[inputName]?.default;
    return defaultValue === undefined ? expression : String(defaultValue);
  });
}

function stepRunsNode(step, workflow, job) {
  if (typeof step?.run !== "string") return false;
  let command = resolveWorkflowInputs(step.run, workflow);
  const environment = { ...(workflow?.env ?? {}), ...(job?.env ?? {}), ...(step?.env ?? {}) };
  for (const [name, rawValue] of Object.entries(environment)) {
    const value = resolveWorkflowInputs(rawValue, workflow);
    if (typeof value !== "string") continue;
    command = command
      .replaceAll(`\${${name}}`, value)
      .replace(new RegExp(`\\$${name}(?![A-Za-z0-9_])`, "g"), value);
  }
  return NODE_COMMAND.test(command);
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

export function validateWorkflowDocument(
  workflow,
  canonicalMajor,
  source,
  { localSetupDefault } = {}
) {
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
    const setupIndexes = steps.flatMap((step, index) => (nodeSetupStep(step) ? [index] : []));
    const nodeCommandIndexes = steps.flatMap((step, index) =>
      stepRunsNode(step, workflow, job) ? [index] : []
    );

    if (nodeCommandIndexes.length > 0 && setupIndexes.length === 0) {
      errors.push(
        `${source} job ${jobName} executes Node tooling without an explicit Node setup step`
      );
    } else if (
      nodeCommandIndexes.some(
        (commandIndex) => !setupIndexes.some((setupIndex) => setupIndex < commandIndex)
      )
    ) {
      errors.push(`${source} job ${jobName} must set up Node before its Node tooling command`);
    }

    for (const setupIndex of setupIndexes) {
      const step = steps[setupIndex];
      const usesLocalDefault =
        step.uses === LOCAL_SETUP_ACTION && step?.with?.["node-version"] === undefined;
      const issue = selectorIssue(
        usesLocalDefault ? localSetupDefault : step?.with?.["node-version"],
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

  const steps = action?.runs?.steps ?? [];
  const setupIndexes = steps.flatMap((step, index) => (nodeSetupStep(step) ? [index] : []));
  const nodeCommandIndexes = steps.flatMap((step, index) =>
    stepRunsNode(step, action, action?.runs) ? [index] : []
  );

  if (nodeCommandIndexes.length > 0 && setupIndexes.length === 0) {
    errors.push(`${source} executes Node tooling without an explicit Node setup step`);
  } else if (
    nodeCommandIndexes.some(
      (commandIndex) => !setupIndexes.some((setupIndex) => setupIndex < commandIndex)
    )
  ) {
    errors.push(`${source} must set up Node before its Node tooling command`);
  }

  for (const [index, step] of steps.entries()) {
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
  const compositePath = ".github/actions/setup-node-with-deps/action.yml";
  const compositeAction = loadYaml(root, compositePath);
  const localSetupDefault = compositeAction?.inputs?.["node-version"]?.default;

  for (const relativePath of workflowFiles) {
    errors.push(
      ...validateWorkflowDocument(loadYaml(root, relativePath), canonicalMajor, relativePath, {
        localSetupDefault,
      })
    );
  }

  errors.push(...validateCompositeDocument(compositeAction, canonicalMajor, compositePath));

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
