# Age

## Purpose

This rule helps extract the age eligibility requirement for the target brand and PsO/Psoriasis from Prior Authorization policy chunks.

## Extraction Rule

Extract whether the policy includes age-based eligibility criteria for the therapy. This can include minimum age thresholds, maximum age thresholds, or age-specific subpopulations for which the drug is approved or restricted.

## What to Look For

Look for explicit age restrictions such as `18 years of age or older`, `adult members`, `>=18`, pediatric thresholds, or other age eligibility language.

If the policy does not specify a numerical age threshold and instead says the therapy is covered according to FDA-labelled age, FDA-approved age, or FDA-approved indication, output `FDA labelled age`.

If the policy lists requirements for two or more age groups, capture the youngest applicable age group.

## Output Guidance

Return the age requirement exactly enough to preserve the policy meaning. If no age requirement is documented in the available chunks, return `NA`.
