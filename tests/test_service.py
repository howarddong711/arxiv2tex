from pathlib import Path
from datetime import datetime, timedelta, timezone

from arxiv2tex.matching import normalize_text
from arxiv2tex.service import PaperService
from arxiv2tex.types import ArxivPaper


CACHE_DIR_NAME = ".arxiv2tex-cache"


def make_paper(arxiv_id: str, title: str) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=arxiv_id,
        version="v1",
        title=title,
        summary="Sentence one. Sentence two.",
        authors=["First Author", "Second Author"],
        published="2024-01-01T00:00:00Z",
        updated="2024-01-01T00:00:00Z",
        pdf_url="",
        abs_url="",
        source_url="",
    )


def test_confirm_does_not_write_alias_cache(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)

    papers = [
        make_paper("1706.03762", "Attention Is All You Need"),
        make_paper("2501.09166", "Attention is All You Need Until You Need Retention"),
    ]
    service.arxiv.search_title = lambda query, max_results=10: papers  # type: ignore[assignment]
    service.arxiv.search_title_tokens = lambda tokens, max_results=12: []  # type: ignore[assignment]
    service.arxiv.search_all = lambda query, max_results=12: []  # type: ignore[assignment]

    result = service.resolve("帮我看一下 attention all you need")

    assert result["status"] == "confirm"
    assert result["candidates"][0]["first_author"] == "First Author"
    assert not (
        tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1" / "aliases.json"
    ).exists()


def test_read_section_supports_cn_alias(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper_dir = service.cache.paper_dir("demo")
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "reader.tex").write_text(
        "\\section{Results}\nExperiments here.\n", encoding="utf-8"
    )

    result = service.read_section("demo", "实验")

    assert result["status"] == "ok"
    assert result["section"]["title"] == "Results"


