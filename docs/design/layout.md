<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Layout

SecPal and GuardGuide application surfaces use a top navigation shell by default. Product repositories own route structure, breakpoints, and implementation details, but shared application layouts should follow the shell model in this document.

## Default Shell

Use a topbar as the persistent application shell. Do not use a permanent left sidebar as the default pattern for SecPal or GuardGuide.

The default desktop shell includes:

- a topbar for product identity, primary navigation, global actions, account controls, and theme or workspace controls where needed
- an optional breadcrumb or context bar below the topbar for location, parent entity, route context, and local actions
- a full-width work area that lets dense operational views use the available horizontal space
- module tabs inside the work area where a section needs peer-level views

Left navigation may be used only as a product-specific exception for a surface with a documented workflow need, such as a specialist administration area with many persistent peer sections. The owning repository should document the exception and keep the topbar as the main application anchor.

## Work Area

The work area should be full width within the application shell, with product-owned responsive constraints where readability or data density requires them. Avoid decorative page frames that reduce usable space for dashboards, tables, forms, audit trails, or operational workflows.

Use contained widths for reading-focused content, settings forms, and generated document previews when long line lengths would reduce comprehension. Do not apply narrow content widths globally to operational views.

## Page Structure

Standard pages should use this order:

- topbar
- optional breadcrumb or context bar
- page header with title and primary action when the route needs one
- optional module tabs
- primary content
- secondary panels, filters, or drawers only when they support the current workflow

Page headers should identify the current task or entity. Use the browser title rules in `docs/design/page-titles.md` for the corresponding document title.

## Mobile Layout

Mobile layouts keep the topbar as the shell anchor, then move secondary navigation and dense controls into sheets, drawers, collapsible filter regions, or route-level tabs. The main work area should remain readable without a permanent sidebar.

Use bottom actions sparingly for high-frequency mobile workflows. Destructive or complex actions should remain explicit, labeled, and reachable by keyboard and assistive technology.
