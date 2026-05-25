import csv
import json
import os
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from extraction.llm_client import call_llm_text, resolve_model


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_MD_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_OUT = OUTPUT_DIR / "brand_names.csv"
JSON_OUT = OUTPUT_DIR / "brand_names.json"

ENV_FILE = BASE_DIR / ".env"


logger = logging.getLogger("brand_name_extractor")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def load_dotenv_value(key: str) -> str:
    if not ENV_FILE.exists():
        return ""

    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip().strip('"').strip("'")
        return value
    return ""


LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or load_dotenv_value("LLM_PROVIDER") or "groq").strip().lower()
DEEPSEEK_API_KEY = (
    os.getenv("DEEPSEEK_API_KEY")
    or load_dotenv_value("DEEPSEEK_API_KEY")
    or os.getenv("DEEPSEEK_V3_API_KEY")
    or load_dotenv_value("DEEPSEEK_V3_API_KEY")
).strip()
DEEPSEEK_MODEL = (os.getenv("DEEPSEEK_MODEL") or load_dotenv_value("DEEPSEEK_MODEL") or "deepseek-chat").strip()
DEEPSEEK_API_URL = (
    os.getenv("DEEPSEEK_API_URL")
    or load_dotenv_value("DEEPSEEK_API_URL")
    or "https://api.deepseek.com/chat/completions"
).strip()
ACTIVE_MODEL = {
    "deepseek": DEEPSEEK_MODEL,
    "groq": resolve_model("groq"),
    "llama": resolve_model("groq"),
    "gemini": resolve_model("gemini"),
}.get(LLM_PROVIDER, resolve_model("groq"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS") or load_dotenv_value("MAX_OUTPUT_TOKENS") or "2048")
REQUESTS_PER_MINUTE = int(os.getenv("REQUESTS_PER_MINUTE") or load_dotenv_value("REQUESTS_PER_MINUTE") or "5")
REQUEST_DELAY_SECONDS = float(
    os.getenv("REQUEST_DELAY_SECONDS") or load_dotenv_value("REQUEST_DELAY_SECONDS") or str(60 / REQUESTS_PER_MINUTE)
)
_LAST_LLM_CALL_AT = 0.0

# Seed brands to improve normalization and reduce false negatives on pharma-specific aliases.
SAMPLE_BRANDS = [
    "Acitretin",
    "Amjevita",
    "Avsola",
    "Bimzelx",
    "Cimzia",
    "Cosentyx",
    "Cyclosporine",
    "Cyltezo",
    "Enbrel",
    "Hulio",
    "Humira",
    "Hyrimoz",
    "Idacio",
    "Ilumya",
    "Inflectra",
    "Methotrexate",
    "Otezla",
    "Otulfi",
    "Psychiva / Quallent",
    "Remicade",
    "Renflexis",
    "Selarsdi",
    "Siliq",
    "Skyrizi",
    "Sotyktu",
    "Stelara",
    "Steqeyma",
    "Taltz",
    "Tremfya",
    "Vtama",
    "Wezlana",
    "Yesintek",
    "Yuflyma",
    "Yusimry",
    "Zoryve",
    "Pyzchiva",
    "Imuldosa",
    "Quallent",
]


def read_markdown_files() -> list[Path]:
    return sorted(RAW_MD_DIR.glob("*.md"))


def split_text(text: str, max_chars: int = 9000) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para)
        if current and current_len + para_len + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + 2

    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text[:max_chars]]


