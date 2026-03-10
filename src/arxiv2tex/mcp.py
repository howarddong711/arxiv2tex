import argparse
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .service import PaperService


SERVER_INFO = {"name": "arxiv2tex", "version": "0.1.0"}
DEFAULT_CACHE_ROOT = Path(os.environ.get("ARXIV2TEX_CACHE_ROOT", ".arxiv2tex-cache"))
SERVER_INSTRUCTIONS = (
    "Use arxiv2tex tools to resolve arXiv papers from natural-language prompts, "
    "prepare cached TeX views, and retrieve sections or writing-oriented examples "
    "without loading whole papers into context."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arxiv2tex-mcp")
    parser.add_argument(
        "--cache-root",
        default=str(DEFAULT_CACHE_ROOT),
        help="Cache directory for downloaded papers and indexes.",
    )
    return parser


def build_server(service: PaperService) -> FastMCP:
    server = FastMCP(
        name=SERVER_INFO["name"],
        instructions=SERVER_INSTRUCTIONS,
        log_level="ERROR",
    )

    @server.tool(
        name="arxiv2tex_interpret_prompt",
        description="Extract the likely paper query, section hint, and action hint from a natural-language request.",
    )
    def interpret_prompt(prompt: str, session_id: str | None = None) -> dict:
        _ = session_id
        return service.interpret_prompt(prompt)

    @server.tool(
        name="arxiv2tex_handle_prompt",
        description="Run the default agent workflow for a free-form request: interpret, resolve, prepare, and optionally return a section-specific reading payload.",
    )
    def handle_prompt(prompt: str, session_id: str | None = None) -> dict:
        return service.handle_prompt(prompt, session_id=session_id)

    @server.tool(
        name="arxiv2tex_pending_status",
        description="Inspect the latest pending candidate confirmation state, if any.",
    )
    def pending_status(session_id: str | None = None) -> dict:
        return service.pending_status(session_id=session_id)

    @server.tool(
        name="arxiv2tex_resolve",
        description="Resolve a natural-language paper request to an arXiv paper or candidate list.",
    )
    def resolve(prompt: str, session_id: str | None = None) -> dict:
        return service.resolve(prompt, session_id=session_id)

    @server.tool(
        name="arxiv2tex_select_candidate",
        description="Resolve a prompt that returned multiple candidates and choose one by ordinal, arXiv id, or title fragment.",
    )
    def select_candidate(
        prompt: str,
        selection: str,
        prepare: bool = True,
        session_id: str | None = None,
    ) -> dict:
        return service.select_candidate(prompt, selection, prepare=prepare, session_id=session_id)

    @server.tool(
        name="arxiv2tex_prepare",
        description="Download and cache an arXiv paper source package and build full.tex/snippet indexes.",
    )
    def prepare(prompt: str, session_id: str | None = None) -> dict:
        return service.prepare(prompt, session_id=session_id)

    @server.tool(
        name="arxiv2tex_extract_writing",
        description="Extract writing-oriented examples for a target such as abstract, introduction, method, experiment, or conclusion.",
    )
    def extract_writing(
        cache_key: str,
        target: str,
        top_k: int = 3,
        view: str = "reader",
    ) -> dict:
        return service.extract_writing_examples(cache_key, target, top_k=top_k, view=view)

    @server.tool(
        name="arxiv2tex_overview",
        description="Read cached metadata, manifest, and section tree for a paper.",
    )
    def overview(cache_key: str) -> dict:
        return service.overview(cache_key)

    @server.tool(
        name="arxiv2tex_search",
        description="Search the local snippet index for a cached paper.",
    )
    def search(
        cache_key: str,
        query: str,
        top_k: int = 5,
        view: str = "reader",
    ) -> dict:
        return service.search(cache_key, query, top_k=top_k, view=view)

    @server.tool(
        name="arxiv2tex_read_section",
        description="Read one cached section by fuzzy section name.",
    )
    def read_section(cache_key: str, section_ref: str, view: str = "reader") -> dict:
        return service.read_section(cache_key, section_ref, view=view)

    @server.tool(
        name="arxiv2tex_read_fulltex",
        description="Read a slice of cached full.tex.",
    )
    def read_fulltex(
        cache_key: str,
        offset: int = 0,
        limit: int = 4000,
        view: str = "reader",
    ) -> dict:
        return service.read_fulltex(cache_key, offset=offset, limit=limit, view=view)

    return server


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    service = PaperService(Path(args.cache_root))
    server = build_server(service)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
