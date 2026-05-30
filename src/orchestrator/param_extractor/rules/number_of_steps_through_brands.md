# Number of Steps through Brands

## Purpose

This rule helps count branded or biologic step requirements for the target brand and indication from Prior Authorization policy chunks. More branded steps generally indicate more restrictive access before the target therapy can be covered.

## Extraction Rule

Count the number of branded, biologic, targeted, or named drug steps required before the target drug can be approved.

A preferred ustekinumab product, preferred adalimumab product, biosimilar, biologic, targeted synthetic therapy, or any other named non-generic product counts as a branded/biologic step.

If the policy references an indication/class/category of drugs and the target brand belongs to that indication/class/category, the indication/class-level step applies to the target brand. An indication/class can include multiple brands.

## Counting Logic

Combine universal criteria that apply generally with indication-specific, class-specific, or brand-specific criteria. Treat universal criteria and indication/class/brand-specific criteria as both required when both are present.

Universal Criteria implies those steps which do no involve the specific target brand or indication.

From the combined required criteria, identify the least restrictive approval path which means if requirements appear in an `OR` statement, count the path with fewer required generic or non-biologic steps.

DO NOT COUNT PHOTOTHERAPY STEPS IN THIS PARAMETER.

From the combined required criteria, identify the least restrictive approval path. If requirements appear in an OR statement, count the path with fewer required branded or biologic steps.

Count only branded or biologic steps. Do not count phototherapy steps in this parameter. Do not count non-biologic generic steps in this parameter.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

Statements joined by `AND` means both of them are necessary so both the steps are counted but make sure the statements involve branded/biologic product.

Statements joined by `OR` means either the steps are necessary so one of the step is counted but make sure the statements involve branded/biologic product..

## Output Guidance

Return the numeric count of branded or biologic steps after determinig it based on the counting logic. Output `NA` if no branded or biologic steps are required in the available chunks.