def estimate_output_tokens(chunk_text: str) -> int:
    """
    Brand extraction should return compact JSON, so we keep the cap modest.
    Larger chunks get a bit more room, but not a huge allowance.
    """
    base = 512
    scaled = len(chunk_text) // 8
    return max(512, min(MAX_OUTPUT_TOKENS, base + scaled))


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_array_text(text: str) -> str:
    text = strip_markdown_fences(text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1:
        return text
    if end != -1 and end > start:
        return text[start : end + 1]
    return text[start:]


def salvage_complete_objects(text: str) -> list[dict]:
    text = extract_json_array_text(text)
    decoder = json.JSONDecoder()
    items: list[dict] = []
    idx = 0

    while idx < len(text):
        obj_start = text.find("{", idx)
        if obj_start == -1:
            break
        try:
            obj, next_idx = decoder.raw_decode(text[obj_start:])
        except json.JSONDecodeError:
            idx = obj_start + 1
            continue
        if isinstance(obj, dict):
            items.append(obj)
        idx = obj_start + next_idx

    return items


def salvage_partial_brand_objects(text: str) -> list[dict]:
    text = extract_json_array_text(text)
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for match in re.finditer(
        r'"brand_name"\s*:\s*"(?P<brand>[^"]+)"\s*,\s*'
        r'"normalized_brand_name"\s*:\s*"(?P<normalized>[^"]+)"'
        r'(?:\s*,\s*"confidence"\s*:\s*(?P<confidence>[0-9.]+))?',
        text,
        flags=re.DOTALL,
    ):
        brand = match.group("brand").strip()
        normalized = match.group("normalized").strip()
        if not brand and not normalized:
            continue
        key = (brand.lower(), normalized.lower())
        if key in seen:
            continue
        seen.add(key)
        confidence = match.group("confidence")
        items.append(
            {
                "brand_name": brand,
                "normalized_brand_name": normalized or brand,
                "confidence": float(confidence) if confidence else "",
            }
        )

    return items


def parse_gemini_items(text: str) -> list[dict]:
    json_text = extract_json_array_text(text)
    try:
        parsed = json.loads(json_text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        salvaged = salvage_complete_objects(json_text)
        if salvaged:
            logger.warning("Recovered %s complete objects from malformed Gemini JSON", len(salvaged))
            return salvaged
        partial = salvage_partial_brand_objects(json_text)
        if partial:
            logger.warning("Recovered %s partial brand objects from malformed Gemini JSON", len(partial))
            return partial
        preview = text[:500].replace("\n", "\\n")
        logger.warning("Unable to parse Gemini response preview: %s", preview)
        return []


def extract_retry_delay_seconds(error: Exception) -> float | None:
    text = str(error)
    match = re.search(r"retryDelay':\s*'(?P<seconds>[0-9.]+)s'", text)
    if match:
        return float(match.group("seconds"))

    match = re.search(r"Please retry in (?P<seconds>[0-9.]+)s", text)
    if match:
        return float(match.group("seconds"))

    return None


def is_daily_quota_error(error: Exception) -> bool:
    text = str(error)
    return "GenerateRequestsPerDayPerProjectPerModel" in text


def throttle_llm_call() -> None:
    global _LAST_LLM_CALL_AT

    elapsed = time.time() - _LAST_LLM_CALL_AT
    wait_seconds = REQUEST_DELAY_SECONDS - elapsed
    if wait_seconds > 0:
        logger.info("Rate limit throttle: sleeping %.2fs before next %s call", wait_seconds, LLM_PROVIDER)
        time.sleep(wait_seconds)

    _LAST_LLM_CALL_AT = time.time()


def prompt_text_from_payload(payload: dict) -> str:
    try:
        return payload["contents"][0]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Prompt payload is malformed.")


def build_prompt(chunk_text: str, source_name: str) -> dict:
    sample_block = "\n".join(f"- {brand}" for brand in SAMPLE_BRANDS)
    instruction = (
        "You are a pharma market-access analyst at Johnson & Johnson, and your task is to extract only branded drug names from payer prior authorization (PA) policy documents.\n"
        "Keep a pharma-commercial perspective: favor recognizing real marketed brands, brand aliases, and slash-separated brand forms.\n"
        "The document may be imperfectly formatted because it was extracted from a PDF, so tables, bullets, headings, and labels may be flattened or merged.\n"
        "\n"
        "TASK:\n"
        "- Extract only brand names and obvious brand aliases that appear in the document.\n"
        "- Treat PA group names or drug group labels as brand candidates when the context clearly points to a marketed drug.\n"
        "- Use the sample list to normalize spelling variants, aliases, and combined brand names.\n"
        "- If a brand appears in a step-therapy example, still extract it.\n"
        "\n"
        "STRICT EXCLUSIONS:\n"
        "- Do not output diagnoses, diseases, payer names, section headings, lab values, dosage forms, or generic-only terms.\n"
        "- Do not invent brands that are not present or strongly implied by the document.\n"
        "- Do not return generic molecules unless they are clearly tied to a branded entity in the text.\n"
        "\n"
        "OUTPUT RULES:\n"
        "Return ONLY compact valid JSON. Do not wrap it in markdown fences.\n"
        "Use this exact schema: [{\"brand_name\":\"...\",\"normalized_brand_name\":\"...\",\"confidence\":1.0}]\n"
        "Do not include evidence, notes, explanations, markdown, or extra text.\n"
        "Confidence must be a number from 0 to 1.\n"
    )   

    user_text = (
        f"Source file: {source_name}\n\n"
        f"Sample brand names:\n{sample_block}\n\n"
        f"Document excerpt:\n{chunk_text}\n"
    )
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": instruction + "\n" + user_text}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.9,
            "maxOutputTokens": estimate_output_tokens(chunk_text),
        },
    }


