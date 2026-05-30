from dataclasses import dataclass, field
import re
from typing import Iterable, List, Set


@dataclass
class PolicyChunk:
    chunk_id: str
    title: str
    text: str
    start_line: int
    end_line: int
    tags: Set[str] = field(default_factory=set)


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6}\s+.+|\*\*.+\*\*\s*)$")


def split_markdown(markdown_text: str, max_chars: int = 1800) -> List[PolicyChunk]:
    sections = list(_split_by_headings(markdown_text))
    chunks: List[PolicyChunk] = []

    for section_index, (title, start_line, lines) in enumerate(sections):
        buffer: List[str] = []
        buffer_start = start_line

        for offset, line in enumerate(lines):
            if _buffer_len(buffer) + len(line) > max_chars and buffer:
                chunk = _make_chunk(section_index, len(chunks), title, buffer, buffer_start)
                chunks.append(chunk)
                buffer = []
                buffer_start = start_line + offset

            buffer.append(line)

        if buffer:
            chunk = _make_chunk(section_index, len(chunks), title, buffer, buffer_start)
            chunks.append(chunk)

    return chunks


def _split_by_headings(markdown_text: str) -> Iterable[tuple[str, int, List[str]]]:
    current_title = "Document Start"
    current_start = 1
    current_lines: List[str] = []

    for line_number, line in enumerate(markdown_text.splitlines(), start=1):
        if HEADING_RE.match(line) and current_lines:
            yield current_title, current_start, current_lines
            current_title = _clean_heading(line)
            current_start = line_number
            current_lines = [line]
        else:
            if HEADING_RE.match(line):
                current_title = _clean_heading(line)
                current_start = line_number
            current_lines.append(line)

    if current_lines:
        yield current_title, current_start, current_lines


def _make_chunk(section_index: int, chunk_index: int, title: str, lines: List[str], start_line: int) -> PolicyChunk:
    text = "\n".join(lines).strip()
    end_line = start_line + len(lines) - 1
    return PolicyChunk(
        chunk_id=f"s{section_index:03d}-c{chunk_index:04d}",
        title=title,
        text=text,
        start_line=start_line,
        end_line=end_line,
    )


def _buffer_len(lines: List[str]) -> int:
    return sum(len(line) + 1 for line in lines)


def _clean_heading(line: str) -> str:
    heading = line.strip().strip("#").strip()
    heading = heading.strip("*").strip()
    return heading or "Untitled Section"
