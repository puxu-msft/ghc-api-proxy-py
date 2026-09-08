# MCP 契约一节 + `027698f` 评审的处置

**评审报告**：`260822-review-mcp-contract-and-deadline-order.md`（异源评审，gpt-opus）。**结论**：0 blocker、2 major、5 minor、10 条核对无误，`needs-fix`。
**处置日期**：2026-08-22。**处置提交**：主仓 `25432d4`（注释）、`.dev` `4642eb4`（文档）。

评审自己跑了 3 个探针与 2 轮受控变异，还原后 sha256 逐字复核，仓库未被它改动。它的变异手法值得记一笔：**不用 `git checkout --` 还原**（共享树里有同伴与主会话的未提交改动），而是 `cp` 冻结基线 + `diff -u` 导出补丁 + `git apply --reverse`，还原写在 `trap ... EXIT` 里；并且**在测试会读到的那一层验证变异确已装载**，而不是只看 diff。

## 全部采纳并已改

| 发现 | 分级 | 处置 |
|---|---|---|
| **F9** README 契约一节给了 `num_messages` 的来源，没给**判读规则**；而 `decisions.md` 四.3 正是仍打开的待对齐项 | major | 补进那一节。另一个仓最自然的写法是「没增长就中止」，而并行子智能体与主会话共享同一个 MCP server 进程、调用交错，那样写会把 B 会话的正常调用误判成无进展 |
| **F11** 工作树里 `config.example.yaml` 把 `max_output_tokens` 写进 `hand_over_stop_reasons`，该值结构上永不匹配 | major | **不动手改**（`docs/.human-controlled/` 归用户），已端给用户并加强了候选材料。见下一节 |
| **F4** `category` 错误取值写成四者，`internal` 今天不可达 | minor | 收窄为三者，并单列一条说明它为什么在表里、为什么接收端仍应兜住 |
| **F7** 引用行号指向语句首行、路径省略前缀 | minor | 改成 `513-515` 与全路径。这一节的读者手上可能没有这个仓 |
| **F10** 未给工具全名默认值 | minor | 补上，并写明三段命名各自载重、错一段会**静默失效** |
| **F14** 代码注释「The attempt deadline just below」指向一个不存在的分支 | minor | 改成「它在这里没有自己的分支，作为普通 tear 落到下面」，把「相反的次序」锚在 `terminal.seen` 这个真实位置上 |
| **F15** `deferred.md` 第 11 条收尾句「这是本条唯一还要动手的部分」已过期 | minor | **追加**一句「已完成，见 `027698f`」，**不改写原句**——那会篡改这份原始分析记录的时间点 |
| **F16** 「未挂载的 legacy hooks 链」措辞可被证伪 | 措辞 | 收紧为「这条链路**不被服务进程构建**」。`ObserverEvent.ERROR` 带 `response_body` 的分发确实存在（`pipeline/executor.py:477-487`），说成「没接线」会让下一个核对的人以为整句错了 |

## 端给用户裁决（不代判）

1. **`config.example.yaml:339` 的 `max_output_tokens`**。评审的证伪对照把它从「无害的冗余」抬到了值得处置：不只是默认配置下不会出现，而是**配成它也不会生效**（归一化在门之前）。危害不在今天，在于这是一份**用户亲笔的权威样例**在暗示一个有意义的取值——下一个读者据此把 `max_tokens` 删掉，此后所有撞上限的回合既不交接、又保留半截块、且不打任何告警。候选材料：`../../human-controlled-docs-candidates/upstream-retry-and-continuation-supplements.md` 第十节。
2. **`client-side-block-delivery.md:16` 的配置节名写错**（评审列为范围外观察，本会话独立复核确认）：写的是 `upstream_request_retry.upstream_request_deadline`，实际在 `upstream_request_timeouts` 节下。**用户自己的 `config.example.yaml` 是对的**（第 313 行在 `upstream_request_retry:` 之前）。建议只改文档那一处，不要反过来改代码——三个上游守卫同节才读得出互补关系。候选材料同上，第十一节。

## 未采纳

无。

## 这一轮值得记的一条

评审对 F12 没有停在「变异打红了」，而是问了**打红的是哪一层**：先证明改夹具确实把「次序」那一层鉴别力从两条旧测试上拿走了（在 `/tmp` 复刻 pre-commit 版本对照，未变异时六条全绿以证明复刻忠实），再证明它们**名义上的**属性仍被咬住（换一个把整支禁掉的变异，六条全红），最后还补了一个**非平凡性对照**——held-back 那条断言「缓冲块被丢弃」，如果新夹具下那个块压根没被组装出来，断言就成了恒真；实测同一截断夹具不触发时限时块确实存在。

这正是本项目 memory 里那条「变异结果证明了什么、没证明什么」的具体做法：**打红只证明它打到的那一层**。
