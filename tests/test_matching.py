from paper2tex.matching import rerank_papers
from paper2tex.types import ArxivPaper


def make_paper(arxiv_id: str, title: str) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=arxiv_id,
        version="v1",
        title=title,
        summary="",
        authors=["A. Author"],
        published="",
        updated="",
        pdf_url="",
        abs_url="",
        source_url="",
    )


def test_partial_title_prefers_subset_match():
    papers = [
        make_paper("1706.03762", "Attention Is All You Need"),
        make_paper("1801.00001", "All You Need Is a Good Attention Mechanism for Summarization"),
        make_paper("1901.00001", "Transformers for Machine Translation"),
    ]
    results = rerank_papers("attention all you need", papers)
    assert results[0].paper.arxiv_id == "1706.03762"
    assert results[0].score > results[1].score


def test_exact_title_beats_extended_title():
    papers = [
        make_paper("1706.03762", "Attention Is All You Need"),
        make_paper("2501.09166", "Attention is All You Need Until You Need Retention"),
    ]
    results = rerank_papers("attention is all you need", papers)
    assert results[0].paper.arxiv_id == "1706.03762"
    assert results[0].score > results[1].score


def test_distinctive_number_token_matters():
    papers = [
        make_paper("2310.00001", "Llama 2: Open Foundation and Fine-Tuned Chat Models"),
        make_paper("2401.00001", "Llama 3: Open Foundation Models"),
    ]
    results = rerank_papers("llama 3", papers)
    assert results[0].paper.arxiv_id == "2401.00001"
