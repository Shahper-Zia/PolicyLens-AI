# Access Score Scoring Framework

## Purpose

This framework estimates how easy it is for a pharma company to get the target brand covered by a payer policy for the target indication. The score is calculated from the extracted prior authorization parameters and normalized to a `0` to `100` scale:

- `0`: No access.
- `25`: Restricted access compared with FDA guidelines.
- `50`: Parity with FDA label.
- `75`: Preferred access compared with FDA label.
- `100`: Best possible access compared with competitors, with no meaningful restrictions applied.

The score should reward broad, low-burden access and penalize restrictions that reduce eligible patients, increase physician burden, require prior treatment failures, shorten approval windows, or impose quantity/prescriber limits.

## Core Principle

Start from a baseline score of `100`, subtract restriction penalties, then clamp the final value to `0-100`.

```text
raw_score = 100 - total_restriction_penalty
access_score = min(100, max(0, raw_score))
```

If the policy explicitly indicates the target brand is not covered or is excluded, assign `0` regardless of other parameters.

If critical evidence is missing for most parameters, do not assume best access. Use the uncertainty handling section.

## Parameter Implications

| Parameter | Access implication |
| --- | --- |
| Age | Restricts eligible patient population. More restrictive than FDA-labelled age lowers access. |
| Step Therapy Requirements Documented in Policy | Captures explicit approval hurdles. More criteria and stricter AND conditions lower access. |
| Number of Steps through Brands | Requires failure/use of branded, biologic, biosimilar, targeted, or named products before target brand. This is a major access barrier. |
| Number of Steps through Generic | Requires cheaper/generic/non-biologic therapy before target brand. This is a major access barrier, though usually less restrictive than branded biologic steps. |
| Step through-Phototherapy | Requires phototherapy/PUVA before approval. This adds clinical and logistical burden. |
| TB Test Required | Adds a prerequisite and delays treatment, but is usually a modest safety-related burden. |
| Specialist Types | Restricts prescribing authority, increasing access friction. |
| Initial Authorization Duration | Short initial approval periods force early renewal and increase administrative burden. |
| Reauthorization Required | Requires repeated proof of eligibility and physician documentation. |
| Reauthorization Duration | Short renewal periods increase repeated administrative burden. |
| Reauthorization Requirements Documented in Policy | Clinical response, documentation, lab, or toxicity criteria can cause loss of coverage at renewal. |
| Quantity Limits | Caps covered drug amount and may restrict dosing flexibility. |

## Penalty Model

### 1. Age

Use the `Age` parameter.

| Extracted value | Penalty |
| --- | ---: |
| `NA` | `0` if no evidence of age restriction; otherwise use uncertainty handling. |
| `FDA labelled age` | `0` |
| Pediatric or broader-than-label access | `0` |
| `>=18`, `18+`, adult-only when FDA label is adult-only | `0-3` |
| More restrictive than expected label, such as `>=21`, `>=30`, or narrow subgroup | `8-15` |
| Multiple age groups where only a narrow group qualifies | `10-20` |

Default penalty: `0` for `FDA labelled age`; `5` for a numeric threshold if label parity cannot be verified; `12` for clearly restrictive numeric thresholds above adult age.

### 2. Step Therapy Requirements Documented in Policy

Use this parameter as the source set of approval hurdles. Preserve AND/OR logic.

| Requirement structure | Penalty |
| --- | ---: |
| `NA` or no step/prior therapy criteria | `0` |
| Criteria exist but no prior therapy failure/use requirement | `3-6` |
| One simple prior therapy requirement | `8-12` |
| Multiple AND requirements | `12-25` |
| Complex multi-branch criteria with documentation/exceptions | `15-30` |
| Any explicit no-access or impossible pathway | escalate toward `60+` or assign `0` if no covered path exists |

This parameter should not double count branded/generic steps. It captures complexity and administrative burden. The branded/generic count parameters capture the number/type of prior therapy steps.

Recommended default:

```text
step_therapy_text_penalty =
  0 if step_therapy_requirements is NA
  6 if criteria exist but no prior therapy step is present
  10 if simple prior therapy criteria exist
  18 if multiple AND criteria exist
  25 if complex criteria include several alternatives, exceptions, or documentation burdens
```

