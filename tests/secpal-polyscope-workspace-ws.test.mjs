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
const defaultSocketUrl = "ws://127.0.0.1:4321/ws?client=secpal-workspace-bridge";
function client(socketUrl, expectedSocketUrl = socketUrl ?? defaultSocketUrl) {
  const handlers = new Map();
  const inputHandlers = new Map();
  const output = [];
  const sent = [];
  const connections = [];
  const exitSignal = {};
  let exitCode;
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
      connections.push(url);
      assert.equal(url, expectedSocketUrl);
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
    require(name) {
      assert.fail(`unexpected module access: ${name}`);
    },
    URL,
    WebSocket: Socket,
    process: {
      argv: ["node", "helper"],
      stdin: {
        setEncoding(encoding) {
          assert.equal(encoding, "utf8");
        },
        on(name, handler) {
          inputHandlers.set(name, handler);
        },
      },
      stdout: { write: (value) => output.push(JSON.parse(value)) },
      exit(code) {
        exitCode = code;
        throw exitSignal;
      },
    },
    setTimeout(fn, ms) {
      if (ms === 120000) timeout = fn;
      return ms;
    },
    clearTimeout() {},
  };
  function runWithExit(fn) {
    try {
      fn();
    } catch (error) {
      if (error !== exitSignal) throw error;
    }
  }
  runWithExit(() => vm.runInNewContext(source, context));
  const input = JSON.stringify(payload);
  runWithExit(() => {
    inputHandlers.get("data")(input.slice(0, 17));
    inputHandlers.get("data")(input.slice(17));
    inputHandlers.get("end")();
  });
  return {
    open: () => handlers.get("open")(),
    message: (message) => handlers.get("message")({ data: JSON.stringify(message) }),
    timeout: () => timeout(),
    output,
    sent,
    connections,
    exitCode,
  };
}

test("the default endpoint and configured loopback transports remain available", () => {
  const bridge = client();
  bridge.open();
  assert.deepEqual(bridge.connections, [defaultSocketUrl]);
  assert.equal(bridge.sent.length, 1);
  for (const protocol of ["ws", "wss"]) {
    for (const host of ["127.0.0.1", "localhost", "[::1]"]) {
      for (const port of ["", ":1", ":5432", ":65535"]) {
        const url = `${protocol}://${host}${port}/ws?client=secpal-workspace-bridge`;
        const configured = client(url);
        configured.open();
        assert.deepEqual(configured.connections, [url]);
        assert.equal(configured.sent.length, 1);
      }
    }
  }
});

test("accepted endpoints are rebuilt as canonical loopback URLs", () => {
  const suffix = "/ws?client=secpal-workspace-bridge";
  for (const [input, expected] of [
    [`WS://LOCALHOST:05432${suffix}`, `ws://localhost:5432${suffix}`],
    [`ws://127.1:4321${suffix}`, defaultSocketUrl],
    [`ws://[0:0:0:0:0:0:0:1]:4321${suffix}`, `ws://[::1]:4321${suffix}`],
    [`ws://127.0.0.1:80${suffix}`, `ws://127.0.0.1${suffix}`],
    [`wss://127.0.0.1:443${suffix}`, `wss://127.0.0.1${suffix}`],
  ]) {
    const bridge = client(input, expected);
    bridge.open();
    assert.deepEqual(bridge.connections, [expected]);
    assert.equal(bridge.sent.length, 1);
  }
});

test("unsafe stdin endpoints fail before opening a socket or sending file data", () => {
  const suffix = "/ws?client=secpal-workspace-bridge";
  for (const url of [
    `ws://remote.invalid${suffix}`,
    `wss://remote.invalid${suffix}`,
    `ws://127.0.0.1.remote.invalid${suffix}`,
    `ws://localhost.remote.invalid${suffix}`,
    `ws://127.0.0.1@remote.invalid${suffix}`,
    `ws://192.0.2.1${suffix}`,
    `ws://0.0.0.0${suffix}`,
    `ws://[::]${suffix}`,
    `ws://[::ffff:192.0.2.1]${suffix}`,
    `http://127.0.0.1:4321${suffix}`,
    `https://127.0.0.1:4321${suffix}`,
    `file://localhost${suffix}`,
    `ws://user:private@127.0.0.1:4321${suffix}`,
    `ws://127.0.0.1:0${suffix}`,
    `ws://127.0.0.1:65536${suffix}`,
    `ws://127.0.0.1:4321${suffix}#private`,
    `ws://127.0.0.1:4321${suffix}&private=value`,
    "ws://127.0.0.1:4321/other?client=secpal-workspace-bridge",
    "ws://127.0.0.1:4321/ws?client=other",
    "ws://127.0.0.1:4321/ws",
    "private malformed input",
    "",
    null,
    false,
    4321,
    {},
    [defaultSocketUrl],
  ]) {
    const bridge = client(url);
    assert.deepEqual(bridge.connections, [], `connected to ${JSON.stringify(url)}`);
    assert.deepEqual(bridge.sent, []);
    assert.deepEqual(bridge.output, [{ error: "polyscope-bridge-unavailable" }]);
    assert.equal(bridge.exitCode, 2);
  }
});

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
  bridge.message({
    type: "worktree.create_error",
    repoId: "832b2ca0",
    error: "private server diagnostic",
  });
  assert.deepEqual(bridge.output, [{ error: "polyscope-create-rejected" }]);
});

test("unscoped, foreign and generic errors never authorize a create retry", () => {
  for (const message of [
    { type: "worktree.create_error" },
    { type: "worktree.create_error", repoId: "foreign" },
    { type: "error", repoId: "832b2ca0" },
  ]) {
    const bridge = client();
    bridge.open();
    bridge.message(message);
    assert.deepEqual(bridge.output, [{ error: "polyscope-create-unverified" }]);
  }
});
