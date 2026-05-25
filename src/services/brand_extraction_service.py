"""Batch brand extraction service."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_wrapper import extract_brands_from_markdown as wrapper_extract_brands_from_markdown


def extract_brands_from_markdown(file_path: str | Path, provider: str | None = None) -> Dict[str, List[str]]:
    path = Path(file_path)
    markdown_text = path.read_text(encoding="utf-8", errors="ignore")
    return wrapper_extract_brands_from_markdown(path.name, markdown_text, provider=provider)
