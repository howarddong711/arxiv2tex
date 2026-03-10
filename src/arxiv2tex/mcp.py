import json
import sys
from pathlib import Path
from typing import Any, Dict

from .service import PaperService


SERVER_INFO = {"name": "arxiv2tex", "version": "0.1.0"}


def read_message() -> Dict[str, Any]:
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    payload = sys.stdin.buffer.read(length)
    return json.loads(payload.decode("utf-8"))


def write_message(payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def tool_spec() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "arxiv2tex_interpret_prompt",
                "description": "Extract the likely paper query, section hint, and action hint from a natural-language request.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "arxiv2tex_handle_prompt",
                "description": "Run the default agent workflow for a free-form request: interpret, resolve, prepare, and optionally return a section-specific reading payload.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "arxiv2tex_pending_status",
                "description": "Inspect the latest pending candidate confirmation state, if any.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                },
            },
            {
                "name": "arxiv2tex_resolve",
                "description": "Resolve a natural-language paper request to an arXiv paper or candidate list.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "arxiv2tex_select_candidate",
                "description": "Resolve a prompt that returned multiple candidates and choose one by ordinal, arXiv id, or title fragment.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "selection": {"type": "string"},
                        "prepare": {"type": "boolean", "default": True},
                        "session_id": {"type": "string"},
                    },
                    "required": ["prompt", "selection"],
                },
            },
            {
                "name": "arxiv2tex_prepare",
                "description": "Download and cache an arXiv paper source package and build full.tex/snippet indexes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "arxiv2tex_extract_writing",
                "description": "Extract writing-oriented examples for a target such as abstract, introduction, method, experiment, or conclusion.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cache_key": {"type": "string"},
                        "target": {"type": "string"},
                        "top_k": {"type": "integer", "default": 3},
                        "view": {"type": "string", "default": "reader"},
                    },
                    "required": ["cache_key", "target"],
                },
            },
            {
                "name": "arxiv2tex_overview",
                "description": "Read cached metadata, manifest, and section tree for a paper.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"cache_key": {"type": "string"}},
                    "required": ["cache_key"],
                },
            },
            {
                "name": "arxiv2tex_search",
                "description": "Search the local snippet index for a cached paper.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cache_key": {"type": "string"},
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                        "view": {"type": "string", "default": "reader"},
                    },
                    "required": ["cache_key", "query"],
                },
            },
            {
                "name": "arxiv2tex_read_section",
                "description": "Read one cached section by fuzzy section name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cache_key": {"type": "string"},
                        "section_ref": {"type": "string"},
                        "view": {"type": "string", "default": "reader"},
                    },
                    "required": ["cache_key", "section_ref"],
                },
            },
            {
                "name": "arxiv2tex_read_fulltex",
                "description": "Read a slice of cached full.tex.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cache_key": {"type": "string"},
                        "offset": {"type": "integer", "default": 0},
                        "limit": {"type": "integer", "default": 4000},
                        "view": {"type": "string", "default": "reader"},
                    },
                    "required": ["cache_key"],
                },
            },
        ]
    }


def handle_request(service: PaperService, request: Dict[str, Any]) -> Dict[str, Any]:
    method = request.get("method")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }

    if method == "notifications/initialized":
        return {}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": tool_spec()}

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "arxiv2tex_interpret_prompt":
            result = service.interpret_prompt(arguments["prompt"])
        elif name == "arxiv2tex_handle_prompt":
            result = service.handle_prompt(arguments["prompt"], session_id=arguments.get("session_id"))
        elif name == "arxiv2tex_pending_status":
            result = service.pending_status(session_id=arguments.get("session_id"))
        elif name == "arxiv2tex_resolve":
            result = service.resolve(arguments["prompt"], session_id=arguments.get("session_id"))
        elif name == "arxiv2tex_select_candidate":
            result = service.select_candidate(arguments["prompt"], arguments["selection"], arguments.get("prepare", True), session_id=arguments.get("session_id"))
        elif name == "arxiv2tex_prepare":
            result = service.prepare(arguments["prompt"], session_id=arguments.get("session_id"))
        elif name == "arxiv2tex_extract_writing":
            result = service.extract_writing_examples(arguments["cache_key"], arguments["target"], arguments.get("top_k", 3), arguments.get("view", "reader"))
        elif name == "arxiv2tex_overview":
            result = service.overview(arguments["cache_key"])
        elif name == "arxiv2tex_search":
            result = service.search(arguments["cache_key"], arguments["query"], arguments.get("top_k", 5), arguments.get("view", "reader"))
        elif name == "arxiv2tex_read_section":
            result = service.read_section(arguments["cache_key"], arguments["section_ref"], arguments.get("view", "reader"))
        elif name == "arxiv2tex_read_fulltex":
            result = service.read_fulltex(arguments["cache_key"], arguments.get("offset", 0), arguments.get("limit", 4000), arguments.get("view", "reader"))
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unsupported method: {method}"},
    }


def main() -> None:
    service = PaperService(Path(".arxiv2tex-cache"))
    while True:
        try:
            request = read_message()
        except EOFError:
            return
        response = handle_request(service, request)
        if response:
            write_message(response)
