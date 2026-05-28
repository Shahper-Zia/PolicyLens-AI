# Specialist Types

## Purpose

This rule helps extract specialist prescriber requirements for the target brand and indication from Prior Authorization policy chunks. Specialist restrictions affect ease of access because they determine which clinicians can initiate or manage covered therapy.

## Extraction Rule

Extract the specific medical specialties that are acceptable for initiating, prescribing, consulting on, or managing treatment.

## What to Look For

Look for requirements that the drug must be prescribed by, managed by, or prescribed in consultation with a specialist.

Examples of specialties can include dermatologist, rheumatologist, gastroenterologist, infectious disease specialist, or other explicitly named specialties or multiple specialities.

If multiple specialities are mentioned then extract all and return with a `;` separating them.

## Output Guidance

Return only the specialist types explicitly documented in the policy chunks. If no specialist requirement is documented in the available chunks, return `NA`.
