---
report_id: retry-continuation-review-round-seven-followup
attempt_id: round-seven-followup-bb17558-gpt
status: in-review
reviewed_at_rev:
  main: bb175586fce8632adf65175c61a256667196d951
  parent: b5bc8f90adf368b98a5f82a660a3ed1e3574ef52
  previous_review: /home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260824-review-round-seven.md@da5fcc1c3719c344ec40c15b88464691ead19865
  dot_dev: da5fcc1c3719c344ec40c15b88464691ead19865
reviewed_at: 2026-08-24
---

# 第七轮复评：exception pairing 与 post-terminal tear

## 评审范围

本轮复评主仓提交 `bb175586fce8632adf65175c61a256667196d951` 及新增父提交 `b5bc8f90adf368b98a5f82a660a3ed1e3574ef52`。前者逐项处置上一轮 5 条 minor、2 条 nit 与 2 条未计级建议；后者新增 post-terminal tear 观测。判据沿用上一轮提交态 human-controlled 文档和本主题 living docs，并额外核对 `.dev@da5fcc1` 对 §22之七的更新。

所有代码读取、探针、变异与正式 gate 都在 `/home/xp/.claude/jobs/06dcd6c1/tmp/tree-bb17558/`。tracked 清单初次对账为 `expected_files=528`、`missing=0`、`mismatched=0`；受控变异全部恢复后再次逐 blob 与 mode 对账为 `mismatched=0`。目录中的 `.venv`、cache 等 11,166 个 ignored extra 不参与提交身份。

明确不在范围：主工作树未提交内容、真实 upstream 调用、未挂载 legacy 链路是否应重新接线。本轮未修改被评对象，只新增 `/tmp` 探针与本报告。

## 总体裁决

**verdict：`pass-with-fixes`。**

**blocker：0。major：0。minor：2。nit：1。**

R7-01、R7-03、R7-04、R7-05、R7-06 与两条建议的主体均已闭合；R7-07 的数量事实已改正。R7-02 只部分闭合：same-object 与 helper 在安静上下文中连续调用的两个反例修掉了，但正常“cleanup 在 primary 正被处理时失败”的形状仍会丢旧 context，显式 cause back-edge 还能造两对象环。新增父提交的普通 `end_turn` post-terminal tear 也能留痕，但 `max_tokens` 会随后 hand-over，`if/elif` 让 tear 再次只活在临时 accounting object 中，最终 record 与 line 都看不见。

提交态正式 gate 全绿：Ruff clean、Pyright 0 error、`1649 passed, 2 skipped`、coverage 90.19%。这些绿不推翻上述两个反例：二者都在现有测试输入集合之外，并由 exact tree 探针或真实服务入口复现。

## 上一轮逐条完成度

| 上一轮条目 | 复评状态 | 依据 |
|---|---|---|
| R7-01 两个未迁移调用点 | closed | `session_liveness_stream` 与 `DelayedStartStreamingResponse` 均调用 shared helper；全仓 production callsite 共五处。带 root 的 session test 同时断言 root cause 与 close context |
| R7-02 context/self-cycle | partially-closed | same-object 与安静上下文连续调用已闭合；活动 cleanup context 丢旧链、显式 back-edge 两对象环仍在，见 F01 |
| R7-03 falsey primary | closed | 四处全部改为 `if primary is None`；真实 `_counted_upstream` 新 test 的忠实 `or` 变异按预期红；排除该 test 的 1591 条 unit+int 在同一变异下全绿，数字断言成立 |
| R7-04 shield future diagnostic | closed | `asyncio.wait` 保持 child cleanup；忠实变异回 `shield` 后新 test 收到一条 `RuntimeError exception in shielded future` 并红 |
| R7-05 stale attribution comment | closed | marker/counter 当前事实与 §22之六／§22之七已分开 |
| R7-06 opened attempt wording | closed | test 名、docstring、injection scope 均已收窄，不再把 `attempt_count` 写成 wire oracle |
| R7-07 wrapper count | closed-with-nit | 五个对象逐个列对；同一句残留重复短语，见 F03 |
| Event 建议 | closed | `close_entered`／`allow_close` 已接线；前提由 event 判定，变异仍咬住 release interruption |
| typed pool 建议 | closed | `getattr` + `isinstance(AsyncConnectionPool)`，Pyright 与 runtime tests 均通过 |

