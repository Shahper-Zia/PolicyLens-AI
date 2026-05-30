# Step Therapy Requirements Documented in Policy

## Purpose

This rule helps extract step therapy requirements for the target brand and PsO/Psoriasis from Prior Authorization policy chunks. Step therapy requirements show what therapies a patient must try before the target therapy can be covered.

## Extraction Rule

Extract all step therapy language documented in the policy that applies to the target brand and PsO/Psoriasis.

Include both:

- Universal criteria that apply to all brands, all products, all indications, or the relevant psoriasis indication/class.
- Criteria specific to the target indication/class, drug class/category, or brand.

Indication-level or class-level criteria can apply to multiple brands. If the target brand belongs to the stated indication/class/category, include those requirements.

Include phototherapy language if it appears within a step requirement, but do not count phototherapy as a branded or generic step in the separate count parameters.

## What to Look For

Look for policy language requiring prior use, trial, failure, inadequate response, intolerance, contraindication, or inability to use another therapy before approval.

Include step language involving branded therapies, biologics, generic therapies, topical therapies, and phototherapy if it appears within a step requirement.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, extract only the moderate-to-severe criteria.

## Output Guidance

Return the requirements as documented in the policy. Do not summarize away important alternatives, AND/OR structure, contraindication exceptions, or intolerance exceptions. If no such requirement is documented in the available chunks, return `NA`.
