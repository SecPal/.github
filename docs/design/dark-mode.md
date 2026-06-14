<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Dark Mode

SecPal product surfaces that support dark mode should use an explicit, testable theme model and a documented token vocabulary that fits the owning platform. Repository-specific frameworks and implementation details vary, but the behavior should be explicit and portable.

## Mode Selection

Do not leave dark-mode behavior implicit. System preference may initialize the setting, but the owning repository should document how the active mode is represented, persisted, previewed, and tested so application state, screenshots, tests, and generated previews remain deterministic on that platform.

## Token Requirements

Dark mode should be implemented through design tokens or equivalent platform-native theme abstractions rather than one-off color overrides scattered through components.

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

Focus rings must remain visible in both modes. Borders and muted surfaces should be strong enough to separate dense operational content without creating heavy visual noise. Generated documents and native surfaces that do not support interactive theme switching should still derive colors from explicit theme tokens or equivalent theme abstractions when a dark variant is produced.