## Major

未发现 major。

## Minor

### F01：cycle guard 收得过窄，真实 active-cleanup 形状仍丢旧 context，显式 cause back-edge 仍可造环

- finding_id: `retry-continuation-review-round-seven-followup-01`
- severity: `minor`
- primary_location: `src/app/streaming/keepalive.py:89-120`
- related_locations: `src/app/server/routes/inference.py:649-665`、`tests/unit/streaming/test_streaming_resilience.py:524-587`

**证据一：carry test 没有复现调用点最关键的上下文。** 当前 carry 只在 `cleanup_error.__context__ is None` 时执行（`:110-118`）。但 `_AccountedStreamingResponse.__call__` 在 primary 正传播的 `finally` 中直接 `await self._content.aclose()`；close 在这里抛错时，Python 先把 `cleanup_error.__context__` 设为 primary。exact tree 探针构造 `Primary from Root`，让 primary 还带一条较早的 cleanup context，再在处理 primary 时抛新 cleanup：

```text
before cleanup_context_is_primary=True
after primary_context_is_cleanup=True
after cleanup_context_is_primary=False
earlier_reachable=False
walk=['Primary:primary', 'Cleanup:new cleanup', 'Root:root']
```

也就是说，`cleanup_error.__context__ is None` 把真实活动形状挡在 carry 外；最终 re-raise 时 Python 为避免普通 implicit-context 环而拆掉 `cleanup -> primary`，旧 context 没挂到任何地方，第一条 cleanup 再次不可达。现有 `test_a_cleanup_failure_does_not_displace_an_earlier_one` 连续两次直接调用 helper，第二次 cleanup 进入时没有 active primary，因而只能证明安静上下文。

**证据二：两处写向 primary 不能一律不守。** exact tree 让 `cleanup_error.__cause__ = primary`，再调用 helper。primary 原本无 cause 时得到：

```text
primary_cause_cleanup=True
cleanup_cause_primary=True
cause_first_chain=['RuntimeError:primary', 'RuntimeError:cleanup', 'RuntimeError:primary']
```

这不是 ordinary implicit context，Python不会替 helper 拆显式 cause back-edge。`cleanup_error is primary` 守卫只挡自环，挡不住两对象环。helper docstring `:102` 所称“两个 primary 写入不需 guard；普通 Python 每次闭环而 traceback 用 seen-set 走”也不是最终对象图的事实：普通 `cleanup.__context__ is primary` 在 re-raise 后会被 Python 清掉，本轮探针的 cause 有／无两种正常形状都得到 `cleanup_context_primary=False`。

**判断。** R7-02 的目标是“nothing already reachable lost”且不造环；当前实现仍各有一个反例。最常见的一次 cleanup、same-object 与安静上下文连续 cleanup 都正确，剩余问题需要多层 cleanup 或显式异常 back-edge，故沿用 minor，不升 major。但这不是只改 docstring 就能闭合：活动调用点确实会丢对象。

**建议处置。** 区分两类 back-edge，而不是把 guard 从 primary links 全撤掉：若唯一回边是 ordinary `cleanup_error.__context__ is primary`，在挂 `primary -> cleanup` 前先把这条临时回边替换为 displaced context，再做 cycle check；若 cleanup 通过 `__cause__` 或更深链已经能到 primary，则不能再建立反向 link，应采用不造环的承载方式。新增两个 test：一个在 `except primary` 内抛 cleanup 并确认旧 context 仍可达；一个令 `cleanup.__cause__ = primary` 并确认两向遍历均无环。同步重写 `:94,100,102` 的契约说明。

### F02：post-terminal tear 与 `max_tokens` hand-over 可同时成立，`elif` 让新增 cause 再次不落 record；living docs 两边还互相冲突

- finding_id: `retry-continuation-review-round-seven-followup-02`
- severity: `minor`
- primary_location: `src/app/server/routes/inference.py:592-610`
- related_locations: `src/app/pipeline/delivery/stream.py:377-389`、`src/app/pipeline/delivery/stream.py:449-470`、`tests/int/test_pipeline_app.py:3161-3205`、`.dev/docs/upstream/retry-and-continuation/README.md:48-51`、`.dev/docs/upstream/retry-and-continuation/deferred.md:348-367`

