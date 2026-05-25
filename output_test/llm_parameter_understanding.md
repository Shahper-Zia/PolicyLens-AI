# PolicyLens PA Parameter Extraction Reference (LLM-Ready)

# LLM Extraction Protocol: Given a Brand Name and PA Document, Extract Brand-Specific Evidence and Determine Parameter Values Using Rule-Based Decisions Only (No Hallucination)

Source: `paramater_rules_definition.csv` + user-provided fallback output normalization

## Global Output Normalization (Fallback Rule)
Apply this only when a parameter's rule does **not** define explicit output labels after inferring the chunk **not** hardcoding the values:
- `NA`: The chunk does not mention the parameter value.
- `No`: The parameter is mentioned as not mandatory / not required.
- `Yes`: The parameter is mentioned as required / mandatory.

## Parameter 1: `Age`
- Meaning: Age-based eligibility or restriction criteria for therapy approval.
- What to extract:
  - Numeric minimum/maximum age thresholds if explicitly stated.
  - Age subgroup language if present.
- Special rules:
  - If policy does not provide a numeric age and instead refers to indication-based/FDA-labelled population, output `FDA labelled age`.
  - If two age groups are listed, capture the youngest group.
- Applicability: When age eligibility language is present.

## Parameter 2: `Step Therapy Requirements Documented in Policy`
- Meaning: Full step-therapy text as documented.
- What to include:
  - Universal criteria (applies across indications/brands in policy).
  - Indication-specific and brand-specific criteria.
  - Phototherapy text if it appears inside step statements.
- PsO rule:
  - If policy separates moderate-to-severe PsO and severe PsO, capture moderate-to-severe criteria only.

## Parameter 3: `Number of Steps through Brands`
- Meaning: Count of required branded/biologic steps before target drug approval.
- Output type: Integer count or `NA`.
- Counting logic:
  - Build required set = union of universal + indication/brand-specific step criteria.
  - Treat universal and specific criteria as AND (both required).
  - If OR branches exist, choose least restrictive path (fewest required steps).
  - Count only branded/biologic steps on chosen path.
- Classification rules:
  - Preferred ustekinumab/adalimumab product counts as branded step.
  - If a class-level step is required and target drug belongs to that class, count as branded.
- Exclusions:
  - Do not count phototherapy here.
- PsO rule:
  - Use moderate-to-severe criteria only when split exists.
- NA condition:
  - Output `NA` if no branded steps are required.

## Parameter 4: `Number of Steps through Generic`
- Meaning: Count of required non-biologic/generic steps before approval.
- Output type: Integer count or `NA`.
- Counting logic:
  - Build required set = union of universal + indication/brand-specific steps.
  - Treat universal and specific criteria as AND.
  - Resolve OR by least restrictive path.
  - Count only generic/non-biologic steps on chosen path.
- Classification rules:
  - Topicals count as generic steps.
  - If a parent indication requires a step but names no brand/biologic, default to generic.
  - For non-preferred selected drugs, universal preferred-alternative step requirements also apply:
    - If explicitly biologic/targeted -> branded.
    - If not explicitly biologic/targeted -> generic.
- Exclusions:
  - Do not count phototherapy here.
- PsO rule:
  - Use moderate-to-severe criteria only when split exists.
- NA condition:
  - Output `NA` if no generic steps are required.

## Parameter 5: `Step through-Phototherapy`
- Meaning: Whether phototherapy is a required prerequisite step.
- Output labels (explicit): `Yes`, `No`, `N/A`.
- Decision logic:
  - Combine universal + indication-specific phototherapy requirements with AND.
  - `Yes`: phototherapy is mandatory in combined criteria and not optional via OR.
  - `No`: phototherapy is not required for approval.
  - `N/A`: policy contains no criteria at all.

## Parameter 6: `TB Test required`
- Meaning: Whether TB test is required for approval.
- Rule in source:
  - `Y` when TB test is required.
- If absent/unspecified in chunk and no explicit label rule applies, use global fallback normalization.

## Parameter 7: `Initial Authorization Duration(in-months)`
- Meaning: Initial PA approval duration.
- Output type: Numeric months (e.g., 6, 12) or `Unspecified`.
- Constraint:
  - If PA indication for PsO is `Yes`, output should be either explicit duration or `Unspecified`.

## Parameter 8: `Reauthorization Duration(in-months)`
- Meaning: Duration granted at reauthorization.
- Output type: Numeric months or `Unspecified`.
- Constraint:
  - If `Reauthorization Required` is `Yes`, output should be duration or `Unspecified`.

## Parameter 9: `Reauthorization Required`
- Meaning: Whether renewal is needed after initial authorization period.
- Dependency rule:
  - If either `Reauthorization Duration` or `Reauthorization Requirements Documented in Policy` is non-NA, set this to `Yes`.

## Parameter 10: `Reauthorization Requirements Documented in Policy`
- Meaning: Continuation/reauthorization criteria text in policy.
- What to include:
  - Explicit continuation criteria such as sustained clinical benefit, no progression, labs, or equivalent documented requirements.

## Parameter 11: `Specialist Types`
- Meaning: Acceptable specialist types for initiation/management of therapy.
- What to extract:
  - Policy-approved specialist labels (e.g., dermatologist, rheumatologist, gastroenterologist).

## Parameter 12: `Quantity Limits`
- Meaning: Policy-stated quantity limits.
- Strict inclusion rule:
  - Capture only statements explicitly framed as "quantity limit".
- Exclusion rule:
  - Do not capture language stated only as "dosage" or "dosing limit".

## Cross-Parameter Dependency Graph (Operational)
1. Step-related fields share same combination logic:
   - universal criteria AND indication/brand-specific criteria
   - OR resolved to least restrictive path.
2. Phototherapy handling:
   - Included in documented step text.
   - Excluded from brand/generic numeric step counts.
   - Independently evaluated in `Step through-Phototherapy`.
3. PsO stratification handling:
   - If moderate-to-severe vs severe are both present, use moderate-to-severe for step-related extraction.
4. Reauthorization linkage:
   - Presence of reauth duration or reauth requirements implies `Reauthorization Required = Yes`.

## Extraction Priority Order (Recommended)
1. Identify if criteria exist for chunk/indication.
2. Parse universal criteria.
3. Parse indication/brand-specific criteria.
4. Merge with AND logic.
5. Resolve OR branches via least restrictive path.
6. Compute step counts by class (branded vs generic), excluding phototherapy.
7. Determine phototherapy requirement independently using merged criteria.
8. Extract duration and reauthorization fields with dependency checks.
9. Apply explicit parameter label rules first; apply global fallback normalization only where labels are undefined.
