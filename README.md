# arxiv2tex

`arxiv2tex` is an arXiv-first paper cache for coding agents such as Codex, Claude Code, and OpenCode.

It resolves natural-language requests for papers, searches arXiv, downloads source packages, expands multi-file LaTeX projects into a cached `full.tex`, and exposes low-context retrieval tools through a CLI and a minimal MCP server.

## Features

- Extract a likely paper query from a natural-language prompt
- Search arXiv by title-like phrases and rerank candidates locally
- Cache arXiv source packages on disk
- Detect the main `.tex` file and expand `\input` / `\include` into `full.tex`
- Build section and snippet indexes for low-context reading
- Serve the workflow through CLI commands and MCP tools

## Quick Start

Create a virtual environment and install the package:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Resolve a paper from a prompt:

```powershell
arxiv2tex resolve "请你阅读这篇论文《attention is all you need》"
```

Inspect how a free-form prompt is interpreted:

```powershell
arxiv2tex interpret-prompt "帮我参考 attention is all you need 的实验部分写法"
```

Run the default end-to-end workflow for an agent-facing prompt:

```powershell
arxiv2tex handle-prompt "帮我参考 attention is all you need 的实验部分写法"
```

If a previous request returned multiple candidates, `handle-prompt` can consume a short follow-up confirmation such as `就这篇`, `第一个`, `就第一个吧`, or an arXiv id:

```powershell
arxiv2tex resolve "帮我看 attention all you need"
arxiv2tex handle-prompt "就这篇"
```

To isolate multiple parallel conversations, pass a `session_id`:

```powershell
arxiv2tex --session-id thread-a resolve "帮我看 attention all you need"
arxiv2tex --session-id thread-a handle-prompt "就这篇"
arxiv2tex --session-id thread-b pending-status
```

Prepare and cache the paper:

```powershell
arxiv2tex prepare "请你阅读这篇论文《attention is all you need》"
```

Read a section using the default `reader` view:

```powershell
arxiv2tex read-section 1706.03762v7 实验
```

Confirm one paper from an ambiguous candidate list:

```powershell
arxiv2tex select-candidate "帮我看 attention all you need" 第一个 --no-prepare
```

Inspect the latest pending confirmation state:

```powershell
arxiv2tex pending-status
```

Pending confirmations expire automatically after 30 minutes by default, so stale candidate lists do not linger forever.

Read from a specific view:

```powershell
arxiv2tex read-fulltex 1706.03762v7 --view clean --limit 400
```

Extract writing-oriented examples for a section such as abstract, related work, method, or experiments:

```powershell
arxiv2tex extract-writing 1706.03762v7 实验 --top-k 2
```

Run the MCP server over stdio:

```powershell
arxiv2tex-mcp
```

The default cache location is `.arxiv2tex-cache` in the current working directory.

Cached view files:

- `full.tex`: expanded source with comments preserved
- `clean.tex`: expanded source with comments removed
- `reader.tex`: comment-stripped source with appendix removed for lower-context reading

`extract-writing` returns:

- matched sections
- top snippets
- starter sentences
- simple style signals such as citation or figure-reference density
- section-specific guidance for agent-assisted writing
