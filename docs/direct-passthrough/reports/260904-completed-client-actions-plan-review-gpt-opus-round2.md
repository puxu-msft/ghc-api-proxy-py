# Responses completed client actions 实施计划复评

## 评审范围

只复评首轮 F01～F03，以及其在主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md` Task 10.2、10.4、10.6 和 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260904-completed-client-actions-plan-review-disposition.md` 中的处置。按协调者要求，没有重开其它 C1～C8，也没有扩展到实现代码或未形成的测试结果。

## 总体 verdict

**pass，可执行。** Blocker：0。Major：0。首轮 F01～F03 均已关闭，处置表对整改内容的转述成立；未发现处置自身引入的新 blocker／major。

## 首轮 findings 复核

### F01 — closed
- `producer_scope`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:231-233,261` 现在只允许 `openai_responses_passthrough._read_terminal()` 在 `response.completed` 填三项新 facts，并明确 `response.incomplete` 不填字段、保留 shared `max_tokens` 路径。
- `producer_control`：同文件 `:263` 用带 terminal output 的 `response.incomplete` 断言 `stop_reason == "max_tokens"`、status／actions 默认、completeness false，能判红 producer 范围泄漏。
- `renderer_control`：同文件 `:329-331` 仅以非空 `terminal_status` 进入新 branch，并新增 `response.incomplete` 仍走黄色 legacy `max_tokens` formatter 的回归；两层控制分别覆盖产生点和展示点。
- `disposition`：处置表 `:10` 对上述整改的概括与计划逐项一致，未把未完成实现写成已验证结果。

### F02 — closed
- `order`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:376-380` 已改为 targeted／快照恢复核对 → independent review、处置与同一 reviewer 复评 → relevant targeted tests／mutation controls → 共识后一次 Ruff、Pyright、full regression。
- `review_loop`：同文件 `:378` 明确 relevant bytes 改动时只重跑受影响 targeted evidence，再恢复同一 reviewer；full suite 在此阶段被明确禁止。
- `finality`：同文件 `:380` 把三个全量检查绑定到共识后的 stable final candidate，随后 `:382` 才提交 source；因此 review 修复不会让 final evidence 预先陈旧。
- `disposition`：处置表 `:11` 准确记录该顺序，没有遗漏复评或受影响 mutation controls。

### F03 — closed
- `source_stage`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:382-405` 先保留并观察全局 staged entries，再以同一 `paths` array 执行 exact-pathspec `git add`、scoped cached audit、pathspec `git commit -F`；新建的 `openai_responses_actions.py` 明确位于 `:388`。
- `peer_state`：同文件 `:382,400-404` 不 reset／restore index，commit 带同一 source pathspec，因此不会把其它 staged entries 卷入，也不会为清索引抹掉它们。
- `dot_dev_stage`：同文件 `:409` 对 `.dev` 独立提交同样要求先 exact-pathspec `git add`，再 scoped cached audit 与 pathspec commit，并明确包含新 disposition report、排除无关 `.dev` WIP。
- `disposition`：处置表 `:12` 对 source 与 `.dev` 两侧的 add／audit／commit 修复均有对应计划事实，成立。

## 剩余问题与排除项

- 未发现剩余 blocker、major 或需要阻止执行的 minor；本轮限定范围内计划可执行。
- 没有把“full regression 失败后需回到处置循环”重新立为 F02：`:378-380` 已把共识、相关字节变化与 final candidate 绑定，相关字节发生变化就不再是同一 stable candidate，必须重新取得相应证据；这不会让一个失败运行冒充最终成功证据。
- 没有重开 Task 10.1、10.3、10.5 或其它 C1～C8；也没有将未来实现是否正确、测试是否真实变红提前记成计划缺陷。

## 搜索面与证据边界

逐行读取了当前主树 Task 10.2、10.4、10.6 和新处置表，并逐条对照首轮 F01～F03 的 primary location、影响与 required correction。此次是文档复评，未修改主树、未运行 Git 写操作，也未执行尚不存在的实现测试；`pass` 只表示这三项计划缺陷已在文档层关闭，不表示未来实现或验证结果已经通过。
