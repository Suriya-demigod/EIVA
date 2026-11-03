"""Structure-aware overlapping chunker with page and source-location metadata."""

from __future__ import annotations

import re

from backend.rag.models import DocumentSegment, RagChunkInput

_STRUCTURE = re.compile(
    r"^\s*(?:#{1,6}\s+.+|(?:async\s+)?def\s+\w+.*|class\s+\w+.*|"
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+\w+.*|"
    r"(?:class|module|def)\s+[^\s].*)$"
)
_CLASS = re.compile(r"^\s*(?:class|module)\s+[^\s].*")
_FUNCTION = re.compile(r"^\s*(?:(?:async\s+)?def|(?:export\s+)?(?:default\s+)?(?:async\s+)?function)\s+\w+.*")


def _sections(text: str) -> list[tuple[str, int, str | None]]:
    lines = text.splitlines()
    if not lines:
        return []
    starts = [0]
    first_line = lines[0].strip()
    labels: dict[int, str] = {0: first_line.lstrip("# ")[:160]} if _STRUCTURE.match(lines[0]) else {}
    parent_name: str | None = first_line.strip() if _CLASS.match(lines[0]) else None
    parent_indent = len(lines[0]) - len(lines[0].lstrip()) if parent_name else 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index and _STRUCTURE.match(line):
            starts.append(index)
            if _CLASS.match(line):
                parent_name = stripped
                parent_indent = len(line) - len(line.lstrip())
                labels[index] = stripped[:160]
            elif _FUNCTION.match(line):
                indent = len(line) - len(line.lstrip())
                if parent_name and indent > parent_indent:
                    labels[index] = f"{parent_name} > {stripped}"[:160]
                else:
                    parent_name = None
                    labels[index] = stripped[:160]
            else:
                labels[index] = stripped.lstrip("# ")[:160]
    starts = sorted(set(starts))
    result: list[tuple[str, int, str | None]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            result.append((body, start + 1, labels.get(start)))
    return result


def chunk_segment(segment: DocumentSegment, target_chars: int = 1100, overlap_chars: int = 175) -> list[RagChunkInput]:
    if target_chars < 400 or target_chars > 4000 or overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("Chunk target must be 400-4000 characters with smaller nonnegative overlap")
    result: list[RagChunkInput] = []
    for section_text, start_line, detected_section in _sections(segment.text):
        section_name = segment.section or detected_section
        start = 0
        while start < len(section_text):
            end = min(len(section_text), start + target_chars)
            if end < len(section_text):
                candidates = [section_text.rfind("\n\n", start + int(target_chars * 0.65), end),
                              section_text.rfind("\n", start + int(target_chars * 0.75), end),
                              section_text.rfind(" ", start + int(target_chars * 0.8), end)]
                boundary = max(candidates)
                if boundary > start:
                    end = boundary
            body = section_text[start:end].strip()
            if body:
                local_start_line = section_text.count("\n", 0, start) + start_line + segment.start_line - 1
                local_end_line = section_text.count("\n", 0, end) + start_line + segment.start_line - 1
                if segment.location_unit == "paragraph":
                    # DOCX loader emits one non-empty paragraph per line.
                    location = {"location_unit": "paragraph"}
                else:
                    location = {"location_unit": "line"}
                metadata: dict[str, object] = dict(location)
                if section_name:
                    metadata["section"] = section_name
                result.append(RagChunkInput(
                    text=body,
                    page_number=segment.page_number,
                    line_start=local_start_line,
                    line_end=max(local_start_line, local_end_line),
                    metadata=metadata,
                    embedding=[],
                ))
            if end >= len(section_text):
                break
            start = max(start + 1, end - overlap_chars)
    return result


def chunk_document(segments: list[DocumentSegment], target_chars: int = 1100, overlap_chars: int = 175) -> list[RagChunkInput]:
    chunks: list[RagChunkInput] = []
    for segment in segments:
        chunks.extend(chunk_segment(segment, target_chars, overlap_chars))
    return chunks
