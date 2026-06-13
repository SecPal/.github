<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Accessibility

SecPal and GuardGuide surfaces should be usable with keyboard navigation, assistive technology, high-contrast needs, and light or dark themes. Product repositories own testing tools and implementation details, but shared design decisions must preserve the requirements in this document.

## Core Requirements

Application interfaces must provide:

- keyboard access for all interactive controls and workflows
- visible focus states in light and dark mode
- sufficient contrast for text, icons, controls, focus rings, borders, and status indicators
- proper labels and descriptions for controls, fields, regions, dialogs, and status messages
- clear error states that explain what happened and how to recover
- status communication that does not rely on color alone

Use text, accessible labels, icons, shape, layout, or state messaging with color whenever status, validation, selection, or severity must be understood.

## Radix Patterns

Dialogs, dropdowns, sheets, menus, popovers, tabs, tooltips, and similar layered controls should use Radix-based accessibility patterns from the approved component stack. These patterns should preserve expected focus management, escape behavior, keyboard operation, accessible names, and focus return.

Do not replace Radix-based behavior with custom implementations unless the owning repository documents why the standard primitive cannot meet the workflow.

## Keyboard And Focus

Keyboard order should follow visual and reading order. Users must be able to reach, operate, and leave every control without a pointer.

Focus should be trapped only for modal surfaces such as dialogs and modal sheets. When a modal closes, focus should return to the element that opened it or another predictable recovery point.

## Labels And Messages

Controls need visible labels unless the surrounding context makes a visible label redundant and an accessible name is still provided. Icon-only buttons require accessible names and should expose tooltips or nearby context when the icon meaning is not universal.

Error, warning, success, loading, and empty states should be written as user-facing messages, not only visual decoration. Live updates that affect task completion should be announced to assistive technology.
