<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Components

SecPal and GuardGuide application UI should use a shared web component stack so product surfaces remain consistent while implementation details stay in the owning repositories.

## Standard Stack

The standard application UI stack is:

- shadcn/ui for component composition and reusable application patterns
- Radix UI for accessible primitives such as dialogs, dropdowns, popovers, menus, tabs, tooltips, and sheets
- Tailwind CSS for utility styling and token-backed visual implementation
- Lucide icons for standard interface iconography

Product repositories own installation, file layout, build configuration, component APIs, and token values. These shared standards define the approved stack and expected behavior, not a central component package.

## Component Selection

Prefer standard shadcn/ui and Radix-based components before adding custom replacements. Do not introduce parallel UI libraries, ad hoc component kits, or one-off replacements for standard controls unless the owning repository documents a specific product need.

Use Lucide icons for common UI actions and navigation where an appropriate icon exists. Do not mix unrelated icon libraries for ordinary actions such as search, settings, filters, save, edit, delete, expand, close, or navigation.

## Composition Rules

Components should preserve consistent spacing, focus states, disabled states, loading states, validation states, and dark-mode behavior. Product-specific styling may adapt the presentation, but it should not remove expected accessibility or interaction behavior from the underlying component.

Reusable application components should support labels, descriptions, empty states, error states, and status indicators without relying on color alone.

## Exceptions

Use custom components when the standard stack does not cover a specialized workflow, visualization, editor, map, chart, or native platform surface. Keep exceptions focused and document why the standard component was not sufficient.

Do not use a custom exception to bypass keyboard navigation, visible focus states, accessible names, contrast requirements, or Radix-based behavior for dialogs, dropdowns, sheets, and menus.
