// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import MarkdownIt from "markdown-it";

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}

let request;
try {
  request = JSON.parse(Buffer.concat(chunks).toString("utf8"));
} catch {
  process.stderr.write("reference parser input is not valid JSON\n");
  process.exit(2);
}

if (
  request === null ||
  typeof request !== "object" ||
  Array.isArray(request) ||
  Object.keys(request).length !== 1 ||
  typeof request.markdown !== "string"
) {
  process.stderr.write("reference parser input has unknown or missing fields\n");
  process.exit(2);
}

// HTML parsing keeps comments in dedicated html_block/html_inline tokens so
// code-looking references inside comments never become operative references.
// Nothing is rendered or executed.
const markdown = new MarkdownIt({ html: true, linkify: false, typographer: false });
const references = [];
let blockquoteDepth = 0;
for (const token of markdown.parse(request.markdown, {})) {
  if (token.type === "blockquote_open") {
    blockquoteDepth += 1;
    continue;
  }
  if (token.type === "blockquote_close") {
    blockquoteDepth -= 1;
    continue;
  }
  if (blockquoteDepth !== 0 || token.type !== "inline" || !token.children) {
    continue;
  }
  for (const child of token.children) {
    if (child.type === "code_inline") {
      references.push(child.content);
    } else if (child.type === "link_open") {
      const href = child.attrGet("href");
      if (href !== null) {
        references.push(href);
      }
    }
  }
}

process.stdout.write(JSON.stringify({ references }));
