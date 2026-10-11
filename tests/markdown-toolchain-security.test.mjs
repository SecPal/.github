// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { micromark } from "micromark";
import { math, mathHtml } from "micromark-extension-math";
import { lint } from "markdownlint/sync";

const require = createRequire(import.meta.url);
const cliPath = require.resolve("markdownlint-cli");
const mathRequire = createRequire(require.resolve("micromark-extension-math"));
const katex = mathRequire("katex");

test("all locked smol-toml copies include the GHSA-r4xh-jqrq-34v2 fix", () => {
  const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
  const copies = Object.entries(lock.packages).filter(([path]) => path.endsWith("/smol-toml"));
  assert.ok(copies.length > 0);
  for (const [path, { version }] of copies) {
    const [major, minor] = version.split(".").map(Number);
    assert.ok(major > 1 || (major === 1 && minor >= 9), `${path}@${version} is vulnerable`);
  }
});

test("the CLI still accepts TOML configuration and enforces its rules", () => {
  const workspace = mkdtempSync(join(tmpdir(), "secpal-markdown-toml-"));
  try {
    const config = join(workspace, "lint.toml");
    const document = join(workspace, "example.md");
    writeFileSync(config, "default = false\n[MD013]\nline_length = 20\n");
    writeFileSync(document, "# Example\n\nShort paragraph.\n");
    execFileSync(process.execPath, [cliPath, "--config", config, "--", document], {
      cwd: workspace,
      encoding: "utf8",
    });
    writeFileSync(document, "# Example\n\nThis paragraph exceeds the configured maximum length.\n");
    const result = spawnSync(process.execPath, [cliPath, "--config", config, "--", document], {
      cwd: workspace,
      encoding: "utf8",
    });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /MD013/);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("KaTeX ignores inherited trust while preserving explicitly trusted rendering", () => {
  const expression = String.raw`\href{https://example.invalid/}{x}`;
  for (const options of [{}, Object.create({ trust: true })]) {
    assert.doesNotMatch(katex.renderToString(expression, options), /<a href=/);
  }
  assert.match(katex.renderToString(expression, { trust: true }), /<a href=/);
});

test("the math extension and markdownlint remain compatible with patched KaTeX", () => {
  const markdown = "# Example\n\n$x^2$\n\n$$\ny^2\n$$\n";
  const html = micromark(markdown, { extensions: [math()], htmlExtensions: [mathHtml()] });
  assert.match(html, /class="katex"/);
  assert.match(html, /class="katex-display"/);
  assert.doesNotMatch(html, /katex-error/);
  assert.deepEqual(lint({ strings: { "math.md": markdown } })["math.md"], []);
});
