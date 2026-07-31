#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

"use strict";

const fs = require("node:fs");
const acorn = require("acorn");
const yaml = require("js-yaml");

function childNodes(node) {
  if (Array.isArray(node)) return node;
  if (!node || typeof node !== "object") return [];
  return Object.entries(node)
    .filter(
      ([key, value]) =>
        !["end", "loc", "range", "raw", "start"].includes(key) && value && typeof value === "object"
    )
    .map(([, value]) => value);
}

function mergeSets(...sets) {
  return new Set(sets.flatMap((value) => [...value]));
}

function collectFunctions(node, result = new Map()) {
  if (!node || typeof node !== "object") return result;
  if (node.type === "FunctionDeclaration" && node.id?.type === "Identifier") {
    result.set(node.id.name, node);
  } else if (
    node.type === "VariableDeclarator" &&
    node.id?.type === "Identifier" &&
    ["ArrowFunctionExpression", "FunctionExpression"].includes(node.init?.type)
  ) {
    result.set(node.id.name, node.init);
  }
  childNodes(node).forEach((child) => collectFunctions(child, result));
  return result;
}

function calledFunction(node, functions) {
  if (node?.type !== "CallExpression") return null;
  if (node.callee?.type === "Identifier" && functions.has(node.callee.name)) {
    return { key: node.callee.name, node: functions.get(node.callee.name) };
  }
  if (["ArrowFunctionExpression", "FunctionExpression"].includes(node.callee?.type)) {
    return { key: null, node: node.callee };
  }
  return null;
}

function calledFunctionIdentifiers(call, called, identifiers) {
  const result = new Set(identifiers);
  called.node.params?.forEach((parameter, index) => {
    if (parameter.type === "Identifier" && hasIdentifier(call.arguments[index], identifiers)) {
      result.add(parameter.name.toLowerCase());
    }
  });
  return result;
}

function memberName(node) {
  if (node?.type === "Identifier") return node.name;
  if (node?.type !== "MemberExpression") return null;
  const property = node.computed ? node.property?.value : memberName(node.property);
  const owner = memberName(node.object);
  return owner && typeof property === "string" ? `${owner}.${property}` : null;
}

function nonzeroStatus(node, emptyIsFailure) {
  if (node == null) return emptyIsFailure;
  if (node.type === "Literal") return ![0, false, null].includes(node.value);
  if (node.type === "UnaryExpression" && node.operator === "+") {
    return nonzeroStatus(node.argument, emptyIsFailure);
  }
  return true;
}

function failureKinds(node, functions, resolving = new Set()) {
  if (Array.isArray(node)) {
    return node.reduce(
      (result, item) => mergeSets(result, failureKinds(item, functions, resolving)),
      new Set()
    );
  }
  if (!node || typeof node !== "object") return new Set();
  if (["ArrowFunctionExpression", "FunctionDeclaration", "FunctionExpression"].includes(node.type))
    return new Set();
  if (node.type === "TryStatement") {
    const failures = failureKinds(node.block, functions, resolving);
    const caughtThrow = failures.delete("throw");
    return mergeSets(
      failures,
      caughtThrow && node.handler ? failureKinds(node.handler, functions, resolving) : new Set(),
      failureKinds(node.finalizer, functions, resolving)
    );
  }
  if (node.type === "ThrowStatement") return new Set(["throw"]);
  if (
    node.type === "CallExpression" &&
    ["process.exit", "Deno.exit", "Bun.exit"].includes(memberName(node.callee)) &&
    nonzeroStatus(node.arguments[0], true)
  )
    return new Set(["process"]);
  if (node.type === "CallExpression" && memberName(node.callee) === "core.setFailed") {
    return new Set(["process"]);
  }
  const called = calledFunction(node, functions);
  if (called && (called.key == null || !resolving.has(called.key))) {
    const nested = called.key == null ? resolving : new Set(resolving).add(called.key);
    return mergeSets(
      failureKinds(called.node.body, functions, nested),
      failureKinds(node.arguments, functions, resolving)
    );
  }
  if (
    node.type === "AssignmentExpression" &&
    memberName(node.left) === "process.exitCode" &&
    nonzeroStatus(node.right, false)
  )
    return new Set(["process"]);
  return failureKinds(childNodes(node), functions, resolving);
}

function hasIdentifier(node, identifiers) {
  if (node?.type === "Identifier" && identifiers.has(node.name.toLowerCase())) return true;
  return childNodes(node).some((child) => hasIdentifier(child, identifiers));
}

