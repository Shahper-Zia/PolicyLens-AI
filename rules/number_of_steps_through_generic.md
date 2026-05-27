# Number of Steps through Generic

## Purpose

This rule helps count generic or non-biologic step requirements for a target brand and indication from Prior Authorization policy chunks. Generic step requirements affect how easily the target therapy can be covered by requiring lower-cost or non-biologic therapies first.

## Extraction Rule

Count the number of non-biologic or generic steps required before the target drug can be approved.

Topical agents count as generic steps.

If a parent indication requires a step but does not name any brand or biologic, count that requirement as a generic step.

If preferred and non-preferred products are listed and the selected drug is non-preferred, include universal criteria requiring steps through preferred alternatives. Steps that explicitly mention biologics or targeted drugs count as branded steps, not generic steps. Steps with no such specification count as generic steps.

## Counting Logic

Combine universal criteria that apply generally with indication-specific or brand-specific criteria. Treat universal criteria and indication/brand-specific criteria as both required when both are present.

From the combined required criteria, identify the least restrictive approval path. If requirements appear in an OR statement, count the path with fewer required generic or non-biologic steps.

Count only generic or non-biologic steps. Do not count phototherapy steps in this parameter. Do not count branded or biologic steps in this parameter.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

## Output Guidance

Return the numeric count of generic or non-biologic steps. Output `NA` if no generic or non-biologic steps are required in the available chunks.
