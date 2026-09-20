<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Naming

Use these names exactly in public and contributor-facing materials.

## Required Names

| Context                          | Use                     | Do not use as a current name                                          |
| -------------------------------- | ----------------------- | --------------------------------------------------------------------- |
| Organization, company, and brand | `SecPal`                | `Secpal`, `SecPAL`                                                    |
| Main product                     | `SecPal`                | `SecPal Core`, `SecPal Operations`, `SecPal Guard`, `SecPal Platform` |
| Product-family umbrella          | `SecPal product family` | `SecPal Suite` as a formal name                                       |
| Assure specialist product        | `SecPal Assure`         | `Assure` when the SecPal relationship is unclear                      |
| Visit specialist product         | `SecPal Visit`          | `Visit` when the SecPal relationship is unclear                       |

## Public Copy Rules

- Use `SecPal` for both the organization/brand and the main product. Make the
  intended meaning clear from nearby context instead of adding a suffix.
- Use `SecPal product family`, or a semantically equivalent surface-appropriate
  phrase, when the umbrella meaning needs to be explicit.
- Use `SecPal Assure` and `SecPal Visit` when introducing the specialist
  products or where the family relationship is not already clear.
- `Assure` and `Visit` are acceptable in nearby references only where the SecPal
  relationship remains unambiguous.
- Do not abbreviate the approved product names.
- Do not use or revive `GuardGuide`, `GuardGuide by SecPal`, `VisitGuide`, or
  `VisitGuard` as current product brands. Preserve those strings where needed
  for truthful historical or technical evidence.
- Follow domain terminology rules from `docs/brand/terminology.md` for concepts
  such as customer locations and role names.
- Keep repository names, package names, domains, and code identifiers in their
  technical form when documenting existing commands, historical evidence, or
  file paths.
- Do not invent campaign names, editions, or abbreviations unless a brand
  authority adds them explicitly.

## Status Boundary

An approved product name is not proof of implementation, release, availability,
deployment, integration, or production qualification. Apply the
[Public Status Semantics](../public-status-semantics.md) to every stronger claim.

## Rationale

One family naming system keeps the SecPal relationship explicit without
manufacturing a suffix for the main product or turning independently operable
specialist products into unrelated brands.
