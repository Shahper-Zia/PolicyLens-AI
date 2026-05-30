# Step through-Phototherapy

## Purpose

This rule helps determine whether phototherapy is required before the target brand can be covered for PsO/Psoriasis.

## Extraction Rule

Determine whether the policy requires the patient to step through phototherapy before the target drug can be approved.

Denial of Phototherapy/PUVA or any synonym also means that the step would be required.

Phototherapy includes PUVA, psoralen combined with UVA light exposure, ultraviolet light therapy, UVB, narrowband UVB, or similar light therapy terms.

## Decision Logic

Determine logically whether the phototherapy would be needed to be done by the patient so that the drug is covered by the payer.

Return `Yes` when phototherapy is a mandatory required step in the combined criteria and is not merely one option inside an OR statement.

Return `No` when the policy has approval criteria but does not mention phototherapy as a required step for approval of the target drug and indication.

Return `N/A` when the policy lists no criteria at all in the available chunks.

## Output Guidance

Return only `Yes`, `No`, or `N/A`.
