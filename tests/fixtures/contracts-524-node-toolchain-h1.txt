#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 SecPal Contributors
// SPDX-License-Identifier: MIT

import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve, dirname } from 'node:path'

import { load as loadYaml } from 'js-yaml'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const expectedMajor = '26'
const expectedEngine = '^26.0.0'
const requiredWorkflows = ['local-openapi-lint.yml', 'local-prettier.yml']

function requireInvariant(condition, message) {
  if (!condition) throw new Error(message)
}

export function validateNodeToolchain({
  runtimeVersion,
  nvmrc,
  packageJson,
  packageLock,
  workflows,
}) {
  requireInvariant(
    runtimeVersion.startsWith(`v${expectedMajor}.`),
    `Node.js ${expectedMajor} is required; found ${runtimeVersion}.`
  )
  requireInvariant(
    nvmrc.trim() === expectedMajor,
    `.nvmrc must select Node.js ${expectedMajor}.`
  )
  requireInvariant(
    packageJson.engines?.node === expectedEngine,
    `package.json engines.node must be ${expectedEngine}.`
  )
  requireInvariant(
    packageLock.packages?.['']?.engines?.node === expectedEngine,
    `package-lock.json root engines.node must be ${expectedEngine}.`
  )

  const found = new Set()
  for (const [name, workflow] of Object.entries(workflows)) {
    for (const job of Object.values(workflow?.jobs ?? {})) {
      for (const step of job?.steps ?? []) {
        if (!/^actions\/setup-node@[0-9a-f]{40}$/.test(step?.uses ?? ''))
          continue
        found.add(name)
        requireInvariant(
          step.with?.['node-version'] === expectedMajor,
          `${name} setup-node must select Node.js ${expectedMajor}.`
        )
      }
    }
  }
  for (const name of requiredWorkflows) {
    requireInvariant(
      found.has(name),
      `${name} must have a pinned setup-node step.`
    )
  }
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const read = (path) => readFileSync(resolve(root, path), 'utf8')
    const workflows = Object.fromEntries(
      readdirSync(resolve(root, '.github/workflows'), { withFileTypes: true })
        .filter((entry) => /\.ya?ml$/.test(entry.name))
        .map((entry) => {
          requireInvariant(
            entry.isFile(),
            `${entry.name} must be a regular file.`
          )
          return [entry.name, loadYaml(read(`.github/workflows/${entry.name}`))]
        })
    )
    validateNodeToolchain({
      runtimeVersion: process.version,
      nvmrc: read('.nvmrc'),
      packageJson: JSON.parse(read('package.json')),
      packageLock: JSON.parse(read('package-lock.json')),
      workflows,
    })
    console.log('Node.js toolchain selectors are coherent.')
  } catch (error) {
    console.error(`Error: ${error.message}`)
    process.exitCode = 1
  }
}
