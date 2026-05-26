"""Document loading, section parsing, and section-aware chunking."""

from __future__ import annotations

import re
from pathlib import Path

from src.pa_extraction.models import Chunk, Section


SECTION_TYPE_KEYWORDS: dict[str, list[str]] = {
    "indication": ["indication", "diagnosis", "plaque psoriasis", "psoriasis", "psoriatic", "ulcerative", "crohn"],
    "criteria": ["criteria", "policy/guideline", "policy", "requirements", "medical necessity"],
    "documentation": ["documentation", "submission", "records", "chart notes"],
    "initial": ["initial", "initiation", "new start"],
    "continuation": ["continuation", "reauthorization", "renewal", "continued"],
    "authorization": ["authorization", "approval duration", "duration"],
    "quantity": ["quantity", "limits", "quantity limit"],
    "reference": ["references", "appendix", "background"],
    "all_indications": ["all indications", "universal"],
    "description": ["description", "fda-approved"],
}


def resolve_document_path(file_name: str, docs_dir: str | Path) -> Path:
    """Find the extracted text/markdown document for an input row file name."""

    docs_path = Path(docs_dir)
    requested = Path(str(file_name).strip())
    candidates = [
        docs_path / requested.name,
        docs_path / f"{requested.stem}.md",
        docs_path / f"{requested.stem}.txt",
        docs_path / f"{requested.name}.md",
        docs_path / f"{requested.name}.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(docs_path.glob(f"{requested.stem}.*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"No extracted document found for {file_name!r} in {docs_path}")


def read_document(file_name: str, docs_dir: str | Path) -> tuple[Path, str]:
    """Read a target policy document as UTF-8 text with replacement fallback."""

    path = resolve_document_path(file_name, docs_dir)
    return path, path.read_text(encoding="utf-8", errors="ignore")


def parse_document_into_sections(text: str) -> list[Section]:
    """Parse markdown headings first, with a heuristic heading fallback.

    The parser intentionally keeps offsets so selected chunks can be traced back
    to the source document during debugging.
    """

    headings: list[tuple[int, int, str, int]] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.strip()
        heading = _extract_heading(line)
        if heading:
            title, level = heading
            headings.append((offset, offset + len(raw_line), title, level))
        offset += len(raw_line)

    if not headings:
        return [Section("Document", text, 0, len(text), 0, _classify_section("Document"))]

    sections: list[Section] = []
    if headings[0][0] > 0:
        preface = text[: headings[0][0]].strip()
        if preface:
            sections.append(Section("Document Preface", preface, 0, headings[0][0], 0, "unknown"))

    title_stack: list[tuple[int, str]] = []
    for idx, (start, heading_end, title, level) in enumerate(headings):
        while title_stack and title_stack[-1][0] >= level:
            title_stack.pop()
        title_stack.append((level, title))
        section_end = headings[idx + 1][0] if idx + 1 < len(headings) else len(text)
        body = text[heading_end:section_end].strip()
        full_title = " > ".join(item[1] for item in title_stack)
        sections.append(
            Section(
                title=full_title,
                text=body,
                start=heading_end,
                end=section_end,
                heading_level=level,
                section_type=_classify_section(full_title),
            )
        )
    return [section for section in sections if section.text.strip() or section.title.strip()]


def build_contextual_chunks(sections: list[Section], max_chars: int = 2200) -> list[Chunk]:
    """Build chunks from paragraphs, bullets, and table blocks within sections."""

    chunks: list[Chunk] = []
    chunk_index = 0
    for section in sections:
        blocks = _split_section_blocks(section.text)
        current: list[str] = []
        current_start = section.start
        cursor = section.start

        for block in blocks:
            block_start = _safe_find_offset(section.text, block, cursor - section.start) + section.start
            prospective = "\n\n".join([*current, block]).strip()
            if current and len(prospective) > max_chars:
                chunk_text = "\n\n".join(current).strip()
                chunks.append(
                    Chunk(
                        text=f"[Section: {section.title}]\n{chunk_text}",
                        section_title=section.title,
                        section_type=section.section_type,
                        chunk_index=chunk_index,
                        start=current_start,
                        end=block_start,
                        heading_level=section.heading_level,
                    )
                )
                chunk_index += 1
                current = [block]
                current_start = block_start
            else:
                if not current:
                    current_start = block_start
                current.append(block)
            cursor = block_start + len(block)

        if current:
            chunk_text = "\n\n".join(current).strip()
            chunks.append(
                Chunk(
                    text=f"[Section: {section.title}]\n{chunk_text}",
                    section_title=section.title,
                    section_type=section.section_type,
                    chunk_index=chunk_index,
                    start=current_start,
                    end=section.end,
                    heading_level=section.heading_level,
                )
            )
            chunk_index += 1
    return chunks


def _extract_heading(line: str) -> tuple[str, int] | None:
    markdown_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if markdown_match:
        return _clean_heading(markdown_match.group(2)), len(markdown_match.group(1))

    if not line or len(line) > 140:
        return None
    if line.startswith("|") or re.match(r"^-{3,}", line):
        return None
    cleaned = _clean_heading(line)
    heading_words = ["criteria", "requirements", "authorization", "continuation", "initial", "indication", "quantity", "documentation"]
    if cleaned.endswith(":") and any(word in cleaned.lower() for word in heading_words):
        return cleaned.rstrip(":"), 3
    if cleaned.isupper() and len(cleaned.split()) <= 10:
        return cleaned, 3
    return None


def _clean_heading(value: str) -> str:
    value = re.sub(r"[*_`#]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _classify_section(title: str) -> str:
    lowered = title.lower()
    for section_type, keywords in SECTION_TYPE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return section_type
    return "unknown"


def _split_section_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    in_table = False

    def flush() -> None:
        nonlocal current
        block = "\n".join(current).strip()
        if block:
            blocks.append(block)
        current = []

    for line in lines:
        stripped = line.strip()
        is_table = stripped.startswith("|")
        is_bullet = bool(re.match(r"^(\s*[-*+]\s+|\s*\d+[.)]\s+)", line))
        if not stripped:
            flush()
            in_table = False
            continue
        if is_table:
            if not in_table:
                flush()
            current.append(line)
            in_table = True
            continue
        if is_bullet:
            flush()
            current.append(line)
            flush()
            in_table = False
            continue
        if in_table:
            flush()
            in_table = False
        current.append(line)
    flush()
    return blocks or [text]


def _safe_find_offset(text: str, needle: str, start: int) -> int:
    found = text.find(needle, max(0, start))
    if found >= 0:
        return found
    found = text.find(needle)
    return max(0, found)
