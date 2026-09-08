---
checklist_id: function-call-grouping-closeout-review-checklist-260906
status: active
artifact: 260906-function-call-grouping-closeout.md
owner: coordinator
---

# Responses client-action grouping 收尾评审核查清单

## 必核声称

- F1：2026-09-06 `fix: coalesce adjacent response actions in logs` 只提交 `request_log.py`、对应 unit test 与既有 integration test，parent／subject／path／blob 链已核验，当前三个路径 clean。
- F2：用户复现通过真实 `ResponsesObserver → format_completion_line` 输出 `completed reason(enc:1) function_call(TaskCreate,Bash)`。
- F3：最新 targeted 为 85 passed；Ruff 全树 clean；Pyright 全树 0 errors；第二次完整 default suite 为 2854 passed、2 skipped、coverage 91.77%。第一次 full run 的一次 streaming-resilience failure 与随后单测／完整重跑的关系被如实记录。
- F4：Job-private archive 中只禁用 named-action merge arm，三个指定 grouping tests精确为 `3 failed`、无 `ERROR`，主树 source hash未变；该证据只证明 action merge oracle 的分辨力。
- F5：Code review 首轮唯一 major 已由 nonempty `NOT_REQUIRED` green-completed 测试关闭；最终 report tail 为 pass、0 blocker／major。
- F6：`spec.md`、`design.md`、terminal plan、tracking 和 disposition 描述同一终态；Spec仍是行为权威；Chat 条款未被删除或覆盖；disposition 无 open／disputed／response_required。
- F7：Main 分支相对 origin ahead 2，但本轮只归属最新 grouping commit；未 push、未创建 PR、未执行 cutover。其它 untracked paths 与 worktrees 均未触碰。
- F8：Dotdev 未提交限制、并行 Chat 会话与不归档理由写实；报告没有把 `.dev` 工作副本说成已持久化到 Git。
- F9：Scratch manifest 的 fd／os.walk 集合相等且 865 项来自写 marker 后的实际枚举；没有删除行为，也没有把未评审 manifest 写成删除许可。
- F10：报告明确限定未运行真实 upstream 与 `tests/tui/`，没有把 mock／default suite 外推。

## 评审要求

1. 先加载 `my-agents:as-reviewer`，再读本清单与 closeout report。
2. 逐项读取 `spec.md`、`design.md`、terminal plan、tracking、disposition、最终 code review report和提交对象；不要只信 closeout 自述。
3. 复核 `$CLAUDE_JOB_DIR/tmp/CLOSEOUT_DISPOSITION.md` 与 `closeout-manifest.tsv` 的存在、计数和无删除措辞，但本轮不授权删除任何 temp 文件。
4. 对 F1～F10 分别给出 pass／fail 与证据；重新计算提交 path set、当前 target status、disposition open/disputed count和文档 stale-state scan。
5. 只报 blocker／major，最多 6 条；若只剩 minor，直接 pass。不得建议 push、cutover、删除 peer worktree 或归档并行文档。
6. 只写自己的报告，不修改被评对象；尾部交付声明必须包含最新 verdict 与计数。
