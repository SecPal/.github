<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Components

SecPal and GuardGuide application UI should preserve consistent component behavior and accessibility expectations while runtime implementation choices stay in the owning repositories.

## Ownership Boundaries

This repository does not define a single required runtime UI stack for every SecPal surface. Product repositories own their framework, component library, styling system, icon set, installation steps, file layout, build configuration, component APIs, and token values.

Shared standards in this directory define cross-product expectations such as accessible interaction behavior, predictable states, and documentation boundaries. Repository-local instruction files may standardize specific stacks for individual products.

## Component Selection

Prefer the owning repository's documented component patterns before adding custom replacements. Do not introduce parallel component kits, ad hoc control libraries, or one-off replacements for standard controls unless the owning repository documents a specific product need.

Use one documented icon system per product surface for ordinary UI actions and navigation. Do not mix unrelated icon libraries for common actions such as search, settings, filters, save, edit, delete, expand, close, or navigation without a documented reason in the owning repository.

## Composition Rules

Components should preserve consistent spacing, focus states, disabled states, loading states, validation states, and dark-mode behavior. Product-specific styling may adapt the presentation, but it should not remove expected accessibility or interaction behavior from the underlying component.

Reusable application components should support labels, descriptions, empty states, error states, and status indicators without relying on color alone.

## Exceptions

Use custom components when the owning repository's standard patterns do not cover a specialized workflow, visualization, editor, map, chart, or native platform surface. Keep exceptions focused and document why the standard pattern was not sufficient.

Do not use a custom exception to bypass keyboard navigation, visible focus states, accessible names, contrast requirements, or expected accessible behavior for dialogs, dropdowns, sheets, tabs, and menus.
