#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: CC0-1.0

/**
 * Regression guard: fail if docs/openapi.yaml omits any verified API operation
 * (US-001 matrix + email verification resend + employee documents).
 *
 * Usage: node scripts/check-openapi-verified-endpoints.mjs <path-to-openapi.yaml>
 */

import fs from "fs";
import path from "path";
import yaml from "js-yaml";

/** @type {readonly [method: string, pathTemplate: string][]} */
const REQUIRED_OPERATIONS = [
  ["post", "/auth/email/verification-notification"],
  ["get", "/employees/{employee}/documents"],
  ["post", "/employees/{employee}/documents"],
  ["get", "/employees/{employee}/documents/{document}"],
  ["get", "/employees/{employee}/documents/{document}/download"],
  ["delete", "/employees/{employee}/documents/{document}"],
  ["get", "/qualifications"],
  ["post", "/qualifications"],
  ["get", "/qualifications/{qualification}"],
  ["patch", "/qualifications/{qualification}"],
  ["delete", "/qualifications/{qualification}"],
  ["get", "/employees/{employee}/qualifications"],
  ["post", "/employees/{employee}/qualifications"],
  ["get", "/employee-qualifications/{employeeQualification}"],
  ["patch", "/employee-qualifications/{employeeQualification}"],
  ["delete", "/employee-qualifications/{employeeQualification}"],
];

const target = process.argv[2];
if (!target) {
  console.error("Usage: node scripts/check-openapi-verified-endpoints.mjs <path-to-openapi.yaml>");
  process.exit(2);
}

const abs = path.resolve(target);
let raw;
try {
  raw = fs.readFileSync(abs, "utf8");
} catch (e) {
  console.error(`Cannot read OpenAPI file: ${abs}`);
  console.error(e);
  process.exit(2);
}

let doc;
try {
  doc = yaml.load(raw);
} catch (e) {
  console.error(`Invalid YAML: ${abs}`);
  console.error(e);
  process.exit(2);
}

const paths = doc && typeof doc.paths === "object" && doc.paths !== null ? doc.paths : {};
const missing = [];

for (const [method, pathKey] of REQUIRED_OPERATIONS) {
  const op = paths[pathKey];
  if (!op || op[method] == null) {
    missing.push(`${method.toUpperCase()} ${pathKey}`);
  }
}

if (missing.length) {
  console.error("OpenAPI verified-endpoint presence guard failed. Missing operations:");
  for (const line of missing) {
    console.error(`  - ${line}`);
  }
  process.exit(1);
}

console.log(`Verified-endpoint presence guard OK (${REQUIRED_OPERATIONS.length} operations).`);
