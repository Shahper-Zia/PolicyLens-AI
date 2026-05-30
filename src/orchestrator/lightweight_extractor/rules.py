from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULES_DIR = PROJECT_ROOT / "src" / "orchestrator" / "param_extractor" / "rules"

FIELD_TO_RULE_FILE = {
    "age": "age.md",
    "step_therapy_requirements": "step_therapy_requirements_documented_in_policy.md",
    "number_of_steps_brands": "number_of_steps_through_brands.md",
    "number_of_steps_generic": "number_of_steps_through_generic.md",
    "step_through_phototherapy": "step_through_phototherapy.md",
    "tb_test_required": "tb_test_required.md",
    "initial_auth_duration": "initial_authorization_duration_in_months.md",
    "reauthorization_duration": "reauthorization_duration_in_months.md",
    "reauthorization_required": "reauthorization_required.md",
    "reauthorization_requirements": "reauthorization_requirements_documented_in_policy.md",
    "specialist_types": "specialist_types.md",
    "quantity_limits": "quantity_limits.md",
}

COMPACT_PARAMETER_RULES = {
    "age": "Extract numeric age eligibility for target brand/PsO. If policy says FDA-labelled/FDA-approved age without a number, return FDA labelled age. Return NA if absent.",
    "step_therapy_requirements": "Extract all step/prior therapy language applying to target brand/PsO, including universal, indication, class, and brand criteria. Preserve AND/OR alternatives and intolerance/contraindication exceptions.",
    "number_of_steps_brands": "Count required branded/biologic/targeted/named-drug steps. Include preferred ustekinumab/adalimumab/biosimilar/biologic steps. For OR paths, count the least restrictive supported path. Do not count phototherapy or generic steps.",
    "number_of_steps_generic": "Count required generic/non-biologic steps, such as topical or conventional systemic therapy, when not named as branded/biologic. Do not count phototherapy or branded/biologic steps.",
    "step_through_phototherapy": "Return Yes only if phototherapy/PUVA is mandatory for approval. Return No when criteria exist but phototherapy is not required. Return NA when no relevant criteria exist.",
    "tb_test_required": "Return Yes if TB/tuberculosis testing or screening is required before or during therapy for the target scope, including all-indication clauses. Return No if criteria exist and no TB requirement is documented. Return NA if insufficient.",
    "initial_auth_duration": "Extract initial authorization/approval/coverage duration for target brand/PsO in months when possible. Return Unspecified if initial authorization exists but duration is not stated. Return NA if absent.",
    "reauthorization_duration": "Extract renewal/continuation/reauthorization duration in months when possible. Return Unspecified if reauthorization exists but duration is not stated. Return NA if absent.",
    "reauthorization_required": "Return Yes if renewal/continuation/reauthorization criteria are required after initial approval. Return No if policy explicitly says no renewal requirement. Return NA if unclear.",
    "reauthorization_requirements": "Extract continuation/renewal requirements such as clinical response, chart notes, improvement, no toxicity, adherence, or continued diagnosis. Preserve important exceptions. Return NA if absent.",
    "specialist_types": "Extract required prescriber/specialist types such as dermatologist or rheumatologist, including consultation requirements. Return semicolon-separated types or NA.",
    "quantity_limits": "Extract only explicit quantity limits or equivalent maximum quantity restrictions. Do not infer quantity limits from ordinary dosing instructions. Return NA if absent.",
}


def load_parameter_rules(compact: bool = False) -> Dict[str, str]:
    if compact:
        return COMPACT_PARAMETER_RULES.copy()

    rules = {}
    for field_name, rule_file in FIELD_TO_RULE_FILE.items():
        rule_path = RULES_DIR / rule_file
        with open(rule_path, "r", encoding="utf-8") as f:
            rules[field_name] = f.read().strip()
    return rules
