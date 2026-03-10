from pathlib import Path

from arxiv2tex.latex import (
    build_manifest,
    build_section_tree,
    build_sections,
    build_snippets,
    expand_full_tex,
    strip_appendix,
    strip_comments,
)


def test_expand_full_tex(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{sections/intro}\n\\section{Method}\nBody\n\\end{document}\n",
        encoding="utf-8",
    )
    (root / "sections").mkdir()
    (root / "sections" / "intro.tex").write_text("\\section{Intro}\nHello\n", encoding="utf-8")

    manifest = build_manifest(root)
    full_tex = expand_full_tex(root, manifest)
    sections = build_sections(full_tex)
    snippets = build_snippets(full_tex, sections, snippet_size=20)

    assert manifest.entrypoint == "main.tex"
    assert "% BEGIN FILE: main.tex\n" in full_tex
    assert "Intro" in full_tex
    assert any(section.title == "Intro" for section in sections)
    assert sections[0].source_file == "sections/intro.tex"
    assert snippets


def test_strip_comments_and_appendix():
    full_tex = (
        "% BEGIN FILE: main.tex\n"
        "\\section{Intro}\n"
        "Alpha % inline comment\n"
        "\\appendix\n"
        "\\section{Appendix}\n"
        "Beta\n"
        "\\end{document}\n"
    )
    clean = strip_comments(full_tex)
    reader = strip_appendix(clean)

    assert "inline comment" not in clean
    assert "\\appendix" not in reader
    assert "Beta" not in reader
    assert "\\end{document}" in reader


def test_build_section_tree():
    full_tex = (
        "\\section{Intro}\n"
        "A\n"
        "\\subsection{Motivation}\n"
        "B\n"
        "\\section{Method}\n"
        "C\n"
    )
    sections = build_sections(full_tex)
    tree = build_section_tree(sections)
    assert tree[0]["title"] == "Intro"
    assert tree[0]["children"][0]["title"] == "Motivation"
    assert tree[1]["title"] == "Method"


def test_section_range_includes_nested_subsections():
    full_tex = (
        "\\section{Results}\n"
        "Lead.\n"
        "\\subsection{Machine Translation}\n"
        "MT body.\n"
        "\\subsection{Parsing}\n"
        "Parsing body.\n"
        "\\section{Conclusion}\n"
        "End.\n"
    )
    sections = build_sections(full_tex)
    results = sections[0]
    assert "Machine Translation" in full_tex[results.start_offset : results.end_offset]
    assert "Parsing body." in full_tex[results.start_offset : results.end_offset]