**证据。** `assembler.terminal.seen` 不等于“客户端什么也不欠”：默认 hand-over stop reason `max_tokens` 正是 terminal 已见但回合未完成。`_deliver` 先在 `:377-389` 调 `on_tear_after_terminal` 并 break，随后在 `:459-470` 对 `max_tokens` 合成 hand-over。直接 delivery 探针确认两个事实同时为真：

```text
stop_reason=max_tokens tears=["ConnectionError('tear after max_tokens')"] handovers=[('None', 'max_tokens')] has_carry_on=True
```

production 入口探针复用真实 app、默认 continuation 与 completion writer，结果为：

```text
status=retry
detail='turn handed back to the client to continue'
tear_persisted=False
tool_use=True
line='... max_tokens: turn handed back to the client to continue ...'
```

原因正是 `finish()` 的 `if self.handed_over ... elif self.tore_after_terminal`：它们不是互斥状态，只是渲染时前者吃掉后者。新增 integration test 只造 `end_turn`，结构上无法看到 hand-over 共存。

**replay 问题单独核过。** 第一 attempt pre-terminal tear、第二 attempt terminal 后 tear 时，callback 正常收到第二次异常：

```text
reopened=1
tears=["ConnectionError('replayed attempt tore after terminal')"]
kept=True lost=False
```

所以 wiring 穿过 replay 成立；`note_tear_after_terminal` 的 first-one guard今天不会盖掉后一次，因为任何一次 post-terminal tear 都 break 整个 loop，最多发生一次。反而是它的 docstring `:607` 写“replayed attempt cannot tear after its own terminal”被上述 exact probe直接推翻——replayed attempt 可以，不能的是“记录一次 post-terminal tear 后再 replay”。

**文档同步。** `.dev deferred.md:361-367` 说最后一格已修、状态总是 `ok`、四格都不再不可见；max_tokens 反例推翻后两项。与此同时 `.dev README.md:51` 仍写这格“未修”。同一 living topic 现在一边说未修、一边说完全修完，且完整那边又写宽了。

**判断。** 普通 `end_turn` 路径实现与测试成立，客户端 wire 行为也没有错；缺的是与 hand-over 共存时的 operator record，因此定为 minor。它仍直接否定父提交“最后一个 swallowed cause 已闭合”的全称。

**建议处置。** 不要让单一 `trace.detail` 的 `if/elif` 充当事实互斥。可给 structured record 单列 bounded `tear_after_terminal`，console 再决定与 hand-over detail 并列或追加；至少在 `handed_over` 分支把该 note 合并进去。补 `max_tokens + terminal tear` 的真实入口 test，同时保留 `status=retry` 与 tool_use 断言。把 comments 收窄为“terminal event seen”；只有不触发 hand-over且完整交付时才是 `ok`。同步修 README 与 deferred 表格。

## Nit

### F03：三处改写 residue 仍陈述旧机制、重复短语或无边界全称

- finding_id: `retry-continuation-review-round-seven-followup-03`
- severity: `nit`
- primary_location: `tests/unit/pipeline/delivery/test_stream_delivery.py:1377-1386`
- related_locations: `tests/unit/pipeline/delivery/test_stream_delivery.py:1520-1525`、`tests/unit/pipeline/delivery/test_stream_delivery.py:1468-1474`、`tests/unit/streaming/test_streaming_resilience.py:590-620`

**证据与判断。** `test_a_second_cancellation...` 的 docstring `:1382` 仍说 cleanup task 在 `asyncio.shield` 后面，本提交已经改为 `asyncio.wait`；这是直接错误。`:1523` 把“`_counted_upstream` is this side's bookkeeping”连续说了两遍，显然是本轮 five-object 改写残留。两个 falsey test 又写“Nothing in the standard library defines a falsey BaseException”；本轮能确认的是项目已知／测试覆盖的标准异常 truthy，没有做足以支撑整个 stdlib 的穷举。它没有当前反例，但属于用户点名要求核查的无边界绝对句。三处都不改变测试 oracle 或实现，定为 nit。

