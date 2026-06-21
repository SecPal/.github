<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Terminology

Use these domain terms consistently in product, documentation, and contributor-facing copy.

## Customer Locations

| Context                                                                 | Use       | Do not use |
| ----------------------------------------------------------------------- | --------- | ---------- |
| English domain term for a customer location where services are provided | `site`    | `object`   |
| English plural                                                          | `sites`   | `objects`  |
| German domain term for a customer building/location                     | `Objekt`  | `Object`   |
| German plural                                                           | `Objekte` | `Objects`  |

## Rule

- A customer location, building, campus, or service area is a `site` in English.
- In German domain language, the same concept may be called `Objekt` or `Objekte`.
- Do not translate German `Objekt` to English `object` when the meaning is a customer location.
- Reserve `object` for technical contexts such as programming, schemas, or license text like `object code`.

## Related Terms

| Context                                       | Use                                                |
| --------------------------------------------- | -------------------------------------------------- |
| Optional subdivision of a site                | `site area`                                        |
| German optional subdivision of a site         | `Objektbereich` or `Bereich`                       |
| Person responsible for a site in English copy | `Site Manager`                                     |
| Person responsible for a site in German copy  | `Objektleiter` or repository-specific role wording |

## Rationale

`Site` is the correct English domain term for the place where security services are delivered. It is clearer internationally and avoids confusion with the programming term `object`.
