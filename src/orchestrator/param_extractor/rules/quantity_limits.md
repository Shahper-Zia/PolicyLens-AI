# Quantity Limits

## Purpose

This rule helps extract quantity limits for the target brand and PsO/Psoriasis from Prior Authorization policy chunks.

## Extraction Rule

Extract only limits that are explicitly stated as a quantity limit.

## What to Look For

Look for text that explicitly says `quantity limit`, `quantity limits`, or equivalent quantity-limit language.

Capture the stated quantity, unit, and time period when present.

## Exclusions

Do not capture text that is explicitly described as `dosage`.

Do not capture text that is explicitly described as `dosing limit`.

Do not infer a quantity limit from dosing instructions unless the policy explicitly frames it as a quantity limit.

## Output Guidance

Return the quantity limit as documented. If no explicit quantity limit is documented in the available chunks, return `NA`.
