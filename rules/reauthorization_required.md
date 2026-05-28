# Reauthorization Required

## Purpose

This rule helps determine whether renewed approval is required after the initial coverage period expires. Reauthorization requirements affect access because providers may need to submit updated documentation to continue therapy.

## Extraction Rule

Determine whether reassessment and renewed approval are needed after the initial authorization period ends.

## What to Look For

Look for reauthorization, renewal, continuation approval, continuation of therapy, reassessment, or updated documentation requirements after the initial coverage period kind of terms..

## Decision Logic

Return `Yes` if the policy documents a reauthorization duration.

Return `Yes` if the policy documents reauthorization or continuation requirements.

Return `No` if the policy explicitly indicates no reauthorization is required.

Return `NA` if the available chunks do not provide enough information to determine whether reauthorization is required.

## Output Guidance

Return only `Yes`, `No`, or `NA`.
