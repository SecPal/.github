// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

// Structural heading extraction for the SecPal work-graph resolver.
//
// Reads a JSON array of issue bodies on stdin and writes a JSON array of
// per-body heading records. It reports only what a standards-compliant parser
// sees; the canonical normalization procedure of docs/work-graph-contract.md
// section 4.1 is applied by the caller.
//
// A record is emitted for every real ATX heading at the document's top level,
// which excludes headings inside fenced or indented code and inside any
// container block such as a blockquote or a list item.

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const MarkdownIt = require("markdown-it");

const parser = new MarkdownIt();

function textContent(inlineToken) {
  if (!inlineToken || !inlineToken.children) {
    return inlineToken ? inlineToken.content : "";
  }
  return inlineToken.children
    .map((child) => {
      if (child.type === "text" || child.type === "code_inline") {
        return child.content;
      }
      if (child.type === "softbreak" || child.type === "hardbreak") {
        return " ";
      }
      return "";
    })
    .join("");
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

function headings(body) {
  const tokens = parser.parse(body ?? "", {});
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

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}
const bodies = JSON.parse(Buffer.concat(chunks).toString("utf8"));
process.stdout.write(JSON.stringify(bodies.map(headings)));
