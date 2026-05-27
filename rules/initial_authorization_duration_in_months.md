# Initial Authorization Duration (in months)

## Purpose

This rule helps extract the initial authorization duration for the target brand and indication from Prior Authorization policy chunks. Shorter initial approval periods can indicate tighter utilization management and more restricted access.

## Extraction Rule

Extract the time period for which coverage is initially granted upon Prior Authorization approval.

## What to Look For

Look for initial authorization, initial approval, authorization duration, coverage duration, or approval period language tied to the first approval.

The duration is typically expressed in months, such as 6 months or 12 months.

## Output Guidance

Return the duration in months when documented.

If the policy indicates PA approval for psoriasis but does not specify the initial authorization duration, return `Unspecified`.

If no applicable initial authorization information is documented in the available chunks, return `NA`.
