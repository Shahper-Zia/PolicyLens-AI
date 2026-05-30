# Initial Authorization Duration (in months)

## Purpose

This rule helps extract the initial authorization duration for the target brand and indication from Prior Authorization policy chunks.

## Extraction Rule

Extract the time period for which coverage is initially granted upon Prior Authorization approval. This is typically expressed in months, such as `6 months` or `12 months` or any number of months, and may vary by product, indication/class, or payer.

## What to Look For

Look for initial approval, initial authorization, initial coverage, authorization period, approval duration, or PA approval duration language.

## Output Guidance

Return the duration in months when documented.

If PA approval applies to PsO/Psoriasis but the initial authorization duration is not specified, return `Unspecified`.

If no applicable initial authorization information is documented in the available chunks, return `NA`.
