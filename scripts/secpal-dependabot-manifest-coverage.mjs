#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, lstatSync, openSync, readSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import * as yaml from "js-yaml";
import { parse as parseToml } from "smol-toml";

const SCRIPT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_POLICY = path.join(SCRIPT_ROOT, "policies", "dependabot-manifest-catalog-v1.json");
const DEFAULT_CONFIG = ".github/dependabot.yml";
const DEFAULT_EXCEPTIONS = ".github/dependabot-manifest-exceptions.yml";
const TOP_LEVEL_KEYS = new Set([
  "enable-beta-ecosystems",
  "multi-ecosystem-groups",
  "registries",
  "updates",
  "version",
]);
const UPDATE_KEYS = new Set([
  "allow",
  "assignees",
  "commit-message",
  "cooldown",
  "directories",
  "directory",
  "exclude-paths",
  "groups",
  "ignore",
  "insecure-external-code-execution",
  "labels",
  "milestone",
  "multi-ecosystem-group",
  "open-pull-requests-limit",
  "package-ecosystem",
  "patterns",
  "pull-request-branch-name",
  "rebase-strategy",
  "registries",
  "schedule",
  "target-branch",
  "vendor",
  "versioning-strategy",
]);
const SCHEDULE_KEYS = new Set(["cronjob", "day", "interval", "time", "timezone"]);
const EXCEPTION_KEYS = new Set(["ecosystem", "manifest", "reason", "reviewed-by", "reviewed-on"]);
const CLASSIFICATION_KEYS = new Set([
  "directory",
  "ecosystem",
  "reason",
  "reviewed-by",
  "reviewed-on",
]);
const REVIEW_KEYS = new Set(["reason", "reviewed-by", "reviewed-on"]);
const POLICY_KEYS = new Set([
  "behavior_provenance",
  "candidate_rules",
  "discovery_dispositions",
  "expires_on",
  "manifest_rules",
  "non_manifest_rules",
  "policy_version",
  "reviewed_on",
  "schema",
  "supported_config_ecosystems",
  "upstream",
]);
const MANIFEST_RULE_KEYS = new Set([
  "case_insensitive",
  "companion",
  "content_kind",
  "coverage_directory",
  "ecosystem",
  "id",
  "ownership",
  "path_regex",
  "source_paths",
]);
const CANDIDATE_RULE_KEYS = new Set([
  "authority",
  "case_insensitive",
  "id",
  "path_regex",
  "source_paths",
]);
const NON_MANIFEST_RULE_KEYS = new Set([
  "authority",
  "candidate_rule",
  "case_insensitive",
  "content_kind",
  "id",
  "justification",
  "path_regex",
]);
const DISCOVERY_DISPOSITION_KEYS = new Set(["justification", "mode", "source_paths"]);
const UPSTREAM_KEYS = new Set([
  "dependabot_core_commit",
  "dependabot_core_repository",
  "dependabot_core_source_paths",
  "github_ecosystems_reference",
  "github_options_reference",
]);
const SCHEDULE_INTERVALS = new Set([
  "cron",
  "daily",
  "monthly",
  "quarterly",
  "semiannually",
  "weekly",
  "yearly",
]);

class ContractError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

function parseArguments(argv) {
  const [assertion, ...rest] = argv;
  if (!new Set(["coverage", "cadence"]).has(assertion)) {
    throw new ContractError("INVALID_ARGUMENT", "first argument must be coverage or cadence");
  }
  const options = {
    assertion,
    asOf: new Date().toISOString().slice(0, 10),
    config: DEFAULT_CONFIG,
    defaultBranch: process.env.GITHUB_DEFAULT_BRANCH || null,
    exceptions: DEFAULT_EXCEPTIONS,
    format: "text",
    policy: DEFAULT_POLICY,
    repository: process.env.GITHUB_REPOSITORY || "local/repository",
    root: process.cwd(),
    trustedPolicyRoot: null,
  };
  const names = new Map([
    ["--as-of", "asOf"],
    ["--config", "config"],
    ["--default-branch", "defaultBranch"],
    ["--exceptions", "exceptions"],
    ["--format", "format"],
    ["--policy", "policy"],
    ["--repository", "repository"],
    ["--root", "root"],
    ["--trusted-policy-root", "trustedPolicyRoot"],
  ]);
  for (let index = 0; index < rest.length; index += 2) {
    const name = names.get(rest[index]);
    if (!name || rest[index + 1] === undefined) {
      throw new ContractError("INVALID_ARGUMENT", `invalid argument ${rest[index]}`);
    }
    options[name] = rest[index + 1];
  }
  if (!new Set(["json", "text"]).has(options.format)) {
    throw new ContractError("INVALID_ARGUMENT", "format must be json or text");
  }
  parseDate(options.asOf, "as-of", "INVALID_ARGUMENT");
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(options.repository)) {
    throw new ContractError("INVALID_ARGUMENT", "repository must be owner/name");
  }
  options.config = normalizeManifest(options.config, "config path");
  options.exceptions = normalizeManifest(options.exceptions, "exceptions path");
  options.root = path.resolve(options.root);
  if (options.trustedPolicyRoot)
    options.trustedPolicyRoot = path.resolve(options.trustedPolicyRoot);
  if (options.defaultBranch !== null && !/^[A-Za-z0-9._/-]+$/.test(options.defaultBranch))
    throw new ContractError("INVALID_ARGUMENT", "default-branch is invalid");
  return options;
}

function parseDate(value, label, code = "SCHEMA_ERROR") {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    throw new ContractError(code, `${label} must be a real YYYY-MM-DD date`);
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value)
    throw new ContractError(code, `${label} must be a real YYYY-MM-DD date`);
  return value;
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ContractError("SCHEMA_ERROR", `${label} must be a mapping`);
  }
  return value;
}

function closedKeys(value, allowed, label) {
  const unknown = Object.keys(value)
    .filter((key) => !allowed.has(key))
    .sort();
  if (unknown.length) {
    throw new ContractError(
      "SCHEMA_ERROR",
      `${label} contains unknown keys: ${unknown.join(", ")}`
    );
  }
}

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function readSecureRegularFile(
  absolute,
  label,
  maximumBytes,
  { optional = false, code = "FILE_ERROR" } = {}
) {
  let descriptor;
  try {
    descriptor = openSync(
      absolute,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK
    );
  } catch (error) {
    if (optional && error.code === "ENOENT") return null;
    throw new ContractError(code, `cannot read ${label}: ${error.message}`);
  }

  try {
    const stat = fstatSync(descriptor);
    if (!stat.isFile()) throw new ContractError(code, `${label} must be a regular file`);
    if (stat.size > maximumBytes)
      throw new ContractError(code, `${label} exceeds ${maximumBytes} bytes`);

    const chunks = [];
    let total = 0;
    while (true) {
      const chunk = Buffer.allocUnsafe(Math.min(64 * 1024, maximumBytes - total + 1));
      const length = readSync(descriptor, chunk, 0, chunk.length, null);
      if (length === 0) break;
      total += length;
      if (total > maximumBytes)
        throw new ContractError(code, `${label} exceeds ${maximumBytes} bytes`);
      chunks.push(chunk.subarray(0, length));
    }
    return Buffer.concat(chunks, total);
  } catch (error) {
    if (error instanceof ContractError) throw error;
    throw new ContractError(code, `cannot read ${label}: ${error.message}`);
  } finally {
    try {
      closeSync(descriptor);
    } catch (error) {
      throw new ContractError(code, `cannot close ${label}: ${error.message}`);
    }
  }
}

