# arxiv2tex Workflow

When the user asks to read or imitate an arXiv paper, use the `arxiv2tex` MCP tools instead of browsing raw PDFs.

Preferred workflow (agent parses user prompt first):

1. Parse the user's message with your own reasoning and extract structured fields: `paper_query`, optional `section_hint`, optional `action_hint`.
2. Call `arxiv2tex_handle_intent` with those structured fields and include `raw_prompt` for traceability.
   - If you only need cache preparation, call `arxiv2tex_prepare_intent`.
3. If the result status is `confirm`, show candidates and wait for the user's confirmation.
4. For short follow-ups like `就这篇`, `第一个`, or an arXiv id, call `arxiv2tex_handle_prompt` again with the same `session_id` to consume pending confirmation.
5. Once the paper is ready, prefer `section_result`, `writing_examples`, `arxiv2tex_read_section`, and `arxiv2tex_search` over reading full TeX.
6. Only call `arxiv2tex_read_fulltex` when the user explicitly asks for the full source or when section/snippet retrieval is insufficient.

Fallback workflow:

- If you cannot confidently extract `paper_query`, call `arxiv2tex_handle_prompt` with the raw user text and let arxiv2tex local parsing handle it.

Usage rules:

- Reuse a stable `session_id` inside the same chat so pending confirmations work correctly.
- Prefer `arxiv2tex_handle_intent` when your agent already has structured fields; this reduces parsing ambiguity and keeps behavior deterministic.
- Prefer the `reader` view unless the user explicitly asks for comments or the untouched expanded source.
- For writing help, prefer `arxiv2tex_extract_writing` with targets like `摘要`, `相关工作`, `方法`, `实验`, or `结论`.
- If the tool reports `not_found`, ask the user for a more specific title or an arXiv link.
