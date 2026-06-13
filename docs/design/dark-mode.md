<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Dark Mode

SecPal product surfaces that support dark mode must use class-based dark mode and theme tokens. Repository-specific frameworks and token names may vary, but the behavior must be explicit and portable.

## Mode Selection

Use class-based dark mode, such as a `dark` class on the root application or document element. Do not depend only on `prefers-color-scheme` media queries for product UI state. System preference may initialize the setting, but the active mode should be represented by a class so application state, screenshots, tests, and generated previews are deterministic.

## Token Requirements

Dark mode must be implemented through design tokens or CSS variables rather than one-off color overrides scattered through components.

Each product surface should define token concepts for:

- `background` - default page or app background
- `foreground` - default readable text and icon color
- `card` - elevated or grouped content surfaces
- `muted` - subdued backgrounds and secondary text contexts
- `border` - dividers, outlines, and low-emphasis separators
- `primary` - primary action and selected-state color
- `accent` - secondary brand or product emphasis color
- `destructive` - destructive actions and serious error emphasis
- `ring` - focus rings and keyboard-visible interaction outlines

Product repositories may add more tokens for charts, sidebars, overlays, and document-specific output, but these concepts form the shared minimum vocabulary.

## Theme Behavior

Light and dark themes should preserve semantic meaning. Changing modes should not change whether an action is primary, destructive, muted, or informational.

Focus rings must remain visible in both modes. Borders and muted surfaces should be strong enough to separate dense operational content without creating heavy visual noise. Generated documents that do not support interactive theme switching should still derive colors from explicit theme tokens when a dark variant is produced.
