// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

"use strict";

const packagePath = process.argv[2];

if (!packagePath) {
  process.exit(2);
}

try {
  const yaml = require(require.resolve(packagePath));
  if (typeof yaml.load !== "function") {
    process.exit(1);
  }
} catch (_error) {
  process.exit(1);
}
