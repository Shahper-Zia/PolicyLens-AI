# Number of Steps through Generic

## Purpose

This rule helps count generic or non-biologic step requirements for a target brand and indication from Prior Authorization policy chunks. Generic step requirements affect how easily the target therapy can be covered by requiring lower-cost or non-biologic therapies first.

## Extraction Rule

Count the number of non-biologic or generic steps required before the target drug can be approved.

Topical agents count as generic steps.

If a parent indication requires a step but does not name any brand or biologic, count that requirement as a generic step.

If preferred and non-preferred products are listed in the document and the selected drug is non-preferred, include universal criteria requiring steps through preferred alternatives. Steps that explicitly mention biologics or targeted drugs count as branded steps, not generic steps. Steps with no such specification count as generic steps.

## Counting Logic

Combine universal criteria that apply generally with indication-specific or brand-specific criteria. Treat universal criteria and indication/brand-specific criteria as both required when both are present.

For the target brand and indication if any requirement is mentioned about a step which is non branded in nature for example:mention of topical agents a requirement for the target brand to be covered that counts as a generic step.

If multiple steps are mentioned and the steps are joined with OR think of the least restrictive path which means the path where covering the the target drug brand is easiest.
Only consider generic/non branded steps.

Count only generic or non-biologic steps. Do not count phototherapy steps in this parameter. Do not count branded or biologic steps in this parameter.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

## Output Guidance

Return the numeric count of generic or non-biologic steps. Output `NA` if no generic or non-biologic steps are required in the available chunks.
