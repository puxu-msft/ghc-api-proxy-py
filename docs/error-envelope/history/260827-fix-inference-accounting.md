# 修复报告：inference.py / stream.py 上的四条记账假事实

> **落盘说明**：本报告由实施 agent（gpt-opus）产出。该 agent 的 harness 约束禁止它创建报告类 `.md` 文件，因此由主会话代为落盘，**正文逐字保留**，仅添加本说明块与文末的「主会话复核」一节。日期 2026-08-27，基线 `main` 的 `efeab76`。

## 修复结果

### 1. retry §9：one-shot 交付结局未接入记账

- 修改：在 `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py` 的 `_StreamAccounting.finish()` 中，为 `assembler is None` 的 one-shot 路径补上结局判断。
- 行为：
  - `failure` 存在时记为 `fail`。
  - 未排空且无 failure 时记为 `gone`。
  - 正常排空仍为 `ok`，不会被误报成 terminal-less failure。
- 原因：Chat Completions 没有可用的 `BlockAssembler`；正确做法不是伪造 assembler，而是直接使用该记账对象已有的 `failure`、`drained` 与 `_ending()`。
- 测试：`test_one_shot_accounting_reports_how_delivery_actually_ended`，覆盖 upstream tear、client left、clean drain 三格。
- 变异验证：临时删掉无 assembler 分支后，该测试得到 `2 failed, 1 passed`；tear 与 client-left 都退回错误的 `ok`，clean-drain 正控继续通过。恢复后 `3 passed`。

### 2. error-envelope E-11：完成行错误说明改读 `ErrorInfo.message`

- 修改：在 upstream outcome 没有 response 的分支中调用 `describe(...)` 一次，得到 `ErrorInfo`；`trace.detail` 与 `error_response(...)` 共用该记录。
- 原因：此前 wire 读取 `ErrorInfo.message`，完成行却读取 SDK exception 的 `__str__`，导致同一次失败出现不可互相对照的两套说法。
- 测试：`test_an_upstream_refusal_is_described_by_the_same_error_info_on_the_line_and_wire`，从真实 app 入口比较客户端错误 message 与完成行，并排除 `Error code: 400` 的 SDK repr。
- 变异验证：临时把 `trace.detail` 改回 `str(error)` 后，该测试 `1 failed`，完成行重新出现 `upstream rejected the request: Error code: 400 - {...}`。恢复后 `1 passed`。

### 3. error-envelope E-6：客户端 deadline 不再被记成正常排空

