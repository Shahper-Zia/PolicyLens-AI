# Step Therapy Requirements Documented in Policy

## Purpose

This rule helps extract requirements for the target brand and indication from Prior Authorization policy chunks. Step therapy requirements show what therapies or criterias or conditions a patient must have tried or try before the target therapy can be covered.

## Extraction Rule

Extract all step therapy language documented in the policy that applies to the target brand.
Which can include all the criteias mentioned for the drug to be approved/authorized/covered.

Include both:

- Universal criteria that apply to all brands, all products, all indications, or the relevant psoriasis indication/class.
- Universal criteria even means such criteria where there is no explicit mention of a drug brand or indication.
- Criterias specific to the target indication/class, drug class/category, or brand mention the specic brand or indication name along with the criteria.

Indication-level or class-level criteria can apply to multiple brands. If the target brand belongs to the stated indication/class/category, include those requirements.

Make sure to include phototherapy/PUVA related language if it appears within a step requirement.

Take into account those statements which have AND/OR conditions and mention it properly.

DO NOT MISS OR HALLUCINATE CRITERIA OR APPROVAL CONDITIONS SO THAT THE DOWNSTREAM LOGIC CAN BE BUILT ACCURATELY ON THIS PARAMETER.

## What to Look For

Look for policy language requiring prior use, trial, failure, inadequate response, intolerance, contraindiction, or inability to use another therapy before approval.

Include step language involving branded therapies, biologics, generic therapies, topical therapies, and phototherapy if it appears within a step requirement.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, extract only the moderate-to-severe criteria.

## Output Guidance

Return the requirements as documented in the policy. Do not summarize away important alternatives, AND/OR structure, contraindication exceptions, or intolerance exceptions. If no such requirement is documented in the available chunks, return `NA`.

Mention both the universal criterias and then mention target indication specific criteris for approvals/authorization/coverage of the drug brand.
