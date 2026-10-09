// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { pathToFileURL } from "node:url";

// Resolve through the consumers so a nested vulnerable copy cannot be hidden
// by a patched package installed at the repository root.
const require = createRequire(import.meta.url);
const cliPath = require.resolve("markdownlint-cli");
const cliRequire = createRequire(cliPath);
const lintRequire = createRequire(cliRequire.resolve("markdownlint"));
const { micromark } = await import(pathToFileURL(lintRequire.resolve("micromark")));
const { math, mathHtml } = await import(
  pathToFileURL(lintRequire.resolve("micromark-extension-math"))
);

function renderMath(source, options) {
  return micromark(source, { extensions: [math()], htmlExtensions: [mathHtml(options)] });
}

test("the lint toolchain's math extension renders inline and block expressions", () => {
  const html = renderMath("Inline $x^2$.\n\n$$\n\\frac{1}{2}\n$$\n");
  assert.match(html, /class="math math-inline"/);
  assert.match(html, /class="math math-display"/);
  assert.match(html, /class="katex"/);
  assert.match(html, /class="mfrac"/);
});

test("inherited trust cannot enable unsafe links in math output", () => {
  // GHSA-238p-pmpm-9mq7 requires pre-existing prototype pollution.
  const source = "$\\href{javascript:alert(1)}{click}$";
  assert.doesNotMatch(renderMath(source), /href="javascript:/);
  assert.match(renderMath(source, { trust: true }), /href="javascript:/);

  const original = Object.getOwnPropertyDescriptor(Object.prototype, "trust");
  let html;
  try {
    Object.defineProperty(Object.prototype, "trust", {
      configurable: true,
      writable: true,
      value: true,
    });
    html = renderMath(source);
  } finally {
    if (original) {
      Object.defineProperty(Object.prototype, "trust", original);
    } else {
      delete Object.prototype.trust;
    }
  }
  assert.doesNotMatch(html, /href="javascript:/);
});

test("markdownlint-cli applies TOML configuration and still rejects rule violations", () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "secpal-markdown-toolchain-"));
  try {
    fs.writeFileSync(path.join(workspace, "config.toml"), "default = false\nMD001 = true\n");
    const run = (content) => {
      fs.writeFileSync(path.join(workspace, "input.md"), content);
      const result = spawnSync(process.execPath, [cliPath, "--config", "config.toml", "input.md"], {
        cwd: workspace,
        encoding: "utf8",
        timeout: 10000,
      });
      assert.ifError(result.error);
      return result;
    };
    // Missing final newline would fail MD047 if the TOML settings were ignored.
    const valid = run("# Title\n\n## Child");
    assert.equal(valid.status, 0, valid.stderr);
    const invalid = run("# Title\n\n### Skipped\n");
    assert.equal(invalid.status, 1, invalid.stderr);
    assert.match(invalid.stderr, /MD001/);
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
});
