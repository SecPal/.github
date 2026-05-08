#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

PR_TITLE="${PR_TITLE:-}"
PR_BODY="${PR_BODY:-}"

if [ -z "${PR_TITLE//[[:space:]]/}" ] && [ -z "${PR_BODY//[[:space:]]/}" ]; then
  echo 'Pull request title or body is required for PR language validation.' >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo 'Node.js is required to validate PR title/body language.' >&2
  exit 1
fi

node <<'NODE'
const title = String(process.env.PR_TITLE || '');
const body = String(process.env.PR_BODY || '');

const strongMarkers = [
  { label: 'einladung', regex: /\beinladung(?:s)?\b/u },
  { label: 'abgleichen', regex: /\babgleichen\b/u },
  { label: 'aktualisiert', regex: /\baktualisiert\b/u },
  { label: 'behoben', regex: /\bbehoben\b/u },
  { label: 'hinzugefügt', regex: /\bhinzugef(?:ü|u)gt\b/u },
  { label: 'weitere repos', regex: /\bweitere\s+repos\b/u },
  { label: 'pflichtangaben', regex: /\bpflichtangaben\b/u },
  { label: 'persönliche', regex: /\bpers(?:ö|o)nliche\b/u },
  { label: 'erforderlich', regex: /\berforderlich\b/u },
  { label: 'wichtig', regex: /\bwichtig\b/u },
];

const softMarkers = [
  { label: 'inhalte', regex: /\binhalte\b/u },
  { label: 'unterstützte', regex: /\bunterst(?:ü|u)tzte\b/u },
  { label: 'schritte', regex: /\bschritte\b/u },
  { label: 'abschnitte', regex: /\babschnitte\b/u },
  { label: 'belege', regex: /\bbelege\b/u },
  { label: 'sowie', regex: /\bsowie\b/u },
  { label: 'ohne', regex: /\bohne\b/u },
];

const germanCharacterMarker = { label: 'umlaut-or-esszett', regex: /[äöüß]/u };

function stripGeneratedSections(markdown) {
  return markdown
    .replace(/<!--\s*CURSOR_SUMMARY\s*-->[\s\S]*?<!--\s*\/CURSOR_SUMMARY\s*-->/giu, ' ')
    .replace(/<!--[^]*?-->/g, ' ')
    .replace(/```[^]*?```/g, ' ')
    .replace(/`[^`\n]+`/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, ' ');
}

function normalize(text) {
  return stripGeneratedSections(text)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function findLabels(text, markers) {
  return markers.filter((marker) => marker.regex.test(text)).map((marker) => marker.label);
}

function unique(values) {
  return [...new Set(values)];
}

function classify(text, { titleThreshold, bodyThreshold, strongThreshold }) {
  const normalized = normalize(text);
  const strong = findLabels(normalized, strongMarkers);
  const soft = findLabels(normalized, softMarkers);
  const germanCharacters = germanCharacterMarker.regex.test(normalized) ? [germanCharacterMarker.label] : [];
  const total = unique([...strong, ...soft, ...germanCharacters]);

  return {
    strong,
    soft,
    germanCharacters,
    total,
    titleLikelyGerman: germanCharacters.length > 0 || strong.length >= strongThreshold || total.length >= titleThreshold,
    bodyLikelyGerman: germanCharacters.length > 0 || strong.length >= strongThreshold || total.length >= bodyThreshold,
  };
}

const titleResult = classify(title, { titleThreshold: 2, bodyThreshold: 3, strongThreshold: 1 });
const bodyResult = classify(body, { titleThreshold: 2, bodyThreshold: 3, strongThreshold: 2 });

if (!titleResult.titleLikelyGerman && !bodyResult.bodyLikelyGerman) {
  process.exit(0);
}

console.error('PR title/body must be in English.');
console.error('This check intentionally blocks only obvious German PR title/body markers to keep false positives low.');

if (titleResult.titleLikelyGerman) {
  console.error(`- title markers: ${titleResult.total.join(', ')}`);
}

if (bodyResult.bodyLikelyGerman) {
  console.error(`- body markers: ${bodyResult.total.join(', ')}`);
}

process.exit(1);
NODE
