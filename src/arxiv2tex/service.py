import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .arxiv import ArxivClient
from .cache import PaperCache
from .latex import (
    build_manifest,
    build_section_tree,
    build_sections,
    build_snippets,
    expand_full_tex,
    strip_appendix,
    strip_comments,
)
from .matching import STOPWORDS, normalize_text, rerank_papers, score_title_match
from .query import (
    expand_section_queries,
    extract_arxiv_id,
    extract_title_candidates,
    parse_prompt_intent,
)
from .storage import write_json
from .types import ArxivPaper, PromptIntent


class PaperService:
    def __init__(self, cache_root: Path, pending_ttl_seconds: int = 1800) -> None:
        self.cache = PaperCache(cache_root)
        self.arxiv = ArxivClient()
        self.pending_ttl_seconds = pending_ttl_seconds

    def resolve(
        self, prompt: str, max_results: int = 25, session_id: Optional[str] = None
    ) -> Dict[str, object]:
        try:
            intent = parse_prompt_intent(prompt)
            arxiv_ref = extract_arxiv_id(prompt)
            if arxiv_ref:
                arxiv_id, version = arxiv_ref
                papers = self.arxiv.fetch_by_id(arxiv_id, version)
                if not papers:
                    return {
                        "status": "not_found",
                        "query": arxiv_id,
                        "message": "No arXiv paper matched the supplied id.",
                    }
                paper = papers[0]
                self._record_aliases(paper, [prompt, arxiv_id, paper.title])
                self.cache.clear_pending_state(session_id=session_id)
                return {
                    "status": "resolved",
                    "mode": "exact_id",
                    "session_id": session_id,
                    "intent": intent.to_dict(),
                    "query": arxiv_id,
                    "selected": paper.to_dict(),
                    "cache_key": paper.cache_key,
                }

            query_candidates = extract_title_candidates(prompt) or [intent.paper_query]
            return self._resolve_from_intent(
                intent,
                query_candidates=query_candidates,
                session_id=session_id,
                max_results=max_results,
                alias_source=prompt,
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": f"Failed to resolve paper: {exc}"}

    def resolve_intent(
        self,
        paper_query: str,
        section_hint: Optional[str] = None,
        action_hint: Optional[str] = None,
        raw_prompt: Optional[str] = None,
        max_results: int = 25,
        session_id: Optional[str] = None,
    ) -> Dict[str, object]:
        try:
            intent = self._structured_intent(
                paper_query=paper_query,
                section_hint=section_hint,
                action_hint=action_hint,
                raw_prompt=raw_prompt,
            )
            query_candidates = extract_title_candidates(paper_query) or [
                intent.paper_query
            ]
            return self._resolve_from_intent(
                intent,
                query_candidates=query_candidates,
                session_id=session_id,
                max_results=max_results,
                alias_source=intent.raw_prompt or intent.paper_query,
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": f"Failed to resolve paper: {exc}"}

    def _resolve_from_intent(
        self,
        intent: PromptIntent,
        query_candidates: List[str],
        session_id: Optional[str],
        max_results: int,
        alias_source: str,
    ) -> Dict[str, object]:
        query = intent.paper_query

        for candidate_query in query_candidates:
            normalized_query = normalize_text(candidate_query)
            cache_key = self.cache.find_by_alias(normalized_query)
            if cache_key:
                metadata = self.cache.load_metadata(cache_key)
                cached_title = str(metadata.get("title", ""))
                score, reasons = score_title_match(candidate_query, cached_title)
                if not (
                    any(reason.startswith("exact_title=") for reason in reasons)
                    or score >= 0.995
                ):
                    continue
                self.cache.clear_pending_state(session_id=session_id)
                return {
                    "status": "resolved",
                    "mode": "cache",
                    "session_id": session_id,
                    "intent": intent.to_dict(),
                    "query": candidate_query,
                    "selected": metadata,
                    "cache_key": cache_key,
                }

        search_queries: List[str] = []
        for candidate_query in query_candidates:
            for strategy in self._search_queries(candidate_query):
                if strategy not in search_queries:
                    search_queries.append(strategy)

        candidates: List[ArxivPaper] = []
        seen = set()
        for strategy in search_queries:
            papers = self._search_strategy(strategy, max_results=max_results)
            for paper in papers:
                if paper.cache_key in seen:
                    continue
                seen.add(paper.cache_key)
                candidates.append(paper)

        primary_query = query_candidates[0]
        ranked = rerank_papers(primary_query, candidates)
        if not ranked:
            return {
                "status": "not_found",
                "intent": intent.to_dict(),
                "query": primary_query,
                "message": "No sufficiently similar arXiv paper was found.",
                "candidates": [],
            }

        top = ranked[0]
        if top.confidence == "low" and not self._should_offer_confirmation(
            primary_query, ranked
        ):
            return {
                "status": "not_found",
                "intent": intent.to_dict(),
                "query": primary_query,
                "message": "No sufficiently similar arXiv paper was found.",
                "candidates": [self._candidate_payload(item) for item in ranked[:3]],
            }

        if top.confidence == "high":
            self._record_aliases(top.paper, [alias_source, query, top.paper.title])
            self.cache.clear_pending_state(session_id=session_id)
            return {
                "status": "resolved",
                "mode": "title_match",
                "session_id": session_id,
                "intent": intent.to_dict(),
                "query": primary_query,
                "selected": top.paper.to_dict(),
                "cache_key": top.paper.cache_key,
                "score": top.score,
                "reasons": top.reasons,
            }

        pending = {
            "session_id": session_id,
            "original_prompt": alias_source,
            "intent": intent.to_dict(),
            "query": primary_query,
            "candidates": [self._candidate_payload(item) for item in ranked[:3]],
        }
        self.cache.save_pending_state(
            pending,
            session_id=session_id,
            ttl_seconds=self.pending_ttl_seconds,
        )
        return {
            "status": "confirm",
            "session_id": session_id,
            "intent": intent.to_dict(),
            "query": query,
            "message": "Multiple plausible arXiv matches were found. Ask the user to confirm one of them.",
            "candidates": pending["candidates"],
        }

    def interpret_prompt(self, prompt: str) -> Dict[str, object]:
        intent = parse_prompt_intent(prompt)
        return {"status": "ok", "intent": intent.to_dict()}

    def interpret_intent(
        self,
        paper_query: str,
        section_hint: Optional[str] = None,
        action_hint: Optional[str] = None,
        raw_prompt: Optional[str] = None,
    ) -> Dict[str, object]:
        intent = self._structured_intent(
            paper_query=paper_query,
            section_hint=section_hint,
            action_hint=action_hint,
            raw_prompt=raw_prompt,
        )
        return {"status": "ok", "intent": intent.to_dict()}

    def handle_prompt(
        self, prompt: str, session_id: Optional[str] = None
    ) -> Dict[str, object]:
        pending_result = self._maybe_consume_pending(prompt, session_id=session_id)
        if pending_result is not None:
            return pending_result

        intent = parse_prompt_intent(prompt)
        resolution = self.resolve(prompt, session_id=session_id)
        if resolution["status"] != "resolved":
            return {
                "status": resolution["status"],
                "session_id": session_id,
                "intent": intent.to_dict(),
                "resolution": resolution,
                "next_action": "confirm"
                if resolution["status"] == "confirm"
                else "stop",
            }

        preparation = self.prepare(prompt, session_id=session_id)
        if preparation["status"] != "prepared":
            return {
                "status": preparation["status"],
                "session_id": session_id,
                "intent": intent.to_dict(),
                "resolution": resolution,
                "preparation": preparation,
                "next_action": "stop",
            }

        cache_key = preparation["cache_key"]
        overview = self.overview(cache_key)
        payload = {
            "status": "ready",
            "session_id": session_id,
            "intent": intent.to_dict(),
            "resolution": resolution,
            "preparation": preparation,
            "overview": overview,
            "next_action": "read",
        }

        if intent.section_hint:
            section_result = self.read_section(
                cache_key, intent.section_hint, view="reader"
            )
            payload["section_result"] = section_result
            if section_result["status"] == "ok" and intent.action_hint == "imitate":
                try:
                    payload["writing_examples"] = self.extract_writing_examples(
                        cache_key, intent.section_hint, top_k=3, view="reader"
                    )
                except FileNotFoundError:
                    payload["writing_examples"] = self.search(
                        cache_key, intent.section_hint, top_k=3, view="reader"
                    )

        return payload

    def handle_intent(
        self,
        paper_query: str,
        section_hint: Optional[str] = None,
        action_hint: Optional[str] = None,
        raw_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, object]:
        intent = self._structured_intent(
            paper_query=paper_query,
            section_hint=section_hint,
            action_hint=action_hint,
            raw_prompt=raw_prompt,
        )
        resolution = self.resolve_intent(
            paper_query=paper_query,
            section_hint=section_hint,
            action_hint=action_hint,
            raw_prompt=raw_prompt,
            session_id=session_id,
        )
        if resolution["status"] != "resolved":
            return {
                "status": resolution["status"],
                "session_id": session_id,
                "intent": intent.to_dict(),
                "resolution": resolution,
                "next_action": "confirm"
                if resolution["status"] == "confirm"
                else "stop",
            }

        preparation = self.prepare_intent(
            paper_query=paper_query,
            section_hint=section_hint,
            action_hint=action_hint,
            raw_prompt=raw_prompt,
            session_id=session_id,
        )
        if preparation["status"] != "prepared":
            return {
                "status": preparation["status"],
                "session_id": session_id,
                "intent": intent.to_dict(),
                "resolution": resolution,
                "preparation": preparation,
                "next_action": "stop",
            }

        cache_key = str(preparation["cache_key"])
        overview = self.overview(cache_key)
        payload = {
            "status": "ready",
            "session_id": session_id,
            "intent": intent.to_dict(),
            "resolution": resolution,
            "preparation": preparation,
            "overview": overview,
            "next_action": "read",
        }

        if intent.section_hint:
            section_result = self.read_section(
                cache_key, intent.section_hint, view="reader"
            )
            payload["section_result"] = section_result
            if section_result["status"] == "ok" and intent.action_hint == "imitate":
                try:
                    payload["writing_examples"] = self.extract_writing_examples(
                        cache_key, intent.section_hint, top_k=3, view="reader"
                    )
                except FileNotFoundError:
                    payload["writing_examples"] = self.search(
                        cache_key, intent.section_hint, top_k=3, view="reader"
                    )

        return payload

    def select_candidate(
        self,
        prompt: str,
        selection: str,
        prepare: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, object]:
        intent = parse_prompt_intent(prompt)
        resolution = self.resolve(prompt, session_id=session_id)
        if resolution["status"] == "resolved":
            if prepare:
                return self.prepare(prompt, session_id=session_id)
            return resolution
        if resolution["status"] != "confirm":
            return resolution

        candidates = resolution.get("candidates", [])
        selected = self._match_candidate_selection(candidates, selection)
        if not selected:
            return {
                "status": "not_found",
                "session_id": session_id,
                "intent": intent.to_dict(),
                "message": f"Could not match selection '{selection}' to any candidate.",
                "candidates": candidates,
            }

        paper_payload = selected["paper"]
        paper = self._paper_from_dict(paper_payload)
        self._record_aliases(paper, [prompt, intent.paper_query, paper.title])
        self.cache.clear_pending_state(session_id=session_id)
        if not prepare:
            return {
                "status": "resolved",
                "mode": "confirmed_candidate",
                "session_id": session_id,
                "intent": intent.to_dict(),
                "query": intent.paper_query,
                "selected": paper.to_dict(),
                "cache_key": paper.cache_key,
            }
        return self.prepare(paper.abs_url or paper.arxiv_id, session_id=session_id)

    def pending_status(self, session_id: Optional[str] = None) -> Dict[str, object]:
        pending = self.cache.load_pending_state(session_id=session_id)
        if not pending:
            return {"status": "empty", "session_id": session_id}
        remaining_seconds = None
        expires_at = pending.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                remaining_seconds = max(
                    0, int((expiry - datetime.now(timezone.utc)).total_seconds())
                )
            except ValueError:
                remaining_seconds = None
        return {
            "status": "pending",
            "session_id": session_id,
            "pending": pending,
            "remaining_seconds": remaining_seconds,
        }

    def extract_writing_examples(
        self, cache_key: str, target: str, top_k: int = 3, view: str = "reader"
    ) -> Dict[str, object]:
        aliases = self._writing_target_aliases(target)
        target_profile = self._classify_writing_target(aliases)
        sections = self._sections_for_view(cache_key, view)
        snippets = self._snippets_for_view(cache_key, view)

        matched_sections = []
        for section in sections:
            normalized_title = normalize_text(section["title"])
            if any(normalize_text(alias) in normalized_title for alias in aliases):
                matched_sections.append(section)

        scored = self._score_snippets(snippets, aliases, matched_sections)
        examples = [
            {**snippet, "score": round(score, 4)} for score, snippet in scored[:top_k]
        ]

        try:
            metadata = self.cache.load_metadata(cache_key)
        except FileNotFoundError:
            metadata = {}
        if not examples and any(alias == "abstract" for alias in aliases):
            summary = str(metadata.get("summary", "")).strip()
            if summary:
                examples.append(
                    {
                        "snippet_id": "abstract-summary",
                        "section_title": "Abstract",
                        "source_file": "metadata.summary",
                        "start_offset": 0,
                        "end_offset": len(summary),
                        "text": summary,
                        "score": 1.0,
                    }
                )

        starter_sentences = self._starter_sentences(examples)
        style_signals = self._style_signals(examples)
        return {
            "status": "ok",
            "target": target,
            "target_profile": target_profile,
            "aliases": aliases,
            "view": view,
            "matched_sections": matched_sections[:5],
            "examples": examples,
            "starter_sentences": starter_sentences,
            "style_signals": style_signals,
            "guidance": self._writing_guidance(target_profile, style_signals),
        }

    def prepare(
        self, prompt: str, view: str = "reader", session_id: Optional[str] = None
    ) -> Dict[str, object]:
        resolved = self.resolve(prompt, session_id=session_id)
        if resolved["status"] != "resolved":
            return resolved

        selected = resolved["selected"]
        paper = self._paper_from_dict(selected)
        return self._prepare_paper(paper, view=view, session_id=session_id)

    def _prepare_paper(
        self, paper: ArxivPaper, view: str = "reader", session_id: Optional[str] = None
    ) -> Dict[str, object]:

        paper_dir = self.cache.paper_dir(paper.cache_key)
        source_archive = paper_dir / "source.tar"
        source_dir = paper_dir / "source"
        metadata_path = paper_dir / "metadata.json"
        manifest_path = paper_dir / "manifest.json"
        sections_path = paper_dir / "sections.json"
        snippets_path = paper_dir / "snippets.jsonl"
        full_tex_path = paper_dir / "full.tex"
        clean_tex_path = paper_dir / "clean.tex"
        reader_tex_path = paper_dir / "reader.tex"

        needs_source_build = (
            not source_archive.exists()
            or not source_dir.exists()
            or not manifest_path.exists()
            or not full_tex_path.exists()
            or not clean_tex_path.exists()
            or not reader_tex_path.exists()
        )
        needs_index_build = not sections_path.exists() or not snippets_path.exists()

        if needs_source_build:
            try:
                self.arxiv.download_source(paper, source_archive)
                self.arxiv.extract_source(source_archive, source_dir)
                manifest = build_manifest(source_dir)
                full_tex = expand_full_tex(source_dir, manifest)
                clean_tex = strip_comments(full_tex)
                reader_tex = strip_appendix(clean_tex)
                sections = build_sections(reader_tex)
                snippets = build_snippets(reader_tex, sections)
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "error",
                    "message": f"Failed to prepare paper source: {exc}",
                    "cache_key": paper.cache_key,
                }

            paper_dir.mkdir(parents=True, exist_ok=True)
            self.cache.save_metadata(paper)
            self.cache.save_manifest(paper.cache_key, manifest)
            self.cache.save_sections(paper.cache_key, sections)
            self.cache.save_snippets(paper.cache_key, snippets)
            full_tex_path.write_text(full_tex, encoding="utf-8")
            clean_tex_path.write_text(clean_tex, encoding="utf-8")
            reader_tex_path.write_text(reader_tex, encoding="utf-8")
            write_json(
                paper_dir / "status.json",
                {
                    "prepared": True,
                    "views": ["full", "clean", "reader"],
                    "section_count": len(sections),
                    "snippet_count": len(snippets),
                },
            )
        elif needs_index_build:
            reader_tex = reader_tex_path.read_text(encoding="utf-8")
            sections = build_sections(reader_tex)
            snippets = build_snippets(reader_tex, sections)
            if not metadata_path.exists():
                self.cache.save_metadata(paper)
            self.cache.save_sections(paper.cache_key, sections)
            self.cache.save_snippets(paper.cache_key, snippets)
            write_json(
                paper_dir / "status.json",
                {
                    "prepared": True,
                    "views": self._available_views(paper.cache_key),
                    "section_count": len(sections),
                    "snippet_count": len(snippets),
                },
            )
        elif not metadata_path.exists():
            self.cache.save_metadata(paper)

        return {
            "status": "prepared",
            "session_id": session_id,
            "cache_key": paper.cache_key,
            "paper_dir": str(paper_dir),
            "default_view": view,
            "metadata": self.cache.load_metadata(paper.cache_key),
        }

    def prepare_intent(
        self,
        paper_query: str,
        section_hint: Optional[str] = None,
        action_hint: Optional[str] = None,
        raw_prompt: Optional[str] = None,
        view: str = "reader",
        session_id: Optional[str] = None,
    ) -> Dict[str, object]:
        resolved = self.resolve_intent(
            paper_query=paper_query,
            section_hint=section_hint,
            action_hint=action_hint,
            raw_prompt=raw_prompt,
            session_id=session_id,
        )
        if resolved["status"] != "resolved":
            return resolved
        selected = resolved["selected"]
        paper = self._paper_from_dict(selected)
        return self._prepare_paper(paper, view=view, session_id=session_id)

    def overview(self, cache_key: str) -> Dict[str, object]:
        paper_dir = self.cache.paper_dir(cache_key)
        metadata = self.cache.load_metadata(cache_key)
        sections = self.cache.load_sections(cache_key)
        manifest_path = paper_dir / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            from .storage import read_json

            manifest = read_json(manifest_path)
        return {
            "status": "ok",
            "metadata": metadata,
            "manifest": manifest,
            "views": self._available_views(cache_key),
            "sections": sections,
            "section_tree": build_section_tree(
                [self._section_from_dict(section) for section in sections]
            ),
        }

    def search(
        self, cache_key: str, query: str, top_k: int = 5, view: str = "reader"
    ) -> Dict[str, object]:
        snippets = self._snippets_for_view(cache_key, view)
        query_terms = [query] + expand_section_queries(query)
        query_tokens = []
        for term in query_terms:
            for token in normalize_text(term).split(" "):
                if token and token not in query_tokens:
                    query_tokens.append(token)
        scored = []
        for snippet in snippets:
            text = normalize_text(snippet["text"])
            hit_count = sum(1 for token in query_tokens if token in text)
            if not hit_count:
                continue
            score = hit_count / max(1, len(query_tokens))
            normalized_section = normalize_text(snippet.get("section_title") or "")
            if any(
                normalize_text(term) in normalized_section
                for term in query_terms
                if term
            ):
                score += 0.2
            scored.append((score, snippet))
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "status": "ok",
            "view": view,
            "results": [
                {**snippet, "score": round(score, 4)}
                for score, snippet in scored[:top_k]
            ],
        }

    def read_section(
        self, cache_key: str, section_ref: str, view: str = "reader"
    ) -> Dict[str, object]:
        sections = self._sections_for_view(cache_key, view)
        text = self._read_view(cache_key, view)
        aliases = expand_section_queries(section_ref)
        queries = [normalize_text(item) for item in aliases if item]
        for section in sections:
            normalized_title = normalize_text(section["title"])
            if any(query in normalized_title for query in queries):
                return {
                    "status": "ok",
                    "view": view,
                    "section": section,
                    "text": text[section["start_offset"] : section["end_offset"]],
                }
        return {
            "status": "not_found",
            "message": f"No section matched '{section_ref}'.",
        }

    def read_fulltex(
        self, cache_key: str, offset: int = 0, limit: int = 4000, view: str = "reader"
    ) -> Dict[str, object]:
        text = self._read_view(cache_key, view)
        end = min(len(text), offset + limit)
        return {
            "status": "ok",
            "view": view,
            "offset": offset,
            "end": end,
            "text": text[offset:end],
        }

    def _search_strategy(self, query: str, max_results: int) -> List[ArxivPaper]:
        tokens = [
            token
            for token in normalize_text(query).split(" ")
            if token and token not in STOPWORDS
        ]
        candidates: List[ArxivPaper] = []
        seen = set()

        fetchers = [
            lambda: self.arxiv.search_title(query, max_results=min(max_results, 10)),
            lambda: self.arxiv.search_title_tokens(
                tokens[:6], max_results=min(max_results, 12)
            ),
            lambda: self.arxiv.search_all(query, max_results=min(max_results, 12)),
        ]

        for fetch in fetchers:
            try:
                batch = fetch()
            except Exception:  # noqa: BLE001
                continue
            for paper in batch:
                if paper.cache_key in seen:
                    continue
                seen.add(paper.cache_key)
                candidates.append(paper)
            if candidates and len(candidates) >= 5:
                break
        return candidates

    def _record_aliases(self, paper: ArxivPaper, aliases: List[str]) -> None:
        normalized: List[str] = []
        title_aliases = {
            normalize_text(paper.title),
            normalize_text(paper.arxiv_id),
            normalize_text(paper.cache_key),
            normalize_text(f"{paper.arxiv_id}{paper.version}"),
        }

        for alias in aliases:
            alias_norm = normalize_text(alias)
            if not alias_norm:
                continue
            if alias_norm in title_aliases:
                normalized.append(alias_norm)
                continue

            score, reasons = score_title_match(alias, paper.title)
            if (
                any(reason.startswith("exact_title=") for reason in reasons)
                or score >= 0.995
            ):
                normalized.append(alias_norm)

        normalized.extend(title_aliases)
        self.cache.save_aliases(paper.cache_key, normalized)
        if not (self.cache.paper_dir(paper.cache_key) / "metadata.json").exists():
            self.cache.save_metadata(paper)

    def _search_queries(self, query: str) -> List[str]:
        normalized = re.sub(r"\s+", " ", query.strip())
        variants = [normalized]
        tokens = [token for token in normalize_text(query).split(" ") if token]
        filtered = [token for token in tokens if len(token) > 2]
        if filtered:
            variants.append(" ".join(filtered))
        deduped = []
        seen = set()
        for item in variants:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _candidate_payload(self, match_result) -> Dict[str, object]:
        paper = match_result.paper
        published_year = paper.published[:4] if paper.published else ""
        summary_sentence = paper.summary.split(". ")[0].strip()
        return {
            **match_result.to_dict(),
            "first_author": paper.authors[0] if paper.authors else "",
            "published_year": published_year,
            "summary_preview": summary_sentence[:240],
        }

    def _should_offer_confirmation(self, query: str, ranked) -> bool:
        normalized = normalize_text(query)
        if not normalized or not ranked:
            return False
        tokens = [token for token in normalized.split(" ") if token]
        top_score = ranked[0].score
        has_ascii_or_digit = any(
            any(char.isascii() and char.isalnum() for char in token) for token in tokens
        )
        is_short_query = len(tokens) <= 4 and len(normalized) <= 32
        return top_score >= 0.45 and (has_ascii_or_digit or is_short_query)

    def _structured_intent(
        self,
        paper_query: str,
        section_hint: Optional[str],
        action_hint: Optional[str],
        raw_prompt: Optional[str],
    ) -> PromptIntent:
        intent = PromptIntent(
            raw_prompt=raw_prompt or paper_query,
            paper_query=paper_query.strip(),
            section_hint=section_hint.strip() if section_hint else None,
            section_queries=[],
            action_hint=action_hint.strip() if action_hint else None,
        )
        intent.section_queries = expand_section_queries(intent.section_hint)
        return intent

    def _match_candidate_selection(
        self, candidates: List[Dict[str, object]], selection: str
    ) -> Optional[Dict[str, object]]:
        cleaned = self._canonicalize_selection_text(selection)
        if not cleaned:
            return None

        ordinal_map = {
            "1": 0,
            "第一个": 0,
            "第1个": 0,
            "第一篇": 0,
            "2": 1,
            "第二个": 1,
            "第2个": 1,
            "第二篇": 1,
            "3": 2,
            "第三个": 2,
            "第3个": 2,
            "第三篇": 2,
        }
        if cleaned in ordinal_map:
            index = ordinal_map[cleaned]
            if index < len(candidates):
                return candidates[index]

        normalized = normalize_text(cleaned)
        for candidate in candidates:
            paper = candidate["paper"]
            if normalized == normalize_text(
                paper["arxiv_id"]
            ) or normalized == normalize_text(
                f"{paper['arxiv_id']}{paper.get('version', '')}"
            ):
                return candidate
        for candidate in candidates:
            paper = candidate["paper"]
            if normalized and normalized in normalize_text(paper["title"]):
                return candidate
        return None

    def _available_views(self, cache_key: str) -> List[str]:
        root = self.cache.paper_dir(cache_key)
        views = []
        for view in ("full", "clean", "reader"):
            if (root / f"{view}.tex").exists():
                views.append(view)
        return views

    def _read_view(self, cache_key: str, view: str) -> str:
        allowed = {"full", "clean", "reader"}
        selected = view if view in allowed else "reader"
        path = self.cache.paper_dir(cache_key) / f"{selected}.tex"
        if not path.exists():
            raise FileNotFoundError(
                f"View '{selected}' is not available for {cache_key}."
            )
        return path.read_text(encoding="utf-8")

    def _sections_for_view(self, cache_key: str, view: str) -> List[Dict[str, object]]:
        if view == "reader":
            cached = self.cache.load_sections(cache_key)
            if cached:
                return cached
        text = self._read_view(cache_key, view)
        return [section.to_dict() for section in build_sections(text)]

    def _snippets_for_view(self, cache_key: str, view: str) -> List[Dict[str, object]]:
        if view == "reader":
            cached = self.cache.load_snippets(cache_key)
            if cached:
                return cached
        text = self._read_view(cache_key, view)
        sections = build_sections(text)
        return [snippet.to_dict() for snippet in build_snippets(text, sections)]

    def _writing_target_aliases(self, target: str) -> List[str]:
        aliases = expand_section_queries(target)
        normalized_target = normalize_text(target)
        extras = {
            "abstract": ["abstract", "summary"],
            "related work": ["related work", "background", "previous work"],
            "background": ["background", "related work"],
            "method": ["method", "methods", "approach", "model architecture"],
            "experiment": ["experiment", "experiments", "evaluation", "results"],
            "results": ["results", "evaluation", "experiments"],
            "conclusion": ["conclusion", "discussion"],
        }
        for key, values in extras.items():
            normalized_key = normalize_text(key)
            if (
                normalized_target == normalized_key
                or normalized_key in normalized_target
            ):
                for value in values:
                    if value not in aliases:
                        aliases.append(value)
        if target not in aliases:
            aliases.insert(0, target)
        return aliases

    def _classify_writing_target(self, aliases: List[str]) -> str:
        normalized = {normalize_text(alias) for alias in aliases}
        if "abstract" in normalized or "summary" in normalized:
            return "abstract"
        if "related work" in normalized or "background" in normalized:
            return "related_work"
        if (
            "method" in normalized
            or "methods" in normalized
            or "approach" in normalized
        ):
            return "method"
        if (
            "experiment" in normalized
            or "experiments" in normalized
            or "evaluation" in normalized
            or "results" in normalized
        ):
            return "experiment"
        if "conclusion" in normalized or "discussion" in normalized:
            return "conclusion"
        return "general"

    def _score_snippets(
        self,
        snippets: List[Dict[str, object]],
        query_terms: List[str],
        matched_sections: List[Dict[str, object]],
    ) -> List[tuple]:
        matched_titles = {
            normalize_text(section["title"]) for section in matched_sections
        }
        query_tokens: List[str] = []
        for term in query_terms:
            for token in normalize_text(term).split(" "):
                if token and token not in query_tokens:
                    query_tokens.append(token)

        scored = []
        for snippet in snippets:
            text = normalize_text(snippet["text"])
            section_title = normalize_text(snippet.get("section_title") or "")
            hit_count = sum(1 for token in query_tokens if token in text)
            if not hit_count and section_title not in matched_titles:
                continue
            score = hit_count / max(1, len(query_tokens))
            if section_title in matched_titles:
                score += 0.4
            if any(normalize_text(term) in section_title for term in query_terms):
                score += 0.2
            scored.append((score, snippet))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _starter_sentences(
        self, examples: List[Dict[str, object]], limit: int = 3
    ) -> List[str]:
        starters: List[str] = []
        for example in examples:
            text = str(example.get("text", "")).strip()
            if not text:
                continue
            sentence = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", text, maxsplit=1)[
                0
            ].strip()
            sentence = re.sub(r"\s+", " ", sentence)
            if len(sentence) < 12:
                continue
            if sentence not in starters:
                starters.append(sentence)
            if len(starters) >= limit:
                break
        return starters

    def _style_signals(self, examples: List[Dict[str, object]]) -> Dict[str, object]:
        joined = "\n".join(str(example.get("text", "")) for example in examples)
        citation_hits = len(
            re.findall(r"\\cite\{|\\citet\{|\\citep\{|(?:\[\d+(?:,\s*\d+)*\])", joined)
        )
        figure_hits = len(
            re.findall(
                r"\b(?:fig(?:ure)?\.?\s*\d+|table\s*\d+)\b", joined, flags=re.IGNORECASE
            )
        )
        equation_hits = len(
            re.findall(r"\b(?:eq(?:uation)?\.?\s*\d+)\b", joined, flags=re.IGNORECASE)
        )
        sentence_count = max(1, len(re.findall(r"[.!?。！？]+", joined)))
        token_count = max(1, len(joined.split()))
        return {
            "citation_hits": citation_hits,
            "figure_hits": figure_hits,
            "equation_hits": equation_hits,
            "avg_tokens_per_sentence": round(token_count / sentence_count, 1),
        }

    def _writing_guidance(
        self, target_profile: str, style_signals: Dict[str, object]
    ) -> List[str]:
        guidance_map = {
            "abstract": [
                "Open with the problem or task, then state the proposed method and the main quantitative result.",
                "Keep the paragraph dense and avoid literature survey details.",
            ],
            "related_work": [
                "Group prior work by theme instead of summarizing papers one by one.",
                "Use citations to anchor comparisons, then end with the gap your paper addresses.",
            ],
            "method": [
                "Lead with the core idea, then introduce components in the order they appear in the pipeline.",
                "Define notation only when it becomes necessary for the mechanism being described.",
            ],
            "experiment": [
                "Start with the evaluation setup or task, then move into the main results and ablations.",
                "Keep claims close to numbers, tables, or figure references.",
            ],
            "conclusion": [
                "Restate the main contribution in one sentence, then summarize empirical takeaways and limits.",
                "Keep the ending shorter and less citation-heavy than the body sections.",
            ],
            "general": [
                "Reuse the section's opening sentence pattern before adapting the details to your own paper.",
            ],
        }
        guidance = list(guidance_map.get(target_profile, guidance_map["general"]))
        if style_signals.get("citation_hits", 0) >= 2:
            guidance.append(
                "This section style leans on explicit citations, so keep related claims attached to references."
            )
        if style_signals.get("figure_hits", 0) or style_signals.get("equation_hits", 0):
            guidance.append(
                "The examples frequently point to figures, tables, or equations; preserve those anchors near the claim they support."
            )
        return guidance

    def _section_from_dict(self, payload: Dict[str, object]):
        from .types import SectionRecord

        return SectionRecord(
            title=str(payload["title"]),
            level=str(payload["level"]),
            source_file=str(payload["source_file"]),
            line_number=int(payload["line_number"]),
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
        )

    def _paper_from_dict(self, payload: Dict[str, object]) -> ArxivPaper:
        return ArxivPaper(
            arxiv_id=str(payload["arxiv_id"]),
            version=str(payload.get("version", "")),
            title=str(payload["title"]),
            summary=str(payload.get("summary", "")),
            authors=list(payload.get("authors", [])),
            published=str(payload.get("published", "")),
            updated=str(payload.get("updated", "")),
            pdf_url=str(payload.get("pdf_url", "")),
            abs_url=str(payload.get("abs_url", "")),
            source_url=str(payload.get("source_url", "")),
        )

    def _maybe_consume_pending(
        self, prompt: str, session_id: Optional[str] = None
    ) -> Optional[Dict[str, object]]:
        pending = self.cache.load_pending_state(session_id=session_id)
        if not pending:
            return None

        selection = self._normalize_selection_input(prompt)
        if not selection:
            return None

        selected = self._match_candidate_selection(
            pending.get("candidates", []), selection
        )
        if not selected:
            return None

        paper = self._paper_from_dict(selected["paper"])
        intent = (
            pending.get("intent")
            or parse_prompt_intent(pending.get("original_prompt", prompt)).to_dict()
        )
        original_prompt = str(pending.get("original_prompt", prompt))
        self._record_aliases(
            paper, [original_prompt, str(intent.get("paper_query", "")), paper.title]
        )
        self.cache.clear_pending_state(session_id=session_id)

        preparation = self.prepare(
            paper.abs_url or paper.arxiv_id, session_id=session_id
        )
        if preparation["status"] != "prepared":
            return {
                "status": preparation["status"],
                "session_id": session_id,
                "intent": intent,
                "selected": paper.to_dict(),
                "preparation": preparation,
                "next_action": "stop",
            }

        cache_key = preparation["cache_key"]
        overview = self.overview(cache_key)
        payload = {
            "status": "ready",
            "session_id": session_id,
            "intent": intent,
            "resolution": {
                "status": "resolved",
                "mode": "pending_confirmation",
                "session_id": session_id,
                "query": intent.get("paper_query", paper.title),
                "selected": paper.to_dict(),
                "cache_key": cache_key,
            },
            "preparation": preparation,
            "overview": overview,
            "next_action": "read",
            "confirmation": {
                "selection": selection,
                "source": "pending_state",
            },
        }
        section_hint = intent.get("section_hint")
        action_hint = intent.get("action_hint")
        if section_hint:
            section_result = self.read_section(
                cache_key, str(section_hint), view="reader"
            )
            payload["section_result"] = section_result
            if section_result["status"] == "ok" and action_hint == "imitate":
                try:
                    payload["writing_examples"] = self.extract_writing_examples(
                        cache_key, str(section_hint), top_k=3, view="reader"
                    )
                except FileNotFoundError:
                    payload["writing_examples"] = self.search(
                        cache_key, str(section_hint), top_k=3, view="reader"
                    )
        return payload

    def _normalize_selection_input(self, prompt: str) -> Optional[str]:
        cleaned = self._canonicalize_selection_text(prompt)
        if not cleaned:
            return None
        explicit = {
            "就第一个": "第一个",
            "第一个": "第一个",
            "第一篇": "第一篇",
            "就第一篇": "第一篇",
            "第1个": "第1个",
            "1": "1",
            "就第二个": "第二个",
            "第二个": "第二个",
            "第二篇": "第二篇",
            "就第二篇": "第二篇",
            "第2个": "第2个",
            "2": "2",
            "就第三个": "第三个",
            "第三个": "第三个",
            "第三篇": "第三篇",
            "第3个": "第3个",
            "3": "3",
            "是第一个": "第一个",
            "是第二个": "第二个",
            "是第三个": "第三个",
            "yes": "第一个",
            "y": "第一个",
            "是这篇": "第一个",
            "就这篇": "第一个",
            "这篇": "第一个",
        }
        lowered = cleaned.lower()
        if lowered in explicit:
            return explicit[lowered]
        if cleaned in explicit:
            return explicit[cleaned]
        if extract_arxiv_id(cleaned):
            return cleaned
        if len(cleaned) <= 80:
            return cleaned
        return None

    def _canonicalize_selection_text(self, text: str) -> str:
        cleaned = re.sub(r"[\s,.;:!?，。！？]+", " ", text.strip())
        cleaned = re.sub(r"^(?:那|就|我选|我觉得是|应该是|选)\s*", "", cleaned)
        cleaned = re.sub(r"\s*(?:吧|呀|啊|呢|啦|了)\s*$", "", cleaned)
        return cleaned.strip()
