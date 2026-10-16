#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

const payload = JSON.parse(process.argv[2]);
const before = new Set(payload.beforeIds || []);
const expectedPr = payload.expectedPr ?? null;
const expectedIssue = payload.expectedIssue ?? null;
const timeoutMs = payload.timeoutMs || 120000;

let done = false;
const socket = new WebSocket("ws://127.0.0.1:4321/ws?client=secpal-workspace-bridge");
const timer = setTimeout(
  () => finish(2, { error: "Polyscope workspace creation timed out" }),
  timeoutMs
);

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
socket.addEventListener("error", () =>
  finish(2, { error: "Polyscope WebSocket connection failed" })
);
socket.addEventListener("message", (event) => {
  let message;
  try {
    message = JSON.parse(String(event.data));
  } catch (_) {
    return;
  }
  if (message.type === "worktree.create_error" || message.type === "error") {
    finish(2, { error: message.error || message.message || "Polyscope creation failed" });
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
  if (matching.length > 1)
    finish(2, { error: "Polyscope returned multiple new matching workspaces" });
});
