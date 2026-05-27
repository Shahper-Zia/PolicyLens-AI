# Number of Steps through Brands

## Purpose

This rule helps count branded or biologic step requirements for a target brand and indication from Prior Authorization policy chunks. More branded steps generally indicate more restrictive access before the target therapy can be covered.

## Extraction Rule

Count the number of branded or biologic steps required before the target drug can be approved.

A preferred ustekinumab product counts as a branded step.

A preferred adalimumab product counts as a branded step.

If the policy references a drug class and the target drug belongs to that class, the class-level step counts as a branded step for that drug.

## Counting Logic

Combine universal criteria that apply generally with indication-specific or brand-specific criteria. Treat universal criteria and indication/brand-specific criteria as both required when both are present.

From the combined required criteria, identify the least restrictive approval path. If requirements appear in an OR statement, count the path with fewer required branded or biologic steps.

Count only branded or biologic steps. Do not count phototherapy steps in this parameter. Do not count non-biologic generic steps in this parameter.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

## Output Guidance

Return the numeric count of branded or biologic steps. Output `NA` if no branded or biologic steps are required in the available chunks.
