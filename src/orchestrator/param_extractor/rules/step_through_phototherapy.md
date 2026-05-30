# Step through-Phototherapy

## Purpose

This rule helps determine whether phototherapy is required before the target brand can be covered for PsO/Psoriasis.

## Extraction Rule

Determine whether the policy requires the patient to step through phototherapy before the target drug can be approved.

Phototherapy includes PUVA, psoralen combined with UVA light exposure, ultraviolet light therapy, UVB, narrowband UVB, or similar light therapy terms.

## Decision Logic

Combine universal criteria that apply generally with indication-specific, class-specific, or brand-specific criteria. Treat universal criteria and indication/class/brand-specific criteria as both required when both are present.

Return `Yes` when phototherapy is a mandatory required step in the combined criteria and is not merely one option inside an OR statement.

Return `No` when the policy has approval criteria but does not mention phototherapy as a required step for approval of the target drug and indication.

Return `N/A` when the policy lists no criteria at all in the available chunks.

## Output Guidance

Return only `Yes`, `No`, or `N/A`.
