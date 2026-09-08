# `.dev` 脏文件处置复核

日期：2026-09-04。
评审对象：`260904-dotdev-dirty-inventory.md` 与 `260904-dotdev-dirty-inventory-disposition.md` 的当前未提交候选。
评审能力说明：按要求首先尝试加载 `my-agents:as-reviewer`，harness 返回 `Unknown skill`；随后按原报告 A／B／C／D 清单逐项只读复核。
结论：**needs-fix**。blocker=0，major=2。除下列两项外，没有发现 A 原件丢失、verification 被继续冒充 current、D 类归档误导，或 principles finding 缺少 living carrier。

## Major findings

### M-1　Spec 同时禁止与要求合成 Responses terminal

- `direct-passthrough/spec.md:281-287` 要求 continuation 隐藏原 terminal，并合成唯一 `response.completed`。
- 同一规范 `:348-350` 仍无条件规定 `response.completed` 等 terminal “必须原样重放”“不得由本代理合成”。
- 两条都是规范性要求，实施者无法同时满足；§5.3 没有在 §6.3 建立具名例外或收窄后者到 upstream-native terminal。
- 这使 B 类增量尚未被一致的 authoritative carrier 完整接管；提交前必须消除冲突并同步修订记录。

### M-2　Non-stream Responses body 把 event-level `output_index` 写成 item 字段

- `direct-passthrough/spec.md:698-703` 要求向 non-stream `output[]` 追加 synthetic `function_call` item，并称其 `output_index` 取下一个位置。
- 本机 OpenAI SDK 3.3.1 `response_function_tool_call.py:25-58` 的 item 字段没有 `output_index`；该字段属于 streaming event，non-stream body 的位置由数组索引表达。
- 三份 current cassette 的 terminal `response.output[]` item 也都没有 `output_index`；这支持层级区别，但不冒充 function-call 实样本。
- 按现文实施会增加无合同字段或让 writer 无法判断“自洽”的对象；应改成“数组位置”，并把 event-level index 只留在 streaming §5.3。

## 已核通过的处置面

- A：11 份移动的原报告／分析与初始盘点的逐文件 line／byte size 全部一致；16 份 verification 原件也逐文件一致。未观察到原件丢失或正文被改写。
- Verification：三个日期 archive 共 16 个原件，入口 `docs/early-verification/README.md` 明确 current authority、历史时点与旧 runner 不可运行；旧 `verification/` 已清空，没有 current 冒充。
- Principles：`PPR-260903-01` 由 direct Spec §10／plan §11.7 承接；`PPR-260903-02`、`03` 与 skill 自身过期问题由 `docs/project-review-principles-skill/deferred.md` 承接。
- C：`probe_cap_designs.py` 与 httpx2 plan 已补参数、五项度量、exit 边界和当前状态；本轮实跑证据只被表述为入口／输出验证，没有冒充生产负载。
- D：`stage_migration.py` 保持原始 104 行／3468 bytes，archive README 与 living plan 均明确一次性上下文、参数不一致与禁止当前 `--write`；归档没有把它重新分类为 current tool。

## 否决的处置路线及理由

1. 否决“因原报告要求 D 保持未跟踪，必须把 `stage_migration.py` 移回 live 根”：原字节完整、归档可逆且显式阻断 current 使用；继续未跟踪反而没有 durable carrier。
2. 否决“verification 三个日期 archive 拆散了一个 artifact”：Phase 3 report／runner、final report／runner／probes、Hooks report 三组内部保持完整，根入口统一说明 current authority，拆分依据是各自验收日期与 oracle。
3. 否决“principles 三条 finding 必须全塞进同一个 deferred”：PPR-01 的 owner 是 direct-passthrough Spec／plan，另外两条与 skill 维护归 skill 主题；强行合并会建立第二份状态源。
4. 否决“仅由 plan 解释上述两处 Spec 歧义”：Spec 是行为 authority，plan 不能替一份自相矛盾或字段层级错误的规范裁决其含义。

## 交付声明

verdict: needs-fix
blocker_count: 0
major_count: 2
rejected_disposition_routes: 4
