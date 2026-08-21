# 项目开发指令

> 本文件由用户控制，请勿直接修改。如果你要添加或更新项目级指令，写入 `.claude/rules/` 目录。

本项目主要由你（LLM）和你的同伴们共同开发。

用户会编写、追认“用户控制的文档”（位于 `docs/.human-controlled/`）。你可以将你提供的候选材料写入 `.dev/human-controlled-docs-candidates/` 目录，供用户参考。用户会不定期摘取。

你和你的同伴共同维护开发文档协作。最新的开发文档位于 `.dev/docs/` 目录下。曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移。早期同伴对旧项目 copilot-api-js 的学习笔记、重写想法位于 `.dev/docs/archived-2604-rewrite/`，仅供参考。

用户偶尔动手直接修改主树的内容，你和你的同伴也可能在任务规模不大时直接共享主树开发。

## 开发验证

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

## 可参考项目

本项目前身

- [copilot-api-js](/home/xp/src/copilot-api-js/) - JS

官方实现

- [vscode-copilot](/home/xp/src/refs/vscode-copilot-chat/)

外部参考项目

- [agent-maestro](/home/xp/src/refs/agent-maestro/)
- [awsl-maxx](/home/xp/src/refs/awsl-maxx/)
- [caozhiyuan/copilot-api](/home/xp/src/refs/caozhiyuan-copilot-api/)
- [CLIProxyAPIPlus](/home/xp/src/refs/CLIProxyAPIPlus/)
- [hooyao/copilot-bridge](/home/xp/src/refs/hooyao-copilot-bridge/) -- C#
- [sxwxs/ghc-api-py](/home/xp/src/refs/ghc-api-py/)
