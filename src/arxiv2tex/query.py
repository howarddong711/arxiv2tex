import re
from typing import Optional, Tuple

from .types import PromptIntent


ARXIV_ID_RE = re.compile(
    r"(?:(?:https?://)?arxiv\.org/(?:abs|pdf|html|e-print)/)?(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?",
    re.IGNORECASE,
)

CN_TITLE_RE = re.compile(r"《([^》]+)》")
QUOTE_RE = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{3,})[\"“”'‘’]")
LATIN_TITLE_SPAN_RE = re.compile(r"([A-Z][A-Za-z0-9:+/\-]+(?:\s+[A-Z0-9][A-Za-z0-9:+/\-]+){1,14})")

SECTION_PATTERNS = [
    re.compile(r"(?:的|里|中)(?P<section>摘要|引言|介绍|相关工作|背景|方法|实验|结果|结论|附录|related work|background|introduction|method|methods|experiment|experiments|results|conclusion|appendix)(?:部分|章节|一节)?", re.IGNORECASE),
    re.compile(r"(?:section|章节)\s*(?P<section>[A-Za-z0-9 .:+/\-]+)", re.IGNORECASE),
    re.compile(r"(?P<section>related work|background|introduction|method|methods|experiment|experiments|results|conclusion|appendix)\s+section", re.IGNORECASE),
]

SECTION_ALIASES = {
    "摘要": ["abstract"],
    "引言": ["introduction"],
    "介绍": ["introduction"],
    "相关工作": ["related work", "background"],
    "背景": ["background", "related work"],
    "方法": ["method", "methods", "approach", "model architecture"],
    "实验": ["experiment", "experiments", "evaluation", "results"],
    "结果": ["results", "evaluation", "experiments"],
    "结论": ["conclusion"],
    "附录": ["appendix", "appendices", "supplementary material"],
    "related work": ["related work", "background"],
    "background": ["background", "related work"],
    "introduction": ["introduction"],
    "method": ["method", "methods", "approach", "model architecture"],
    "methods": ["method", "methods", "approach", "model architecture"],
    "experiment": ["experiment", "experiments", "evaluation", "results"],
    "experiments": ["experiment", "experiments", "evaluation", "results"],
    "results": ["results", "evaluation", "experiments"],
    "conclusion": ["conclusion"],
    "appendix": ["appendix", "appendices", "supplementary material"],
}

ACTION_PATTERNS = [
    ("read", re.compile(r"阅读|读一下|看看|看一下|read", re.IGNORECASE)),
    ("summarize", re.compile(r"总结|概括|summari[sz]e", re.IGNORECASE)),
    ("imitate", re.compile(r"借鉴|模仿|参考|写法|风格|imitate|follow", re.IGNORECASE)),
    ("extract", re.compile(r"提取|抽取|extract", re.IGNORECASE)),
]

TRAILING_CLAUSE_RE = re.compile(
    r"(?:并|然后|再|顺便|重点|特别|尤其).*$",
    re.IGNORECASE,
)

LEADING_NOISE_RE = re.compile(
    r"^(?:请你|请|帮我|麻烦你|能不能|你能不能|可以|帮忙|想让你|我想让你|请帮我|read|please)\s*",
    re.IGNORECASE,
)

NOISE_TERMS = [
    r"请你",
    r"请",
    r"帮我",
    r"麻烦你",
    r"阅读",
    r"读一下",
    r"看一下",
    r"看下",
    r"看看",
    r"看",
    r"分析",
    r"总结",
    r"借鉴",
    r"参考",
    r"模仿",
    r"这篇论文",
    r"这个论文",
    r"那篇论文",
    r"这篇",
    r"那篇",
    r"论文",
    r"paper",
    r"arxiv",
    r"官网",
    r"原文",
    r"原始",
    r"写法",
    r"风格",
    r"部分",
    r"章节",
    r"里面",
    r"中的",
    r"中",
    r"里",
]


def extract_arxiv_id(text: str) -> Optional[Tuple[str, str]]:
    match = ARXIV_ID_RE.search(text)
    if not match:
        return None
    version = match.group("version") or ""
    return match.group("id"), version


def parse_prompt_intent(text: str) -> PromptIntent:
    raw = text.strip()
    section_hint = extract_section_hint(raw)
    action_hint = extract_action_hint(raw)
    paper_query = extract_title_query(raw)
    return PromptIntent(
        raw_prompt=raw,
        paper_query=paper_query,
        section_hint=section_hint,
        section_queries=expand_section_queries(section_hint),
        action_hint=action_hint,
    )


def extract_title_query(text: str) -> str:
    text = text.strip()

    for pattern in (CN_TITLE_RE, QUOTE_RE):
        match = pattern.search(text)
        if match:
            return clean_wrapped_title(match.group(1))

    stripped = TRAILING_CLAUSE_RE.sub("", text)
    stripped = strip_section_clauses(stripped)
    stripped = LEADING_NOISE_RE.sub("", stripped)
    stripped = re.sub(r"https?://\S+", " ", stripped)

    named_patterns = [
        re.compile(r"(?:论文|paper)\s*(?:叫|名为|标题是|title is|titled)?\s*(?P<query>.+)", re.IGNORECASE),
        re.compile(r"(?:关于|\bon\b|\babout\b)\s+(?P<query>.+)", re.IGNORECASE),
    ]
    for pattern in named_patterns:
        match = pattern.search(stripped)
        if match:
            candidate = clean_candidate_query(match.group("query"))
            if candidate:
                return candidate

    latin_spans = LATIN_TITLE_SPAN_RE.findall(stripped)
    if latin_spans:
        best = max(latin_spans, key=len)
        candidate = clean_candidate_query(best)
        if candidate:
            return candidate

    candidate = clean_candidate_query(stripped)
    return candidate or text


def extract_section_hint(text: str) -> Optional[str]:
    for pattern in SECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group("section").strip()
    return None


def extract_action_hint(text: str) -> Optional[str]:
    for label, pattern in ACTION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def expand_section_queries(section_hint: Optional[str]):
    if not section_hint:
        return []
    key = section_hint.strip().lower()
    aliases = SECTION_ALIASES.get(section_hint, []) + SECTION_ALIASES.get(key, [])
    ordered = [section_hint]
    for alias in aliases:
        if alias not in ordered:
            ordered.append(alias)
    return ordered


def strip_section_clauses(text: str) -> str:
    text = re.sub(
        r"(?:的|里|中)(?:摘要|引言|介绍|方法|实验|结果|结论|附录|related work|introduction|method|methods|experiment|experiments|results|conclusion|appendix)(?:部分|章节|一节)?",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?:section|章节)\s*[A-Za-z0-9 .:+/\-]+", " ", text, flags=re.IGNORECASE)
    return text


def clean_candidate_query(text: str) -> str:
    stripped = text
    for pattern in NOISE_TERMS:
        stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"[\(\)\[\]\{\},;:!?。，“”‘’\"']", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def clean_wrapped_title(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped
