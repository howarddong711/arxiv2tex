from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class PromptIntent:
    raw_prompt: str
    paper_query: str
    section_hint: Optional[str] = None
    section_queries: List[str] = field(default_factory=list)
    action_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ArxivPaper:
    arxiv_id: str
    version: str
    title: str
    summary: str
    authors: List[str]
    published: str
    updated: str
    pdf_url: str
    abs_url: str
    source_url: str

    @property
    def cache_key(self) -> str:
        return f"{self.arxiv_id}{self.version}"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class MatchResult:
    paper: ArxivPaper
    score: float
    confidence: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "paper": self.paper.to_dict(),
            "score": round(self.score, 4),
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


@dataclass
class SourceManifest:
    entrypoint: str
    tex_files: List[str]
    bib_files: List[str]
    asset_files: List[str]
    includes: Dict[str, List[str]]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class SectionRecord:
    title: str
    level: str
    source_file: str
    line_number: int
    start_offset: int
    end_offset: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class SnippetRecord:
    snippet_id: str
    section_title: Optional[str]
    source_file: str
    start_offset: int
    end_offset: int
    text: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