- 修改：在 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py` 中，写出 `client_deadline_exceeded` frame 后由 `return` 改为 `raise torn`。
- 原因：error frame 是给客户端的说明；原异常仍必须传播到 `_tracked_delivery`，才能把同一事件记成 failure，而不是 clean drain。
- 测试：`test_a_client_deadline_is_accounted_as_the_failure_its_frame_reports` 同时断言：
  - frame 中存在 `client_deadline_exceeded`；
  - 原 `ClientDeadlineError` 继续传播；
  - 完成行写 deadline 原因；
  - 完成行不再写 `upstream stream ended without a terminal event`。
- 配套调整：已有 deadline delivery 测试改为同时要求「先收到 frame，随后抛出 `ClientDeadlineError`」；`test_the_client_deadline_survives_a_replay` 也改为接受新传播契约，同时保留 replay 次数与总截止时间判据。
- 变异验证：临时改回 `return` 后，测试 `1 failed`，失败原因为 `DID NOT RAISE ClientDeadlineError`，完成行同时复现旧说法。恢复后 `1 passed`。

### 4. error-envelope E-1 半条：修正 one-shot 守卫注释

- 修改：注释现在明确说明，guard exception 结束响应前，`one_shot_delivery` 会把此前已到达的 upstream bytes 送出；客户端得到 HTTP 200、`text/event-stream`、这些字节，但没有 error frame。
- 测试：`test_the_one_shot_guard_comment_says_that_arrived_bytes_are_delivered`。由于缺陷本身是错误注释，测试有意检查源码陈述；仅靠 runtime 测试无法识别「行为正确但注释又被改回谎话」。
- 变异验证：临时恢复 `whatever had been buffered, which is nothing` 后，该测试 `1 failed`。恢复后 `1 passed`。

## 验证

证据等级：足以交付。依据是 fresh scoped regression、全仓静态检查以及四轮逐项变异，不是只看一次全绿。

显式绑定 `/home/xp/src/ghc-api-proxy-py` 后执行：

- 两个改动测试文件：`204 passed in 45.86s`
- `uv run ruff check src tests`：`All checks passed!`
- `uv run pyright src tests`：`0 errors, 0 warnings, 0 informations`
- 四轮变异恢复后均用 read-only `git diff` 核对预期差异；未执行 `add`、`commit`、`checkout`、`stash` 或其他 Git 状态修改。

## 我否决了什么

1. **给 one-shot 路径传一个 assembler**：否决。Chat Completions 当前没有块边界 reader；伪造 assembler 会重新引入协议猜测，而且会把正常 clean drain 当成无 terminal failure。
2. **清洗或解析 SDK exception 的字符串**：否决。Python dict repr 不是契约；正确权威是已经存在的 `ErrorInfo.message`。
3. **让 deadline 分支直接修改 accounting 或增加专用 callback**：否决。这会把结局判断复制到 delivery 层。项目已有统一模式是「先 yield error frame，再 raise 原异常给 accounting」。
4. **只用现有 runtime 测试保护注释修复**：否决。注释单独回退不会改变 runtime；这种测试没有分辨力，因此采用明确的源码陈述断言。
5. **顺势把 inference.py 所有 `error_response` 调用重构成统一 helper**：否决。E-11 给出的具体缺陷在 upstream refusal outcome 分支；扩大到所有入口会改变不相关完成行措辞，超出本次范围。
6. **运行 `ruff format`**：未采用，项目明确禁止。

## 我没能做的

1. **未实现 Chat Completions 的 streaming error carrier 或块边界解析**：这是 E-1 中用户已经裁决推迟的主体；本次只修错误注释，不能借机恢复已推迟范围。
2. **未更新 `.dev` 台账或 Spec**：任务严格限定两个源文件及其测试，且另有 agent 并行负责 `.dev/`。主会话应在统一收口时移除已完成的 E-6、E-11、retry §9 及 E-1 注释半条。
3. **未运行全量 pytest**：用户明确要求不要跑全量；只运行了两个被修改测试文件。
4. **未派生独立 reviewer**：当前是叶子执行单元，无权调度其他 agent；建议主会话按其既定编排进行最终 review。
5. **未落盘指定报告文件**：当前 subagent harness 明令报告直接回传、不得创建报告类 `.md`；主会话需将本回复写入 `/home/xp/.claude/jobs/0e3de57b/tmp/fix-inference-accounting.md`。

相关改动文件：

- `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py`
- `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_stream_delivery.py`

## 主会话复核（2026-08-27）

第 4 条那个源码断言测试**过脆，已放宽**。原实现断言的是一个具体短语 `"sends the upstream bytes that had already arrived" in source`，任何对该注释的合理改写都会让它变红，而注释仍然是对的——那会把「诚实的编辑」和「谎话复活」变成同一种红。

改为两条职责不同的断言，且只有第二条允许严格：

- 正向：先取出那一行注释（按 `no framer for this leg` 定位），再要求它同时含 `arrived` 与 `bytes`。钉的是**主张**而不是句子，怎么改写都行，只要还说字节到达了。
- 反向：原样保留 `"whatever had been buffered, which is nothing" not in source`。这一条该严格——它点名的是那句必须永不复活的假话。

放宽后重跑变异确认仍有分辨力：把那行改成不提字节到达、也不说假话的版本（`the guard's exception simply ends the response — 200, text/event-stream, and no error frame.`），正向断言按预期变红；还原后绿，`git diff --stat` 为 `+10/-3`，与 agent 本身的改动一致，无变异残留。

agent 对「runtime 测试保护不了注释」的论证成立，接受源码断言这个手段本身；改的只是它的严格程度。
