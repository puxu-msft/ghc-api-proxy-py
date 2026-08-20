# TUI：请求日志与实时 footer

终端里的两样东西：**请求日志按原生终端滚动**，**其下方一行实时 footer** 显示当前在飞请求。

## 本目录

| 文件 | 性质 | 读它的时机 |
|---|---|---|
| `spec.md` | **规范**，活的 | 想知道「现在的行为是什么」。可观察行为以它为准，本目录任何其它描述与它冲突时它赢。 |
| `deferred.md` | **未决项**，活的 | 想知道「什么还没做、为什么」。 |
| `archive-footer/` | 历史 | 底部面板：机制选型、终端能力探测、宽度纪律、并发安全、生命周期可观测 |
| `archive-request-log/` | 历史 | 每请求一行：字段构成、着色、用词、数据来源的收口 |
| `archive-truncated-stream/` | 历史 | 一行什么都没说时它在说什么：缺席不可读、三种结局的区分、`[GONE]` 档的由来 |
| `archive-token-accounting/` | 历史 | 词元用量换算：Responses 与 Anthropic 两套语义的差异及其后果 |
| `archive-count-tokens-line/` | 历史 | 计数请求那一行：端点与计数提供方各答一半、上游腿的窄含义、以及「修好一层会在上一层重演」 |

## 档案怎么读

每个 `archive-*/` 下：

- `README.md` —— **重写过的**知识文档，是入口。按「做了什么、为什么这样定、踩了什么坑」组织，不是过程流水。每份都有一节专写**已经否定的方案与否定的理由**，那是最难重建、也最容易被下一个人重新踩一遍的部分。
- `reports/` —— 当时的评审报告原件，逐字保留。重写文档承载不了其中的复现步骤、行号与探针输出，而那些有取证价值。**它们是快照，其中的路径与行号可能已经过时。**

想知道「现在是什么」读 `spec.md`；想知道「为什么是这样、别再试哪条路」读档案。

## 相关位置

- 实验脚本（三个机制对照 driver + 六个进程探针）在 `.dev/exp/tui-footer/`。
- 实现代码在 `src/app/observability/`（`footer.py` / `terminal.py` / `request_log.py` / `tui.py` / `active_requests.py`）与 `src/app/server/pipeline_app.py`。
- 整屏抓图测试在 `tests/tui/`，**不进默认扫描**，改动 `src/app/observability/tui.py` 时或手动 `uv run pytest tests/tui` 时跑。
