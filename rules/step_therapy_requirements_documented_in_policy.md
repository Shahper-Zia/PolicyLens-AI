# Step Therapy Requirements Documented in Policy

## Purpose

This rule helps extract step therapy requirements for a target brand and indication from Prior Authorization policy chunks to be covered by the payer. Step therapy requirements show what therapies a patient must try before the target therapy can be covered, which affects how easy coverage is for the pharma product.

## Extraction Rule

Extract all step therapy language documented in the policy that applies to the target brand and indication. Include both universal criteria which means that any part of the document which mentions for anything about `all indications` or `all brands` under the current indication which means the requirements for coverage applies across indications and/or criteria specific to the target brand or indication.Even if the requirements for coverage of the target drug or brand includes phototheraphy that also needs to be extracted.

## What to Look For

Look for policy language requiring prior use, trial, failure, inadequate response, intolerance, contraindication, or inability to use another therapy before approval.

Include step language involving branded therapies, biologics, generic therapies, topical therapies, and phototherapy if it appears within a step requirement.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, extract only the moderate-to-severe criteria.

## Output Guidance

Return the requirements as documented in the policy. Do not summarize away important alternatives, AND/OR structure, contraindication exceptions, or intolerance exceptions. If no such requirement is documented in the available chunks, return `NA`.