def test_select_candidate_by_ordinal_without_prepare(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    candidate = {
        "paper": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
        "score": 0.91,
        "confidence": "medium",
        "reasons": ["strong_coverage=1.00"],
        "first_author": "First Author",
        "published_year": "2024",
        "summary_preview": "Sentence one",
    }
    service.resolve = lambda prompt, max_results=25, session_id=None: {  # type: ignore[assignment]
        "status": "confirm",
        "query": "attention all you need",
        "candidates": [candidate],
    }

    result = service.select_candidate(
        "帮我看 attention all you need", "第一个", prepare=False
    )

    assert result["status"] == "resolved"
    assert result["mode"] == "confirmed_candidate"
    assert result["selected"]["arxiv_id"] == "1706.03762"


def test_handle_prompt_returns_section_result(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.resolve = lambda prompt, max_results=25, session_id=None: {  # type: ignore[assignment]
        "status": "resolved",
        "mode": "title_match",
        "selected": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
        "cache_key": "1706.03762v1",
    }
    service.prepare = lambda prompt, view="reader", session_id=None: {  # type: ignore[assignment]
        "status": "prepared",
        "cache_key": "1706.03762v1",
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1"),
        "metadata": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
    }
    service.overview = lambda cache_key: {
        "status": "ok",
        "sections": [{"title": "Results"}],
    }  # type: ignore[assignment]
    service.read_section = lambda cache_key, section_ref, view="reader": {  # type: ignore[assignment]
        "status": "ok",
        "section": {"title": "Results"},
        "text": "Experiments here.",
    }
    service.search = lambda cache_key, query, top_k=3, view="reader": {
        "status": "ok",
        "results": [{"snippet_id": "results-000"}],
    }  # type: ignore[assignment]
    service.extract_writing_examples = (
        lambda cache_key, target, top_k=3, view="reader": {
            "status": "ok",
            "examples": [{"snippet_id": "results-000"}],
        }
    )  # type: ignore[assignment]

    result = service.handle_prompt("帮我参考 attention is all you need 的实验部分写法")

    assert result["status"] == "ready"
    assert result["intent"]["section_hint"] == "实验"
    assert result["section_result"]["section"]["title"] == "Results"
    assert result["writing_examples"]["examples"][0]["snippet_id"] == "results-000"


def test_resolve_short_acronym_query_returns_confirmation(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    papers = [
        make_paper("1601.07303", "Periodic GMP Matrices"),
        make_paper("2206.08975", "Vibrational Levels of a Generalized Morse Potential"),
    ]
    service.arxiv.search_title = lambda query, max_results=10: papers  # type: ignore[assignment]
    service.arxiv.search_title_tokens = lambda tokens, max_results=12: []  # type: ignore[assignment]
    service.arxiv.search_all = lambda query, max_results=12: []  # type: ignore[assignment]

    result = service.resolve("你学习一下GMP这篇论文附录里表格的写法")

    assert result["status"] == "confirm"
    assert result["query"] == "GMP"
    assert result["candidates"]


def test_resolve_intent_uses_structured_query_without_text_parse(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    service.arxiv.search_title = lambda query, max_results=10: [paper]  # type: ignore[assignment]
    service.arxiv.search_title_tokens = lambda tokens, max_results=12: []  # type: ignore[assignment]
    service.arxiv.search_all = lambda query, max_results=12: []  # type: ignore[assignment]

    result = service.resolve_intent(
        paper_query="Attention Is All You Need",
        section_hint="related work",
        action_hint="imitate",
        raw_prompt="看看这篇论文 related work 怎么组织的",
    )

    assert result["status"] == "resolved"
    assert result["intent"]["paper_query"] == "Attention Is All You Need"
    assert result["intent"]["section_hint"] == "related work"


def test_handle_intent_returns_section_result(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.resolve_intent = lambda **kwargs: {  # type: ignore[assignment]
        "status": "resolved",
        "mode": "title_match",
        "selected": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
        "cache_key": "1706.03762v1",
        "intent": {
            "raw_prompt": "看看这篇论文 related work 怎么组织的",
            "paper_query": "Attention Is All You Need",
            "section_hint": "related work",
            "section_queries": ["related work", "background"],
            "action_hint": "imitate",
        },
    }
    service.prepare_intent = lambda **kwargs: {  # type: ignore[assignment]
        "status": "prepared",
        "cache_key": "1706.03762v1",
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1"),
        "metadata": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
    }
    service.overview = lambda cache_key: {
        "status": "ok",
        "sections": [{"title": "Background"}],
    }  # type: ignore[assignment]
    service.read_section = lambda cache_key, section_ref, view="reader": {  # type: ignore[assignment]
        "status": "ok",
        "section": {"title": "Background"},
        "text": "Prior work here.",
    }
    service.extract_writing_examples = (
        lambda cache_key, target, top_k=3, view="reader": {  # type: ignore[assignment]
            "status": "ok",
            "examples": [{"snippet_id": "background-000"}],
        }
    )

    result = service.handle_intent(
        paper_query="Attention Is All You Need",
        section_hint="related work",
        action_hint="imitate",
        raw_prompt="看看这篇论文 related work 怎么组织的",
    )

    assert result["status"] == "ready"
    assert result["intent"]["paper_query"] == "Attention Is All You Need"
    assert result["section_result"]["section"]["title"] == "Background"
    assert result["writing_examples"]["examples"][0]["snippet_id"] == "background-000"


def test_prepare_intent_uses_selected_paper_directly(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    service.resolve_intent = lambda **kwargs: {  # type: ignore[assignment]
        "status": "resolved",
        "selected": paper.to_dict(),
    }

    sentinel = {
        "status": "prepared",
        "cache_key": paper.cache_key,
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / paper.cache_key),
        "default_view": "reader",
        "metadata": paper.to_dict(),
    }
    service._prepare_paper = lambda selected, view="reader", session_id=None: sentinel  # type: ignore[assignment]

    result = service.prepare_intent(
        paper_query="Attention Is All You Need",
        section_hint="related work",
        action_hint="imitate",
        raw_prompt="看看这篇论文 related work 怎么组织的",
    )

    assert result == sentinel


def test_resolve_confirm_persists_pending_state(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    papers = [
        make_paper("1706.03762", "Attention Is All You Need"),
        make_paper("2501.09166", "Attention is All You Need Until You Need Retention"),
    ]
    service.arxiv.search_title = lambda query, max_results=10: papers  # type: ignore[assignment]
    service.arxiv.search_title_tokens = lambda tokens, max_results=12: []  # type: ignore[assignment]
    service.arxiv.search_all = lambda query, max_results=12: []  # type: ignore[assignment]

    result = service.resolve("帮我看 attention all you need")

    assert result["status"] == "confirm"
    pending = service.pending_status()
    assert pending["status"] == "pending"
    assert pending["pending"]["candidates"][0]["paper"]["arxiv_id"] == "1706.03762"


def test_handle_prompt_consumes_pending_selection(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.cache.save_pending_state(
        {
            "original_prompt": "帮我参考 attention is all you need 的实验部分写法",
            "intent": {
                "raw_prompt": "帮我参考 attention is all you need 的实验部分写法",
                "paper_query": "attention is all you need",
                "section_hint": "实验",
                "section_queries": ["实验", "results"],
                "action_hint": "imitate",
            },
            "query": "attention is all you need",
            "candidates": [
                {
                    "paper": make_paper(
                        "1706.03762", "Attention Is All You Need"
                    ).to_dict(),
                    "score": 0.91,
                    "confidence": "medium",
                    "reasons": ["strong_coverage=1.00"],
                    "first_author": "First Author",
                    "published_year": "2024",
                    "summary_preview": "Sentence one",
                }
            ],
        }
    )
    service.prepare = lambda prompt, view="reader", session_id=None: {  # type: ignore[assignment]
        "status": "prepared",
        "cache_key": "1706.03762v1",
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1"),
        "metadata": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
    }
    service.overview = lambda cache_key: {
        "status": "ok",
        "sections": [{"title": "Results"}],
    }  # type: ignore[assignment]
    service.read_section = lambda cache_key, section_ref, view="reader": {  # type: ignore[assignment]
        "status": "ok",
        "section": {"title": "Results"},
        "text": "Experiments here.",
    }
    service.search = lambda cache_key, query, top_k=3, view="reader": {
        "status": "ok",
        "results": [{"snippet_id": "results-000"}],
    }  # type: ignore[assignment]
    service.extract_writing_examples = (
        lambda cache_key, target, top_k=3, view="reader": {
            "status": "ok",
            "examples": [{"snippet_id": "results-000"}],
        }
    )  # type: ignore[assignment]

    result = service.handle_prompt("就这篇")

    assert result["status"] == "ready"
    assert result["resolution"]["mode"] == "pending_confirmation"
    assert service.pending_status()["status"] == "empty"


def test_handle_prompt_accepts_casual_selection_phrase(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.cache.save_pending_state(
        {
            "original_prompt": "帮我看 attention all you need",
            "intent": {
                "raw_prompt": "帮我看 attention all you need",
                "paper_query": "attention all you need",
                "section_hint": None,
                "section_queries": [],
                "action_hint": None,
            },
            "query": "attention all you need",
            "candidates": [
                {
                    "paper": make_paper(
                        "1706.03762", "Attention Is All You Need"
                    ).to_dict(),
                    "score": 0.91,
                    "confidence": "medium",
                    "reasons": ["strong_coverage=1.00"],
                    "first_author": "First Author",
                    "published_year": "2024",
                    "summary_preview": "Sentence one",
                }
            ],
        }
    )
    service.prepare = lambda prompt, view="reader", session_id=None: {  # type: ignore[assignment]
        "status": "prepared",
        "cache_key": "1706.03762v1",
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1"),
        "metadata": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
    }
    service.overview = lambda cache_key: {"status": "ok", "sections": []}  # type: ignore[assignment]

    result = service.handle_prompt("就第一个吧")

    assert result["status"] == "ready"
    assert result["resolution"]["selected"]["arxiv_id"] == "1706.03762"


def test_pending_state_is_isolated_by_session(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.cache.save_pending_state(
        {
            "session_id": "alpha",
            "candidates": [
                {
                    "paper": make_paper(
                        "1706.03762", "Attention Is All You Need"
                    ).to_dict()
                }
            ],
        },
        session_id="alpha",
    )
    service.cache.save_pending_state(
        {
            "session_id": "beta",
            "candidates": [
                {
                    "paper": make_paper(
                        "2307.12775", "Medical Attention Review"
                    ).to_dict()
                }
            ],
        },
        session_id="beta",
    )

    alpha = service.pending_status(session_id="alpha")
    beta = service.pending_status(session_id="beta")
    latest = service.pending_status()

    assert alpha["pending"]["candidates"][0]["paper"]["arxiv_id"] == "1706.03762"
    assert beta["pending"]["candidates"][0]["paper"]["arxiv_id"] == "2307.12775"
    assert latest["pending"]["session_id"] == "beta"


def test_handle_prompt_consumes_only_requested_session(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    service.cache.save_pending_state(
        {
            "session_id": "alpha",
            "original_prompt": "帮我看 attention all you need",
            "intent": {
                "raw_prompt": "帮我看 attention all you need",
                "paper_query": "attention all you need",
                "section_hint": None,
                "section_queries": [],
                "action_hint": None,
            },
            "query": "attention all you need",
            "candidates": [
                {
                    "paper": make_paper(
                        "1706.03762", "Attention Is All You Need"
                    ).to_dict(),
                    "score": 0.91,
                    "confidence": "medium",
                    "reasons": ["strong_coverage=1.00"],
                    "first_author": "First Author",
                    "published_year": "2024",
                    "summary_preview": "Sentence one",
                }
            ],
        },
        session_id="alpha",
    )
    service.cache.save_pending_state(
        {
            "session_id": "beta",
            "original_prompt": "帮我看 another paper",
            "intent": {
                "raw_prompt": "帮我看 another paper",
                "paper_query": "another paper",
                "section_hint": None,
                "section_queries": [],
                "action_hint": None,
            },
            "query": "another paper",
            "candidates": [
                {
                    "paper": make_paper(
                        "2307.12775", "Medical Attention Review"
                    ).to_dict(),
                    "score": 0.91,
                    "confidence": "medium",
                    "reasons": ["strong_coverage=1.00"],
                    "first_author": "First Author",
                    "published_year": "2024",
                    "summary_preview": "Sentence one",
                }
            ],
        },
        session_id="beta",
    )
    service.prepare = lambda prompt, view="reader", session_id=None: {  # type: ignore[assignment]
        "status": "prepared",
        "session_id": session_id,
        "cache_key": "1706.03762v1",
        "paper_dir": str(tmp_path / CACHE_DIR_NAME / "arxiv" / "1706.03762v1"),
        "metadata": make_paper("1706.03762", "Attention Is All You Need").to_dict(),
    }
    service.overview = lambda cache_key: {"status": "ok", "sections": []}  # type: ignore[assignment]

    result = service.handle_prompt("就这篇", session_id="alpha")

    assert result["status"] == "ready"
    assert result["session_id"] == "alpha"
    assert service.pending_status(session_id="alpha")["status"] == "empty"
    assert service.pending_status(session_id="beta")["status"] == "pending"


def test_pending_state_expires(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    expired = datetime.now(timezone.utc) - timedelta(seconds=10)
    service.cache.save_pending_state(
        {
            "session_id": "expired",
            "created_at": expired.isoformat(),
            "expires_at": expired.isoformat(),
            "candidates": [],
        },
        session_id="expired",
        ttl_seconds=0,
    )

    assert service.pending_status(session_id="expired")["status"] == "empty"


def test_extract_writing_examples_prefers_matching_section(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    paper_dir = service.cache.paper_dir(paper.cache_key)
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "reader.tex").write_text(
        "\\section{Introduction}\nIntro text.\n\\section{Results}\nResult sentence.\n\\subsection{Evaluation}\nMore result details.\n",
        encoding="utf-8",
    )
    service.cache.save_metadata(paper)

    result = service.extract_writing_examples(paper.cache_key, "实验", top_k=2)

    assert result["status"] == "ok"
    assert result["target_profile"] == "experiment"
    assert result["matched_sections"][0]["title"] == "Results"
    assert result["examples"]
    assert result["starter_sentences"]
    assert result["guidance"]


def test_extract_writing_examples_abstract_fallback(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    paper_dir = service.cache.paper_dir(paper.cache_key)
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "reader.tex").write_text(
        "\\section{Introduction}\nIntro text.\n", encoding="utf-8"
    )
    service.cache.save_metadata(paper)

    result = service.extract_writing_examples(paper.cache_key, "摘要", top_k=1)

    assert result["status"] == "ok"
    assert result["target_profile"] == "abstract"
    assert result["examples"][0]["snippet_id"] == "abstract-summary"


def test_extract_writing_examples_reports_style_signals(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    paper_dir = service.cache.paper_dir(paper.cache_key)
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "reader.tex").write_text(
        "\\section{Related Work}\nPrior work improves translation quality \\cite{vaswani2017attention}. Figure 2 summarizes the comparison.\n",
        encoding="utf-8",
    )
    service.cache.save_metadata(paper)

    result = service.extract_writing_examples(paper.cache_key, "相关工作", top_k=1)

    assert result["status"] == "ok"
    assert result["target_profile"] == "related_work"
    assert result["style_signals"]["citation_hits"] >= 1
    assert result["style_signals"]["figure_hits"] >= 1
    assert result["guidance"]


def test_record_aliases_skips_ambiguous_short_title_for_longer_paper(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    review = make_paper(
        "2307.12775", "Is attention all you need in medical image analysis? A review"
    )

    service._record_aliases(  # type: ignore[attr-defined]
        review,
        [
            "看看《Attention Is All You Need》这篇论文的 related work 怎么组织的",
            "Attention Is All You Need",
            review.title,
        ],
    )

    aliases = service.cache.load_aliases(review.cache_key)
    assert normalize_text(review.title) in aliases
    assert normalize_text("Attention Is All You Need") not in aliases


def test_prepare_rebuilds_indexes_without_redownloading(tmp_path: Path):
    service = PaperService(tmp_path / CACHE_DIR_NAME)
    paper = make_paper("1706.03762", "Attention Is All You Need")
    paper_dir = service.cache.paper_dir(paper.cache_key)
    source_dir = paper_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "source.tar").write_text("cached", encoding="utf-8")
    (paper_dir / "manifest.json").write_text(
        '{"entrypoint": "main.tex", "tex_files": [], "bib_files": [], "asset_files": [], "includes": {}}',
        encoding="utf-8",
    )
    (paper_dir / "full.tex").write_text(
        "\\section{Results}\nResult sentence.\n", encoding="utf-8"
    )
    (paper_dir / "clean.tex").write_text(
        "\\section{Results}\nResult sentence.\n", encoding="utf-8"
    )
    (paper_dir / "reader.tex").write_text(
        "\\section{Results}\nResult sentence.\n", encoding="utf-8"
    )

    service.resolve = lambda prompt, max_results=25, session_id=None: {  # type: ignore[assignment]
        "status": "resolved",
        "mode": "cache",
        "selected": paper.to_dict(),
        "cache_key": paper.cache_key,
    }
    service.arxiv.download_source = lambda paper, destination: (_ for _ in ()).throw(
        AssertionError("download_source should not be called")
    )  # type: ignore[assignment]
    service.arxiv.extract_source = lambda archive, destination: (_ for _ in ()).throw(
        AssertionError("extract_source should not be called")
    )  # type: ignore[assignment]

    result = service.prepare("attention is all you need")

    assert result["status"] == "prepared"
    assert (paper_dir / "sections.json").exists()
    assert (paper_dir / "snippets.jsonl").exists()