def call_deepseek(payload: dict, retries: int = 3) -> list[dict]:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment or .env file.")

    prompt_text = prompt_text_from_payload(payload)

    for attempt in range(retries):
        try:
            throttle_llm_call()
            logger.info(
                "Calling DeepSeek model=%s attempt=%s max_output_tokens=%s",
                DEEPSEEK_MODEL,
                attempt + 1,
                payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
            )

            request_body = {
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": payload.get("generationConfig", {}).get("temperature", 0.1),
                "top_p": payload.get("generationConfig", {}).get("topP", 0.9),
                "max_tokens": payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
                "stream": False,
            }
            request = urllib.request.Request(
                DEEPSEEK_API_URL,
                data=json.dumps(request_body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=120) as response:
                response_json = json.loads(response.read().decode("utf-8"))

            text = response_json["choices"][0]["message"]["content"].strip()
            if not text:
                logger.warning("Empty response from DeepSeek")
                return []

            parsed = parse_gemini_items(text)
            logger.info("DeepSeek returned %s parseable items", len(parsed))
            return parsed

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            logger.warning("DeepSeek HTTP error on attempt %s: %s %s", attempt + 1, e.code, body[:500])
            if attempt < retries - 1:
                retry_delay = extract_retry_delay_seconds(Exception(body))
                time.sleep(retry_delay if retry_delay is not None else REQUEST_DELAY_SECONDS)
                continue
            raise RuntimeError(f"DeepSeek API failed: HTTP {e.code} {body}") from e

        except Exception as e:
            logger.warning("DeepSeek call failed on attempt %s: %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            raise


def call_groq(payload: dict, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            throttle_llm_call()
            logger.info(
                "Calling Groq model=%s attempt=%s max_output_tokens=%s",
                resolve_model("groq"),
                attempt + 1,
                payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
            )

            text = call_llm_text(
                prompt_text_from_payload(payload),
                provider="groq",
                model=resolve_model("groq"),
                temperature=payload.get("generationConfig", {}).get("temperature", 0.1),
                top_p=payload.get("generationConfig", {}).get("topP", 0.9),
                max_tokens=payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
                json_mode=False,
            )
            if not text:
                logger.warning("Empty response from Groq")
                return []

            parsed = parse_gemini_items(text)
            logger.info("Groq returned %s parseable items", len(parsed))
            return parsed

        except Exception as e:
            logger.warning("Groq call failed on attempt %s: %s", attempt + 1, e)
            if attempt < retries - 1:
                retry_delay = extract_retry_delay_seconds(e)
                time.sleep(retry_delay if retry_delay is not None else REQUEST_DELAY_SECONDS)
                continue
            raise


def call_gemini(payload: dict, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            throttle_llm_call()
            logger.info(
                "Calling Gemini model=%s attempt=%s max_output_tokens=%s",
                resolve_model("gemini"),
                attempt + 1,
                payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
            )

            text = call_llm_text(
                prompt_text_from_payload(payload),
                provider="gemini",
                model=resolve_model("gemini"),
                temperature=payload.get("generationConfig", {}).get("temperature", 0.1),
                top_p=payload.get("generationConfig", {}).get("topP", 0.9),
                max_tokens=payload.get("generationConfig", {}).get("maxOutputTokens", MAX_OUTPUT_TOKENS),
                json_mode=False,
            )
            if not text:
                logger.warning("Empty response from Gemini")
                return []

            parsed = parse_gemini_items(text)
            logger.info("Gemini returned %s parseable items", len(parsed))
            return parsed

        except Exception as e:
            logger.warning("Gemini call failed on attempt %s: %s", attempt + 1, e)
            if attempt < retries - 1:
                retry_delay = extract_retry_delay_seconds(e)
                time.sleep(retry_delay if retry_delay is not None else REQUEST_DELAY_SECONDS)
                continue
            raise


def call_llm(payload: dict, retries: int = 3) -> list[dict]:
    if LLM_PROVIDER == "deepseek":
        return call_deepseek(payload, retries=retries)
    if LLM_PROVIDER in {"groq", "llama"}:
        return call_groq(payload, retries=retries)
    if LLM_PROVIDER == "gemini":
        return call_gemini(payload, retries=retries)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


def normalize_item(item: dict, source_file: str) -> dict | None:
    brand_name = str(item.get("brand_name", "")).strip()
    normalized = str(item.get("normalized_brand_name", "")).strip() or brand_name
    evidence = str(item.get("evidence", "")).strip()
    notes = str(item.get("notes", "")).strip()
    confidence = item.get("confidence", "")

    if not brand_name and not normalized:
        return None

    return {
        "brand_name": brand_name or normalized,
        "normalized_brand_name": normalized,
        "source_file": source_file,
        "confidence": confidence,
        "evidence": evidence[:350],
        "notes": notes[:350],
    }


def upsert_brand_rows(by_brand: dict[str, dict], rows: list[dict]) -> None:
    for row in rows:
        key = row["normalized_brand_name"].lower()
        existing = by_brand.get(key)
        if not existing:
            by_brand[key] = row
            continue

        existing_conf = existing.get("confidence", 0) or 0
        new_conf = row.get("confidence", 0) or 0
        if isinstance(existing_conf, str):
            try:
                existing_conf = float(existing_conf)
            except ValueError:
                existing_conf = 0
        if isinstance(new_conf, str):
            try:
                new_conf = float(new_conf)
            except ValueError:
                new_conf = 0

        if new_conf >= existing_conf and len(row.get("evidence", "")) > len(existing.get("evidence", "")):
            by_brand[key] = row


def save_outputs(rows: list[dict], per_file_counts: dict[str, int]) -> None:
    rows = sorted(rows, key=lambda r: r["normalized_brand_name"].lower())

    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "brand_name",
                "normalized_brand_name",
                "source_file",
                "confidence",
                "evidence",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    with JSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "provider": LLM_PROVIDER,
                "model": ACTIVE_MODEL,
                "file_count": len(per_file_counts),
                "chunk_count_by_file": per_file_counts,
                "brand_count": len(rows),
                "brands": rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def load_existing_outputs() -> tuple[dict[str, dict], dict[str, int]]:
    if not JSON_OUT.exists():
        return {}, {}

    try:
        data = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Could not parse existing output JSON; starting fresh")
        return {}, {}

    by_brand: dict[str, dict] = {}
    for row in data.get("brands", []):
        if not isinstance(row, dict):
            continue
        normalized = str(row.get("normalized_brand_name", "")).strip()
        if not normalized:
            continue
        by_brand[normalized.lower()] = row

    raw_counts = data.get("chunk_count_by_file", {})
    per_file_counts = {
        str(filename): int(count)
        for filename, count in raw_counts.items()
        if str(filename).strip()
    } if isinstance(raw_counts, dict) else {}

    logger.info(
        "Loaded resume state: %s brands across %s completed files",
        len(by_brand),
        len(per_file_counts),
    )
    return by_brand, per_file_counts


def main() -> None:
    start = time.time()
    files = read_markdown_files()
    if not files:
        raise FileNotFoundError(f"No markdown files found in {RAW_MD_DIR}")

    logger.info("Starting extraction for %s markdown files", len(files))
    logger.info("LLM provider: %s | model: %s", LLM_PROVIDER, ACTIVE_MODEL)
    logger.info("Output CSV: %s", CSV_OUT)
    logger.info("Output JSON: %s", JSON_OUT)

    by_brand, per_file_counts = load_existing_outputs()
    completed_files = set(per_file_counts)

    for md_file in files:
        if md_file.name in completed_files:
            logger.info("Skipping completed file from existing output: %s", md_file.name)
            continue

        logger.info("Reading file: %s", md_file.name)
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        chunks = split_text(text)
        logger.info("Chunk count for %s: %s", md_file.name, len(chunks))

        file_rows: list[dict] = []
        for idx, chunk in enumerate(chunks, start=1):
            logger.info(
                "Processing %s chunk %s/%s (chars=%s)",
                md_file.name,
                idx,
                len(chunks),
                len(chunk),
            )
            payload = build_prompt(chunk, f"{md_file.name} [chunk {idx}/{len(chunks)}]")
            try:
                items = call_llm(payload)
            except (TimeoutError, json.JSONDecodeError, RuntimeError, Exception) as e:
                logger.exception("Gemini extraction failed for %s chunk %s", md_file.name, idx)
                if file_rows:
                    upsert_brand_rows(by_brand, file_rows)
                    save_outputs(list(by_brand.values()), per_file_counts)
                    logger.info(
                        "Saved partial progress for %s before stopping: %s unique brands",
                        md_file.name,
                        len(by_brand),
                    )
                if is_daily_quota_error(e):
                    logger.error(
                        "Stopping because daily Gemini quota is exhausted. %s is not marked completed.",
                        md_file.name,
                    )
                    return
                raise RuntimeError(f"Gemini extraction failed for {md_file.name} chunk {idx}: {e}") from e

            for item in items:
                normalized = normalize_item(item, md_file.name)
                if normalized:
                    file_rows.append(normalized)

            logger.info(
                "Completed %s chunk %s/%s with %s candidate brands",
                md_file.name,
                idx,
                len(chunks),
                len(items),
            )

        upsert_brand_rows(by_brand, file_rows)
        per_file_counts[md_file.name] = len(chunks)
        save_outputs(list(by_brand.values()), per_file_counts)
        logger.info(
            "Saved progress after %s: %s unique brands",
            md_file.name,
            len(by_brand),
        )
    rows = sorted(by_brand.values(), key=lambda r: r["normalized_brand_name"].lower())
    save_outputs(rows, per_file_counts)

    elapsed = round(time.time() - start, 2)
    logger.info("Extraction completed in %ss", elapsed)
    logger.info("Unique brands extracted: %s", len(rows))
    print(f"Extracted {len(rows)} unique brand names in {elapsed}s")
    print(f"CSV: {CSV_OUT}")
    print(f"JSON: {JSON_OUT}")


if __name__ == "__main__":
    main()
