# arxiv2tex Agent Install Guide

Goal: install arxiv2tex and connect it as an MCP server in the current coding-agent client.

## Steps

1. Ensure this repository is available locally.
   - If missing: clone `https://github.com/howarddong711/arxiv2tex`.
   - Then run all commands from the repository root.

2. Detect one usable Python interpreter and keep using the same one.

3. Install arxiv2tex in editable mode:
   - `<python> -m pip install -e .[dev]`

4. Verify MCP module startup:
   - `<python> -m arxiv2tex.mcp --help`

5. Register MCP for the current client with this stdio command:
   - `<python> -m arxiv2tex.mcp --cache-root .arxiv2tex-cache`

6. Confirm MCP is connected in the current client.
   - Codex: `codex mcp list` / `/mcp`
   - OpenCode: `opencode mcp list`
   - Other MCP clients: use their MCP server list/status command

7. Run one smoke test prompt through arxiv2tex:
   - `介绍一下这个论文 COLD: A Benchmark for Chinese Offensive Language Detection`

8. Output a final report:
   - interpreter path
   - commands run
   - MCP connection status
   - smoke test result
