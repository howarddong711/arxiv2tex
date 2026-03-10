# arxiv2tex Workflow

When the user asks to read or imitate an arXiv paper, use the `arxiv2tex` MCP tools instead of browsing raw PDFs.

Preferred workflow:

1. Call `arxiv2tex_handle_prompt` with the user's original request.
2. If the result status is `confirm`, show the candidate list and wait for the user's confirmation.
3. For a short follow-up like `就这篇`, `第一个`, or an arXiv id, call `arxiv2tex_handle_prompt` again with the same `session_id`.
4. Once the paper is ready, prefer `section_result`, `writing_examples`, `arxiv2tex_read_section`, and `arxiv2tex_search` over reading full TeX.
5. Only call `arxiv2tex_read_fulltex` when the user explicitly asks for the full source or when section/snippet retrieval is insufficient.

Usage rules:

- Reuse a stable `session_id` inside the same chat so pending confirmations work correctly.
- Prefer the `reader` view unless the user explicitly asks for comments or the untouched expanded source.
- For writing help, prefer `arxiv2tex_extract_writing` with targets like `摘要`, `相关工作`, `方法`, `实验`, or `结论`.
- If the tool reports `not_found`, ask the user for a more specific title or an arXiv link.
