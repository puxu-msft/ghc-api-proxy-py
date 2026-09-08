# 2026-08-21 `history/decisions.md` §6 原始上下文

> **来源与保真性**：逐字复制自 `.dev/docs/history/decisions.md` 的「六、实施完成（2026-08-21）」一节，2026-09-08 为承接其中尚未裁决的 §6.1、§6.2 而迁入本主题。原来源主题计划退役；本副本保留产生待裁决项时的实施背景，不能被读作当前状态或永久裁决。

## 六、实施完成（2026-08-21）

两个增量已合入 main：`7d6e26c`（出站字节级保真）、`9c7e971`（逐帧沉默时长）。

**验证**：1561 passed / 1 skipped；`ruff check src tests` 干净；`pyright` 29 个 error 全在未改动文件（`stream_cap.py` 一族 21 个、`cli.py` 8 个），改动的 11 个文件零 error。四次变异全部打红并已还原，其中主会话独立抽查了「字段存在但没人赋值」那一次——端到端测试红在 `a stream that arrived in one piece cannot have a gap in it`。

**「字典不能替代字节」已一手实测坐实**（主会话独立复跑）：同一 payload，httpx 送裸 UTF-8 `\xc3\xbc\xe4\xb8\xad`，而捕获文件用的 stdlib `json.dumps` 写转义形式 `ü中` 且分隔符不同；`orjson` 对超 64 位整数直接 `TypeError`。三者互不相等，所以重新序列化 `payload` 恢复不出线上字节。

### 实施中新产生的两项待裁决

| # | 事项 | 现状 | 我的建议 |
|---|---|---|---|
| 6.1 | 字节保真是否扩到 5xx / 超时 / 流截断 | **只做了 4xx 非限流** | 暂不扩。`KEEP_NEWEST=50` 是按份数封顶，扩大结局集会**用说明不了任何事的失败驱逐唯一值得读的那份**；且超时类 SDK 异常没有 `.response`，需另一条取值路径。若确需，正解是分目录（`rejected/` 与 `failed/` 各自独立份数上限），而不是扩大现有触发集——那是新增机制，值得单独一次裁决 |
| 6.2 | `upstream_max_gap_s` 是否上终端完成行 | **只进记录，不上行** | 暂不上。同性质的 `first_upstream_byte_s` 一直就只在记录里；卡住的一轮在行上已表现为被颜色升级的大 `duration_s`；上行需配阈值与配色，而 `stream_idle` 默认 0 使阈值无依据 |

两项都按 `no-silently-cut-but-defer` 记录，未静默砍掉。