### 3. Number of Steps through Brands

Use the numeric count derived from the extracted step therapy requirements.

| Count | Penalty |
| ---: | ---: |
| `NA` or `0` | `0` |
| `1` | `15` |
| `2` | `25` |
| `3` | `35` |
| `4+` | `45` |

Rationale: branded/biologic steps are major barriers because they often require failure of advanced therapies before the target brand is covered.

### 4. Number of Steps through Generic

Use the numeric count derived from the extracted step therapy requirements.

| Count | Penalty |
| ---: | ---: |
| `NA` or `0` | `0` |
| `1` | `10` |
| `2` | `18` |
| `3` | `25` |
| `4+` | `32` |

Rationale: generic/non-biologic steps are meaningful access barriers, but generally less restrictive than branded/biologic steps.

### 5. Step through-Phototherapy

Use the `Step through-Phototherapy` parameter.

| Extracted value | Penalty |
| --- | ---: |
| `Yes` | `10` |
| `No` | `0` |
| `NA` / `N/A` | `0` unless policy lacks usable criteria; then use uncertainty handling |

Only assign this penalty when phototherapy/PUVA is a required prior step for approval. If phototherapy is prohibited concurrently or listed as a denial/safety condition, do not count that as a phototherapy step-through penalty.

### 6. TB Test Required

Use the `TB Test Required` parameter.

| Extracted value | Penalty |
| --- | ---: |
| `Yes` | `3` |
| `No` | `0` |
| `NA` | `0` unless missing policy context creates uncertainty |

Rationale: TB testing is a modest burden. It delays treatment and creates documentation requirements but is common for biologics.

### 7. Specialist Types

Use the `Specialist Types` parameter.

| Extracted value | Penalty |
| --- | ---: |
| `NA` | `0` |
| One specialist type required | `5` |
| Multiple allowed specialist types | `4` |
| Narrow specialist-only prescribing with no consultation alternative | `8-10` |
| Specialist plus documentation/consultation burden | `8-12` |

Rationale: specialist restrictions reduce prescribing flexibility and may delay access.

### 8. Initial Authorization Duration

Use `Initial Authorization Duration(in-months)`.

| Duration | Penalty |
| --- | ---: |
| `NA` | `0` if no PA duration exists; otherwise uncertainty handling |
| `Unspecified` | `5` |
| `>=12 months` | `0` |
| `6-11 months` | `5` |
| `3-5 months` | `10` |
| `<3 months` | `15` |

Rationale: shorter initial approvals force early reassessment and additional administrative burden.

### 9. Reauthorization Required

Use `Reauthorization Required`.

| Extracted value | Penalty |
| --- | ---: |
| `Yes` | `5` |
| `No` | `0` |
| `NA` | `0-3` depending on whether renewal language is absent or unclear |

Rationale: renewal adds repeated proof of eligibility and physician documentation burden.

### 10. Reauthorization Duration

Use `Reauthorization Duration(in-months)`.

| Duration | Penalty |
| --- | ---: |
| `NA` and reauthorization not required | `0` |
| `Unspecified` while reauthorization is required | `5` |
| `>=12 months` | `0` |
| `6-11 months` | `4` |
| `3-5 months` | `8` |
| `<3 months` | `12` |

Rationale: shorter renewal windows create more repeated administrative burden.

### 11. Reauthorization Requirements Documented in Policy

Use `Reauthorization Requirements Documented in Policy`.

| Requirement type | Penalty |
| --- | ---: |
| `NA` and reauthorization not required | `0` |
| Basic continuation request only | `2` |
| Continued clinical benefit / positive response documentation | `5` |
| Chart notes, objective scores, lab values, or disease activity thresholds | `8-12` |
| Multiple AND renewal criteria | `10-15` |
| Renewal criteria that can easily terminate coverage despite treatment need | `15-20` |

Rationale: renewal criteria can cause loss of access and add documentation burden.

### 12. Quantity Limits

Use `Quantity Limits`.

| Extracted value | Penalty |
| --- | ---: |
| `NA` | `0` |
| Explicit quantity limit aligned with label dosing | `3` |
| Restrictive quantity limit requiring exceptions for normal dosing | `8-15` |
| Quantity limit that blocks dose escalation or maintenance dosing | `15-25` |

