// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../scripts/secpal-polyscope-workspace-ws.js", import.meta.url),
  "utf8"
);
function client(socketUrl = "ws://127.0.0.1:4321/ws?client=secpal-workspace-bridge") {
  const handlers = new Map();
  const output = [];
  const sent = [];
  let timeout;
  const payload = {
    message: {
      type: "worktree.create_from_issue",
      repoId: "832b2ca0",
      issue: { number: 1224 },
    },
    beforeIds: ["old"],
    expectedIssue: 1224,
    expectedPr: null,
    timeoutMs: 120000,
    socketUrl,
  };
  class Socket {
    constructor(url) {
      assert.equal(url, socketUrl);
    }
    addEventListener(name, handler) {
      handlers.set(name, handler);
    }
    send(value) {
      sent.push(JSON.parse(value));
    }
    close() {}
  }
  const context = {
    WebSocket: Socket,
    process: {
      argv: ["node", "helper", JSON.stringify(payload)],
      stdout: { write: (value) => output.push(JSON.parse(value)) },
      exit() {},
    },
    setTimeout(fn, ms) {
      if (ms === 120000) timeout = fn;
      return ms;
    },
    clearTimeout() {},
  };
  vm.runInNewContext(source, context);
  return {
    open: () => handlers.get("open")(),
    message: (message) => handlers.get("message")({ data: JSON.stringify(message) }),
    timeout: () => timeout(),
    output,
    sent,
  };
}

test("native creation binds repository, issue, active state and new ID", () => {
  const bridge = client();
  bridge.open();
  assert.equal(bridge.sent.length, 1);
  for (const workspace of [
    { id: "old", issue_number: 1224, status: "active" },
    { id: "foreign", issue_number: 999, status: "active" },
    { id: "paused", issue_number: 1224, status: "paused" },
  ]) {
    bridge.message({ type: "worktree.list", repoId: "832b2ca0", worktrees: [workspace] });
    assert.equal(bridge.output.length, 0);
  }
  const created = { id: "73355d10", issue_number: 1224, status: "active" };
  bridge.message({ type: "worktree.list", repoId: "foreign", worktrees: [created] });
  assert.equal(bridge.output.length, 0);
  bridge.message({ type: "worktree.list", repoId: "832b2ca0", worktrees: [created] });
  assert.equal(bridge.output[0].id, created.id);
});

test("multiple new candidates and timeout are failures rather than retries", () => {
  const bridge = client();
  bridge.message({
    type: "worktree.list",
    repoId: "832b2ca0",
    worktrees: ["one", "two"].map((id) => ({ id, issue_number: 1224, status: "active" })),
  });
  assert.equal(bridge.output[0].error, "polyscope-create-ambiguous");
  const timed = client();
  timed.open();
  timed.timeout();
  assert.equal(timed.sent.length, 1);
  assert.equal(timed.output[0].error, "polyscope-create-timeout");
});

test("configured bridge uses its supplied origin and returns a closed rejection", () => {
  const bridge = client("ws://127.0.0.1:5432/ws?client=secpal-workspace-bridge");
  bridge.open();
  bridge.message({ type: "worktree.create_error", error: "private server diagnostic" });
  assert.deepEqual(bridge.output, [{ error: "polyscope-create-rejected" }]);
});