function hasSizeComparison(node, identifiers) {
  if (
    ["BinaryExpression", "LogicalExpression"].includes(node?.type) &&
    [">", ">=", "<", "<="].includes(node.operator) &&
    hasIdentifier(node, identifiers)
  ) {
    return true;
  }
  return childNodes(node).some((child) => hasSizeComparison(child, identifiers));
}

function resolveThrow(failures, onThrow) {
  return mergeSets(
    failures.has("process") ? new Set(["process"]) : new Set(),
    failures.has("throw") ? onThrow : new Set()
  );
}

function hardSizeExit(
  node,
  identifiers,
  functions,
  onThrow = new Set(["throw"]),
  resolving = new Set()
) {
  if (!node || typeof node !== "object") return false;
  if (
    ["ArrowFunctionExpression", "FunctionDeclaration", "FunctionExpression"].includes(node.type)
  ) {
    return false;
  }
  if (node.type === "TryStatement") {
    const blockFailures = failureKinds(node.block, functions, resolving);
    const handlerThrow = node.handler
      ? resolveThrow(failureKinds(node.handler, functions, resolving), onThrow)
      : onThrow;
    return (
      hardSizeExit(node.block, identifiers, functions, handlerThrow, resolving) ||
      (blockFailures.has("throw") &&
        hardSizeExit(node.handler, identifiers, functions, onThrow, resolving)) ||
      hardSizeExit(node.finalizer, identifiers, functions, onThrow, resolving)
    );
  }
  if (node.type === "IfStatement" && hasSizeComparison(node.test, identifiers)) {
    if (
      resolveThrow(failureKinds([node.consequent, node.alternate], functions, resolving), onThrow)
        .size > 0
    ) {
      return true;
    }
  }
  const called = calledFunction(node, functions);
  if (called && (called.key == null || !resolving.has(called.key))) {
    const nested = called.key == null ? resolving : new Set(resolving).add(called.key);
    const nestedIdentifiers = calledFunctionIdentifiers(node, called, identifiers);
    if (hardSizeExit(called.node.body, nestedIdentifiers, functions, onThrow, nested)) {
      return true;
    }
  }
  return childNodes(node).some((child) =>
    hardSizeExit(child, identifiers, functions, onThrow, resolving)
  );
}

function javascriptAnalysis(input) {
  const { identifiers: values, source } = JSON.parse(input);
  if (
    !Array.isArray(values) ||
    !values.every((value) => typeof value === "string") ||
    typeof source !== "string"
  )
    throw new Error("invalid JavaScript analysis input");
  const comments = [];
  const tree = acorn.parse(source, {
    allowHashBang: true,
    ecmaVersion: "latest",
    onComment: comments,
    sourceType: "module",
  });
  const executable = source.split("");
  for (const comment of comments) {
    for (let index = comment.start; index < comment.end; index += 1) {
      if (!["\n", "\r"].includes(executable[index])) executable[index] = " ";
    }
  }
  const identifiers = new Set(values);
  const functions = collectFunctions(tree);
  return {
    executableSource: executable.join(""),
    hardSizeExit: hardSizeExit(tree, identifiers, functions),
    processFailure: failureKinds(tree, functions).size > 0,
  };
}

