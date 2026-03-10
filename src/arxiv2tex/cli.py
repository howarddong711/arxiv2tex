import argparse
import json
import sys
from pathlib import Path

from .service import PaperService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arxiv2tex")
    parser.add_argument(
        "--cache-root",
        default=".arxiv2tex-cache",
        help="Cache directory for downloaded papers.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier for isolating pending confirmations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    interpret = subparsers.add_parser("interpret-prompt")
    interpret.add_argument("prompt")

    interpret_intent = subparsers.add_parser("interpret-intent")
    interpret_intent.add_argument("paper_query")
    interpret_intent.add_argument("--section-hint", default=None)
    interpret_intent.add_argument("--action-hint", default=None)
    interpret_intent.add_argument("--raw-prompt", default=None)

    handle = subparsers.add_parser("handle-prompt")
    handle.add_argument("prompt")

    handle_intent = subparsers.add_parser("handle-intent")
    handle_intent.add_argument("paper_query")
    handle_intent.add_argument("--section-hint", default=None)
    handle_intent.add_argument("--action-hint", default=None)
    handle_intent.add_argument("--raw-prompt", default=None)

    subparsers.add_parser("pending-status")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("prompt")

    resolve_intent = subparsers.add_parser("resolve-intent")
    resolve_intent.add_argument("paper_query")
    resolve_intent.add_argument("--section-hint", default=None)
    resolve_intent.add_argument("--action-hint", default=None)
    resolve_intent.add_argument("--raw-prompt", default=None)

    select = subparsers.add_parser("select-candidate")
    select.add_argument("prompt")
    select.add_argument("selection")
    select.add_argument("--no-prepare", action="store_true")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("prompt")

    prepare_intent = subparsers.add_parser("prepare-intent")
    prepare_intent.add_argument("paper_query")
    prepare_intent.add_argument("--section-hint", default=None)
    prepare_intent.add_argument("--action-hint", default=None)
    prepare_intent.add_argument("--raw-prompt", default=None)

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
    elif args.command == "interpret-intent":
        result = service.interpret_intent(
            paper_query=args.paper_query,
            section_hint=args.section_hint,
            action_hint=args.action_hint,
            raw_prompt=args.raw_prompt,
        )
    elif args.command == "handle-prompt":
        result = service.handle_prompt(args.prompt, session_id=args.session_id)
    elif args.command == "handle-intent":
        result = service.handle_intent(
            paper_query=args.paper_query,
            section_hint=args.section_hint,
            action_hint=args.action_hint,
            raw_prompt=args.raw_prompt,
            session_id=args.session_id,
        )
    elif args.command == "pending-status":
        result = service.pending_status(session_id=args.session_id)
    elif args.command == "resolve":
        result = service.resolve(args.prompt, session_id=args.session_id)
    elif args.command == "resolve-intent":
        result = service.resolve_intent(
            paper_query=args.paper_query,
            section_hint=args.section_hint,
            action_hint=args.action_hint,
            raw_prompt=args.raw_prompt,
            session_id=args.session_id,
        )
    elif args.command == "select-candidate":
        result = service.select_candidate(
            args.prompt,
            args.selection,
            prepare=not args.no_prepare,
            session_id=args.session_id,
        )
    elif args.command == "prepare":
        result = service.prepare(args.prompt, session_id=args.session_id)
    elif args.command == "prepare-intent":
        result = service.prepare_intent(
            paper_query=args.paper_query,
            section_hint=args.section_hint,
            action_hint=args.action_hint,
            raw_prompt=args.raw_prompt,
            session_id=args.session_id,
        )
    elif args.command == "overview":
        result = service.overview(args.cache_key)
    elif args.command == "extract-writing":
        result = service.extract_writing_examples(
            args.cache_key, args.target, top_k=args.top_k, view=args.view
        )
    elif args.command == "search":
        result = service.search(
            args.cache_key, args.query, top_k=args.top_k, view=args.view
        )
    elif args.command == "read-section":
        result = service.read_section(args.cache_key, args.section_ref, view=args.view)
    elif args.command == "read-fulltex":
        result = service.read_fulltex(
            args.cache_key, offset=args.offset, limit=args.limit, view=args.view
        )
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
