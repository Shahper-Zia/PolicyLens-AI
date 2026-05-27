# TB Test Required

## Purpose

This rule helps determine whether a TB test is required before the target brand can be covered. TB testing requirements add clinical documentation burden and can affect ease of access.

## Extraction Rule

Extract whether the policy requires TB testing for approval of the concerned product.

## What to Look For

Look for explicit requirements for TB testing, tuberculosis testing, latent TB screening, TB test results, or similar documentation before approval.

## Output Guidance

Return `Yes` if TB testing is required.

Return `No` if the available chunks do not document a TB testing requirement.
