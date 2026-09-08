# `.dev` 合并候选最终评审第三轮极窄复核

日期：2026-09-04。

评审范围：只读检查 r2 唯一剩余的 F-04。对象为当前 `docs/direct-passthrough/plan.md` 顶部状态、`docs/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md` 的 Direct passthrough 段，并以已通过的 `docs/direct-passthrough/spec.md` §2.6、`plan.md` §11、`deferred.md` D-5 为对照。没有修改、新建、暂存或提交文件。

## Verdict

**pass。F-04 closed。** Remaining blocker=0、major=0、minor=0；整改未引入新的 blocker／major。

## F-04　closed

`docs/direct-passthrough/plan.md:3` 已把顶部 mutable status 改为用户裁定的“直连与翻译块级交付 continuation”，并将当前实现 applicability 明确限定为两种 block-aware 生成方言——Anthropic Messages 与 OpenAI Responses。该句同时逐项保留三条相邻边界：passthrough 整体仍覆盖全部 `translation_required is False` 路由；Chat Completions 块级解析是独立推迟项；Embeddings 不适用 continuation。它不再把模型先前自行扩写的“每条直连腿”归给用户。

`docs/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md:30` 已作同义同步：当前两种 applicable block-aware 生成方言具名为 Anthropic Messages／OpenAI Responses；passthrough 整体定义域仍是全部 `translation_required is False`；Chat Completions 与 Embeddings 分别保持“独立推迟”与“不适用”。同句的职责分工也与当前 plan 一致，使用 `replay ledger` 而非模糊 continuation budget。

对照闭合：

- `docs/direct-passthrough/spec.md:90-100` 逐腿列出 Responses、Anthropic、Chat Completions、Embeddings，并在 `:99` 给出比 passthrough 总定义域更窄的 continuation applicability；当前仅 Anthropic／Responses，Chat Completions 的块级解析不因 D-5 重开，Embeddings 不是生成协议。
- `docs/direct-passthrough/plan.md:425-427` 的 §11 标题与状态使用相同的“两种 block-aware 生成方言”定义，`:498` 的完成边界明确只覆盖当前两种 applicable 方言，且不宣称 Chat Completions 已获块级 delivery／continuation，也不把 Embeddings 算入 continuation surface。
- `docs/direct-passthrough/deferred.md:54-76` 的 D-5 标题、Responses 射程和完成边界同样限定当前两种 applicable 方言，并把 Chat Completions 独立块级欠项保留在外。

因此 r2 指出的两个 stale current-state restatement 均已同步，规范整体定义域与 continuation applicability 不再互相覆盖或缩窄。

## 整改相邻检查

本轮只改两处 scope restatement；与已通过的 Spec §2.6、plan §11、deferred D-5 逐项同义，没有新增方言、移除既有义务、改变完成依赖或改写用户裁决。未发现由整改引入的 blocker／major。

## 未采纳建议

无。F-04 已闭合，不需要追加 scope、proof framework 或其它可选工作。
