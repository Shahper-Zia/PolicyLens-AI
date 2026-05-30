import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.orchestrator.large_doc_extractor.chunker import LargeDocChunk, split_large_markdown
from src.orchestrator.large_doc_extractor.retriever import (
    format_large_chunks_for_prompt,
    retrieve_large_doc_parameter_context,
)
from src.orchestrator.large_doc_extractor.vocabulary import build_large_doc_vocabulary
from src.orchestrator.lightweight_extractor.groq_client import GroqClient
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


class LargeDocPolicyExtractor:
    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        verbose: bool = False,
        use_llm_vocabulary: bool = True,
    ):
        self.groq_client = groq_client or GroqClient()
        self.parameter_rules = load_parameter_rules(compact=False)
        self.verbose = verbose
        self.use_llm_vocabulary = use_llm_vocabulary
        self.last_contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def extract(
        self,
        filename: str,
        markdown_text: str,
        brand_names: Sequence[str],
        indication: str = "Psoriasis",
    ) -> ExtractionResponse:
        chunks = split_large_markdown(markdown_text)
        vocabulary = build_large_doc_vocabulary(
            chunks=chunks,
            brand_names=brand_names,
            indication=indication,
            groq_client=self.groq_client,
            use_llm=self.use_llm_vocabulary,
        )

        if self.verbose:
            print(f"Large-doc chunks: {len(chunks)}", flush=True)
            print(f"Vocabulary: {json.dumps(vocabulary, ensure_ascii=False)}", flush=True)

        attributes = [
            self.extract_brand_attributes(filename, chunks, brand, indication, vocabulary)
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
        chunks: Sequence[LargeDocChunk],
        brand: str,
        indication: str,
        vocabulary: Dict[str, Any],
    ) -> BrandAttribute:
        payload, contexts = self._extract_parameters(filename, chunks, brand, indication, vocabulary)
        contexts["_vocabulary"] = vocabulary
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
        chunks: Sequence[LargeDocChunk],
        brand: str,
        indication: str,
        vocabulary: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        extracted: Dict[str, Any] = {}
        contexts: Dict[str, Any] = {}

        for index, field_name in enumerate(FIELD_ORDER, start=1):
            if self.verbose:
                print(f"[{index}/{len(FIELD_ORDER)}] Extracting {field_name} for {brand}...", flush=True)

            evidence_chunks = retrieve_large_doc_parameter_context(
                chunks=chunks,
                brand=brand,
                field_name=field_name,
                vocabulary=vocabulary,
                indication=indication,
                max_chunks=6 if field_name in {"step_therapy_requirements", "reauthorization_requirements"} else 5,
            )

            dependency_context = {}
            if field_name in STEP_DERIVED_FIELDS:
                step_chunks = retrieve_large_doc_parameter_context(
                    chunks=chunks,
                    brand=brand,
                    field_name="step_therapy_requirements",
                    vocabulary=vocabulary,
                    indication=indication,
                    max_chunks=6,
                )
                evidence_chunks = _dedupe_chunks([*step_chunks, *evidence_chunks])
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
                print(f"[{index}/{len(FIELD_ORDER)}] {field_name}: {extracted[field_name]}", flush=True)

        return extracted, contexts

    def _ask_llm_for_field(
        self,
        filename: str,
        brand: str,
        indication: str,
        field_name: str,
        rule_text: str,
        evidence_chunks: Iterable[LargeDocChunk],
        extracted_so_far: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence = format_large_chunks_for_prompt(evidence_chunks, max_chars_per_chunk=950)
        prompt = _build_parameter_prompt(filename, brand, indication, field_name, rule_text, evidence, extracted_so_far)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a payer prior authorization analyst. The supplied parameter rule is mandatory. "
                    "Use only supplied evidence and return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
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
            {"role": "assistant", "content": previous_response},
            {
                "role": "user",
                "content": (
                    "Correct the previous answer. Return exactly one JSON object with keys "
                    f"{field_name}, evidence, reasoning. Follow the parameter rule exactly. "
                    "If evidence does not support a value, return NA."
                ),
            },
        ]
        response_text = self.groq_client.chat(retry_messages, temperature=0.0)
        payload = _parse_json_object(response_text)
        if payload:
            payload["_retry_raw_response"] = response_text
        return payload


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

Return exactly one JSON object:
{{"{field_name}": "<value>", "evidence": "<chunk id/page/lines and supporting policy text>", "reasoning": "<brief rule-based reason>"}}

Policy evidence:
{evidence}
""".strip()


def _step_dependency_instruction(field_name: str, extracted_so_far: Dict[str, Any]) -> str:
    if field_name not in STEP_DERIVED_FIELDS:
        return ""
    return f"""
Dependency instruction:
- step_therapy_requirements has already been extracted.
- Use that extracted step therapy requirement as the universe of steps to classify/count.
- Do not count therapies outside the step therapy requirement set.
- Previously extracted step_therapy_requirements: {extracted_so_far.get("step_therapy_requirements", "NA")}
""".strip()


def _field_specific_instruction(field_name: str) -> str:
    if field_name == "step_therapy_requirements":
        return """
Step therapy output instruction:
- Return the value as direct numbered policy statements, preserving AND/OR criteria and exceptions.
- Do not collapse criteria into a vague summary.
""".strip()
    if field_name == "reauthorization_requirements":
        return """
Reauthorization requirements output instruction:
- Return the value as direct numbered continuation/renewal policy statements.
- Preserve AND/OR criteria, response/documentation requirements, and exceptions.
""".strip()
    return ""


def _parse_json_object(response_text: str) -> Dict[str, Any]:
    response_text = response_text.strip()
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(response_text):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(response_text[index:])
            except json.JSONDecodeError:
                continue
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _valid_field_payload(payload: Dict[str, Any], field_name: str) -> bool:
    return isinstance(payload, dict) and (field_name in payload or "value" in payload) and "evidence" in payload and "reasoning" in payload


def _fallback_payload(field_name: str, raw_response: str) -> Dict[str, Any]:
    return {
        field_name: FIELD_DEFAULTS[field_name],
        "evidence": "",
        "reasoning": "Model did not return valid rule-adherent JSON with evidence.",
        "raw_response": raw_response,
    }


def _field_value(payload: Dict[str, Any], field_name: str) -> Any:
    if field_name in payload:
        return payload[field_name]
    if "value" in payload:
        return payload["value"]
    return FIELD_DEFAULTS[field_name]


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


def _serialize_chunks(chunks: Iterable[LargeDocChunk]) -> List[Dict[str, Any]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "tags": sorted(chunk.tags),
            "text": chunk.text,
        }
        for chunk in chunks
    ]


def _dedupe_chunks(chunks: Sequence[LargeDocChunk]) -> List[LargeDocChunk]:
    seen = set()
    deduped = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped
