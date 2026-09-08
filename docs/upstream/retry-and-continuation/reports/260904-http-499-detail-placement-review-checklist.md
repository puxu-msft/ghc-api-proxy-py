# HTTP 499 detail placement 评审核查清单

## 用户最终裁决

用户表示：“接受修订，但你加入了详细解释，而这些解释不应该放入该文档（但解释本身是对的）。”用户随后亲自把 `docs/.human-controlled/upstream-retry-and-continuation.md` 收敛为 `499 Client Closed Request` 列表项，并以 2026-09-04 `update docs to make HTTP 499 retryable` 提交。

## 固定输入

- 目标 Spec：`fa740133a25163de9647632ade08c0fc8694f0eef33cb2771a4dfdfe3394006d`
- implementation notes：`ad18600fd3b928b874ff8975feaa6ab886e884c831226467a7dbf04cc99c6ae4`
- candidate disposition record：`e556fac8ffa13ada2138331d1117fe2d71adae67e011f299637b62c02c2187c5`
- status：`5d5c2e2066a527abb1d4bcffe7e73359718054a3be419afbae88b737641d0618`
- review disposition：`a2126bda3a8741e37e043a9def346bdfa631cd041cad4cadc106ea43e61c6664`

## 必须逐条核验

- C1：目标 Spec 只保留用户接受的精简 requirement，没有残留 `serverError`、预算、deadline/draining、error envelope、capture、observability、证据或未采用方案的详细解释。
- C2：`http-499-retry.md` 完整保全此前已评审为正确的详细解释，明确它是 implementation/specification understanding 而非 requirement authority；没有把派生策略冒充用户裁决，也没有与当前代码、专项测试或精简 Spec 冲突。
- C3：candidate 已从“待并入条款”改为 `adopted-in-concise-form` 处置记录，忠实记录用户三步裁决、采纳到 requirement 的唯一内容、迁出而非删除的解释、dotdev publication scope 与权威链接。
- C4：status 已记录用户审核完成和 requirement commit，Spec finding 关闭；它不再要求用户重复审核。storage finding 仍因 `origin/dotdev` 未 push 保持 open，没有被 placement 调整误关。
- C5：review disposition 对 closeout Spec major 的事实、用户逐字 ruling、placement action、fix/outcome、next actor 与 open/fixed 计数均闭合；只剩 dotdev storage major open。
- C6：详细说明在 implementation notes 与 status 中的 contextual restatement 有明确 authority/provenance，不产生两个可独立修改的 requirement source；candidate 是处置记录，历史 reports 保持 point-in-time 原文。
- C7：用户最终提交后的 transcription check 与 4 项专项测试证据足以支持“精简 requirement 与实现一致”，但不得外推为重新执行全量回归或真实 upstream canary。

只评上述 placement 与状态闭包，不重新评审 HTTP 499 生产功能或 dotdev branch shape。最多 6 条有具体失败场景的 finding；纯措辞 nit 不报。报告由主会话持久化，不写隔离 worktree临时文件。
