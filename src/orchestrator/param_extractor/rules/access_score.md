# Access Score

## Purpose

This rule helps estimate how easy it is for a pharma company to get the target brand covered by the insurance company under the Prior Authorization policy.

## Scoring Rule

Assign an Access Quality score from `0` to `100` using the extracted policy parameters for the target brand and PsO/Psoriasis.

Use the following framework:

- `0`: No access.
- `25`: Restricted access compared with FDA guidelines.
- `50`: Parity with FDA label.
- `75`: Preferred access compared with FDA label.
- `100`: Best possible access compared with competitors, with no meaningful restrictions applied.

## Output Guidance

Return a numeric score from `0` to `100` and briefly explain which extracted parameters drove the score.
