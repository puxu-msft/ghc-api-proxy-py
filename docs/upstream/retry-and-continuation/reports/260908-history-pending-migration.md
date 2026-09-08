# `history` 待裁决事项迁入报告

- 日期：2026-09-08
- 范围：`.dev/docs/upstream/retry-and-continuation/`，仅文档迁入
- 目标：承接计划退役的 `.dev/docs/history/decisions.md` §6.1 与 §6.2 中仍未裁决／暂缓的事项

## 改动

1. 在活文档 [`../deferred.md`](../deferred.md) 的“已知未闭合”区新增：
   - §24：字节保真是否扩到 5xx、超时与流截断；
   - §25：`upstream_max_gap_s` 是否显示在终端完成行。
2. 两项均明确标记为“需用户裁决”。保留“目前暂不扩／暂不上”作为暂缓建议，而非永久“不做”或既有用户裁决。
3. 新建 [`../history/`](../history/)；其索引说明历史材料的边界，并以 [`../history/decisions-20260821.md`](../history/decisions-20260821.md) 逐字保留原 `decisions.md` §6 的产生背景、两项原文、理由、条件与当时验证摘要。活文档改链到该副本，避免未来退役 `history` 主题后失去来源。

## 来源与事实复核

原始来源是 `.dev/docs/history/decisions.md` §6“实施完成（2026-08-21）”：

- §6.1 说明现有字节保真仅覆盖 4xx 非限流；`KEEP_NEWEST=50` 是按份数封顶；超时异常缺少 `.response`；若扩展，建议 `rejected/`／`failed/` 分目录、独立上限，作为新增机制另行裁决。
- §6.2 说明 `upstream_max_gap_s` 只进记录、不上行；若显示须确定阈值和配色；`stream_idle` 默认 `0`，没有现成阈值依据。

2026-09-08 对当前 `src/` 的符号检索和代码直读确认这些事实仍成立：

- `src/app/observability/rejection_capture.py`：`capture_rejection()` 仅接收 `UpstreamRejected`，`KEEP_NEWEST = 50`，并保存 `error.sent` 的实际 bytes。
- `src/app/server/routes/inference.py`：使用 `response.request.content` 做请求 bytes 观察，并计算 `first_upstream_byte_s`／`upstream_max_gap_s`。
- `src/app/observability/request_completion.py`：把 `upstream_max_gap_s` 投影至 finalized record。
- `src/app/observability/request_log.py`：字段注释明确其不渲染到 console line，并保留与 `first_upstream_byte_s`、`duration_s`、`stream_idle` 的理由关系。

## 未采纳／未做

- 未修改 `.dev/docs/history/`：迁入只复制必要原始上下文，不删除、移动或重写来源。
- 未修改 `status.md`：这两项是尚待裁决的范围与显示取舍，依本主题宪章应由 `deferred.md` 承载；没有把暂缓建议伪装成当前路线的已定状态。
- 未扩展 capture 行为、保留上限、目录布局或 console rendering；这些均超出文档迁入范围，且仍待用户裁决。
- 未修改源码、测试、配置、其他主题或 `.dev/.dev/`；未执行 git add、commit、push 或删除。

## 验证

1. 已先读取 `.dev/docs/dotdev-repository-repair/README.md` 的迁移约束。
2. 已读取原 `.dev/docs/history/decisions.md` §6 和目标主题现有 `README.md`、`deferred.md`、`status.md`，并选择该主题规定的 living deferred 载体。
3. 已检索并直读上述当前 `src/` 符号，结果与两项暂缓的事实前提一致。
4. 编辑后已确认四个迁入文件存在，内容检索确认 `deferred.md` 的 §24／§25 均含“需用户裁决”“当前范围不是永久否决”“暂缓建议与理由”以及本主题 `history/` 的来源链接；历史副本保留两条原表项和 `no-silently-cut-but-defer` 原文。
5. `git -C .dev diff --check -- docs/upstream/retry-and-continuation` 通过（无空白错误）。该 `.dev` checkout 将整个 `docs/upstream/retry-and-continuation/` 报为未跟踪目录，故 git 状态不能按本轮新增文件细分；本轮写操作仅针对本报告列出的目标目录路径。

## MSR-01 补充迁入（2026-09-08）

merged-state review 的 MSR-01 发现：原 `history/decisions.md` 第五节“重定范围”仍有一项未闭合的需求确认，未包含在本报告原先承接的 §6.1／§6.2 中。

1. 在 [`../deferred.md`](../deferred.md) 新增 §26“原‘完整 HTTP 支持’前提消失后，是否仍需查询面”，明确标为**需重新用户确认**。
2. §26 保留了前提与范围：2026-08-20 的“完整 HTTP 支持”所指是当时计划的完整取证库及其 HTTP 查询面；L1 和该库在 2026-08-21 重定范围后不再建设，故原裁决的对象消失。该事实不等于用户撤回 HTTP 支持，也不等于已裁决永不提供查询。
3. 若重新确认需要查询，§26 将对象限定为现有 `requests-*.jsonl` 与 `rejected/*`；没有恢复 L1、`entries/*`、会话／归档、export、replay、WS 或 pin/unpin 的范围。
4. 为使来源主题退役后仍可核对，新增 [`../history/decisions-20260821-query-surface.md`](../history/decisions-20260821-query-surface.md)，逐字保留第五节的相关重定范围表格与 HTTP 查询面段落；`history/README.md` 为其登记边界和 current carrier。

来源：已计划退役的 history 主题之 `decisions.md` 第五节“重定范围（2026-08-21）”，尤其是“HTTP 查询面怎么办”段落（本轮读取时位于第 98 行附近）。本轮未修改该来源文件、§6.1／§6.2、源码、配置或其他主题；未移动、删除、git add、commit 或 push。

验证：§26、history 索引与本报告的 3 个新增相对链接均已解析到存在的文件；`git -C .dev diff --check -- docs/upstream/retry-and-continuation` 通过。
