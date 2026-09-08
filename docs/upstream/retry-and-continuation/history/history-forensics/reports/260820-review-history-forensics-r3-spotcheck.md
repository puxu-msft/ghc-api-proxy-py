# r3 定点抽查报告——五处 + 整体一致性扫描

只读核查，未修改任何文件。对象：`docs/agents/history-forensics/proposal.md`（r3）。

## 抽查 1：§1.3 的 L2 合同表述

对照 `src/app/pipeline/direct_driver/base.py`（`DirectDriver.run`/`_send`/`_handle_failure`）与 `src/app/server/pipeline_app.py`（`_dispatch`）：

- `_dispatch` 里 `trace.bytes_in = len(response.request.content)`（第 256 行）确实只在**最终** `handle_bounded` 返回的那次交换上取值，这是最终 attempt 唯一被读到的 httpx `Response`。这一点准确。
- 前序失败 attempt 确实拿不到 `response.request.content`：`DirectDriver.run` 里失败分支只做 `attempt.error = str(error)`（`base.py:138`），不产生完整 `httpx.Response`。「前序 attempt 的 outbound body 原文、发送阶段异常、上游错误响应体原文，在 `_dispatch` 这个位置看不到」——**这句话本身准确**。

需要补充的一点（非硬矛盾，供参考）：`RequestContext.attempts`（`src/app/pipeline/request.py` 的 `Attempt` dataclass）已经给每次 attempt 记了 `index`、`payload`（字典形式的请求体，发送前赋值）、`status_code`、`error`（字符串）,而且这个列表通过同一个 `context` 对象在 `_dispatch` 里可读（`handled.context.attempts`）。也就是说"前序 attempt 无采集点"若理解为"字面意义上一无所有"并不准确；更准确的表述是"现有采集点只到框架层 payload 字典/状态码/异常摘要这一级，取证要的是原始字节、完整 headers、上游错误体原文，这些确实都不在"。proposal 上下文（1.9 节列出的四项缺口）已经是在这个精度上说话，所以**核心判断没有错**，但 1.3 单独抽出来读容易让人以为完全没有任何 attempt 级记录——建议在 1.3 加一句"已有 `RequestContext.attempts` 提供框架层快照，但取证要的字节级/头级细节需另外扩展"，避免读者误判扩展面的大小。这是措辞精度问题，不是事实错误，不构成阻碍交付的理由。

## 抽查 2：§3.1 / §3.5 headers 分层

全文 grep `headers`/`allowlist`：

- §1.9（cassette 合同）：三项响应头 allowlist，明确是 `Interaction`（cassette）的字段。
- §3.1 表格：`UpstreamExchange.headers` 标注「完整，不裁剪」，footnote 明确「三项 allowlist 是 cassette 的产物合同，属于 3.6 的导出阶段」「与 3.5 的立场一致：本地库不裁剪，导出才裁剪」。
- §3.5：「取证库本身不脱敏……只有 `export-cassette` 那一步才走脱敏（按字段名递归 + 响应头 allowlist）」。
- §7 处置表也如实记录了这处修正。

三处口径完全一致，未发现残留矛盾说法。**此项通过。**

## 抽查 3：§6.1 首次持久化容量边界

- 分片表第 1 行：「L1 落盘 + **容量上限同片交付** + `debug history list --json`」。
- 正文补注：「容量上限被移到分片 1，与首次持久化同片……r2 把双维度 reaper 排在最后一片，意味着分片 1 到 6 之间存在一个『默认开始写盘、没有任何上限』的集成态。这是不可接受的中间状态。」

分片表与正文对得上，没有留下「先写盘、后加上限」的中间态描述。**此项通过。**（附带观察，不算问题：L2/L3 表要到分片 2/4 才出现，分片 1 的容量上限显然只约束当时存在的 L1 行；L2/L3 落地后是否需要在各自分片重申"级联删除已覆盖"这一点，文档未展开，但没有与已写内容矛盾，只是留白。)

## 抽查 4：§4 分叉 E 的 file sink 合同

对照 `src/app/observability/tui.py`：

- `FooterTui.activate()` 第 139-140 行：`previous = list(root.handlers)` 后 `root.handlers = [handler]`——**确认是整体替换，不是追加**，与 proposal 描述完全一致。
- `footer_tui_or_none`（同文件 150-158 行）在 `caps.live` 为真时返回非 `None`；`pipeline_app.py` 的 `_lifespan`（第 489、495 行）在真终端下无条件调用 `tui.activate()` 进入该 context manager——**确认真终端下默认激活，无需额外开关**，与 proposal 描述一致。

