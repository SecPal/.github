<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Forms

Forms should be predictable, accessible, and explicit about required input, validation, errors, and submission state. Product repositories own schemas, validation libraries, and component APIs.

## Structure

Use standard form components from the product repository's chosen UI stack before creating custom controls. Each input must have a visible label or an accessible name when a visible label is not appropriate.

Form fields should support:

- label text that identifies the requested value
- optional description text for constraints, examples, or consequences
- clear required or optional state where ambiguity would affect completion
- visible validation and error messages near the affected field
- disabled, read-only, loading, and success states when those states are possible

## Validation And Errors

Validation should explain what failed and how to fix it. Avoid generic error text when the system can identify a specific missing, invalid, conflicting, or out-of-range value.

Error states must not rely on color alone. Pair color with text, iconography, layout, or another non-color cue. Error messages should be announced to assistive technology when validation happens after user input or submission.

## Keyboard Behavior

Forms must support keyboard navigation in the expected reading order. Focus should move predictably through fields, groups, helper actions, and submission controls.

Visible focus states are required for inputs, checkboxes, radios, switches, buttons, comboboxes, selects, date pickers, file pickers, and custom controls. Keyboard users must be able to open, operate, and close popovers or menus used by form fields.

## Submission

Primary and secondary actions should be clearly distinguished. Destructive form actions need explicit labels and confirmation when the outcome is hard to reverse.

During submission, prevent duplicate actions where needed and expose progress without removing the user's ability to understand the current state. Success, warning, and failure status must include text and must not rely on color alone.
