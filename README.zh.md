# arxiv2tex

[English](README.md) | **中文**

`arxiv2tex` 是一个面向 Codex、Claude Code、OpenCode 等 coding agent 的 arXiv 优先论文缓存层。

它可以根据自然语言请求定位论文、检索 arXiv、下载 source package、展开多文件 LaTeX 项目并缓存为 `full.tex`，再通过 CLI 与 MCP 提供低上下文读取能力。

## 项目定位

`arxiv2tex` 是 agent 基础设施，不是另一个聊天模型。
它位于用户意图与 arXiv 论文源码检索之间：用户只需一句简单 prompt，上游 coding agent 负责理解意图，`arxiv2tex` 负责确定性执行论文解析、缓存、TeX 展开与低上下文阅读。
项目聚焦 arXiv-first、source-package-first、可复用缓存检索流程，服务于 LaTeX 写作与写法借鉴；它不是通用 PDF/OCR 工具，也不是传统文献管理器。

## 功能特性

- 从自然语言 prompt 中提取可能的论文查询
- 基于标题短语检索 arXiv，并在本地重排候选
- 将 arXiv 源码包缓存到本地
- 自动识别主 `.tex` 并展开 `\input` / `\include` 到 `full.tex`
- 构建 section/snippet 索引，支持低上下文读取
- 通过 CLI 与 MCP 工具暴露完整流程

## 快速开始

### Agent 一键部署（推荐）

把下面这一条 prompt 直接发给你的 coding agent（Codex / Claude Code / Cursor / Kiro / Gemini CLI / OpenCode / Antigravity）：

```text
请严格按这个安装指南完成 arxiv2tex 部署与 MCP 连接：
https://github.com/howarddong711/arxiv2tex/blob/main/docs/guide/agent-install.md

如果你的客户端更偏好抓取纯文本，可使用：
https://raw.githubusercontent.com/howarddong711/arxiv2tex/refs/heads/main/docs/guide/agent-install.md
```

这是推荐接入方式：用户一句话，agent 自动完成部署。

创建虚拟环境并安装：

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

从 prompt 解析论文：

```powershell
arxiv2tex resolve "请你阅读这篇论文《attention is all you need》"
```

查看自由文本 prompt 的解析结果：

```powershell
arxiv2tex interpret-prompt "帮我参考 attention is all you need 的实验部分写法"
```

运行默认端到端工作流：

```powershell
arxiv2tex handle-prompt "帮我参考 attention is all you need 的实验部分写法"
```

当你的 agent 已完成结构化解析时（推荐）：

```powershell
arxiv2tex handle-intent "Attention Is All You Need" --section-hint "related work" --action-hint imitate --raw-prompt "看看这篇论文 related work 怎么组织的"
```

在不经过自由文本解析的情况下解析/定位结构化意图：

```powershell
arxiv2tex interpret-intent "Attention Is All You Need" --section-hint "related work" --action-hint imitate
arxiv2tex resolve-intent "Attention Is All You Need" --section-hint "related work" --action-hint imitate
arxiv2tex prepare-intent "Attention Is All You Need" --section-hint "related work" --action-hint imitate
```

如果上一步返回候选确认，`handle-prompt` 可消费短确认语（如 `就这篇`、`第一个` 或 arXiv id）：

```powershell
arxiv2tex resolve "帮我看 attention all you need"
arxiv2tex handle-prompt "就这篇"
```

使用 `session_id` 隔离并行会话：

```powershell
arxiv2tex --session-id thread-a resolve "帮我看 attention all you need"
arxiv2tex --session-id thread-a handle-prompt "就这篇"
arxiv2tex --session-id thread-b pending-status
```

准备并缓存论文：

```powershell
arxiv2tex prepare "请你阅读这篇论文《attention is all you need》"
```

使用默认 `reader` 视图读取 section：

```powershell
arxiv2tex read-section 1706.03762v7 实验
```

从多候选中选择论文：

```powershell
arxiv2tex select-candidate "帮我看 attention all you need" 第一个 --no-prepare
```

查看最新待确认状态：

```powershell
arxiv2tex pending-status
```

待确认状态默认 30 分钟过期，避免陈旧候选长期残留。

对于缩写等短标题歧义场景（如 acronym），`resolve-intent` 仍可能返回 `confirm`，由 agent 与用户确认目标论文。

指定视图读取：

```powershell
arxiv2tex read-fulltex 1706.03762v7 --view clean --limit 400
```

提取写作示例（如摘要、相关工作、方法、实验）：

```powershell
arxiv2tex extract-writing 1706.03762v7 实验 --top-k 2
```

通过 stdio 启动 MCP server：

```powershell
arxiv2tex-mcp
```

启动 MCP server 时指定自定义缓存目录：

```powershell
arxiv2tex-mcp --cache-root .arxiv2tex-cache
```

默认缓存目录是当前工作目录下的 `.arxiv2tex-cache`。

缓存视图文件：

- `full.tex`: 展开后的完整源码，保留注释
- `clean.tex`: 展开后的源码，移除注释
- `reader.tex`: 移除注释并去除 appendix 的低上下文阅读视图

`extract-writing` 返回：

- 匹配到的 section
- top snippets
- 可复用起始句
- 引文密度、图表引用密度等简易风格信号
- 面向 agent 辅助写作的 section 级指导

## OpenCode

仓库内提供了项目级 [`opencode.json`](opencode.json)，会将 `arxiv2tex` 注册为本地 MCP server，并加载工作流说明 [`docs/opencode-arxiv2tex.md`](docs/opencode-arxiv2tex.md)。

先安装包：

```powershell
py -3.10 -m pip install -e .[dev]
```

然后在 OpenCode 打开该项目并确认 MCP 可见：

```powershell
opencode mcp list
```

如果你更偏好全局 OpenCode 配置，可将 `opencode.json` 中 `mcp.arxiv2tex` 配置块复制到用户配置文件中。

项目配置会以 `python.exe -m arxiv2tex.mcp` 方式启动服务，因此在 OpenCode 启动 MCP 前必须先完成 `pip install -e .[dev]`。
