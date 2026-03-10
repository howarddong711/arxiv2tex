import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .types import SectionRecord, SnippetRecord, SourceManifest


INCLUDE_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]+\])?\{([^}]+)\}")
BEGIN_DOCUMENT_RE = re.compile(r"\\begin\{document\}")
SECTION_RE = re.compile(r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^}]+)\}")
BIB_RE = re.compile(r"\\(?:bibliography|addbibresource)\{([^}]+)\}")
COMMENT_RE = re.compile(r"(?<!\\)%.*$")
APPENDIX_COMMAND_RE = re.compile(r"\\appendix\b")
END_DOCUMENT_RE = re.compile(r"\\end\{document\}")
APPENDIX_TITLE_RE = re.compile(r"\\section\*?\{([^}]+)\}")


def list_files(source_root: Path) -> Tuple[List[str], List[str], List[str]]:
    tex_files: List[str] = []
    bib_files: List[str] = []
    asset_files: List[str] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source_root).as_posix()
        suffix = path.suffix.lower()
        if suffix == ".tex":
            tex_files.append(rel)
        elif suffix == ".bib":
            bib_files.append(rel)
        else:
            asset_files.append(rel)
    return sorted(tex_files), sorted(bib_files), sorted(asset_files)


def detect_entrypoint(source_root: Path, tex_files: List[str]) -> str:
    ranked: List[Tuple[int, int, str]] = []
    for rel in tex_files:
        path = source_root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        score = 0
        if DOCUMENTCLASS_RE.search(text):
            score += 2
        if BEGIN_DOCUMENT_RE.search(text):
            score += 3
        score += len(INCLUDE_RE.findall(text))
        penalty = 0
        lower_name = Path(rel).name.lower()
        if lower_name in {"main.tex", "paper.tex", "ms.tex"}:
            score += 2
        ranked.append((score, -penalty, rel))

    if not ranked:
        raise FileNotFoundError("No .tex files found in source package.")
    ranked.sort(reverse=True)
    return ranked[0][2]


def resolve_tex_path(current_file: str, include_target: str, tex_files: Set[str]) -> Optional[str]:
    base = Path(current_file).parent
    candidates = [
        (base / include_target),
        (base / f"{include_target}.tex"),
        Path(include_target),
        Path(f"{include_target}.tex"),
    ]
    for candidate in candidates:
        rel = candidate.as_posix()
        if rel in tex_files:
            return rel
    return None


def build_include_graph(source_root: Path, tex_files: List[str]) -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    tex_set = set(tex_files)
    for rel in tex_files:
        text = (source_root / rel).read_text(encoding="utf-8", errors="ignore")
        includes: List[str] = []
        for match in INCLUDE_RE.finditer(text):
            resolved = resolve_tex_path(rel, match.group(1).strip(), tex_set)
            if resolved:
                includes.append(resolved)
        graph[rel] = includes
    return graph


def build_manifest(source_root: Path) -> SourceManifest:
    tex_files, bib_files, asset_files = list_files(source_root)
    entrypoint = detect_entrypoint(source_root, tex_files)
    includes = build_include_graph(source_root, tex_files)
    return SourceManifest(
        entrypoint=entrypoint,
        tex_files=tex_files,
        bib_files=bib_files,
        asset_files=asset_files,
        includes=includes,
    )


def expand_full_tex(source_root: Path, manifest: SourceManifest) -> str:
    tex_set = set(manifest.tex_files)
    visited: Set[str] = set()

    def expand(rel: str) -> str:
        if rel in visited:
            return f"% SKIP RECURSIVE INCLUDE: {rel}\n"
        visited.add(rel)
        text = (source_root / rel).read_text(encoding="utf-8", errors="ignore")
        lines: List[str] = [f"% BEGIN FILE: {rel}\n"]
        cursor = 0
        for match in INCLUDE_RE.finditer(text):
            lines.append(text[cursor : match.start()])
            target = match.group(1).strip()
            resolved = resolve_tex_path(rel, target, tex_set)
            if resolved:
                lines.append(expand(resolved))
            else:
                lines.append(text[match.start() : match.end()])
            cursor = match.end()
        lines.append(text[cursor:])
        lines.append(f"% END FILE: {rel}\n")
        return "".join(lines)

    return expand(manifest.entrypoint)


