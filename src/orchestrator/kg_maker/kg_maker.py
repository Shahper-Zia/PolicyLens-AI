import os
import re
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv

import yaml

from pathlib import Path

KG_MAKER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(KG_MAKER_DIR / ".env")

if not os.getenv("GRAPHRAG_API_KEY"):
    raise ValueError("GRAPHRAG_API_KEY not found. Check your .env file location.")


EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted_pdfs_mds"
INPUT_DIR = KG_MAKER_DIR / "input"
OUTPUT_DIR = KG_MAKER_DIR / "output"
LANCEDB_DIR = KG_MAKER_DIR / "lancedb"
YAML_PATH = KG_MAKER_DIR / "settings.yaml"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _as_posix(path):
    return Path(path).as_posix()


def get_paths(file_name):
    base_name = os.path.splitext(os.path.basename(file_name))[0]
    md_file = f"{base_name}.md"

    return {
        "base_name": base_name,
        "md_file": md_file,
        "source_file": str(EXTRACTED_DIR / md_file),
        "dest_file": str(INPUT_DIR / md_file),
        "output_dir": str(OUTPUT_DIR / f"{base_name}_output"),
        "final_lancedb_dir": str(LANCEDB_DIR / f"{base_name}_lancedb"),
    }


def update_yaml(file_name, output_dir, lancedb_dir):
    base_name = os.path.splitext(os.path.basename(file_name))[0]

    with open(YAML_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"{YAML_PATH} is empty or invalid.")

    config["input"]["file_pattern"] = f"{re.escape(base_name)}\\.md"
    config["input"]["storage"]["base_dir"] = "input"
    config["output"]["base_dir"] = _as_posix(output_dir)
    config["vector_store"]["default_vector_store"]["db_uri"] = _as_posix(lancedb_dir)

    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, sort_keys=False)

    log("YAML updated:")
    log(f"file_pattern = {config['input']['file_pattern']}")
    log(f"output_dir   = {config['output']['base_dir']}")
    log(f"db_uri       = {config['vector_store']['default_vector_store']['db_uri']}")


def ensure_md_in_input(file_name):
    paths = get_paths(file_name)

    if not os.path.exists(paths["source_file"]):
        log(f"ERROR: Markdown not found: {paths['source_file']}")
        return False

    os.makedirs(INPUT_DIR, exist_ok=True)

    if os.path.exists(paths["dest_file"]):
        os.remove(paths["dest_file"])

    shutil.copy2(paths["source_file"], paths["dest_file"])
    log(f"Copied markdown to input: {paths['md_file']}")

    return True


def graph_exists(file_name):
    paths = get_paths(file_name)

    return (
        os.path.exists(paths["final_lancedb_dir"])
        and os.path.exists(paths["output_dir"])
    )


def _remove_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path)


def build_graph_if_needed(file_name, force_rebuild=False):
    paths = get_paths(file_name)

    log(f"Checking graph for: {file_name}")

    if graph_exists(file_name) and not force_rebuild:
        log("Graph already exists. Skipping indexing.")
        return True

    log("Graph not found or force_rebuild=True. Building graph...")

    if not ensure_md_in_input(file_name):
        return False

    _remove_dir(paths["output_dir"])
    _remove_dir(paths["final_lancedb_dir"])
    os.makedirs(paths["output_dir"], exist_ok=True)
    os.makedirs(LANCEDB_DIR, exist_ok=True)

    update_yaml(
        file_name=file_name,
        output_dir=paths["output_dir"],
        lancedb_dir=paths["final_lancedb_dir"],
    )

    cmd = ["graphrag", "index", "--root", str(KG_MAKER_DIR)]

    log(f"Running: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in process.stdout:
        print(line, end="")

    process.wait()

    log(f"Index return code: {process.returncode}")

    if process.returncode != 0:
        log("ERROR: GraphRAG indexing failed.")
        return False

    if not os.path.exists(paths["final_lancedb_dir"]):
        log("ERROR: LanceDB was not created.")
        return False

    log(f"LanceDB saved to: {paths['final_lancedb_dir']}")

    return True

if __name__ == "__main__":
    print("Starting KG build...")

    build_graph_if_needed(
        "361486-4654549.pdf",

        force_rebuild=True
    )
