// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

// Structural Markdown extraction for the SecPal work-graph resolver.
//
// Reads a JSON array of issue bodies on stdin and writes a JSON array of
// per-body structural facts. It reports only what a standards-compliant parser
// sees; the canonical normalization procedure of docs/work-graph-contract.md
// section 4.1 is applied by the caller.
//
// Heading records are emitted only for real ATX headings at the document's top
// level, excluding headings inside fenced or indented code and inside any
// container block such as a blockquote or a list item.

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const MarkdownIt = require("markdown-it");

const parser = new MarkdownIt();

const mirrorPattern =
  /^[ \t]*(?:\*\*|__)?(parent|order|blocked by|blocks|depends on)(?:\*\*|__)?[ \t]*:/gim;

function textContent(token) {
  if (!token) {
    return "";
  }
  if (token.children) {
    return token.children.map(textContent).join("");
  }
  if (token.type === "softbreak" || token.type === "hardbreak") {
    return " ";
  }
  return token.content || "";
}

function hasContent(tokens, start) {
  for (let index = start; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token.type === "heading_open" && token.level === 0) {
      return false;
    }
    if (token.type === "hr") {
      return true;
    }
    if (
      (token.type === "inline" ||
        token.type === "fence" ||
        token.type === "code_block" ||
        token.type === "html_block") &&
      token.content.trim() !== ""
    ) {
      return true;
    }
  }
  return false;
}

function headings(tokens) {
  const records = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    // level 0 keeps the heading at the document's top level, and a `#` markup
    // keeps it an ATX heading rather than a setext one.
    if (token.type !== "heading_open" || token.level !== 0 || !token.markup.startsWith("#")) {
      continue;
    }
    records.push({
      text: textContent(tokens[index + 1]),
      hasContent: hasContent(tokens, index + 3),
    });
  }
  return records;
}

function relationshipMirrors(tokens) {
  const mirrors = new Set();
  for (let index = 1; index < tokens.length; index += 1) {
    const previous = tokens[index - 1];
    const token = tokens[index];
    if (token.type !== "inline" || previous.type !== "paragraph_open" || previous.level !== 0) {
      continue;
    }
    for (const match of token.content.matchAll(mirrorPattern)) {
      mirrors.add(match[1].toLowerCase());
    }
  }
  return [...mirrors].sort();
}

function hasStatusChecklist(tokens) {
  let listDepth = 0;
  for (const token of tokens) {
    if (token.type === "list_item_open") {
      listDepth += 1;
    } else if (token.type === "list_item_close") {
      listDepth -= 1;
    } else if (listDepth > 0 && token.type === "inline" && /\[[ xX]\]/.test(token.content)) {
      return true;
    }
  }
  return false;
}

function bodyFacts(body) {
  const tokens = parser.parse(body ?? "", {});
  return {
    headings: headings(tokens),
    relationshipMirrors: relationshipMirrors(tokens),
    // A task list is migration evidence only.  The audit never derives issue
    // state or relationships from it.
    hasStatusChecklist: hasStatusChecklist(tokens),
  };
}

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}
const bodies = JSON.parse(Buffer.concat(chunks).toString("utf8"));
process.stdout.write(JSON.stringify(bodies.map(bodyFacts)));
