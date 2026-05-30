import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.orchestrator.lightweight_extractor.chunker import PolicyChunk, split_markdown
try:
    from src.orchestrator.llm.groq_client import GroqClient
except ImportError:  # pragma: no cover
    from orchestrator.llm.groq_client import GroqClient
from src.orchestrator.lightweight_extractor.retriever import (
    format_chunks_for_prompt,
    retrieve_parameter_context,
)
from src.orchestrator.lightweight_extractor.rules import load_parameter_rules
from src.validation.output_schema import BrandAttribute, ExtractionResponse


FIELD_DEFAULTS: Dict[str, str] = {
    "age": "NA",
    "step_therapy_requirements": "NA",
    "number_of_steps_brands": "NA",
    "number_of_steps_generic": "NA",
    "step_through_phototherapy": "NA",
    "tb_test_required": "NA",
    "initial_auth_duration": "NA",
    "reauthorization_duration": "NA",
    "reauthorization_required": "NA",
    "reauthorization_requirements": "NA",
    "specialist_types": "NA",
    "quantity_limits": "NA",
}

FIELD_ORDER = list(FIELD_DEFAULTS)
STEP_DERIVED_FIELDS = {
    "number_of_steps_brands",
    "number_of_steps_generic",
    "step_through_phototherapy",
}


