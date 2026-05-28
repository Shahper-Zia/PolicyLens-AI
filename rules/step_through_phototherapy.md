# Step through-Phototherapy

## Purpose

This rule helps determine whether phototherapy is required before the target brand can be covered for the target indication. Phototherapy requirements are important access restrictions in Prior Authorization policies.

## Extraction Rule

Determine whether the policy requires the patient to step through phototherapy before the target drug can be approved.

Phototherapy includes PUVA, which means psoralen combined with UVA light exposure.

## Decision Logic

Combine universal criteria that apply generally with indication-specific or brand-specific criteria. Treat universal criteria and indication/brand-specific criteria as both required when both are present.

Return `Yes` when phototherapy is a mandatory required step in the combined criteria and is not merely one option inside an OR statement.

Return `No` when the policy does not mention phototherapy as a required step for approval of the target drug and indication.

Return `N/A` when the policy lists no criteria at all in the available chunks about `Phototherapy`/`PUVA`/`psolaren combined with UVA`.

## Output Guidance

Return only `Yes`, `No`, or `N/A`.
