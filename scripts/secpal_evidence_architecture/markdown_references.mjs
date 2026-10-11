// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

// Resolve only the owning checkout's dependency installation, never an
// ancestor checkout or a process-global module search path.
const require = createRequire(import.meta.url);
const packagePath = fileURLToPath(new URL("../../node_modules/markdown-it", import.meta.url));
const MarkdownIt = require(packagePath);

const chunks = [];
let inputBytes = 0;
for await (const chunk of process.stdin) {
  inputBytes += chunk.length;
  if (inputBytes > 1048576) process.exit(2);
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
  !(
    typeof request.markdown === "string" ||
    (Array.isArray(request.documents) &&
      request.documents.length <= 100 &&
      request.documents.every((item) => typeof item === "string"))
  )
) {
  process.stderr.write("reference parser input has unknown or missing fields\n");
  process.exit(2);
}

// HTML parsing keeps comments in dedicated html_block/html_inline tokens so
// code-looking references inside comments never become operative references.
// Nothing is rendered or executed.
const markdown = new MarkdownIt({ html: true, linkify: false, typographer: false });
function extractReferences(text) {
  const references = [];
  let blockquoteDepth = 0;
  for (const token of markdown.parse(text, {})) {
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

  return references;
}

const references =
  typeof request.markdown === "string"
    ? extractReferences(request.markdown)
    : request.documents.map(extractReferences);
process.stdout.write(JSON.stringify({ references }));
