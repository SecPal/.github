#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

node <<'NODE'
const MarkdownIt = require('markdown-it');

const body = process.env.PR_BODY || '';
const draft = process.env.PR_DRAFT;
const fail = (message) => {
  console.error(message);
  process.exit(1);
};
const missingEvidence = 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.';

if (draft !== 'true' && draft !== 'false') {
  fail('PR_DRAFT must be explicitly true (Draft) or false (Ready).');
}
if (!body.trim()) {
  fail('Pull request body is required for PR evidence validation.');
}

const tokens = new MarkdownIt('commonmark', { html: true }).parse(body, {});
const section = tokens.findIndex((token, index) =>
  token.type === 'heading_open' && token.level === 0 && token.markup === '##' &&
  tokens[index + 1]?.content === 'TDD / Validate-First Evidence');
if (section === -1) {
  fail('TDD / Validate-First Evidence section is required.');
}

const labels = [
  'Failing proof before implementation',
  'Passing proof after implementation',
  'Validate-first exception reference',
  'No executable change reason',
];
const fields = new Map();
let bulletList = false;
for (let index = section + 3; index < tokens.length; index += 1) {
  const token = tokens[index];
  if (token.type === 'heading_open' && token.level === 0) break;
  if (token.type === 'bullet_list_open' && token.level === 0) bulletList = true;
  if (token.type === 'bullet_list_close' && token.level === 0) bulletList = false;
  if (!bulletList || token.type !== 'inline' || token.level !== 3) continue;
  if (token.children.some((child) => child.type === 'html_inline' || child.type === 'image')) continue;
  const text = token.children.map((child) =>
    child.type === 'text' || child.type === 'code_inline' ? child.content :
      child.type === 'softbreak' || child.type === 'hardbreak' ? '\n' : '').join('');
  for (const label of labels) {
    if (text.startsWith(`${label}:`) && !fields.has(label)) {
      fields.set(label, text.slice(label.length + 1).trim());
    }
  }
}

const [failing, passing, exception, noExecutable] = labels.map((label) => fields.get(label) || '');
const empty = (value) => !value || /^(n\/?a(?:[\s\p{P}].*)?|none|not applicable)$/isu.test(value);
const placeholder = (value) => /^(TODO|TBD|REPLACE_WITH_(FAILING_PROOF|PASSING_PROOF|VALIDATE_FIRST_REFERENCE|NO_EXECUTABLE_CHANGE_REASON)|<[^<>]+>)$/i.test(value);
if ([failing, passing, exception, noExecutable].some(placeholder)) fail(missingEvidence);
if (!empty(exception)) {
  fail('This repository grants no validate-first exception. PR-body references cannot authorize one; use N/A.');
}
if (!empty(noExecutable)) process.exit(0);
if (!empty(failing) && (draft === 'true' || !empty(passing))) process.exit(0);
fail(`${missingEvidence}\nExecutable Drafts require fail-first proof; Ready PRs also require passing proof.`);
NODE
