import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Sequence, Tuple

from .types import ArxivPaper, MatchResult


STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "for",
    "in",
    "on",
    "and",
    "to",
    "with",
    "by",
    "from",
    "using",
    "via",
    "into",
    "towards",
    "through",
    "without",
    "paper",
    "study",
    "approach",
    "method",
}

GREEK_MAP = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    for source, target in GREEK_MAP.items():
        text = text.replace(source, target)
    text = re.sub(r"[_/:\\\-]+", " ", text)
    text = re.sub(r"[^\w\s.]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    normalized = normalize_text(text)
    return [token for token in normalized.split(" ") if token]


def strong_token(token: str) -> bool:
    return len(token) >= 4 or any(char.isdigit() for char in token) or token.isupper()


def ordered_coverage(query_tokens: Sequence[str], title_tokens: Sequence[str]) -> float:
    if not query_tokens:
        return 0.0
    title_positions = {}
    for idx, token in enumerate(title_tokens):
        title_positions.setdefault(token, []).append(idx)

    last_pos = -1
    hits = 0
    for token in query_tokens:
        positions = title_positions.get(token, [])
        next_pos = next((pos for pos in positions if pos > last_pos), None)
        if next_pos is None:
            continue
        hits += 1
        last_pos = next_pos
    return hits / len(query_tokens)


def phrase_bonus(query: str, title: str) -> float:
    if not query or not title:
        return 0.0
    query_norm = normalize_text(query)
    title_norm = normalize_text(title)
    if query_norm in title_norm:
        return 1.0

    query_tokens = tokenize(query)
    if len(query_tokens) < 2:
        return 0.0

    longest = 0
    for length in range(len(query_tokens), 1, -1):
        for start in range(0, len(query_tokens) - length + 1):
            phrase = " ".join(query_tokens[start : start + length])
            if phrase in title_norm:
                longest = length
                break
        if longest:
            break
    return longest / len(query_tokens) if query_tokens else 0.0


def coverage(query_tokens: Sequence[str], title_tokens: Sequence[str]) -> Tuple[float, float]:
    if not query_tokens:
        return 0.0, 0.0
    title_set = set(title_tokens)
    strong = [token for token in query_tokens if strong_token(token) and token not in STOPWORDS]
    weak = [token for token in query_tokens if token not in strong]

    strong_hits = sum(1 for token in strong if token in title_set)
    weak_hits = sum(1 for token in weak if token in title_set)

    strong_score = strong_hits / len(strong) if strong else 1.0
    weak_score = weak_hits / len(weak) if weak else 0.0
    return strong_score, weak_score


def distinctive_penalty(query_tokens: Sequence[str], title_tokens: Sequence[str]) -> float:
    title_set = set(title_tokens)
    missing = [
        token
        for token in query_tokens
        if strong_token(token) and token not in STOPWORDS and token not in title_set
    ]
    if not missing:
        return 0.0
    penalty = 0.0
    for token in missing:
        penalty += 1.5 if any(char.isdigit() for char in token) else 1.0
    return penalty / max(1.0, len([token for token in query_tokens if strong_token(token)]))


def prefix_bonus(query_tokens: Sequence[str], title_tokens: Sequence[str]) -> float:
    if not query_tokens or not title_tokens:
        return 0.0
    compare_len = min(len(query_tokens), len(title_tokens), 6)
    if compare_len == 0:
        return 0.0
    matches = sum(1 for idx in range(compare_len) if query_tokens[idx] == title_tokens[idx])
    return matches / compare_len


def char_similarity(query: str, title: str) -> float:
    return SequenceMatcher(None, normalize_text(query), normalize_text(title)).ratio()


def score_title_match(query: str, title: str) -> Tuple[float, List[str]]:
    query_norm = normalize_text(query)
    title_norm = normalize_text(title)
    if query_norm and query_norm == title_norm:
        return 1.0, ["exact_title=1.00"]

    query_tokens = tokenize(query)
    title_tokens = tokenize(title)
    strong_cov, weak_cov = coverage(query_tokens, title_tokens)
    ordered = ordered_coverage(query_tokens, title_tokens)
    phrase = phrase_bonus(query, title)
    prefix = prefix_bonus(query_tokens, title_tokens)
    char_sim = char_similarity(query, title)
    penalty = distinctive_penalty(query_tokens, title_tokens)
    extension_penalty = 0.0
    if query_norm and query_norm in title_norm and query_norm != title_norm:
        extra_tokens = max(0, len(title_tokens) - len(query_tokens))
        extension_penalty = extra_tokens / max(1, len(query_tokens))

    score = (
        0.45 * strong_cov
        + 0.10 * weak_cov
        + 0.20 * ordered
        + 0.15 * phrase
        + 0.10 * prefix
        + 0.10 * char_sim
        - 0.25 * penalty
        - 0.20 * extension_penalty
    )
    score = max(0.0, min(1.0, score))

    reasons = [
        f"strong_coverage={strong_cov:.2f}",
        f"ordered={ordered:.2f}",
        f"phrase={phrase:.2f}",
        f"char_similarity={char_sim:.2f}",
    ]
    if penalty:
        reasons.append(f"distinctive_penalty={penalty:.2f}")
    if extension_penalty:
        reasons.append(f"extension_penalty={extension_penalty:.2f}")
    return score, reasons


def classify_confidence(score: float, gap: float, strong_count: int, reasons: Sequence[str]) -> str:
    if any(reason.startswith("exact_title=") for reason in reasons):
        return "high"
    if strong_count >= 4 and score >= 0.93 and gap >= 0.08:
        return "high"
    if score >= 0.82:
        return "medium"
    return "low"


def rerank_papers(query: str, papers: Iterable[ArxivPaper]) -> List[MatchResult]:
    scored: List[Tuple[ArxivPaper, float, List[str], int]] = []
    query_tokens = tokenize(query)
    strong_count = len([token for token in query_tokens if strong_token(token) and token not in STOPWORDS])

    for paper in papers:
        score, reasons = score_title_match(query, paper.title)
        scored.append((paper, score, reasons, strong_count))

    scored.sort(key=lambda item: item[1], reverse=True)
    results: List[MatchResult] = []
    for index, (paper, score, reasons, strong_count) in enumerate(scored):
        next_score = scored[index + 1][1] if index + 1 < len(scored) else 0.0
        confidence = classify_confidence(score, score - next_score, strong_count, reasons)
        results.append(MatchResult(paper=paper, score=score, confidence=confidence, reasons=reasons))
    return results