class LightweightPolicyExtractor:
    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        max_chunks: int = 14,
        verbose: bool = False,
    ):
        self.groq_client = groq_client or GroqClient()
        self.max_chunks = max_chunks
        self.parameter_rules = load_parameter_rules(compact=False)
        self.verbose = verbose
        self.last_contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def extract(
        self,
        filename: str,
        markdown_text: str,
        brand_names: Sequence[str],
        indication: str = "Psoriasis",
    ) -> ExtractionResponse:
        chunks = split_markdown(markdown_text)
        attributes = [
            self.extract_brand_attributes(filename, chunks, brand, indication)
            for brand in brand_names
        ]

        return ExtractionResponse(
            filename=filename,
            detected_brands=list(brand_names),
            brand_attributes=attributes,
        )

    def extract_brand_attributes(
        self,
        filename: str,
        chunks: Sequence[PolicyChunk],
        brand: str,
        indication: str = "Psoriasis",
    ) -> BrandAttribute:
        payload, contexts = self._extract_parameters(filename, chunks, brand, indication)
        self.last_contexts[(filename, brand)] = contexts

        values = {**FIELD_DEFAULTS, **_stringify_values(payload)}
        return BrandAttribute(
            filename=filename,
            brand=brand,
            indication=indication,
            age=values["age"],
            step_therapy_requirements=values["step_therapy_requirements"],
            number_of_steps_brands=values["number_of_steps_brands"],
            number_of_steps_generic=values["number_of_steps_generic"],
            step_through_phototherapy=values["step_through_phototherapy"],
            tb_test_required=values["tb_test_required"],
            initial_auth_duration=values["initial_auth_duration"],
            reauthorization_duration=values["reauthorization_duration"],
            reauthorization_required=values["reauthorization_required"],
            reauthorization_requirements=values["reauthorization_requirements"],
            specialist_types=values["specialist_types"],
            quantity_limits=values["quantity_limits"],
            access_score="NA",
        )

    def _extract_parameters(
        self,
        filename: str,
        chunks: Sequence[PolicyChunk],
        brand: str,
        indication: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        extracted: Dict[str, Any] = {}
        contexts: Dict[str, Any] = {}
        total_fields = len(FIELD_ORDER)
        for index, field_name in enumerate(FIELD_ORDER, start=1):
            if self.verbose:
                print(f"[{index}/{total_fields}] Extracting {field_name} for {brand}...", flush=True)
            evidence_chunks = retrieve_parameter_context(
                chunks=chunks,
                brand=brand,
                field_name=field_name,
                indication=indication,
                max_chunks=3,
            )
            dependency_context = {}
            if field_name in STEP_DERIVED_FIELDS:
                step_evidence_chunks = retrieve_parameter_context(
                    chunks=chunks,
                    brand=brand,
                    field_name="step_therapy_requirements",
                    indication=indication,
                    max_chunks=3,
                )
                evidence_chunks = _dedupe_policy_chunks([*step_evidence_chunks, *evidence_chunks])
                dependency_context = {
                    "source_parameter": "step_therapy_requirements",
                    "source_value": extracted.get("step_therapy_requirements", "NA"),
                    "source_evidence": contexts.get("step_therapy_requirements", {}),
                }
            field_payload = self._ask_llm_for_field(
                filename=filename,
                brand=brand,
                indication=indication,
                field_name=field_name,
                rule_text=self.parameter_rules[field_name],
                evidence_chunks=evidence_chunks,
                extracted_so_far=extracted,
            )
            extracted[field_name] = _field_value(field_payload, field_name)
            contexts[field_name] = {
                "value": extracted[field_name],
                "llm_evidence": field_payload.get("evidence", ""),
                "llm_reasoning": field_payload.get("reasoning", ""),
                "dependency_context": dependency_context,
                "retrieved_context": _serialize_chunks(evidence_chunks),
            }
            if self.verbose:
                print(f"[{index}/{total_fields}] {field_name}: {extracted[field_name]}", flush=True)
        return extracted, contexts

    def _ask_llm_for_field(
        self,
        filename: str,
        brand: str,
        indication: str,
        field_name: str,
        rule_text: str,
        evidence_chunks: Iterable[PolicyChunk],
        extracted_so_far: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence = format_chunks_for_prompt(evidence_chunks, max_chars_per_chunk=700)
        prompt = _build_parameter_prompt(
            filename=filename,
            brand=brand,
            indication=indication,
            field_name=field_name,
            rule_text=rule_text,
            evidence=evidence,
            extracted_so_far=extracted_so_far,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an prior authorization policy analyst in johnsons & johnsons pharma company."
                    "You are extracting parameters for a specific brand and indication from payer policy text."
                    "You are doing this to understand what the policy requires for the brand to be covered or authorised to be coverd by the payer(insurance company)."
                    " You have to find what are The parameter rule supplied by "
                    "the user is mandatory and overrides generic assumptions. Use only supplied "
                    "policy evidence. Return valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        response_text = self.groq_client.chat(messages, temperature=0.0)
        payload = _parse_json_object(response_text)
        if not _valid_field_payload(payload, field_name):
            payload = self._retry_field_extraction(messages, response_text, field_name)
        if not _valid_field_payload(payload, field_name):
            return _fallback_payload(field_name, response_text)
        return payload

    def _retry_field_extraction(
        self,
        original_messages: List[Dict[str, str]],
        previous_response: str,
        field_name: str,
    ) -> Dict[str, Any]:
        retry_messages = [
            *original_messages,
            {
                "role": "assistant",
                "content": previous_response,
            },
            {
                "role": "user",
                "content": (
                    "Correct the previous answer. It must strictly follow the parameter rule, "
                    "must be supported by the supplied evidence, and must be exactly one JSON "
                    f"object with keys: {field_name}, evidence, reasoning. Do not add prose. "
                    "If evidence does not support a value, return NA."
                ),
            },
        ]
        response_text = self.groq_client.chat(retry_messages, temperature=0.0)
        payload = _parse_json_object(response_text)
        if payload:
            payload["_retry_raw_response"] = response_text
        return payload


def extract_policy_from_markdown(
    filename: str,
    markdown_text: str,
    brand_names: Sequence[str],
    indication: str = "Psoriasis",
    max_chunks: int = 14,
) -> ExtractionResponse:
    extractor = LightweightPolicyExtractor(max_chunks=max_chunks)
    return extractor.extract(filename, markdown_text, brand_names, indication)


def _build_parameter_prompt(
    filename: str,
    brand: str,
    indication: str,
    field_name: str,
    rule_text: str,
    evidence: str,
    extracted_so_far: Dict[str, Any],
) -> str:
    return f"""
Target filename: {filename}
Target brand: {brand}
Target indication: {indication} / PsO / Psoriasis
Target field: {field_name}

{_step_dependency_instruction(field_name, extracted_so_far)}
{_field_specific_instruction(field_name)}

The following Parameter rule is the binding source of truth for this extraction.
You must follow it exactly, including edge cases, counting instructions, default outputs, and exclusions.
If the policy evidence appears to imply something different from the rule, follow the rule.
If the evidence is insufficient under the rule, return the rule-specified missing value such as "NA" or "Unspecified".

Use only evidence that applies to:
- the target brand or its generic name,
- the target indication PsO/Psoriasis,
- a drug class/category that clearly includes the target brand,
- universal criteria applying to all brands, all products, all indications, or all products or a genral mention of steps in the relevant class.

Do not use criteria from unrelated indications unless the clause is explicitly universal.
Do not infer requirements that are not stated in the policy evidence.
Do not mention access score or scoring; access score is not being extracted in this run.
Interpret section meaning:
- Approval criteria describe what must be met for coverage in general or for universal indications.
- Coverage requirements may be positive conditions ("patient must have X") or negative conditions ("patient must not have X" / "patient is not receiving X"). Preserve that polarity exactly.
- Negative conditions are still coverage criteria when they appear under approval/denial criteria(think logically).
- For TB: language requiring TB evaluation, testing, screening, or a documented negative TB result before therapy supports tb_test_required = "Yes"; language explicitly saying TB testing is not required supports "No".
- For phototherapy/PUVA: language requiring prior use, trial, failure, inadequate response, intolerance, contraindication, or inability to use phototherapy/PUVA before approval supports step_through_phototherapy = "Yes"; language prohibiting concurrent phototherapy or requiring confirmation the patient is not receiving phototherapy does not.
- Reference, footnote, bibliography, appendix, and history text should not be used as policy criteria.

Parameter rule:
{rule_text}

Output rules:
- The value must be derived from the Parameter rule plus Policy evidence only.
- Do not use medical knowledge, FDA label knowledge, payer assumptions, or prior extracted values unless the current Parameter rule explicitly says to.
- Do not invent criteria, thresholds, requirements, access score language, or therapeutic steps.
- Preserve whether evidence says "required", "not required", "not receiving", "denied", "contraindicated", "failed", or "intolerant"; these are not interchangeable because these might represent the criteria for coverage of the target brand.
- If a value is not directly supported by a cited chunk, return "NA" or the rule-specific fallback.
- Use "NA" when the parameter is not documented in the evidence.
- Use "Unspecified" when the parameter applies but the exact value is not stated.
- For Yes/No fields, return "Yes", "No", or "NA".
- For count fields, return a numeric string or "NA".
- For durations, return months when possible, such as "6" or "12"; otherwise preserve the policy wording.
- Keep step therapy and reauthorization requirements do not remove important alternatives or exceptions.
- The evidence field must cite the chunk id and quote/paraphrase the exact policy context used.
- Use logical reasoning to determine the parameter value but DO NOT HALLUCINATE EVIDENCE.
- If the evidence does not support a value, return "NA" rather than guessing.
- Return exactly one JSON object with this shape:
  {{"{field_name}": "<value>", "evidence": "<chunk id and supporting policy text>", "reasoning": "<brief decision reason>"}}

Policy evidence:
{evidence}
""".strip()


def _step_dependency_instruction(field_name: str, extracted_so_far: Dict[str, Any]) -> str:
    if field_name not in STEP_DERIVED_FIELDS:
        return ""

    step_value = extracted_so_far.get("step_therapy_requirements", "NA")
    return f"""
Dependency instruction:
- The step therapy requirements parameter has already been extracted.
- Use the previously extracted step therapy requirements as the universe of steps to classify/count.
- Do not count therapies that are not part of the step therapy requirements.
- If the previously extracted step therapy requirements are "NA", return "NA" unless the supplied evidence clearly documents a step requirement.
- Previously extracted step_therapy_requirements: {step_value}
""".strip()


def _field_specific_instruction(field_name: str) -> str:
    if field_name == "step_therapy_requirements":
        return """
Step therapy output instruction:
- Return the value as a direct list of all applicable step/prior-therapy policy statements.
- Preserve the original condition structure: AND, OR, alternatives, exceptions, contraindication, intolerance, inadequate response, and inability to use.
- Do not collapse multiple criteria into a vague summary.
- Do not add criteria that are not explicitly supported by the policy evidence.
- Include universal, indication-level, class-level, and brand-level step requirements only when they apply to the target brand/PsO.
- Format the value as concise numbered points, for example:
  1. [AND] Patient meets ...
  2. [AND] Has tried and failed ...
  3. [OR/Exception] Contraindication/intolerance to ...
""".strip()

    if field_name == "reauthorization_requirements":
        return """
Reauthorization requirements output instruction:
- Return the value as a direct list of all applicable reauthorization/renewal/continuation policy statements.
- Preserve the original condition structure: AND, OR, alternatives, exceptions, chart-note requirements, clinical response requirements, safety/toxicity requirements, adherence requirements, and continued diagnosis requirements.
- Do not collapse multiple continuation criteria into a vague summary.
- Do not add requirements that are not explicitly supported by the policy evidence.
- Include universal, indication-level, class-level, and brand-level reauthorization requirements only when they apply to the target brand/PsO.
- Format the value as concise numbered points, for example:
  1. [AND] Continued diagnosis of ...
  2. [AND] Documentation of positive clinical response ...
  3. [OR/Exception] No intolerance/contraindication/unacceptable toxicity ...
""".strip()

    return ""


def _parse_json_object(response_text: str) -> Dict[str, Any]:
    response_text = response_text.strip()
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        parsed = _parse_first_json_object(response_text)

    return parsed if isinstance(parsed, dict) else {}


def _parse_first_json_object(response_text: str) -> Dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(response_text):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(response_text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _valid_field_payload(payload: Dict[str, Any], field_name: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if field_name not in payload and "value" not in payload:
        return False
    if "evidence" not in payload or "reasoning" not in payload:
        return False
    return True


def _fallback_payload(field_name: str, raw_response: str) -> Dict[str, Any]:
    return {
        field_name: FIELD_DEFAULTS[field_name],
        "evidence": "",
        "reasoning": "Model did not return valid rule-adherent JSON with evidence.",
        "raw_response": raw_response,
    }


def _stringify_values(payload: Dict[str, Any]) -> Dict[str, str]:
    values = {}
    for key in FIELD_DEFAULTS:
        value = payload.get(key, FIELD_DEFAULTS[key])
        if value is None:
            values[key] = FIELD_DEFAULTS[key]
        elif isinstance(value, (list, dict)):
            values[key] = json.dumps(value, ensure_ascii=False)
        else:
            values[key] = str(value).strip()
    return values


def _field_value(payload: Dict[str, Any], field_name: str) -> Any:
    if field_name in payload:
        return payload[field_name]
    if "value" in payload:
        return payload["value"]
    return FIELD_DEFAULTS[field_name]


def _dedupe_policy_chunks(chunks: Sequence[PolicyChunk]) -> List[PolicyChunk]:
    seen = set()
    deduped = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _serialize_chunks(chunks: Iterable[PolicyChunk]) -> List[Dict[str, Any]]:
    serialized = []
    for chunk in chunks:
        serialized.append(
            {
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "tags": sorted(chunk.tags),
                "text": chunk.text,
            }
        )
    return serialized
