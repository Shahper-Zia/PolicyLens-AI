
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess

from src.orchestrator.kg_maker.kg_maker import KG_MAKER_DIR, PROJECT_ROOT, get_paths
from src.orchestrator.kg_maker.kg_maker import update_yaml

PARAM_EXTRACTOR_DIR = Path(__file__).resolve().parent
RULES_DIR = PARAM_EXTRACTOR_DIR / "rules"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "src" / "query_results"

results = {}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def query_existing_graph(file_name, brand_name, results_dir=DEFAULT_RESULTS_DIR):
    paths = get_paths(file_name)

    log(f"Starting queries for: {file_name} | {brand_name}")

    update_yaml(
        file_name=file_name,
        output_dir=paths["output_dir"],
        lancedb_dir=paths["final_lancedb_dir"]
    )

    row_results = {}

    rules = sorted([f for f in os.listdir(RULES_DIR) if f.endswith(".md")], reverse=True)

    log(f"Found {len(rules)} rule files.")

    for rule_file in rules:
        rule_path = RULES_DIR / rule_file

        with open(rule_path, "r", encoding="utf-8") as f:
            rule_text = f.read().strip()

        query = f"""
You are extracting a parameter from prior authorization policy.

Target brand: {brand_name}
Target indication: PsO / Psoriasis

Parameter rule:
{rule_text}

Instructions:
- Use only information that applies to the target brand and PsO/Psoriasis.
- Include universal criteria only if they apply to all brands, all products, all indications, or the relevant psoriasis category.
- Do not use criteria from unrelated indications unless explicitly universal.
- Preserve AND/OR logic, exceptions, contraindication language, and duration/quantity units.
- If the policy documents the parameter, return the value and brief supporting evidence.
- If the parameter applies but the exact value is not specified, return `Unspecified`.
- If the parameter is not documented in the available context, return `NA`.

Answer format:
Value: <value or values>
Evidence: <short quoted or paraphrased policy evidence>
Reasoning: <brief reason, especially for counts or Yes/No decisions>
"""

        cmd = [
            "graphrag",
            "query",
            "--root", str(KG_MAKER_DIR),
            "--method", "local",
            query
        ]

        log(f"Running rule: {rule_file}")

        response = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        output = response.stdout.strip()

        row_results[rule_file] = output

        key = (file_name, brand_name, rule_file)
        results[key] = output

        print("===== QUERY OUTPUT PREVIEW =====")
        print(output[:2000])

        if response.stderr:
            print("===== QUERY STDERR =====")
            print(response.stderr)

    os.makedirs(results_dir, exist_ok=True)

    safe_brand = brand_name.strip().replace("/", "_").replace(" ", "_")
    base_name = os.path.splitext(file_name)[0]

    output_file = os.path.join(
        str(results_dir),
        f"{base_name}_{safe_brand}.json"
    )

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "file_name": file_name,
                "brand_name": brand_name,
                "indication": "Pso",
                "results": row_results
            },
            f,
            indent=2,
            ensure_ascii=False
        )

    log(f"Saved row result -> {output_file}")
    log(f"Completed queries for: {file_name} | {brand_name}")

    return row_results
