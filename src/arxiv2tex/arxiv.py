import gzip
import io
import ssl
import tarfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

import certifi

from .types import ArxivPaper


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _is_within_directory(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


class ArxivClient:
    def __init__(self, user_agent: str = "arxiv2tex/0.1.0") -> None:
        self.user_agent = user_agent
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    def fetch_by_id(self, arxiv_id: str, version: str = "") -> List[ArxivPaper]:
        versioned = f"{arxiv_id}{version}"
        data = self._fetch_bytes(
            [
                f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(versioned)}",
                f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(versioned)}",
            ],
            timeout=15,
        )
        root = ET.fromstring(data)
        papers: List[ArxivPaper] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            papers.extend(self._entry_to_papers([entry]))
        return papers

    def search_all(self, query: str, max_results: int = 25) -> List[ArxivPaper]:
        return self._search_raw(f"all:{query}", max_results=max_results)

    def search_title(self, query: str, max_results: int = 25) -> List[ArxivPaper]:
        phrase = f'ti:"{query}"'
        return self._search_raw(phrase, max_results=max_results)

    def search_title_tokens(self, tokens: List[str], max_results: int = 25) -> List[ArxivPaper]:
        if not tokens:
            return []
        expr = " AND ".join(f"ti:{token}" for token in tokens)
        return self._search_raw(expr, max_results=max_results)

    def _search_raw(self, search_query: str, max_results: int = 25) -> List[ArxivPaper]:
        encoded = urllib.parse.quote(search_query)
        path = f"api/query?search_query={encoded}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
        data = self._fetch_bytes(
            [f"http://export.arxiv.org/{path}", f"https://export.arxiv.org/{path}"],
            timeout=12,
        )
        root = ET.fromstring(data)
        return self._entry_to_papers(root.findall("atom:entry", ATOM_NS))

    def _entry_to_papers(self, entries) -> List[ArxivPaper]:
        papers: List[ArxivPaper] = []
        for entry in entries:
            entry_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            if not entry_id:
                continue
            arxiv_id_version = entry_id.rstrip("/").split("/")[-1]
            if "v" in arxiv_id_version:
                arxiv_id, version = arxiv_id_version.split("v", 1)
                version = f"v{version}"
            else:
                arxiv_id, version = arxiv_id_version, ""
            links = {link.attrib.get("title") or link.attrib.get("rel") or "": link.attrib.get("href", "") for link in entry.findall("atom:link", ATOM_NS)}
            pdf_url = ""
            for link in entry.findall("atom:link", ATOM_NS):
                if link.attrib.get("title") == "pdf":
                    pdf_url = link.attrib.get("href", "")
            pdf_url = pdf_url or f"https://arxiv.org/pdf/{arxiv_id}{version}.pdf"
            source_url = f"https://arxiv.org/e-print/{arxiv_id}{version}"

            papers.append(
                ArxivPaper(
                    arxiv_id=arxiv_id,
                    version=version,
                    title=" ".join(entry.findtext("atom:title", default="", namespaces=ATOM_NS).split()),
                    summary=" ".join(entry.findtext("atom:summary", default="", namespaces=ATOM_NS).split()),
                    authors=[
                        author.findtext("atom:name", default="", namespaces=ATOM_NS)
                        for author in entry.findall("atom:author", ATOM_NS)
                    ],
                    published=entry.findtext("atom:published", default="", namespaces=ATOM_NS),
                    updated=entry.findtext("atom:updated", default="", namespaces=ATOM_NS),
                    pdf_url=pdf_url,
                    abs_url=entry_id,
                    source_url=source_url,
                )
            )
        return papers

    def download_source(self, paper: ArxivPaper, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = self._fetch_bytes([paper.source_url], timeout=60)
        destination.write_bytes(data)
        return destination

    def _fetch_bytes(self, urls: List[str], timeout: int) -> bytes:
        last_error = None
        for url in urls:
            request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                if url.startswith("https://"):
                    response = urllib.request.urlopen(request, timeout=timeout, context=self.ssl_context)
                else:
                    response = urllib.request.urlopen(request, timeout=timeout)
                with response:
                    return response.read()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if last_error is None:
            raise RuntimeError("No URL candidates were provided.")
        raise last_error

    def extract_source(self, archive_path: Path, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        raw = archive_path.read_bytes()

        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tar:
                for member in tar.getmembers():
                    member_path = destination / member.name
                    if not _is_within_directory(member_path, destination):
                        raise ValueError("Unsafe path in tar archive.")
                tar.extractall(destination)
                return destination
        except tarfile.TarError:
            # Some arXiv source packages are plain TeX or gzip-compressed TeX.
            text_path = destination / "main.tex"
            if raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            text_path.write_bytes(raw)
            return destination
