# Reauthorization Duration (in months)

## Purpose

This rule helps extract the reauthorization duration for the target brand and PsO/Psoriasis from Prior Authorization policy chunks. Reauthorization duration affects access because shorter renewal periods require more frequent documentation and payer review.

## Extraction Rule

Extract the length of time for which reauthorization is granted after the initial approval period ends.

## What to Look For

Look for reauthorization, renewal, continuation approval, continuation of therapy, or continued coverage duration language.

The duration is often expressed in months, such as `6 months` or `12 months`.

## Output Guidance

Return the reauthorization duration in months when documented.

If reauthorization is required but the duration is not specified, return `Unspecified`.

If no applicable reauthorization duration is documented in the available chunks, return `NA`.
