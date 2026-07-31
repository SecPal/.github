#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

"use strict";

const fs = require("node:fs");
const yaml = require("js-yaml");

function runnerLanguage(shellValue) {
  const shell = typeof shellValue === "string" ? shellValue.trim().toLowerCase() : "bash";
  const [executable = ""] = shell.split(/\s+/u);
  if (executable.startsWith("python")) {
    return "python";
  }
  if (["node", "deno", "bun"].includes(executable)) {
    return "javascript";
  }
  if (/(?:^|\/)(?:ba|da|k|z)?sh$/u.test(executable)) {
    return "shell";
  }
  return "unknown";
}

function condition(value) {
  if (value === undefined || value === null) {
    return [];
  }
  if (!["string", "number", "boolean"].includes(typeof value)) {
    throw new Error("workflow if conditions must be scalar values");
  }
  return [String(value)];
}

function runUnits(steps, inheritedConditions = [], inheritedBlocking = true) {
  if (steps === undefined) {
    return [];
  }
  if (!Array.isArray(steps)) {
    throw new Error("policy steps must be a sequence");
  }

  const units = [];
  for (const step of steps) {
    if (typeof step !== "object" || step === null || Array.isArray(step)) {
      throw new Error("policy steps must be mappings");
    }
    if (step.run === undefined) {
      continue;
    }
    if (typeof step.run !== "string") {
      throw new Error("policy run commands must be strings");
    }
    units.push({
      language: runnerLanguage(step.shell),
      lines: step.run.split(/\r?\n/u),
      blocking: inheritedBlocking && step["continue-on-error"] !== true,
      conditions: [...inheritedConditions, ...condition(step.if)],
    });
  }
  return units;
}

function workflowUnits(document) {
  if (document === undefined || document === null) {
    return [];
  }
  if (typeof document !== "object" || Array.isArray(document)) {
    throw new Error("workflow document must be a mapping");
  }
  if (document.jobs === undefined) {
    return [];
  }
  if (typeof document.jobs !== "object" || document.jobs === null || Array.isArray(document.jobs)) {
    throw new Error("workflow jobs must be a mapping");
  }

  const units = [];
  for (const job of Object.values(document.jobs)) {
    if (typeof job !== "object" || job === null || Array.isArray(job)) {
      throw new Error("workflow jobs must be mappings");
    }
    const jobConditions = condition(job.if);
    const jobBlocking = job["continue-on-error"] !== true;
    units.push(...runUnits(job.steps, jobConditions, jobBlocking));
  }
  return units;
}

function actionUnits(document) {
  if (document === undefined || document === null) {
    return [];
  }
  if (typeof document !== "object" || Array.isArray(document)) {
    throw new Error("action document must be a mapping");
  }
  if (document.runs === undefined) {
    return [];
  }
  if (typeof document.runs !== "object" || document.runs === null || Array.isArray(document.runs)) {
    throw new Error("action runs must be a mapping");
  }
  if (document.runs.using !== "composite") {
    return [];
  }
  return runUnits(document.runs.steps);
}

function preCommitUnits(document) {
  if (document === undefined || document === null) {
    return [];
  }
  if (typeof document !== "object" || Array.isArray(document) || !Array.isArray(document.repos)) {
    throw new Error("pre-commit document must contain a repository sequence");
  }

  const units = [];
  for (const repository of document.repos) {
    if (typeof repository !== "object" || repository === null || Array.isArray(repository)) {
      throw new Error("pre-commit repositories must be mappings");
    }
    if (!Array.isArray(repository.hooks)) {
      continue;
    }
    for (const hook of repository.hooks) {
      if (typeof hook !== "object" || hook === null || Array.isArray(hook)) {
        throw new Error("pre-commit hooks must be mappings");
      }
      if (hook.entry === undefined) {
        continue;
      }
      if (typeof hook.entry !== "string") {
        throw new Error("pre-commit hook entries must be strings");
      }
      units.push({
        language: runnerLanguage(hook.entry),
        lines: [hook.entry],
        blocking: true,
        conditions: [],
      });
    }
  }
  return units;
}

try {
  const source = fs.readFileSync(0, "utf8");
  const document = yaml.load(source, { schema: yaml.JSON_SCHEMA });
  const parsers = {
    action: actionUnits,
    "pre-commit": preCommitUnits,
    workflow: workflowUnits,
  };
  const kind = process.argv[2] ?? "workflow";
  if (!(kind in parsers)) {
    throw new Error(`unknown policy document kind: ${kind}`);
  }
  process.stdout.write(`${JSON.stringify(parsers[kind](document))}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`Unable to parse workflow policy: ${message}\n`);
  process.exitCode = 1;
}
