# Reauthorization Requirements Documented in Policy

## Purpose

This rule helps extract documented reauthorization requirements for the target brand and PsO/Psoriasis from Prior Authorization policy chunks.

## Extraction Rule

Extract criteria that EXPLICITLY MENTION reauthorization, renewal, continuation approval, or continuation of therapy.

## What to Look For

ONLY SELECT CRITERIA WHICH EXPLICITLY MENTION FOR reauthorization, renewal, continuation approval, or continuation of therapy. Look for requirements such as continued clinical benefit, continued positive response, low disease activity, improvement in signs or symptoms, lack of disease progression, required lab values, or updated clinical documentation.


## Output Guidance

Return the reauthorization or continuation criteria as documented in the policy. Preserve important AND/OR structure, response criteria, and documentation requirements.

If no reauthorization or continuation requirements are documented in the available chunks, return `NA`.
