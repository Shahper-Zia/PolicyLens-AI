from pathlib import Path
import json
import sys

from openai import OpenAI

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import extraction.brand_name_extractor as b

TARGET_FILE = "Copy of 195158-4643510.md"
OUTPUT_TEST_DIR = b.BASE_DIR / "output_test"
OUTPUT_TEST_DIR.mkdir(parents=True, exist_ok=True)

RAW_RESPONSE_OUT = OUTPUT_TEST_DIR / "extractor_test_raw_response.txt"
PARSED_OUT = OUTPUT_TEST_DIR / "extractor_test_parsed.json"


def get_raw_response(payload: dict) -> str:
    if not b.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY or LLAMA_API_KEY is not set.")

    client = OpenAI(api_key=b.GROQ_API_KEY, base_url=b.GROQ_API_URL)
    response = client.chat.completions.create(
        model=b.GROQ_MODEL,
        messages=[{"role": "user", "content": b.prompt_text_from_payload(payload)}],
        temperature=payload.get("generationConfig", {}).get("temperature", 0.1),
        top_p=payload.get("generationConfig", {}).get("topP", 0.9),
        max_tokens=payload.get("generationConfig", {}).get("maxOutputTokens", 1024),
    )
    return (response.choices[0].message.content or "").strip()


def main() -> None:
    first = b.RAW_MD_DIR / TARGET_FILE
    if not first.exists():
        raise FileNotFoundError(f"File not found: {first}")

    text = first.read_text(encoding="utf-8", errors="ignore")
    chunks = b.split_text(text)

    print(f"file        : {first.name}")
    print(f"chunk_count : {len(chunks)}")
    print(f"model       : {b.GROQ_MODEL}")
    print(f"api_key     : {bool(b.GROQ_API_KEY)}")
    print(f"output_dir  : {OUTPUT_TEST_DIR}")

    all_parsed = []
    raw_lines = []

    for idx, chunk in enumerate(chunks[:3], start=1):
        print(f"\n===== CHUNK {idx}/3 =====")
        print(chunk[:2500])

        payload = b.build_prompt(chunk, f"{first.name} [chunk {idx}/3]")
        try:
            raw = get_raw_response(payload)
            raw_lines.append(f"\n### CHUNK {idx}/3\n{raw}\n")

            print("\n----- RAW GROQ RESPONSE -----")
            print(raw if raw else "[empty response]")
            print("----- END RAW RESPONSE -----\n")

            parsed = b.parse_gemini_items(raw) if raw else []
            print(f"parsed_items: {len(parsed)}")
            all_parsed.extend(parsed)
            for item in parsed[:5]:
                print(json.dumps(item, ensure_ascii=False))
        except Exception as e:
            print(f"ERROR chunk {idx}: {type(e).__name__}: {e}")
            raise

        RAW_RESPONSE_OUT.write_text("".join(raw_lines), encoding="utf-8")
        PARSED_OUT.write_text(json.dumps(all_parsed, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nraw_response_saved: {RAW_RESPONSE_OUT}")
    print(f"parsed_saved      : {PARSED_OUT}")
    print(f"parsed_total      : {len(all_parsed)}")


if __name__ == "__main__":
    main()
