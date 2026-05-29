# Number of Steps through Brands

## Purpose

This rule helps count branded or biologic step requirements for a target brand and indication from Prior Authorization policy chunks. More branded steps generally indicate more restrictive access before the target therapy can be covered.

## Extraction Rule

Count the number of branded or biologic steps required before the target drug can be approved.

If the extract mentions that a product belonging to any generic medicines like ustekinumab or adalimumab or anything else is preferrable this emplies as branded step requirement.

If the policy references a drug indicaion and the target drug belongs to that indication, the indication-level step counts as a branded step for that drug.

The document might mention AND/OR conditions of various steps needed for a drug to be covered by the insurance company .so multiple and statements implies the number od steps needed to be coverd. Multiple statements joined by OR imply just one step because the condition is OR.

## Counting Logic

From the combined required criteria, identify the least restrictive approval path. If requirements appear in an OR statement, count the path with fewer required branded or biologic steps.

Count only branded or biologic steps. Do not count phototherapy steps in this parameter. Do not count non-biologic generic steps in this parameter.

If the policy distinguishes between moderate-to-severe psoriasis and severe psoriasis, use only the moderate-to-severe criteria.

## Output Guidance

Return the numeric count of branded or biologic steps. Output `NA` if no branded or biologic steps are required in the available chunks.
