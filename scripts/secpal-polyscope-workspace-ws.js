#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

const payload = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const before = new Set(payload.beforeIds || []);
const expectedPr = payload.expectedPr ?? null;
const expectedIssue = payload.expectedIssue ?? null;
const timeoutMs = payload.timeoutMs || 120000;

let done = false;
const socket = new WebSocket(
  payload.socketUrl || "ws://127.0.0.1:4321/ws?client=secpal-workspace-bridge"
);
const timer = setTimeout(() => finish(2, { error: "polyscope-create-timeout" }), timeoutMs);

function finish(code, value) {
  if (done) return;
  done = true;
  clearTimeout(timer);
  process.stdout.write(JSON.stringify(value) + "\n");
  try {
    socket.close();
  } catch (_) {}
  setTimeout(() => process.exit(code), 10);
}

socket.addEventListener("open", () => socket.send(JSON.stringify(payload.message)));
socket.addEventListener("error", () => finish(2, { error: "polyscope-bridge-unavailable" }));
socket.addEventListener("message", (event) => {
  let message;
  try {
    message = JSON.parse(String(event.data));
  } catch (_) {
    return;
  }
  if (message.type === "worktree.create_error" || message.type === "error") {
    const scopedRejection =
      message.type === "worktree.create_error" && message.repoId === payload.message.repoId;
    finish(2, {
      error: scopedRejection ? "polyscope-create-rejected" : "polyscope-create-unverified",
    });
    return;
  }
  if (message.type !== "worktree.list" || message.repoId !== payload.message.repoId) return;
  const matching = (message.worktrees || []).filter((workspace) => {
    if (before.has(workspace.id)) return false;
    if (expectedPr !== null && workspace.pr_number !== expectedPr) return false;
    if (expectedIssue !== null && workspace.issue_number !== expectedIssue) return false;
    return workspace.status === "active";
  });
  if (matching.length === 1) finish(0, matching[0]);
  if (matching.length > 1) finish(2, { error: "polyscope-create-ambiguous" });
});
