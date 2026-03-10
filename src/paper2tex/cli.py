import argparse
import json
import sys
from pathlib import Path

from .service import PaperService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper2tex")
    parser.add_argument("--cache-root", default=".paper-cache", help="Cache directory for downloaded papers.")
    parser.add_argument("--session-id", default=None, help="Optional session identifier for isolating pending confirmations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    interpret = subparsers.add_parser("interpret-prompt")
    interpret.add_argument("prompt")

    handle = subparsers.add_parser("handle-prompt")
    handle.add_argument("prompt")

    subparsers.add_parser("pending-status")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("prompt")

    select = subparsers.add_parser("select-candidate")
    select.add_argument("prompt")
    select.add_argument("selection")
    select.add_argument("--no-prepare", action="store_true")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("prompt")

    overview = subparsers.add_parser("overview")
    overview.add_argument("cache_key")

    extract_writing = subparsers.add_parser("extract-writing")
    extract_writing.add_argument("cache_key")
    extract_writing.add_argument("target")
    extract_writing.add_argument("--top-k", type=int, default=3)
    extract_writing.add_argument("--view", default="reader")

    search = subparsers.add_parser("search")
    search.add_argument("cache_key")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--view", default="reader")

    read_section = subparsers.add_parser("read-section")
    read_section.add_argument("cache_key")
    read_section.add_argument("section_ref")
    read_section.add_argument("--view", default="reader")

    read_full = subparsers.add_parser("read-fulltex")
    read_full.add_argument("cache_key")
    read_full.add_argument("--offset", type=int, default=0)
    read_full.add_argument("--limit", type=int, default=4000)
    read_full.add_argument("--view", default="reader")

    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    service = PaperService(Path(args.cache_root))

    if args.command == "interpret-prompt":
        result = service.interpret_prompt(args.prompt)
    elif args.command == "handle-prompt":
        result = service.handle_prompt(args.prompt, session_id=args.session_id)
    elif args.command == "pending-status":
        result = service.pending_status(session_id=args.session_id)
    elif args.command == "resolve":
        result = service.resolve(args.prompt, session_id=args.session_id)
    elif args.command == "select-candidate":
        result = service.select_candidate(args.prompt, args.selection, prepare=not args.no_prepare, session_id=args.session_id)
    elif args.command == "prepare":
        result = service.prepare(args.prompt, session_id=args.session_id)
    elif args.command == "overview":
        result = service.overview(args.cache_key)
    elif args.command == "extract-writing":
        result = service.extract_writing_examples(args.cache_key, args.target, top_k=args.top_k, view=args.view)
    elif args.command == "search":
        result = service.search(args.cache_key, args.query, top_k=args.top_k, view=args.view)
    elif args.command == "read-section":
        result = service.read_section(args.cache_key, args.section_ref, view=args.view)
    elif args.command == "read-fulltex":
        result = service.read_fulltex(args.cache_key, offset=args.offset, limit=args.limit, view=args.view)
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
