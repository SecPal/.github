<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Tables

Tables are for comparing structured records, operational queues, audit history, and dense status views. Product repositories own data models, query behavior, and component APIs.

## Structure

Use semantic table structure where the content is tabular. Headers should identify each column clearly, and row actions should have accessible names that include enough context for assistive technology users.

Tables should support:

- readable column labels
- visible sorting state when sorting is available
- clear empty, loading, filtered-empty, and error states
- pagination, infinite loading, or virtualization when result size requires it
- responsive behavior that preserves key information on smaller screens

## Interaction

Interactive tables must support keyboard navigation for focusable cells, row actions, selection controls, menus, filters, and pagination. Visible focus states are required for every interactive element.

Row selection should not depend on row color alone. Use checkboxes, selected-state labels, counts, or other non-color cues. Status values should include text or icons with accessible labels, not only colored dots or badges.

## Filtering And Actions

Place table-specific filters and bulk actions near the table they affect, not in the global topbar. Use clear labels and expose active filters so users can understand why rows are included or excluded.

Destructive row or bulk actions should require confirmation when the action is hard to reverse. Disabled actions should explain the reason when the context is not obvious.

## Responsive Tables

On mobile, tables may transform into stacked rows, cards, or summary lists when horizontal scrolling would hide important actions or status. The transformed view should preserve labels, status text, keyboard access, and the same data meaning as the desktop table.
