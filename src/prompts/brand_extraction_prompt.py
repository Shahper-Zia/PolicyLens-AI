"""Prompt helpers for extracting unique drug brand names from markdown."""

def build_brand_extraction_prompt(file_name: str, markdown_text: str) -> str:
    return f"""You are extracting drug brand names from a markdown file converted from a payer policy PDF.

File name: {file_name}

Task:
Find every unique brand name or branded drug name that appears anywhere in the document.

Read carefully across:
- headings
- tables
- inline sentences
- bullet lists
- grouped drug sections
- repeated policy blocks

Rules:
- Return only actual drug brand names or branded product names.
- DO NOT HALLUCINATE OR INVENT BRAND NAMES. 
- DO NOT CREATE NAMES BASED ON DRUG DESCRIPTIONS.
- DO NOT WRITE NAMES WHICH ARE NOT EXPLICITLY PRESENT IN THE FILE.
- Keep uppercase when possible.
- Remove duplicates.
- Do not include generic section labels, document headings, page numbers, or policy boilerplate.
- Do not invent names that are not explicitly present in the file.
- If a name appears in multiple formats, normalize it to one canonical uppercase form.
- Prefer recall over precision, but do not include obvious noise.

Return JSON only, with this exact schema:
{{
  "file_name": "{file_name}",
  "brands": ["BRAND1", "BRAND2", "BRAND3"]
}}

Markdown content:
---
{markdown_text}
---
"""
