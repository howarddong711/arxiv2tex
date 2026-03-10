import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .paths import ensure_cache_root, paper_root
from .storage import read_json, read_jsonl, write_json, write_jsonl
from .types import ArxivPaper, SectionRecord, SnippetRecord, SourceManifest


class PaperCache:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = ensure_cache_root(cache_root)

    def paper_dir(self, cache_key: str) -> Path:
        return paper_root(self.cache_root, cache_key)

    def pending_state_path(self) -> Path:
        return self.cache_root / "pending" / "latest.json"

    def session_pending_state_path(self, session_id: str) -> Path:
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
        return self.cache_root / "pending" / "sessions" / f"{digest}.json"

    def find_by_alias(self, normalized_query: str) -> Optional[str]:
        arxiv_root = self.cache_root / "arxiv"
        if not arxiv_root.exists():
            return None
        for paper_dir in arxiv_root.iterdir():
            alias_path = paper_dir / "aliases.json"
            if not alias_path.exists():
                continue
            aliases = read_json(alias_path)
            values = aliases.get("aliases", [])
            if normalized_query in values:
                return paper_dir.name
        return None

    def save_aliases(self, cache_key: str, aliases: List[str]) -> None:
        path = self.paper_dir(cache_key) / "aliases.json"
        payload = {"aliases": sorted(set(alias.strip() for alias in aliases if alias.strip()))}
        write_json(path, payload)

    def load_aliases(self, cache_key: str) -> List[str]:
        path = self.paper_dir(cache_key) / "aliases.json"
        if not path.exists():
            return []
        return read_json(path).get("aliases", [])

    def save_metadata(self, paper: ArxivPaper) -> None:
        write_json(self.paper_dir(paper.cache_key) / "metadata.json", paper.to_dict())

    def load_metadata(self, cache_key: str) -> Dict[str, object]:
        return read_json(self.paper_dir(cache_key) / "metadata.json")

    def save_manifest(self, cache_key: str, manifest: SourceManifest) -> None:
        write_json(self.paper_dir(cache_key) / "manifest.json", manifest.to_dict())

    def save_sections(self, cache_key: str, sections: List[SectionRecord]) -> None:
        write_json(self.paper_dir(cache_key) / "sections.json", {"sections": [section.to_dict() for section in sections]})

    def load_sections(self, cache_key: str) -> List[Dict[str, object]]:
        path = self.paper_dir(cache_key) / "sections.json"
        if not path.exists():
            return []
        return read_json(path).get("sections", [])

    def save_snippets(self, cache_key: str, snippets: List[SnippetRecord]) -> None:
        write_jsonl(self.paper_dir(cache_key) / "snippets.jsonl", [snippet.to_dict() for snippet in snippets])

    def load_snippets(self, cache_key: str) -> List[Dict[str, object]]:
        path = self.paper_dir(cache_key) / "snippets.jsonl"
        if not path.exists():
            return []
        return read_jsonl(path)

    def save_pending_state(self, payload: Dict[str, object], session_id: Optional[str] = None, ttl_seconds: int = 1800) -> None:
        stamped = dict(payload)
        now = datetime.now(timezone.utc)
        stamped.setdefault("created_at", now.isoformat())
        stamped.setdefault("expires_at", (now + timedelta(seconds=max(0, ttl_seconds))).isoformat())
        if session_id:
            write_json(self.session_pending_state_path(session_id), stamped)
        write_json(self.pending_state_path(), stamped)

    def load_pending_state(self, session_id: Optional[str] = None) -> Optional[Dict[str, object]]:
        path = self.session_pending_state_path(session_id) if session_id else self.pending_state_path()
        if not path.exists():
            return None
        payload = read_json(path)
        expires_at = payload.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry <= datetime.now(timezone.utc):
                    self.clear_pending_state(session_id=session_id)
                    return None
            except ValueError:
                self.clear_pending_state(session_id=session_id)
                return None
        return payload

    def clear_pending_state(self, session_id: Optional[str] = None) -> None:
        if session_id is None:
            path = self.pending_state_path()
            if path.exists():
                path.unlink()
            return

        session_path = self.session_pending_state_path(session_id)
        if session_path.exists():
            session_path.unlink()

        latest_path = self.pending_state_path()
        if latest_path.exists():
            latest = read_json(latest_path)
            if latest.get("session_id") == session_id:
                latest_path.unlink()