function mapping(value, description, optional = false) {
  if ((value == null || value === "") && optional) return {};
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${description} must be a mapping`);
  }
  return value;
}

function runnerLanguage(shellValue) {
  const shell = typeof shellValue === "string" ? shellValue.trim().toLowerCase() : "bash";
  const executable = (shell.split(/\s+/u)[0] ?? "").split("/").at(-1);
  if (executable.startsWith("python")) return "python";
  if (["node", "deno", "bun"].includes(executable)) return "javascript";
  if (/^(?:ba|da|k|z)?sh$/u.test(executable)) return "shell";
  return "unknown";
}

function condition(value) {
  if (value == null) return [];
  if (!["string", "number", "boolean"].includes(typeof value)) {
    throw new Error("workflow if conditions must be scalar values");
  }
  return [String(value)];
}

function defaultShell(scope, fallback = null) {
  return (
    mapping(mapping(scope.defaults, "workflow defaults", true).run, "workflow run defaults", true)
      .shell ?? fallback
  );
}

function runUnits(
  steps,
  conditions = [],
  blocking = true,
  inheritedShell = null,
  permissions = [],
  jobId = null
) {
  if (steps == null) return [];
  if (!Array.isArray(steps)) throw new Error("policy steps must be a sequence");
  return steps.flatMap((value) => {
    const step = mapping(value, "policy step");
    if (step.run == null && step.uses == null) return [];
    if (step.run != null && typeof step.run !== "string") {
      throw new Error("policy run commands must be strings");
    }
    if (step.uses != null && typeof step.uses !== "string") {
      throw new Error("workflow action references must be strings");
    }
    const withValues = mapping(step.with, "workflow action inputs", true);
    const actionScript = withValues.script ?? null;
    if (actionScript != null && typeof actionScript !== "string") {
      throw new Error("workflow action scripts must be strings");
    }
    return [
      {
        actionScript,
        blocking: blocking && step["continue-on-error"] !== true,
        conditions: [...conditions, ...condition(step.if)],
        language: runnerLanguage(step.shell ?? inheritedShell),
        lines: step.run?.split(/\r?\n/u) ?? [],
        jobId,
        permissions,
        uses: step.uses ?? null,
      },
    ];
  });
}

function permissionNames(value) {
  if (value == null || value === "") return [];
  if (typeof value === "string") {
    if (["read-all", "write-all"].includes(value)) return ["pull-requests"];
    throw new Error("workflow permission shorthand is invalid");
  }
  return Object.entries(mapping(value, "workflow permissions")).flatMap(([name, access]) => {
    if (!["read", "write", "none"].includes(access)) {
      throw new Error("workflow permission access must be read, write, or none");
    }
    return access === "none" ? [] : [name];
  });
}

function workflowDocument(document) {
  const root = mapping(document, "workflow document", true);
  const jobs = mapping(root.jobs, "workflow jobs", true);
  const workflowShell = defaultShell(root);
  const rootPermissions = permissionNames(root.permissions);
  const permissions = new Set();
  const units = Object.entries(jobs).flatMap(([jobId, value]) => {
    const job = mapping(value, "workflow job");
    const jobPermissions =
      job.permissions == null ? rootPermissions : permissionNames(job.permissions);
    jobPermissions.forEach((permission) => permissions.add(permission));
    const conditions = condition(job.if);
    const blocking = job["continue-on-error"] !== true;
    const result = runUnits(
      job.steps,
      conditions,
      blocking,
      defaultShell(job, workflowShell),
      jobPermissions,
      jobId
    );
    if (job.uses != null) {
      if (typeof job.uses !== "string")
        throw new Error("reusable workflow references must be strings");
      result.unshift({
        actionScript: null,
        blocking,
        conditions,
        jobId,
        language: "unknown",
        lines: [],
        permissions: jobPermissions,
        uses: job.uses,
      });
    }
    return result;
  });
  const on = root.on && typeof root.on === "object" && !Array.isArray(root.on) ? root.on : {};
  const workflowCall = mapping(on.workflow_call, "workflow_call trigger", true);
  const inputs = mapping(workflowCall.inputs, "workflow inputs", true);
  const maxLines = mapping(inputs["max-lines"], "max-lines input", true);
  if (maxLines.description != null && typeof maxLines.description !== "string") {
    throw new Error("max-lines description must be a string");
  }
  return {
    metadata: { maxLinesDescription: maxLines.description ?? null, permissions: [...permissions] },
    units,
  };
}

function actionDocument(document) {
  const runs = mapping(mapping(document, "action document", true).runs, "action runs", true);
  return { metadata: {}, units: runs.using === "composite" ? runUnits(runs.steps) : [] };
}

function preCommitDocument(document) {
  const repositories = mapping(document, "pre-commit document").repos;
  if (!Array.isArray(repositories)) throw new Error("pre-commit repositories must be a sequence");
  const units = repositories.flatMap((value) => {
    const hooks = mapping(value, "pre-commit repository").hooks;
    if (hooks == null) return [];
    if (!Array.isArray(hooks)) throw new Error("pre-commit hooks must be a sequence");
    return hooks.flatMap((hookValue) => {
      const entry = mapping(hookValue, "pre-commit hook").entry;
      if (entry == null) return [];
      if (typeof entry !== "string") throw new Error("pre-commit hook entries must be strings");
      return [
        {
          actionScript: null,
          blocking: true,
          conditions: [],
          jobId: null,
          language: runnerLanguage(entry),
          lines: [entry],
          permissions: [],
          uses: null,
        },
      ];
    });
  });
  return { metadata: {}, units };
}

try {
  const source = fs.readFileSync(0, "utf8");
  const kind = process.argv[2];
  const parsers = {
    action: actionDocument,
    "pre-commit": preCommitDocument,
    workflow: workflowDocument,
  };
  const result =
    kind === "javascript"
      ? javascriptAnalysis(source)
      : parsers[kind]?.(yaml.load(source, { schema: yaml.JSON_SCHEMA }) ?? null);
  if (!result) throw new Error(`unknown policy syntax: ${kind}`);
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`Unable to parse PR-size policy: ${message}\n`);
  process.exitCode = 1;
}
