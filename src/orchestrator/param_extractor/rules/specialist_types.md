# Specialist Types

## Purpose

This rule helps extract specialist prescriber requirements for the target brand and PsO/Psoriasis from Prior Authorization policy chunks.

## Extraction Rule

Extract the specific medical specialties that are acceptable for initiating, prescribing, consulting on, or managing treatment.

## What to Look For

Look for requirements that the drug must be prescribed by, managed by, or prescribed in consultation with a specialist.

Examples of specialties can include dermatologist, rheumatologist, gastroenterologist, infectious disease specialist, or other explicitly named specialties.

If multiple specialties are mentioned, extract all of them which can are mentioned and can be implied to be included DO NOT MENTION SPECIALITIES WHICH ARE DENIED and separate them with `;`.

## Output Guidance

Return only the specialist types explicitly documented in the policy chunks. If no specialist requirement is documented in the available chunks, return `NA`.