function yamlFile(root, relative, required = false) {
  const absolute = path.join(root, relative);
  const bytes = readSecureRegularFile(absolute, relative, 1024 * 1024, {
    optional: !required,
  });
  if (bytes === null) return null;
  const source = bytes.toString("utf8");
  try {
    return yaml.load(source, {
      filename: relative,
      json: false,
      schema: yaml.JSON_SCHEMA,
    });
  } catch (error) {
    throw new ContractError("MALFORMED_YAML", `${relative}: ${error.message}`);
  }
}

function normalizeManifest(value, label = "manifest path", allowLiteralGlobCharacters = false) {
  if (typeof value !== "string" || value === "" || value.includes("\\")) {
    throw new ContractError("PATH_ERROR", `${label} must be a repository-relative POSIX path`);
  }
  if (
    value.startsWith("/") ||
    value.includes("\0") ||
    value.includes("\uFFFD") ||
    (!allowLiteralGlobCharacters && /[*?\[]/.test(value))
  ) {
    throw new ContractError("PATH_ERROR", `${label} must be repository relative`);
  }
  const normalized = path.posix.normalize(value);
  if (
    normalized !== value ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../") ||
    value.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new ContractError("PATH_ERROR", `${label} is not normalized: ${value}`);
  }
  return normalized;
}

function normalizeDirectory(value, label, allowGlob) {
  if (
    typeof value !== "string" ||
    (!value.startsWith("/") && !(allowGlob && value.includes("*"))) ||
    value.includes("\\")
  ) {
    throw new ContractError(
      "PATH_ERROR",
      `${label} must be an absolute directory or documented directories glob`
    );
  }
  if (!allowGlob && /[*?\[]/.test(value)) {
    throw new ContractError("PATH_ERROR", `${label} does not support globs`);
  }
  if (allowGlob && /[?\[]/.test(value)) {
    throw new ContractError("PATH_ERROR", `${label} supports only * and ** globs`);
  }
  if (value !== "/" && value.endsWith("/")) {
    throw new ContractError("PATH_ERROR", `${label} must not have a trailing slash`);
  }
  const plain = value.replaceAll("**", "x").replaceAll("*", "x");
  const segments = plain.replace(/^\//, "").split("/");
  if (value !== "/" && segments.some((part) => part === "." || part === ".." || part === "")) {
    throw new ContractError("PATH_ERROR", `${label} is ambiguous: ${value}`);
  }
  return value;
}

function reviewRecord(value, label, asOf, extraKeys = new Set()) {
  const entry = object(value, label);
  closedKeys(entry, new Set([...REVIEW_KEYS, ...extraKeys]), label);
  if (
    typeof entry.reason !== "string" ||
    entry.reason.trim().length < 10 ||
    entry.reason.length > 500 ||
    entry.reason !== entry.reason.trim() ||
    /[\r\n\0]/.test(entry.reason)
  ) {
    throw new ContractError("SCHEMA_ERROR", `${label}.reason must contain 10-500 characters`);
  }
  if (
    typeof entry["reviewed-by"] !== "string" ||
    !/^@[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)?$/.test(entry["reviewed-by"])
  ) {
    throw new ContractError(
      "SCHEMA_ERROR",
      `${label}.reviewed-by must be an exact GitHub user or team`
    );
  }
  parseDate(entry["reviewed-on"], `${label}.reviewed-on`);
  if (entry["reviewed-on"] > asOf)
    throw new ContractError("SCHEMA_ERROR", `${label}.reviewed-on must not be in the future`);
  return entry;
}

function loadPolicy(filename) {
  let policy;
  try {
    const source = readSecureRegularFile(filename, "policy", 1024 * 1024, {
      code: "POLICY_ERROR",
    });
    policy = JSON.parse(source.toString("utf8"));
  } catch (error) {
    throw new ContractError("POLICY_ERROR", `cannot load policy: ${error.message}`);
  }
  object(policy, "policy");
  closedKeys(policy, POLICY_KEYS, "policy");
  if (policy.schema !== "secpal-dependabot-manifest-catalog/v1") {
    throw new ContractError("POLICY_ERROR", "unsupported policy schema");
  }
  for (const key of [
    "behavior_provenance",
    "discovery_dispositions",
    "policy_version",
    "reviewed_on",
    "expires_on",
    "supported_config_ecosystems",
    "manifest_rules",
    "non_manifest_rules",
    "upstream",
    "candidate_rules",
  ]) {
    if (!(key in policy)) throw new ContractError("POLICY_ERROR", `policy lacks ${key}`);
  }
  object(policy.upstream, "policy.upstream");
  closedKeys(policy.upstream, UPSTREAM_KEYS, "policy.upstream");
  if (
    !/^[0-9a-f]{40}$/.test(policy.upstream.dependabot_core_commit || "") ||
    !Array.isArray(policy.upstream.dependabot_core_source_paths) ||
    !policy.upstream.dependabot_core_source_paths.length ||
    policy.upstream.dependabot_core_source_paths.some(
      (value) => typeof value !== "string" || value.startsWith("/") || value.includes("..")
    ) ||
    new Set(policy.upstream.dependabot_core_source_paths).size !==
      policy.upstream.dependabot_core_source_paths.length
  ) {
    throw new ContractError("POLICY_ERROR", "upstream Dependabot Core provenance is invalid");
  }
  try {
    parseDate(policy.reviewed_on, "policy.reviewed_on", "POLICY_ERROR");
    parseDate(policy.expires_on, "policy.expires_on", "POLICY_ERROR");
  } catch (error) {
    throw error;
  }
  if (policy.expires_on <= policy.reviewed_on) {
    throw new ContractError("POLICY_ERROR", "policy review and expiry dates are invalid");
  }
  if (
    !Array.isArray(policy.supported_config_ecosystems) ||
    !policy.supported_config_ecosystems.length ||
    policy.supported_config_ecosystems.some((value) => typeof value !== "string") ||
    new Set(policy.supported_config_ecosystems).size !== policy.supported_config_ecosystems.length
  ) {
    throw new ContractError("POLICY_ERROR", "supported_config_ecosystems is invalid");
  }
  object(policy.discovery_dispositions, "policy.discovery_dispositions");
  if (
    Object.keys(policy.discovery_dispositions).sort().join("\0") !==
    [...policy.supported_config_ecosystems].sort().join("\0")
  )
    throw new ContractError(
      "POLICY_ERROR",
      "every supported ecosystem must have exactly one discovery disposition"
    );
  const provenance = new Set(policy.upstream.dependabot_core_source_paths);
  object(policy.behavior_provenance, "policy.behavior_provenance");
  if (
    Object.keys(policy.behavior_provenance).sort().join("\0") !==
      "cargo_workspace\0exclude_paths" ||
    Object.values(policy.behavior_provenance).some(
      (sources) =>
        !Array.isArray(sources) ||
        !sources.length ||
        sources.some((source) => !provenance.has(source))
    )
  )
    throw new ContractError("POLICY_ERROR", "behavior provenance is invalid or incomplete");
  for (const [ecosystem, disposition] of Object.entries(policy.discovery_dispositions)) {
    object(disposition, `policy.discovery_dispositions.${ecosystem}`);
    closedKeys(
      disposition,
      DISCOVERY_DISPOSITION_KEYS,
      `policy.discovery_dispositions.${ecosystem}`
    );
    if (
      !new Set([
        "DIRECT_MANIFEST_RULES",
        "SHARED_DISCOVERY_RULE",
        "EXPLICIT_NOT_DISCOVERABLE_WITH_JUSTIFICATION",
      ]).has(disposition.mode) ||
      !Array.isArray(disposition.source_paths) ||
      disposition.source_paths.some((source) => !provenance.has(source)) ||
      (disposition.mode === "EXPLICIT_NOT_DISCOVERABLE_WITH_JUSTIFICATION" &&
        (typeof disposition.justification !== "string" || disposition.justification.length < 40))
    )
      throw new ContractError("POLICY_ERROR", `invalid discovery disposition for ${ecosystem}`);
  }
  const ids = new Set();
  for (const [kind, propertyKey, rules] of [
    ["manifest", "manifest_rules", policy.manifest_rules],
    ["candidate", "candidate_rules", policy.candidate_rules],
    ["non-manifest", "non_manifest_rules", policy.non_manifest_rules],
  ]) {
    if (!Array.isArray(rules) || (kind === "non-manifest" && !rules.length))
      throw new ContractError("POLICY_ERROR", `${propertyKey} must be an array`);
    for (const rule of rules) {
      closedKeys(
        rule,
        kind === "manifest"
          ? MANIFEST_RULE_KEYS
          : kind === "candidate"
            ? CANDIDATE_RULE_KEYS
            : NON_MANIFEST_RULE_KEYS,
        `policy.${propertyKey}`
      );
      if (!rule.id || ids.has(rule.id))
        throw new ContractError("POLICY_ERROR", `invalid duplicate rule id ${rule.id}`);
      ids.add(rule.id);
      if (
        typeof rule.path_regex !== "string" ||
        (kind === "manifest" &&
          (!policy.supported_config_ecosystems.includes(rule.ecosystem) ||
            !new Set(["devcontainer-root", "parent", "root", "swift-root"]).has(
              rule.coverage_directory
            )))
      ) {
        throw new ContractError("POLICY_ERROR", `invalid rule ${rule.id}`);
      }
      const validSources =
        Array.isArray(rule.source_paths) &&
        rule.source_paths.length &&
        rule.source_paths.every((source) => provenance.has(source));
      const policyBackstop = kind === "candidate" && rule.authority === "secpal-review-backstop";
      const policyNonManifest =
        kind === "non-manifest" &&
        rule.authority === "secpal-reviewed-non-manifest" &&
        typeof rule.candidate_rule === "string" &&
        rule.content_kind === "spdx-json-document" &&
        (!Object.hasOwn(rule, "case_insensitive") || typeof rule.case_insensitive === "boolean") &&
        typeof rule.justification === "string" &&
        rule.justification.length >= 40 &&
        rule.justification.length <= 500;
      if (!validSources && !policyBackstop && !policyNonManifest)
        throw new ContractError(
          "POLICY_ERROR",
          `policy.${propertyKey} rule ${rule.id} lacks valid authority`
        );
      try {
        rule.compiled = new RegExp(rule.path_regex, rule.case_insensitive ? "i" : "");
      } catch (error) {
        throw new ContractError(
          "POLICY_ERROR",
          `invalid policy.${propertyKey} rule ${rule.id}: ${error.message}`
        );
      }
    }
  }
  const candidateRuleIds = new Set(policy.candidate_rules.map((rule) => rule.id));
  for (const rule of policy.non_manifest_rules) {
    if (!candidateRuleIds.has(rule.candidate_rule))
      throw new ContractError(
        "POLICY_ERROR",
        `policy.non_manifest_rules rule ${rule.id} references unknown candidate rule ${rule.candidate_rule}`
      );
  }
  for (const ecosystem of policy.supported_config_ecosystems) {
    const disposition = policy.discovery_dispositions[ecosystem];
    if (
      disposition.mode !== "EXPLICIT_NOT_DISCOVERABLE_WITH_JUSTIFICATION" &&
      !policy.manifest_rules.some(
        (rule) =>
          rule.ecosystem === ecosystem ||
          (rule.ownership === "javascript-package" && ecosystem === "bun") ||
          (rule.ownership === "python-package" && ecosystem === "uv") ||
          (rule.ownership === "terraform-module" && ecosystem === "opentofu")
      )
    )
      throw new ContractError("POLICY_ERROR", `${ecosystem} lacks executable discovery`);
  }
  const usedSources = new Set([
    ...Object.values(policy.discovery_dispositions).flatMap((item) => item.source_paths),
    ...Object.values(policy.behavior_provenance).flat(),
    ...policy.manifest_rules.flatMap((rule) => rule.source_paths),
    ...policy.candidate_rules.flatMap((rule) => rule.source_paths || []),
  ]);
  if (
    [...usedSources].sort().join("\0") !==
    [...policy.upstream.dependabot_core_source_paths].sort().join("\0")
  )
    throw new ContractError("POLICY_ERROR", "upstream provenance contains unused sources");
  return policy;
}

function ensureTracked(root, relative) {
  try {
    execFileSync("git", ["-C", root, "ls-files", "--error-unmatch", "--", relative], {
      stdio: "ignore",
    });
  } catch {
    throw new ContractError(
      "UNTRACKED_POLICY_INPUT",
      `${relative} must be version controlled before it can affect the guard`
    );
  }
}

function trackedFiles(root) {
  let output;
  try {
    output = execFileSync("git", ["-C", root, "ls-files", "-z"], {
      encoding: "buffer",
      maxBuffer: 16 * 1024 * 1024,
    });
  } catch (error) {
    throw new ContractError("DISCOVERY_ERROR", `git ls-files failed: ${error.message}`);
  }
  return output
    .toString("utf8")
    .split("\0")
    .filter(Boolean)
    .map((entry) => normalizeManifest(entry, "tracked path", true))
    .sort();
}

function parentDirectory(manifest) {
  const parent = path.posix.dirname(manifest);
  return parent === "." ? "/" : `/${parent}`;
}

function specialCoverageDirectory(manifestPath, mode) {
  if (mode === "devcontainer-root") {
    const segments = manifestPath.split("/");
    const marker = segments.findIndex(
      (segment) => segment === ".devcontainer" || segment === ".devcontainer.json"
    );
    if (marker < 0) return parentDirectory(manifestPath);
    return marker === 0 ? "/" : `/${segments.slice(0, marker).join("/")}`;
  }
  if (mode === "swift-root") {
    const segments = manifestPath.split("/");
    const marker = segments.findIndex(
      (segment) => segment.endsWith(".xcodeproj") || segment.endsWith(".xcworkspace")
    );
    return marker <= 0 ? "/" : `/${segments.slice(0, marker).join("/")}`;
  }
  return null;
}

function loadExceptions(root, relative, policy, asOf) {
  const raw = yamlFile(root, relative, false);
  if (raw === null)
    return { classifications: new Map(), exceptions: new Map(), noApplicable: null };
  ensureTracked(root, relative);
  const document = object(raw, relative);
  closedKeys(
    document,
    new Set(["classifications", "manifest-exceptions", "no-applicable-manifest", "version"]),
    relative
  );
  if (document.version !== 1)
    throw new ContractError("SCHEMA_ERROR", `${relative}.version must be 1`);
  const result = { classifications: new Map(), exceptions: new Map(), noApplicable: null };
  const classifications = document.classifications || [];
  if (!Array.isArray(classifications))
    throw new ContractError("SCHEMA_ERROR", `${relative}.classifications must be an array`);
  classifications.forEach((candidate, index) => {
    const label = `${relative}.classifications[${index}]`;
    const entry = reviewRecord(candidate, label, asOf, new Set(["directory", "ecosystem"]));
    closedKeys(entry, CLASSIFICATION_KEYS, label);
    const directory =
      entry.directory === "/" ? "" : normalizeManifest(entry.directory, `${label}.directory`);
    if (!new Set(["opentofu", "terraform"]).has(entry.ecosystem))
      throw new ContractError(
        "SCHEMA_ERROR",
        `${label}.ecosystem must select terraform or opentofu module ownership`
      );
    if (result.classifications.has(directory))
      throw new ContractError("SCHEMA_ERROR", `${label} duplicates module ${directory}`);
    result.classifications.set(directory, entry);
  });
  for (const [field, target] of [["manifest-exceptions", result.exceptions]]) {
    const entries = document[field] || [];
    if (!Array.isArray(entries))
      throw new ContractError("SCHEMA_ERROR", `${relative}.${field} must be an array`);
    entries.forEach((candidate, index) => {
      const label = `${relative}.${field}[${index}]`;
      const entry = reviewRecord(candidate, label, asOf, new Set(["ecosystem", "manifest"]));
      closedKeys(entry, EXCEPTION_KEYS, label);
      const manifest = normalizeManifest(entry.manifest, `${label}.manifest`);
      if (
        typeof entry.ecosystem !== "string" ||
        !policy.supported_config_ecosystems.includes(entry.ecosystem)
      ) {
        throw new ContractError(
          "SCHEMA_ERROR",
          `${label}.ecosystem is not supported by this policy`
        );
      }
      const key = `${manifest}\0${entry.ecosystem}`;
      if (target.has(key))
        throw new ContractError(
          "SCHEMA_ERROR",
          `${label} duplicates ${manifest}/${entry.ecosystem}`
        );
      target.set(key, entry);
    });
  }
  if (document["no-applicable-manifest"] !== undefined) {
    result.noApplicable = reviewRecord(
      document["no-applicable-manifest"],
      `${relative}.no-applicable-manifest`,
      asOf
    );
  }
  return result;
}

function loadReviewPolicy(options, policy) {
  const subject = loadExceptions(options.root, options.exceptions, policy, options.asOf);
  if (!options.trustedPolicyRoot) {
    return {
      classifications: new Map(),
      exceptions: new Map(),
      noApplicable: null,
      diagnostics: [],
      proposed: subject,
    };
  }
  const trusted = loadExceptions(
    options.trustedPolicyRoot,
    options.exceptions,
    policy,
    options.asOf
  );
  trusted.diagnostics = [];
  trusted.proposed = subject;
  return trusted;
}

function readTrackedText(root, relative, maximumBytes = 2 * 1024 * 1024) {
  const absolute = path.join(root, relative);
  const content = readSecureRegularFile(absolute, relative, maximumBytes).toString("utf8");
  return content.includes("\uFFFD") ? null : content;
}

function contentMatches(root, manifestPath, kind) {
  if (!kind) return true;
  const source = readTrackedText(root, manifestPath);
  if (source === null) return false;
  if (kind === "python-requirements") {
    if (/requirements/i.test(path.posix.basename(manifestPath))) return true;
    let hasDependency = false;
    for (const line of source.split(/\r?\n/)) {
      const value = line.trim();
      if (value === "" || value.startsWith("#") || value.startsWith("-")) continue;
      if (/^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(?:[<>=!~]=?|===)\s*\S+/.test(value)) {
        hasDependency = true;
        continue;
      }
      return false;
    }
    return hasDependency;
  }
  if (kind === "kubernetes-resource") {
    try {
      let matched = false;
      yaml.loadAll(
        source.replace(/^\uFEFF/, ""),
        (document) => {
          if (
            document &&
            typeof document === "object" &&
            !Array.isArray(document) &&
            Object.hasOwn(document, "apiVersion") &&
            Object.hasOwn(document, "kind")
          )
            matched = true;
        },
        { schema: yaml.JSON_SCHEMA }
      );
      return matched;
    } catch {
      return false;
    }
  }
  if (kind === "spdx-json-document") {
    try {
      const document = JSON.parse(source);
      const plainObject = (value) => value && typeof value === "object" && !Array.isArray(value);
      const nonEmptyString = (value) => typeof value === "string" && value.trim().length > 0;
      const validUtcTimestamp = (value) => {
        const match =
          /^(\d{4})-(\d{2})-(\d{2})T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?:\.\d+)?Z$/.exec(value);
        if (!match) return false;
        const parsed = new Date(value);
        return (
          !Number.isNaN(parsed.valueOf()) &&
          parsed.getUTCFullYear() === Number(match[1]) &&
          parsed.getUTCMonth() + 1 === Number(match[2]) &&
          parsed.getUTCDate() === Number(match[3])
        );
      };
      return (
        plainObject(document) &&
        document.spdxVersion === "SPDX-2.3" &&
        document.SPDXID === "SPDXRef-DOCUMENT" &&
        document.dataLicense === "CC0-1.0" &&
        nonEmptyString(document.name) &&
        nonEmptyString(document.documentNamespace) &&
        plainObject(document.creationInfo) &&
        validUtcTimestamp(document.creationInfo.created) &&
        Array.isArray(document.creationInfo.creators) &&
        document.creationInfo.creators.length > 0 &&
        document.creationInfo.creators.every(nonEmptyString) &&
        Array.isArray(document.packages) &&
        document.packages.every(
          (item) =>
            plainObject(item) &&
            nonEmptyString(item.SPDXID) &&
            nonEmptyString(item.name) &&
            nonEmptyString(item.downloadLocation)
        ) &&
        Array.isArray(document.relationships) &&
        document.relationships.every(
          (item) =>
            plainObject(item) &&
            nonEmptyString(item.spdxElementId) &&
            nonEmptyString(item.relationshipType) &&
            nonEmptyString(item.relatedSpdxElement)
        )
      );
    } catch {
      return false;
    }
  }
  throw new ContractError("POLICY_ERROR", `unsupported content matcher ${kind}`);
}

function workspacePatterns(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object" && Array.isArray(value.packages)) return value.packages;
  return [];
}

function normalizedWorkspacePattern(pattern) {
  if (typeof pattern !== "string" || pattern === "" || pattern.startsWith("/")) return null;
  const normalized = path.posix.normalize(pattern).replace(/^\.\//, "").replace(/\/$/, "");
  if (
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../") ||
    normalized.includes("\\")
  )
    return null;
  return normalized;
}

function matchesWorkspacePattern(pattern, relative) {
  const normalized = normalizedWorkspacePattern(pattern);
  return normalized !== null && globRegex(normalized).test(relative);
}

function javascriptOwnership(root, manifestPath, tracked) {
  const manifestDirectory =
    path.posix.dirname(manifestPath) === "." ? "" : path.posix.dirname(manifestPath);
  let selected = manifestPath;
  for (const candidate of tracked.filter((item) => item.endsWith("package.json"))) {
    const candidateDirectory =
      path.posix.dirname(candidate) === "." ? "" : path.posix.dirname(candidate);
    if (
      candidate === manifestPath ||
      (candidateDirectory && !manifestDirectory.startsWith(`${candidateDirectory}/`))
    )
      continue;
    const relative = path.posix.relative(candidateDirectory || ".", manifestDirectory || ".");
    if (!relative || relative.startsWith("..")) continue;
    try {
      const document = JSON.parse(readTrackedText(root, candidate));
      if (
        workspacePatterns(document.workspaces).some((pattern) =>
          matchesWorkspacePattern(pattern, relative)
        )
      )
        selected = candidate;
    } catch (error) {
      if (error instanceof ContractError) throw error;
      continue;
    }
  }
  const selectedDirectory =
    path.posix.dirname(selected) === "." ? "" : path.posix.dirname(selected);
  const files = new Set(tracked);
  let ecosystem = "npm";
  try {
    const document = JSON.parse(readTrackedText(root, selected));
    const manager = typeof document.packageManager === "string" ? document.packageManager : "";
    if (
      manager.startsWith("bun@") ||
      files.has(path.posix.join(selectedDirectory, "bun.lock")) ||
      files.has(path.posix.join(selectedDirectory, "bun.lockb"))
    )
      ecosystem = "bun";
  } catch (error) {
    if (error instanceof ContractError) throw error;
    // Dependabot will surface malformed package.json; discovery still retains it as npm data.
  }
  return { coverageDirectory: parentDirectory(selected), ecosystem };
}

function cargoDocument(root, manifestPath) {
  try {
    return parseToml(readTrackedText(root, manifestPath));
  } catch (error) {
    if (error instanceof ContractError) throw error;
    return null;
  }
}

function cargoWorkspacePatterns(value) {
  return Array.isArray(value) ? value : [];
}

function matchesCargoWorkspacePattern(pattern, relative) {
  const normalized = normalizedWorkspacePattern(pattern);
  return normalized !== null && globRegex(normalized).test(relative);
}

function isCargoWorkspaceExcluded(pattern, relative) {
  return normalizedWorkspacePattern(pattern) === relative;
}

function cargoOwnership(root, manifestPath, tracked) {
  const manifestDirectory =
    path.posix.dirname(manifestPath) === "." ? "" : path.posix.dirname(manifestPath);
  const trackedSet = new Set(tracked);
  const manifest = cargoDocument(root, manifestPath);
  const explicitWorkspace = manifest?.package?.workspace;
  if (typeof explicitWorkspace === "string") {
    const workspaceDirectory = path.posix.normalize(
      path.posix.join(manifestDirectory, explicitWorkspace)
    );
    const workspaceManifest = path.posix.join(
      workspaceDirectory === "." ? "" : workspaceDirectory,
      "Cargo.toml"
    );
    if (
      workspaceDirectory !== ".." &&
      !workspaceDirectory.startsWith("../") &&
      trackedSet.has(workspaceManifest) &&
      cargoDocument(root, workspaceManifest)?.workspace
    )
      return parentDirectory(workspaceManifest);
  }

  let selected = null;
  for (const candidate of tracked.filter((item) => item.endsWith("Cargo.toml"))) {
    if (candidate === manifestPath) continue;
    const candidateDirectory =
      path.posix.dirname(candidate) === "." ? "" : path.posix.dirname(candidate);
    if (candidateDirectory && !manifestDirectory.startsWith(`${candidateDirectory}/`)) continue;
    const relative = path.posix.relative(candidateDirectory || ".", manifestDirectory || ".");
    if (!relative || relative.startsWith("..")) continue;
    const workspace = cargoDocument(root, candidate)?.workspace;
    if (!workspace || typeof workspace !== "object" || Array.isArray(workspace)) continue;
    const members = cargoWorkspacePatterns(workspace.members);
    const excluded = [
      ...cargoWorkspacePatterns(workspace.exclude),
      ...cargoWorkspacePatterns(workspace.excluded_paths),
    ];
    if (
      members.some((pattern) => matchesCargoWorkspacePattern(pattern, relative)) &&
      !excluded.some((pattern) => isCargoWorkspaceExcluded(pattern, relative)) &&
      (selected === null || candidateDirectory.length > selected.directory.length)
    )
      selected = { directory: candidateDirectory, manifest: candidate };
  }
  return selected ? parentDirectory(selected.manifest) : parentDirectory(manifestPath);
}

function discover(root, policy, reviewed) {
  const manifests = [];
  const diagnostics = [...(reviewed.diagnostics || [])];
  const tracked = trackedFiles(root);
  const trackedSet = new Set(tracked);
  const terraformModules = new Map();
  for (const manifestPath of tracked) {
    const pathRules = policy.manifest_rules.filter((rule) => rule.compiled.test(manifestPath));
    const candidateRules = policy.candidate_rules.filter((rule) =>
      rule.compiled.test(manifestPath)
    );
    const nonManifestRules = policy.non_manifest_rules.filter(
      (rule) =>
        candidateRules.some((candidate) => candidate.id === rule.candidate_rule) &&
        rule.compiled.test(manifestPath)
    );
    if (!pathRules.length && !candidateRules.length && !nonManifestRules.length) continue;
    let stat;
    try {
      stat = lstatSync(path.join(root, manifestPath));
    } catch (error) {
      diagnostics.push({
        code: "MISSING_TRACKED_FILE",
        expected_ecosystem: null,
        manifest_path: manifestPath,
        reason: `tracked manifest candidate is unavailable in the worktree: ${error.code || "error"}`,
      });
      continue;
    }
    if (stat.isSymbolicLink()) {
      diagnostics.push({
        code: "UNSAFE_SYMLINK",
        expected_ecosystem: null,
        manifest_path: manifestPath,
        reason: "tracked manifest candidates must be regular files, not symlinks",
      });
      continue;
    }
    if (!stat.isFile()) continue;
    const matchingRules = pathRules.filter(
      (rule) =>
        contentMatches(root, manifestPath, rule.content_kind) &&
        (!rule.companion ||
          trackedSet.has(path.posix.join(path.posix.dirname(manifestPath), rule.companion)))
    );
    if (!matchingRules.length) {
      if (!candidateRules.length) continue;
      if (nonManifestRules.some((rule) => contentMatches(root, manifestPath, rule.content_kind)))
        continue;
      diagnostics.push({
        candidate_rules: candidateRules.map((rule) => rule.id).sort(),
        code: "UNCLASSIFIED_MANIFEST_CANDIDATE",
        expected_ecosystem: null,
        manifest_path: manifestPath,
        reason: "dependency-manifest candidate is not safely classified by the versioned catalog",
      });
      continue;
    }
    const ownershipRule = matchingRules.find((rule) => rule.ownership);
    if (ownershipRule?.ownership === "terraform-module") {
      const directory =
        path.posix.dirname(manifestPath) === "." ? "" : path.posix.dirname(manifestPath);
      if (!terraformModules.has(directory)) terraformModules.set(directory, []);
      terraformModules.get(directory).push(manifestPath);
      continue;
    }
    const primaryRule = matchingRules.find((item) => !item.content_kind) || matchingRules[0];
    let ecosystem = primaryRule.ecosystem;
    let coverageDirectory =
      primaryRule.coverage_directory === "root" ? "/" : parentDirectory(manifestPath);
    if (ownershipRule?.ownership === "javascript-package") {
      const ownership = javascriptOwnership(root, manifestPath, tracked);
      ecosystem = ownership.ecosystem;
      coverageDirectory = ownership.coverageDirectory;
    } else if (ownershipRule?.ownership === "python-package") {
      const directory = path.posix.dirname(manifestPath);
      const uvLock = path.posix.join(directory === "." ? "" : directory, "uv.lock");
      ecosystem = trackedSet.has(uvLock) ? "uv" : "pip";
    } else if (ownershipRule?.ownership === "cargo-package") {
      coverageDirectory = cargoOwnership(root, manifestPath, tracked);
    }
    const rule = matchingRules.find((item) => item.ecosystem === ecosystem);
    manifests.push({
      coverage_directory:
        specialCoverageDirectory(manifestPath, rule?.coverage_directory) ?? coverageDirectory,
      expected_ecosystem: ecosystem,
      manifest_path: manifestPath,
    });
  }
  for (const [directory, moduleFiles] of [...terraformModules.entries()].sort()) {
    const classification = reviewed.classifications.get(directory);
    const proposedClassification = reviewed.proposed?.classifications.get(directory);
    const hasTofu = moduleFiles.some((manifest) => manifest.endsWith(".tofu"));
    let ecosystem = hasTofu ? "opentofu" : classification?.ecosystem;
    if (hasTofu && classification && classification.ecosystem !== "opentofu") {
      diagnostics.push({
        code: "CONTRADICTORY_CLASSIFICATION",
        expected_ecosystem: "opentofu",
        manifest_path: moduleFiles[0],
        reason: `module ${directory || "."} contains .tofu but protected policy selects terraform`,
      });
      continue;
    }
    if (!ecosystem) {
      if (proposedClassification)
        diagnostics.push({
          code: "UNTRUSTED_POLICY_INPUT",
          expected_ecosystem: proposedClassification.ecosystem,
          manifest_path: moduleFiles[0],
          reason: `subject classification for ${directory || "."} is not protected-history authority`,
        });
      diagnostics.push({
        code: "AMBIGUOUS_MANIFEST_CLASSIFICATION",
        expected_ecosystem: "opentofu|terraform",
        manifest_path: moduleFiles[0],
        reason: `protected module classification must select one ecosystem for ${directory || "."}`,
      });
      continue;
    }
    for (const manifestPath of moduleFiles.sort()) {
      manifests.push({
        coverage_directory: parentDirectory(manifestPath),
        expected_ecosystem: ecosystem,
        manifest_path: manifestPath,
      });
    }
  }
  manifests.sort(
    (left, right) =>
      compareText(left.manifest_path, right.manifest_path) ||
      compareText(left.expected_ecosystem, right.expected_ecosystem)
  );
  diagnostics.sort(
    (left, right) =>
      compareText(left.manifest_path, right.manifest_path) || compareText(left.code, right.code)
  );
  return { diagnostics, manifests };
}

function globRegex(pattern) {
  let expression = "^";
  for (let index = 0; index < pattern.length; index += 1) {
    const character = pattern[index];
    if (character === "*" && pattern[index + 1] === "*" && pattern[index + 2] === "/") {
      expression += "(?:.*/)?";
      index += 2;
    } else if (character === "*" && pattern[index + 1] === "*") {
      expression += ".*";
      index += 1;
    } else if (character === "*") expression += "[^/]*";
    else expression += character.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`${expression}$`);
}

function matchesGlob(pattern, value) {
  const normalizedPattern = pattern.replace(/^\//, "").replace(/\/$/, "");
  const normalizedValue = value.replace(/^\//, "").replace(/\/$/, "");
  if (!normalizedPattern.includes("/"))
    return globRegex(normalizedPattern).test(path.posix.basename(normalizedValue));
  return globRegex(normalizedPattern).test(normalizedValue);
}

function matchesDirectoryScope(pattern, directory) {
  const normalizedPattern = pattern.replace(/^\//, "").replace(/\/$/, "");
  const normalizedDirectory = directory.replace(/^\//, "").replace(/\/$/, "");
  return globRegex(normalizedPattern).test(normalizedDirectory);
}

function validExcludePattern(value) {
  if (typeof value !== "string" || value === "" || value.startsWith("/") || value.includes("\\"))
    return false;
  const normalized = value.endsWith("/") ? value.slice(0, -1) : value;
  return !normalized
    .split("/")
    .some((segment) => segment === "." || segment === ".." || segment === "");
}

function parseConfig(root, relative, policy) {
  const alternate = relative.endsWith(".yml") ? `${relative.slice(0, -4)}.yaml` : null;
  let selected = relative;
  let raw = yamlFile(root, relative, false);
  if (alternate) {
    const other = yamlFile(root, alternate, false);
    if (raw !== null && other !== null)
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        "both dependabot.yml and dependabot.yaml exist"
      );
    if (raw === null && other !== null) {
      raw = other;
      selected = alternate;
    }
  }
  if (raw === null) return { entries: [], groups: {}, path: selected };
  ensureTracked(root, selected);
  const config = object(raw, selected);
  closedKeys(config, TOP_LEVEL_KEYS, selected);
  if (config.version !== 2)
    throw new ContractError("CONFIG_SCHEMA_ERROR", `${selected}.version must be 2`);
  if (!Array.isArray(config.updates))
    throw new ContractError("CONFIG_SCHEMA_ERROR", `${selected}.updates must be an array`);
  const groups = config["multi-ecosystem-groups"] || {};
  object(groups, `${selected}.multi-ecosystem-groups`);
  for (const [name, group] of Object.entries(groups)) {
    object(group, `${selected}.multi-ecosystem-groups.${name}`);
    closedKeys(
      group,
      new Set([
        "assignees",
        "commit-message",
        "labels",
        "milestone",
        "pull-request-branch-name",
        "schedule",
        "target-branch",
      ]),
      `${selected}.multi-ecosystem-groups.${name}`
    );
    validateSchedule(group.schedule, `${selected}.multi-ecosystem-groups.${name}.schedule`, false);
    if (
      group["target-branch"] !== undefined &&
      (typeof group["target-branch"] !== "string" || group["target-branch"] === "")
    )
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.multi-ecosystem-groups.${name}.target-branch must be a string`
      );
  }
  const entries = config.updates.map((candidate, index) => {
    const label = `updates[${index}]`;
    const entry = object(candidate, `${selected}.${label}`);
    closedKeys(entry, UPDATE_KEYS, `${selected}.${label}`);
    if (
      typeof entry["package-ecosystem"] !== "string" ||
      !policy.supported_config_ecosystems.includes(entry["package-ecosystem"])
    ) {
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.package-ecosystem is unknown to policy ${policy.policy_version}`
      );
    }
    const hasDirectory = Object.hasOwn(entry, "directory");
    const hasDirectories = Object.hasOwn(entry, "directories");
    if (hasDirectory === hasDirectories)
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label} must define exactly one of directory or directories`
      );
    let scopes;
    if (hasDirectory)
      scopes = [normalizeDirectory(entry.directory, `${selected}.${label}.directory`, false)];
    else {
      if (!Array.isArray(entry.directories) || !entry.directories.length)
        throw new ContractError(
          "CONFIG_SCHEMA_ERROR",
          `${selected}.${label}.directories must be a non-empty array`
        );
      scopes = entry.directories.map((scope, scopeIndex) =>
        normalizeDirectory(scope, `${selected}.${label}.directories[${scopeIndex}]`, true)
      );
      if (new Set(scopes).size !== scopes.length)
        throw new ContractError(
          "CONFIG_SCHEMA_ERROR",
          `${selected}.${label}.directories contains duplicates`
        );
    }
    const groupName = entry["multi-ecosystem-group"];
    if (groupName !== undefined && (typeof groupName !== "string" || !groups[groupName])) {
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.multi-ecosystem-group is undefined`
      );
    }
    if (
      groupName !== undefined &&
      (!Array.isArray(entry.patterns) ||
        !entry.patterns.length ||
        entry.patterns.some((value) => typeof value !== "string" || value === ""))
    )
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.patterns must be a non-empty array for multi-ecosystem-group`
      );
    if (groupName !== undefined && entry["target-branch"] !== undefined)
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.target-branch must be configured on the multi-ecosystem group`
      );
    validateSchedule(entry.schedule, `${selected}.${label}.schedule`, Boolean(groupName));
    if (
      entry["target-branch"] !== undefined &&
      (typeof entry["target-branch"] !== "string" || entry["target-branch"] === "")
    ) {
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.target-branch must be a string`
      );
    }
    if (
      entry["exclude-paths"] !== undefined &&
      (!Array.isArray(entry["exclude-paths"]) ||
        entry["exclude-paths"].some((value) => !validExcludePattern(value)))
    ) {
      throw new ContractError(
        "CONFIG_SCHEMA_ERROR",
        `${selected}.${label}.exclude-paths must contain relative glob strings`
      );
    }
    return {
      ecosystem: entry["package-ecosystem"],
      excludes: entry["exclude-paths"] || [],
      group: groupName || null,
      index,
      schedule: groupName ? groups[groupName].schedule : entry.schedule,
      scopes,
      targetBranch: groupName
        ? groups[groupName]["target-branch"] || null
        : entry["target-branch"] || null,
    };
  });
  const identities = new Set();
  for (const entry of entries) {
    for (const scope of entry.scopes) {
      const identity = `${entry.ecosystem}\0${scope}\0${entry.targetBranch || ""}`;
      if (identities.has(identity))
        throw new ContractError(
          "DUPLICATE_CONFIGURATION",
          `duplicate Dependabot scope ${entry.ecosystem}:${scope}`
        );
      identities.add(identity);
    }
  }
  return { entries, groups, path: selected };
}

function validateSchedule(value, label, optional) {
  if (value === undefined && optional) return;
  const schedule = object(value, label);
  closedKeys(schedule, SCHEDULE_KEYS, label);
  if (typeof schedule.interval !== "string")
    throw new ContractError("CONFIG_SCHEMA_ERROR", `${label}.interval is required`);
  if (!SCHEDULE_INTERVALS.has(schedule.interval))
    throw new ContractError("CONFIG_SCHEMA_ERROR", `${label}.interval is invalid`);
  for (const key of ["cronjob", "day", "time", "timezone"]) {
    if (schedule[key] !== undefined && typeof schedule[key] !== "string")
      throw new ContractError("CONFIG_SCHEMA_ERROR", `${label}.${key} must be a string`);
  }
}

function entryLabel(entry, scope) {
  return `updates[${entry.index}]:${entry.ecosystem}:${scope}`;
}

function relativeToDirectory(manifest, directory) {
  if (directory === "/") return manifest;
  const prefix = `${directory.slice(1)}/`;
  return manifest.startsWith(prefix) ? manifest.slice(prefix.length) : null;
}

function excluded(entry, manifest, actualDirectory) {
  const relative = relativeToDirectory(manifest, actualDirectory);
  return (
    relative !== null &&
    entry.excludes.some((pattern) => {
      const normalized = pattern.replace(/^\//, "").replace(/\/$/, "");
      return (
        relative === normalized ||
        relative.startsWith(`${normalized}/`) ||
        matchesGlob(normalized, relative)
      );
    })
  );
}

function coverageReport(options, policy, config, reviewed, discovery) {
  const manifests = [];
  const diagnostics = [...discovery.diagnostics];
  for (const manifest of discovery.manifests) {
    const candidates = [];
    const considered = [];
    const matches = [];
    for (const entry of config.entries) {
      for (const scope of entry.scopes) {
        const scopeMatches = scope.includes("*")
          ? matchesDirectoryScope(scope, manifest.coverage_directory)
          : scope === manifest.coverage_directory;
        if (entry.ecosystem === manifest.expected_ecosystem || scopeMatches) {
          considered.push(entryLabel(entry, scope));
        }
        if (entry.ecosystem === manifest.expected_ecosystem && scopeMatches) {
          const label = entryLabel(entry, scope);
          candidates.push(label);
          if (
            (!entry.targetBranch || entry.targetBranch === options.defaultBranch) &&
            !excluded(entry, manifest.manifest_path, manifest.coverage_directory)
          )
            matches.push(label);
        }
      }
    }
    considered.sort();
    matches.sort();
    const exception = reviewed.exceptions.get(
      `${manifest.manifest_path}\0${manifest.expected_ecosystem}`
    );
    const proposedException = reviewed.proposed?.exceptions.get(
      `${manifest.manifest_path}\0${manifest.expected_ecosystem}`
    );
    let status;
    let reason;
    if (matches.length === 1) {
      status = "COVERED";
      reason = "exact ecosystem and directory match";
    } else if (matches.length > 1) {
      status = "AMBIGUOUS";
      reason = "multiple Dependabot entries match the same manifest";
    } else if (exception) {
      status = "EXCEPTED";
      reason = `protected-history exact exception in ${options.exceptions}`;
    } else {
      status = "UNCOVERED";
      const sameEcosystem = config.entries.some(
        (entry) => entry.ecosystem === manifest.expected_ecosystem
      );
      const sameDirectory = config.entries.some((entry) =>
        entry.scopes.some(
          (scope) =>
            scope === manifest.coverage_directory ||
            (scope.includes("*") && matchesDirectoryScope(scope, manifest.coverage_directory))
        )
      );
      if (candidates.length)
        reason = "matching entry targets another branch or excludes this manifest";
      else if (sameEcosystem)
        reason = "expected ecosystem is configured only for an unrelated directory";
      else if (sameDirectory)
        reason = "manifest directory is configured only for an unrelated ecosystem";
      else reason = "no Dependabot entry has the expected ecosystem and directory";
      if (proposedException)
        diagnostics.push({
          accepted_exception_mechanism: `${options.exceptions}: protected-history manifest-exceptions[] (exact path + ecosystem)`,
          code: "UNTRUSTED_POLICY_INPUT",
          expected_ecosystem: manifest.expected_ecosystem,
          manifest_path: manifest.manifest_path,
          matched_configuration: [],
          reason: "subject-authored exception cannot exempt the same unprotected revision",
        });
    }
    const item = {
      ...manifest,
      matched_configuration: matches,
      reason,
      status,
    };
    manifests.push(item);
    if (!new Set(["COVERED", "EXCEPTED"]).has(status)) {
      diagnostics.push({
        accepted_exception_mechanism: `${options.exceptions}: protected-history manifest-exceptions[] (exact path + ecosystem)`,
        code: status === "AMBIGUOUS" ? "AMBIGUOUS_COVERAGE" : "UNCOVERED_MANIFEST",
        considered_configuration: considered,
        expected_ecosystem: manifest.expected_ecosystem,
        manifest_path: manifest.manifest_path,
        matched_configuration: matches,
        reason,
      });
    }
  }
  if (reviewed.noApplicable && (discovery.manifests.length || discovery.diagnostics.length)) {
    diagnostics.push({
      accepted_exception_mechanism: `${options.exceptions}: no-applicable-manifest`,
      code: "INVALID_NO_APPLICABLE_MANIFEST_EXCEPTION",
      expected_ecosystem: null,
      manifest_path: null,
      matched_configuration: [],
      reason:
        "repository-level exception cannot hide a discovered or unclassified manifest candidate",
    });
  }
  if (
    reviewed.proposed?.noApplicable &&
    !reviewed.noApplicable &&
    (discovery.manifests.length || discovery.diagnostics.length)
  ) {
    diagnostics.push({
      accepted_exception_mechanism: `${options.exceptions}: protected-history no-applicable-manifest`,
      code: "INVALID_NO_APPLICABLE_MANIFEST_EXCEPTION",
      expected_ecosystem: null,
      manifest_path: null,
      matched_configuration: [],
      reason: "subject no-applicable-manifest assertion conflicts with discovered repository state",
    });
  }
  return report(options, policy, "MANIFEST_COVERAGE", manifests, diagnostics);
}

function cadenceReport(options, policy, config) {
  const entries = [];
  const diagnostics = [];
  for (const entry of config.entries) {
    for (const scope of entry.scopes) {
      const schedule = entry.schedule || {};
      const failures = [];
      if (schedule.interval !== "daily")
        failures.push(`interval is ${JSON.stringify(schedule.interval)}, expected "daily"`);
      if (schedule.time !== "04:00")
        failures.push(`time is ${JSON.stringify(schedule.time)}, expected "04:00"`);
      if (schedule.timezone !== "Europe/Berlin")
        failures.push(`timezone is ${JSON.stringify(schedule.timezone)}, expected "Europe/Berlin"`);
      const item = {
        configuration: entryLabel(entry, scope),
        ecosystem: entry.ecosystem,
        schedule: {
          interval: schedule.interval ?? null,
          time: schedule.time ?? null,
          timezone: schedule.timezone ?? null,
        },
        status: failures.length ? "FAIL" : "PASS",
      };
      entries.push(item);
      if (failures.length)
        diagnostics.push({
          code: "CADENCE_POLICY_MISMATCH",
          expected_ecosystem: entry.ecosystem,
          manifest_path: null,
          matched_configuration: [item.configuration],
          reason: failures.join("; "),
        });
    }
  }
  return report(options, policy, "CADENCE_POLICY", entries, diagnostics, "entries");
}

function report(options, policy, assertion, items, inputDiagnostics, itemName = "manifests") {
  const diagnostics = inputDiagnostics.map((diagnostic) => ({
    accepted_exception_mechanism:
      diagnostic.accepted_exception_mechanism ??
      `${options.exceptions}: exact protected-history records only`,
    expected_ecosystem: diagnostic.expected_ecosystem ?? null,
    manifest_path: diagnostic.manifest_path ?? null,
    matched_configuration: diagnostic.matched_configuration ?? [],
    reason: diagnostic.reason,
    repository: options.repository,
    ...diagnostic,
  }));
  if (options.asOf > policy.expires_on)
    diagnostics.push({
      accepted_exception_mechanism: "none; refresh and review the versioned catalog",
      code: "CATALOG_STALE",
      expected_ecosystem: null,
      manifest_path: null,
      matched_configuration: [],
      reason: `catalog expired on ${policy.expires_on}`,
      repository: options.repository,
    });
  if (options.asOf < policy.reviewed_on)
    diagnostics.push({
      accepted_exception_mechanism: "none; evaluate on or after the catalog review date",
      code: "CATALOG_NOT_YET_REVIEWED",
      expected_ecosystem: null,
      manifest_path: null,
      matched_configuration: [],
      reason: `catalog was reviewed on ${policy.reviewed_on}`,
      repository: options.repository,
    });
  diagnostics.sort(
    (left, right) =>
      compareText(String(left.manifest_path), String(right.manifest_path)) ||
      compareText(left.code, right.code)
  );
  return {
    assertion,
    catalog: {
      expires_on: policy.expires_on,
      policy_version: policy.policy_version,
      reviewed_on: policy.reviewed_on,
      upstream_dependabot_core_commit: policy.upstream.dependabot_core_commit,
    },
    diagnostics,
    exception_path: options.exceptions,
    [itemName]: items,
    repository: options.repository,
    schema: "secpal-dependabot-manifest-guard-report/v1",
    status: diagnostics.length ? "FAIL" : "PASS",
  };
}

function textReport(value) {
  const lines = [
    `${value.assertion} ${value.status} ${value.repository} policy=${value.catalog?.policy_version ?? "-"}`,
  ];
  for (const diagnostic of value.diagnostics) {
    lines.push(
      [
        diagnostic.code,
        `repository=${diagnostic.repository}`,
        `manifest=${diagnostic.manifest_path ?? "-"}`,
        `ecosystem=${diagnostic.expected_ecosystem ?? "-"}`,
        `matched=${diagnostic.matched_configuration.join(",") || "-"}`,
        `considered=${diagnostic.considered_configuration?.join(",") || "-"}`,
        `reason=${diagnostic.reason}`,
        `exception=${diagnostic.accepted_exception_mechanism}`,
      ].join(" | ")
    );
  }
  return `${lines.join("\n")}\n`;
}

function errorReport(options, error) {
  return {
    assertion: options.assertion === "coverage" ? "MANIFEST_COVERAGE" : "CADENCE_POLICY",
    catalog: null,
    diagnostics: [
      {
        accepted_exception_mechanism: "none; correct the invalid guard input",
        code: error.code || "INTERNAL_ERROR",
        expected_ecosystem: null,
        manifest_path: null,
        matched_configuration: [],
        reason: error.message,
        repository: options.repository,
        ...error.details,
      },
    ],
    exception_path: options.exceptions,
    repository: options.repository,
    schema: "secpal-dependabot-manifest-guard-report/v1",
    status: "FAIL",
  };
}

let options;
let output;
try {
  options = parseArguments(process.argv.slice(2));
  const policy = loadPolicy(options.policy);
  const config = parseConfig(options.root, options.config, policy);
  if (
    options.assertion === "coverage" &&
    config.entries.some((entry) => entry.targetBranch) &&
    !options.defaultBranch
  )
    throw new ContractError(
      "DEFAULT_BRANCH_AUTHORITY_REQUIRED",
      "target-branch coverage requires an authenticated repository default branch"
    );
  if (options.assertion === "coverage") {
    const reviewed = loadReviewPolicy(options, policy);
    const discovery = discover(options.root, policy, reviewed);
    output = coverageReport(options, policy, config, reviewed, discovery);
  } else output = cadenceReport(options, policy, config);
} catch (error) {
  options ||= {
    assertion: process.argv[2] || "coverage",
    exceptions: DEFAULT_EXCEPTIONS,
    format: "text",
    repository: process.env.GITHUB_REPOSITORY || "local/repository",
  };
  output = errorReport(options, error);
}

process.stdout.write(
  options.format === "json" ? `${JSON.stringify(output, null, 2)}\n` : textReport(output)
);
if (output.status !== "PASS") process.exitCode = 1;