**建议处置。** 把 `asyncio.shield` 改成“独立 cleanup task + wait”；删重复半句；把 stdlib 全称收成“the standard exceptions exercised here are truthy”或写明实测集合。`keepalive.py:102` 与 `note_tear_after_terminal:607` 的更承重错误已分别纳入 F01/F02，不在此重复计数。

## 重点问题的直接答复

1. **R7-02 guard 收窄过头。** ordinary implicit back-edge 需要先拆再 carry；显式 cause back-edge 仍需守。当前既会丢旧 context，也能造两对象 cause 环，见 F01。
2. **`asyncio.wait` 没改变已要求的取消计数语义。** exact probe连续两次 cancel：`count=1 -> 2`，cleanup 未提前结束，release 后顶层仍是 `CancelledError`、`task_cancelled=True`、`close_finished=True`；close failure 仍成为 cause，且不再有 loop exception report。`cleanup_task.done()` 后 while 条件自然退出；取消与 done 同时发生时 except 分支也在下轮条件前检查 done，不见空转路径。
3. **replayed attempt 会走 post-terminal callback。** 已由一退一成的两 attempt probe确认。first-one 不会盖后一次，因为 post-terminal branch 一旦触发就 break；其 docstring 只是把“后面不会再 replay”错写成“replayed attempt不能触发”。`trace.detail` 与 `_ending()` 对普通成功互斥，但与 max_tokens hand-over 不互斥，且会丢 tear，见 F02。
4. **带数字断言。** 五个 pairing production callsite属实；忠实 falsey mutation下排除新增 discriminator 后为 `1591 passed, 1 deselected`，新增 test 自身在同一 mutation下按 `RuntimeError` 红；`shield` mutation也按 loop report 红。“三条既有测试”描述的是未提交第一版，当前 commit无法恢复那份精确代码，本轮不把它当放行依据，也未发现相反证据。
5. **绝对化陈述。** 承重的两条不成立：helper 的“nothing reachable lost／normal loop always persists”与 post-terminal 的“client owes nothing／always ok”；分别是 F01、F02。stdlib falsey 全称证据边界过宽，列 F03。

## 明确排除的怀疑

1. **排除 R7-01 仍漏 production spelling。** production helper callsite正好五处：keepalive、sse、delivery、response close、counter close；旧 `raise primary from cleanup_error` 只剩 helper 自己的无-cause branch与解释文本。结论强到可把 R7-01 关闭。
2. **排除 R7-03 只靠相邻 test 假绿。** `_counted_upstream` 忠实变异回 `or` 后，runtime source probe确认加载 mutation；新增 test 红，且其余 1591 条 unit+int 全绿。这个 test确实新增了此前没有的分辨力。
3. **排除 R7-04 新 test 再次没打中。** `wait -> shield` 忠实变异后，loop handler收到精确一条 `RuntimeError exception in shielded future`，目标 test红；还原后正式全量绿。
4. **排除 `asyncio.wait` 取消 child cleanup。** 单／双 cancel探针都显示 outer task未在 release前完成，source close最终完成；有 close failure时结果为 `CancelledError from RuntimeError`，无 stderr duplicate。
5. **排除 post-terminal callback只覆盖第一 attempt。** replay probe显示第二 attempt的 terminal tear进入同一 callback，完整 reply保留、第一 attempt草稿丢弃。
6. **排除 first-one 今天吞掉“更重要的后一次 post-terminal tear”。** 一旦任何 attempt走该 branch，loop立即 break，不会再有下一 attempt。问题是 hand-over detail并存，不是多个 post-terminal tear竞选。
7. **排除普通 `end_turn` note行为错误。** 提交自带真实入口 test与本轮 probe均得到 `status=ok`、完整 `message_stop`、bounded tear detail；F02只否定 max_tokens／其他优先结局的全称覆盖。
8. **排除 R7-05 注释仍把 counter归 upstream。** 当前 marker段明确说 `_counted_upstream` 是 ours，并区分已闭合 §22之六与 httpcore §22之七。
9. **排除 attempt-count语义又被写宽。** 改名测试明确承认 begin_attempt早于 subscriber／limiter／send，注入点不区分 logical与wire attempt；R7-06已闭合。
10. **排除 typed pool修法制造新 Pyright或proxy gap。** 全量 Pyright 0 error；direct、proxy、configured/default四条既有 runtime test均通过，assert落在 production patch使用的同一 private reach。
11. **排除 five-object数量仍错。** idle timeout、attempt deadline、marker、counter、client deadline五项逐一与 production expression对上；F03只报同一句的重复词。
12. **排除正式绿来自工作树叠加态。** tracked blob与mode在变异前后均对上 `bb17558`，正式命令cwd为用户提供的解包树。