def build_sections(full_tex: str) -> List[SectionRecord]:
    sections: List[SectionRecord] = []
    matches = list(SECTION_RE.finditer(full_tex))
    level_order = {
        "section": 1,
        "subsection": 2,
        "subsubsection": 3,
        "paragraph": 4,
        "subparagraph": 5,
    }
    line_starts = [0]
    for idx, char in enumerate(full_tex):
        if char == "\n":
            line_starts.append(idx + 1)

    def line_for_offset(offset: int) -> int:
        low = 0
        high = len(line_starts) - 1
        while low <= high:
            mid = (low + high) // 2
            if line_starts[mid] <= offset:
                low = mid + 1
            else:
                high = mid - 1
        return high + 1

    for index, match in enumerate(matches):
        start = match.start()
        current_level = level_order.get(match.group(1), 99)
        end = len(full_tex)
        for next_match in matches[index + 1 :]:
            next_level = level_order.get(next_match.group(1), 99)
            if next_level <= current_level:
                end = next_match.start()
                break
        source_file = detect_source_file(full_tex, start)
        sections.append(
            SectionRecord(
                title=match.group(2).strip(),
                level=match.group(1),
                source_file=source_file,
                line_number=line_for_offset(start),
                start_offset=start,
                end_offset=end,
            )
        )
    return sections


def detect_source_file(full_tex: str, offset: int) -> str:
    marker_re = re.compile(r"% BEGIN FILE: ([^\n]+)")
    current = ""
    for match in marker_re.finditer(full_tex):
        if match.start() > offset:
            break
        current = match.group(1).strip()
    return current


def build_snippets(full_tex: str, sections: List[SectionRecord], snippet_size: int = 1800) -> List[SnippetRecord]:
    snippets: List[SnippetRecord] = []
    if not sections:
        chunks = chunk_text(full_tex, snippet_size)
        for index, (start, end, text) in enumerate(chunks):
            snippets.append(
                SnippetRecord(
                    snippet_id=f"snippet-{index:04d}",
                    section_title=None,
                    source_file=detect_source_file(full_tex, start),
                    start_offset=start,
                    end_offset=end,
                    text=text,
                )
            )
        return snippets

    for section in sections:
        text = full_tex[section.start_offset : section.end_offset]
        for local_index, (start, end, chunk) in enumerate(chunk_text(text, snippet_size, base_offset=section.start_offset)):
            snippets.append(
                SnippetRecord(
                    snippet_id=f"{slugify(section.title)}-{local_index:03d}",
                    section_title=section.title,
                    source_file=section.source_file,
                    start_offset=start,
                    end_offset=end,
                    text=chunk,
                )
            )
    return snippets


def strip_comments(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("% BEGIN FILE:") or line.lstrip().startswith("% END FILE:") or line.lstrip().startswith("% SKIP RECURSIVE INCLUDE:"):
            lines.append(line)
            continue
        cleaned = COMMENT_RE.sub("", line).rstrip()
        lines.append(cleaned)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def strip_appendix(text: str) -> str:
    appendix_match = APPENDIX_COMMAND_RE.search(text)
    if appendix_match:
        end_document = END_DOCUMENT_RE.search(text, appendix_match.start())
        suffix = end_document.group(0) if end_document else ""
        return text[: appendix_match.start()].rstrip() + ("\n\n" + suffix if suffix else "\n")

    sections = list(APPENDIX_TITLE_RE.finditer(text))
    for match in sections:
        title = match.group(1).strip().lower()
        if title.startswith("appendix") or title.startswith("appendices") or title == "supplementary material":
            end_document = END_DOCUMENT_RE.search(text, match.start())
            suffix = end_document.group(0) if end_document else ""
            return text[: match.start()].rstrip() + ("\n\n" + suffix if suffix else "\n")
    return text


def build_section_tree(sections: List[SectionRecord]) -> List[Dict[str, object]]:
    level_order = {
        "section": 1,
        "subsection": 2,
        "subsubsection": 3,
        "paragraph": 4,
        "subparagraph": 5,
    }
    tree: List[Dict[str, object]] = []
    stack: List[Tuple[int, Dict[str, object]]] = []
    for section in sections:
        node = {
            "title": section.title,
            "level": section.level,
            "source_file": section.source_file,
            "line_number": section.line_number,
            "children": [],
        }
        depth = level_order.get(section.level, 99)
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            tree.append(node)
        stack.append((depth, node))
    return tree


def chunk_text(text: str, size: int, base_offset: int = 0) -> List[Tuple[int, int, str]]:
    chunks: List[Tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = text.rfind("\n\n", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((base_offset + start, base_offset + end, chunk))
        start = end
    return chunks


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return slug or "section"
