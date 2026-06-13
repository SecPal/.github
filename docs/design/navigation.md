<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Navigation

SecPal and GuardGuide use top navigation as the default application shell. Navigation should help users understand product location, current context, available modules, and next actions without creating repository-specific routing rules in these shared standards.

## Desktop Pattern

The standard desktop pattern includes:

- a persistent topbar with product identity, primary destinations, global actions, and account or workspace controls
- an optional breadcrumb or context bar for entity hierarchy, parent routes, active workspace, or page-level actions
- a full-width work area for the active route
- module tabs where a route has peer-level subsections that users switch between frequently

Do not make a permanent left sidebar the default navigation pattern. A product repository may document a focused exception for a specialist surface, but the shared default remains top navigation.

## Topbar

The topbar should contain stable global destinations and controls. Keep labels short, use clear active states, and avoid placing page-specific filters or table controls in the global shell.

Topbar items should support keyboard navigation and visible focus states. Menus, dropdowns, and account controls should use Radix-based accessibility patterns as described in `docs/design/accessibility.md`.

## Breadcrumb And Context Bar

Use breadcrumbs when hierarchy matters, such as moving from an organization to a site to an entity. Use a context bar when users need persistent awareness of an active workspace, tenant, product area, or parent object.

Breadcrumbs and context bars are optional. Do not add them to routes where the topbar, page title, and content already make the location clear.

## Module Tabs

Use module tabs for peer views inside a route, such as overview, activity, settings, and history. Tabs should remain local to the current module and should not replace primary product navigation.

Tabs must have clear selected states, keyboard support, and labels that remain understandable outside color alone.

## Mobile Pattern

Mobile navigation should preserve the topbar and move secondary navigation into sheets. Use sheet navigation for primary destination lists, account controls, workspace switching, filters, and longer local navigation groups.

Mobile sheets should have an accessible title, predictable close behavior, focus trapping while open, focus return on close, and touch targets sized for comfortable use.