Rationale: quantity limits cap drug supply and may require exceptions or appeals.

## Interaction Rules

### Step Therapy Interaction

Do not treat the step therapy text penalty as a replacement for step counts. Use both:

```text
step_burden =
  step_therapy_text_penalty
  + branded_step_penalty
  + generic_step_penalty
  + phototherapy_penalty
```

However, cap combined step burden at `55` to avoid a single policy dimension overwhelming all other dimensions.

```text
step_burden = min(step_burden, 55)
```

### Reauthorization Interaction

If `Reauthorization Required = No`, set reauthorization duration and reauthorization requirement penalties to `0` unless the policy separately documents continuation restrictions.

If `Reauthorization Required = Yes`, combine:

```text
reauth_burden =
  reauth_required_penalty
  + reauth_duration_penalty
  + reauth_requirements_penalty
```

Cap combined reauthorization burden at `25`.

### Duration Interaction

Initial authorization and reauthorization durations are separate. A short initial approval and short renewal approval both reduce access.

### Safety Requirement Interaction

TB testing should usually remain a small penalty. Do not over-penalize safety monitoring unless the policy requires repeated testing, lab documentation, or specialist coordination beyond ordinary screening.

## Normalization

After all penalties and caps:

```text
total_penalty =
  age_penalty
  + min(step_burden, 55)
  + tb_penalty
  + specialist_penalty
  + initial_auth_duration_penalty
  + min(reauth_burden, 25)
  + quantity_limit_penalty

access_score = round(max(0, min(100, 100 - total_penalty)))
```

## Score Band Interpretation

| Score range | Interpretation |
| --- | --- |
| `0-10` | No access or near-no access. |
| `11-35` | Highly restricted access. |
| `36-55` | Restricted access; likely worse than FDA-label parity. |
| `56-70` | Moderate access; some payer burden but workable. |
| `71-85` | Preferred or favorable access with limited restrictions. |
| `86-100` | Best access; minimal meaningful restrictions. |

## Missing and Uncertain Values

Use these rules to avoid hallucinating:

1. `NA` means the policy evidence did not document the parameter. Do not automatically penalize `NA`.
2. `Unspecified` means the policy applies but the exact value is not stated. Apply a small burden because uncertainty creates operational friction.
3. If more than half of the core parameters are `NA`, reduce confidence and optionally cap the score at `75` unless the available evidence clearly shows minimal restrictions.
4. If step therapy requirements are `NA`, then branded/generic/phototherapy step penalties should generally be `0` or `NA`-neutral.
5. If reauthorization required is `NA`, do not infer renewal burden from unrelated continuation language.

## Recommended JSON Output

When calculating access score downstream, return:

```json
{
  "access_score": "72",
  "raw_score": "72",
  "total_penalty": "28",
  "penalty_breakdown": {
    "age": "0",
    "step_therapy_text": "10",
    "number_of_steps_brands": "0",
    "number_of_steps_generic": "10",
    "step_through_phototherapy": "0",
    "tb_test_required": "3",
    "specialist_types": "0",
    "initial_authorization_duration": "10",
    "reauthorization_required": "5",
    "reauthorization_duration": "0",
    "reauthorization_requirements": "0",
    "quantity_limits": "0"
  },
  "reasoning": "Main restrictions are generic step therapy, TB screening, short initial approval, and reauthorization requirement."
}
```

## Data Scientist Notes

This is a rule-based additive penalty model. It is interpretable, debuggable, and suitable before ground truth calibration. If gold-standard access scores are available, calibrate the penalty weights by minimizing mean absolute error against the labeled score:

```text
minimize MAE(gold_score, predicted_score)
subject to:
  branded_step_penalty > generic_step_penalty
  step_burden_cap <= 60
  reauth_burden_cap <= 30
  TB penalty <= 5
```

The initial weights above are intentionally conservative:

- Step therapy receives the largest penalty.
- Branded/biologic steps are more restrictive than generic/non-biologic steps.
- Reauthorization and short durations reduce access but should not dominate unless severe.
- TB testing and specialist restrictions add friction but are usually secondary.
- Quantity limits can become severe when they conflict with normal dosing.
