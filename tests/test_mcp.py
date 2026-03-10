import asyncio
from pathlib import Path

from arxiv2tex.mcp import build_parser, build_server
from arxiv2tex.service import PaperService


def test_mcp_parser_accepts_cache_root():
    parser = build_parser()

    args = parser.parse_args(["--cache-root", ".custom-cache"])

    assert args.cache_root == ".custom-cache"


def test_mcp_server_registers_expected_tools():
    server = build_server(PaperService(Path(".arxiv2tex-cache")))

    tool_names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert "arxiv2tex_handle_prompt" in tool_names
    assert "arxiv2tex_extract_writing" in tool_names
    assert len(tool_names) == 11
