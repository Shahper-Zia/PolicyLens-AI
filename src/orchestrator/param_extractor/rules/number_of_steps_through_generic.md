# Number of Steps through Generic

## Purpose

This rule helps count generic or non-biologic step requirements for the target brand and PsO/Psoriasis from Prior Authorization policy chunks.

## Extraction Rule

Count the number of non-biologic or generic steps required before the target drug can be approved.

Topical agents count as generic steps.

If a parent indication/class/category requires a step but does not name any brand, biologic, or targeted therapy, count that requirement as a generic step.

If preferred and non-preferred products are listed and the target brand is non-preferred, include universal criteria requiring steps through preferred alternatives. Steps that explicitly mention biologics, targeted therapies, or named brand products count as branded steps, not generic steps. Steps with no such specification count as generic steps.

## Counting Logic

Combine universal criteria that apply generally with indication-specific, class-specific, or brand-specific criteria. Treat universal criteria and indication/class/brand-specific criteria as both required when both are present.

Universal Criteria implies those steps which do no involve the specific target brand or indication.

From the combined required criteria, identify the least restrictive approval path which means if requirements appear in an `OR` statement, count the path with fewer required generic or non-biologic steps.

Count only generic or non-biologic steps. 

Do not count branded or biologic steps in this parameter.

DO NOT COUNT PHOTOTHERAPY STEPS IN THIS PARAMETER.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

Statements joined by `AND` means both of them are necessary so both the steps are counted but make sure the statements involve generic product or a generic criteria or a generic condition or any criteria which is non biological or non branded in nature is also included.

Statements joined by `OR` means either the steps are necessary so one of the step is counted but make sure the statements involve  generic product or a generic criteria or a generic condition or any criteria which is non biological or non branded in nature is also included.

## Output Guidance

Return the numeric count of branded or biologic steps after determinig it based on the counting logic. Output `NA` if no generic or non-biologic steps are required in the available chunks.
