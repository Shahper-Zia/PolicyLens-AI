import json
import re
from pathlib import Path
from typing import Any, Dict

try:
    from src.orchestrator.llm.groq_client import GroqClient
except ImportError:  # pragma: no cover
    from orchestrator.llm.groq_client import GroqClient


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LARGE_DOC_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "large_doc_extractor"
SCORING_FRAMEWORK_PATH = Path(__file__).with_name("access_score_scoring_framework.md")


def calculate_access_score(file_name: str, brand: str) -> Dict[str, Any]:
    file_brand_key = f"{Path(str(file_name)).stem}_{brand}".lower()
    output_file = find_large_doc_output(file_name, brand)

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    brand_attributes = payload.get("brand_attributes")
    if not isinstance(brand_attributes, dict):
        raise ValueError(f"brand_attributes was not found in {output_file}")

    scoring_framework = SCORING_FRAMEWORK_PATH.read_text(encoding="utf-8")
    prompt = (
        "Use the scoring framework to calculate the access score from brand_attributes only.\n"
        "Do not hallucinate missing policy facts. NA should not be penalized unless the framework says so.\n"
        "Return JSON only in this format: {\"access_score\": 0, \"reasoning\": \"brief reason\"}.\n\n"
        f"SCORING FRAMEWORK:\n{scoring_framework}\n\n"
        f"BRAND ATTRIBUTES:\n{json.dumps(brand_attributes, ensure_ascii=False, indent=2)}"
    )

    response_text = GroqClient().chat(
        [
            {
                "role": "system",
                "content": "You calculate normalized payer access scores from 0 to 100. Return valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.0,
    )
    llm_result = _parse_json(response_text)
    access_score = _normalize_score(llm_result.get("access_score"))

    brand_attributes["access_score"] = str(access_score)
    _update_nested_brand_attributes(payload, brand_attributes)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        file_brand_key: {
            "file_name": file_name,
            "brand": brand,
            "access_score": access_score,
            "brand_attributes": brand_attributes,
            "reasoning": llm_result.get("reasoning", ""),
        }
    }


def find_large_doc_output(file_name: str, brand: str) -> Path:
    expected = f"{Path(str(file_name)).stem}_{brand}".lower()

    for output_file in LARGE_DOC_OUTPUT_DIR.glob("*.json"):
        if output_file.stem.lower() == expected:
            return output_file

    raise FileNotFoundError(
        f"Could not find {expected}.json in {LARGE_DOC_OUTPUT_DIR}"
    )


def _update_nested_brand_attributes(payload: Dict[str, Any], brand_attributes: Dict[str, Any]) -> None:
    extraction = payload.get("extraction")
    if not isinstance(extraction, dict):
        return

    nested_attributes = extraction.get("brand_attributes")
    if isinstance(nested_attributes, list) and nested_attributes:
        nested_attributes[0]["access_score"] = brand_attributes["access_score"]
    elif isinstance(nested_attributes, dict):
        nested_attributes["access_score"] = brand_attributes["access_score"]


def _parse_json(response_text: str) -> Dict[str, Any]:
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", response_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_score(value: Any) -> int:
    if value is None:
        raise ValueError("LLM did not return access_score")

    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if not match:
            raise ValueError(f"access_score is not numeric: {value}")
        value = match.group(0)

    return max(0, min(100, round(float(value))))