## 验证记录与搜索面

### 提交身份与正式 gate

```text
commit=bb175586fce8632adf65175c61a256667196d951
parent=b5bc8f90adf368b98a5f82a660a3ed1e3574ef52
expected_files=528
missing=0
mismatched=0

ruff: All checks passed!
pyright: 0 errors, 0 warnings, 0 informations
pytest: 1649 passed, 2 skipped in 124.34s
coverage: 90.19%
```

### 正控与探针

- falsey live-path mutation presence：`mutated_or_present=True`；目标 test `1 failed`，最终 raised `RuntimeError`；排除目标后 `1591 passed, 1 deselected`。
- shield mutation presence：`shield_present=True`；目标 test收到 `RuntimeError exception in shielded future` 并红。
- helper active-context probe：普通 implicit back-edge最终由 Python拆掉，但 displaced context不可达；显式 cause back-edge可形成 `primary -> cleanup -> primary`。
- wait repeated-cancel probe：`first_cancel=True count=1`、`second_cancel=True count=2`、release前 task未完成、release后 `CancelledError` 且 cleanup完成。
- post-terminal direct probe：end_turn只 note；max_tokens同时 note callback与 hand-over。
- post-terminal production probe：max_tokens record为 retry／hand-over detail，tear文本不存在。
- replay probe：第一 attempt pre-terminal tear、第二 attempt post-terminal tear时 callback收到第二条。

逐行或承重区间读取了本轮八个 changed files、父提交三文件、request detail全部赋值点、replay replacement路径、living README/deferred §22之七。全仓搜索 pairing callsites、truthiness旧拼法、shield事实、数字与绝对化新增句。未尝试恢复作者未提交的第一版 broad guard，因此“三条既有 tests红”仅记用户报告，不作为本轮独立证据。

## 我最没把握的三个判断

1. **F01 仍定 minor。** helper契约被反例直接推翻，但需要多层 cleanup或显式 back-edge；若 production可稳定造出两次独立 cleanup failure并让第一条成为唯一根因，级别应上调。
2. **F02 定 minor而不是 major。** max_tokens是默认重要路径，living docs也写错；但客户端仍收到正确 hand-over，丢失只在 operator cause record。若 §22之七的“每个 swallowed cause必须持久化”被视为公共可观测性契约，级别可上调。
3. **stdlib falsey全称列 nit。** 本轮没有反例，只确认它缺少穷举证据。若作者有 CPython全源码扫描或类型注册表证据，可直接删掉 F03中这一小项，shield stale与重复短语仍成立。

## 执行本契约时遇到的摩擦

第一次尝试用 `git apply` 在非 Git 解包目录注入 mutation时，命令以 0 退出却明确输出 `Skipped patch`；runtime presence probe随即显示 mutation未加载，因此那次 1591 绿没有被采信。之后改用带唯一计数断言的 exact string replacement、runtime `inspect.getsource` presence与 trap反向替换，正控才有效。该失败过程保留在验证记录的依据里，避免把 no-op injection误记为 false green。

## 整体判定

`bb17558` 实质关闭了上一轮大部分发现，`asyncio.wait` 与新增正控尤其成立；`b5bc8f9` 也让普通成功 post-terminal tear第一次可见。仍需修 F01 的真实 active-context链与 F02 的 max_tokens共存路径，另清理 F03 文本 residue。没有 blocker或major；修完后可转 `pass`。

## 交付声明

- delivery_complete: true
- completed_at: 2026-08-24
- finding_total: 3
- blocker: 0
- major: 0
- minor: 2
- nit: 1
- exclusions_recorded: 12