§4 与 §6.1 分片 6 的描述互相一致（both 提到 `activate()` 改造、1.5 片、人眼验收、从分片 1 后移到分片 6）。**此项通过。**

## 抽查 5：§6.3 Spec 顺序边界

- 分片 0 内容：测试库改落 `tmp_path`（缺陷修复，不是新行为）+ 取证库独立文件名（此时尚无表结构，不产生新写入）+ `_serve` 异常退出补进幂等终结器（让已有 stdout 完成记录的既有承诺真正成立，不引入新磁盘目标）。
- 分片 1 起：L1 落盘，是第一次真正把新数据写进磁盘（新数据库文件的第一张表）。

「分片 0 不需要 Spec、分片 1 起需要」与分片表内容一致，没有自相矛盾。**此项通过。**

## 整体一致性扫描：发现一处硬矛盾（超出五项清单，但在扫描范围内）

**§6.2「并行会话约束」引用的分片编号是 r2 时期的旧编号，与 §6.1 定稿的新分片表冲突：**

> 2. **先做不冲突的分片**——分片 0（测试）与**分片 1（日志 sink）**几乎不碰这些文件，可以立刻开始。
> 我建议 1 + 2 组合：立刻开始分片 0 与 1，其余进 worktree。

但按 §6.1 定稿的分片表，分片 1 是「L1 落盘 + 容量上限 + `debug history list --json`」，日志 sink 已经明确从 r2 的分片 1 后移到**分片 6**（§6.1 正文与 §7 处置表 N1 行都写明了这次调动）。§6.2 这两句显然是 r2 重排前的旧措辞，定点修改时漏改。

更实质的问题是：即便把「分片 1」按新编号理解为 L1，这句话「几乎不碰这些文件」（指 `pipeline_app.py`/`request_log.py`/`assembler.py`）本身也站不住——分片 0 的「`_serve` 异常退出补进幂等终结器」直接改的就是 `pipeline_app.py` 的 `_serve`；分片 1 的 L1 落盘要从 `_log_completion`/`_StreamAccounting.finish`（同样在 `pipeline_app.py`）里调用新 writer。这两处恰恰是并行会话在改的文件的核心函数，不是"几乎不碰"。

结论：§6.2 给出的实施建议（"分片 0、1 可以立刻在主 worktree 做，不必等"）目前建立在过期编号 + 对文件接触面的错误判断之上，需要重写，否则会引导执行者把该进 worktree 的改动当成可以直接在共享文件上动手的改动——考虑到当前确实有并行会话在编辑 `pipeline_app.py`，这不是文风问题，是会导致误操作的事实错误。

其余分叉字母（A–H）与分片编号（0–7）交叉引用逐一核对：分叉 F 前置「需要 A1+B1」→ 落在分片 5，晚于 L1/L2/L3 所在的分片 1/2/4，成立；分叉 H 前置「需要 L2」→ 落在分片 3，晚于 L2 所在的分片 2，成立；分叉 D（REST/WS）正确地未出现在分片表中（对应 D3"本次只做 CLI"的裁决）；§7 处置表里的分叉/分片指向经逐条核对均与正文一致。除 §6.2 这一处外，未发现其他 r1/r2 残留表述与 r3 结论打架。

## 结论

五项定点抽查：4 项完全通过（2、3、4、5），1 项（§1.3）核心判断准确但措辞可以更精确（非阻碍项，建议顺手一并改掉）。

**整体一致性扫描发现一处真实硬矛盾：§6.2 的分片编号引用是 r2 遗留，与 §6.1 定稿的分片表对不上，且其"分片 0/1 不碰共享文件"的实操建议本身也与分片 0/1 的实际改动内容矛盾。**

**r3 尚不能直接进入执行**：§6.2 需要重写（更新编号，并重新判断哪些分片真的不碰 `pipeline_app.py`——按当前分片表看,分片 0/1/2/4 都会碰,能安全排除在共享文件之外的更可能是分片 3、5、6（部分）、7）。这是一处定位明确、修改量很小的编辑问题,不影响第四节各分叉的裁决内容本身,但会误导实施顺序,应在提交给用户裁决前先修好。
