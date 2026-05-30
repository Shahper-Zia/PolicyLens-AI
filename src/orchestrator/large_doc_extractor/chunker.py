from dataclasses import dataclass, field
import re
from typing import Iterable, List, Set


@dataclass
class LargeDocChunk:
    chunk_id: str
    title: str
    text: str
    start_line: int
    end_line: int
    page_start: int | None = None
    page_end: int | None = None
    tags: Set[str] = field(default_factory=set)


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6}\s+.+|\*\*.+\*\*\s*)$")
PAGE_RE = re.compile(r"page_number\s*=\s*(\d+)", re.IGNORECASE)


def split_large_markdown(markdown_text: str, max_chars: int = 2200, overlap_lines: int = 4) -> List[LargeDocChunk]:
    sections = list(_split_by_heading_or_page(markdown_text))
    chunks: List[LargeDocChunk] = []

    for section_index, section in enumerate(sections):
        title, start_line, page_number, lines = section
        buffer: List[str] = []
        buffer_start = start_line

        for offset, line in enumerate(lines):
            if _buffer_len(buffer) + len(line) > max_chars and buffer:
                chunks.append(_make_chunk(section_index, len(chunks), title, buffer, buffer_start, page_number))
                overlap = buffer[-overlap_lines:] if overlap_lines else []
                buffer = [*overlap]
                buffer_start = start_line + max(0, offset - len(overlap))

            buffer.append(line)

        if buffer:
            chunks.append(_make_chunk(section_index, len(chunks), title, buffer, buffer_start, page_number))

    return chunks


def _split_by_heading_or_page(markdown_text: str) -> Iterable[tuple[str, int, int | None, List[str]]]:
    current_title = "Document Start"
    current_start = 1
    current_page: int | None = None
    current_lines: List[str] = []

    for line_number, line in enumerate(markdown_text.splitlines(), start=1):
        page_match = PAGE_RE.search(line)
        heading_match = HEADING_RE.match(line)
        should_split = bool((heading_match or page_match) and current_lines)

        if should_split:
            yield current_title, current_start, current_page, current_lines
            current_start = line_number
            current_lines = []

        if heading_match:
            current_title = _clean_heading(line)
        if page_match:
            current_page = int(page_match.group(1))
            current_title = f"Page {current_page}"

        current_lines.append(line)

    if current_lines:
        yield current_title, current_start, current_page, current_lines


def _make_chunk(
    section_index: int,
    chunk_index: int,
    title: str,
    lines: List[str],
    start_line: int,
    page_number: int | None,
) -> LargeDocChunk:
    text = "\n".join(lines).strip()
    end_line = start_line + len(lines) - 1
    return LargeDocChunk(
        chunk_id=f"ld-s{section_index:04d}-c{chunk_index:05d}",
        title=title,
        text=text,
        start_line=start_line,
        end_line=end_line,
        page_start=page_number,
        page_end=page_number,
    )


def _buffer_len(lines: List[str]) -> int:
    return sum(len(line) + 1 for line in lines)


def _clean_heading(line: str) -> str:
    heading = line.strip().strip("#").strip()
    heading = heading.strip("*").strip()
    return heading or "Untitled Section"
