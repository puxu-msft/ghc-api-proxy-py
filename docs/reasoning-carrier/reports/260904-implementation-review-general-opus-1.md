# Reasoning carrier v2 implementation review

## Scope and provenance

- Role: reasoning carrier 协议／codec 正确性 reviewer。
- Candidate: `9cd96cebef0e3bc5e726a692d178499d79e0d8a5`；base: `39274d7bc3601f2236ffdfc52ea6f34f885ba405`。
- Source worktree: `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2`。
- Authoritative Spec: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`。
- Capability note: runtime 的可用 skill 列表中没有用户指定的 `my-agents:as-reviewer`，因此无法加载；按用户合同继续。已加载 `my-skills:qualifying-a-claim-and-its-coverage`；因任务涉及 Anthropic thinking carrier 语义，亦按强制触发规则加载 `claude-api:claude-api`。
- CodeGraph note: worktree 内虽有 `.codegraph/`，但 `codegraph_explore` 明确报告索引冻结且来源是另一 worktree；该结果未作为证据。全部承重源码与测试均通过绝对路径直接读取目标 worktree。
- Frozen-byte check: 先由 `/home/xp/src/ghc-api-proxy-py/.git/worktrees/reasoning-carrier-v2/HEAD` 与对应 ref 确认目标 HEAD；评审后把 candidate diff 的 26 个文件逐一与 `git show 9cd96ce:<path>` 比较，结果 `compared 26 mismatches []`。另对本报告引用的 5 个未变文件比较，结果 `compared 5 mismatches []`。

## Verdict

**NEEDS-FIX**。发现 3 条 major、0 条 blocker。C3、C4、C8 可通过；C1、C2、C5、C6、C7 因下列 major 不满足，候选不可进入集成。

## Findings

### MAJOR-1：v2 codec 未执行 Spec 的严格 UTF-8／JSON／record-type grammar（C1、C7）
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_carrier.py:182-189` 把 bytes 直接交给 `json.loads`，Python 因而自动接受 UTF-16／UTF-32；独立 UTF-16LE probe 得到 `project_v2` 并成功恢复 `[]`，而 Spec §6.2 要求非 UTF-8 为 malformed。
- 同文件 `:173-179` 未设 `allow_nan=False`，`:182-189` 也未用 `parse_constant` 拒绝非 JSON 常量；probe 证实 producer 生成含裸 `NaN` 的 payload，consumer 又把它作为 layout extension 成功恢复，未分类为 malformed。
- 同文件 `:219-225` 只检查 non-empty ASCII，未检查 Spec 要求的 namespaced string；`CarrierRecord("x", None)` 可编码，consumer 结果为 `project_v2`＋unknown，而不是 grammar-malformed。
- 影响：非法 wire 可进入成功恢复路径，producer 也能生成非 JSON carrier；现有边界测试全绿却看不见该类输入。证据强度：直接运行反例，足以据此修复。

### MAJOR-2：详细 v2 classification 被声明却不由统一 classifier 产生，compat facade 对四类错误一律误报 `project_v2`（C2、C6）
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_carrier.py:46-63` 声明 unsupported／direction／profile／presentation classifications，但 `decode_reasoning_carrier()` 在 `:137-147` 对所有 grammar-valid payload 只产出 `project_v2`；细分类只作为 `ReasoningBridgeError.code` 在 `reasoning_bridge.py:257-350` 产生。
- Compat facade 在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/anthropic/thinking/responses_reasoning.py:77-95` 预先保存 structural classification，随后吞掉 bridge error code；生产兼容调用方 `src/app/protocols/anthropic_responses.py:527-532` 正会记录这个错误值。
- 独立 probe 的 core／facade 对照依次为：unsupported→`project_v2_unsupported_record`／`project_v2`、direction→`project_v2_direction_mismatch`／`project_v2`、profile→`project_v2_profile_mismatch`／`project_v2`、presentation→`project_v2_presentation_mismatch`／`project_v2`。
- `rg` 全测试只找到两条 presentation、各一条 unsupported／direction 断言，找不到任何 profile assertion，也没有 Spec §12.1／§12.4 要求的 driver／facade／streaming classification 一致性向量。证据强度：可达调用链＋四个直接反例，足以据此修复。

### MAJOR-3：resident last-mile guard 漏扫 Anthropic `redacted_thinking.data`，项目 carrier 可到达 provider（C5）
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_bridge.py:77-91` 把任意 string `redacted_thinking.data` 当作 Anthropic native state，`:188-194` 在 same-format writer 原样写回。
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/subscribers/reasoning_carrier.py:42-63` 在 Anthropic wire 只检查 `thinking.signature`，完全跳过 `redacted_thinking.data`，与 Spec §7.3 及 C5 的“任何项目 carrier 不到 provider”不变量冲突。
- 全路径 probe 经 `default_registry().translate(Anthropic→Anthropic)` 再执行 `guard_and_layout_reasoning()` 后仍输出 `{'type': 'redacted_thinking', 'data': 'ghc-api-proxy:synthetic-reasoning:v2'}`，没有拒绝。
- 影响：same-format direct path 可绕过 consumer 和 resident guard，把项目 synthetic value 放入 Anthropic provider opaque slot。证据强度：真实 writer＋已注册 subscriber 接缝的直接反例，足以据此修复。

## C1-C8 verification matrix

| Criterion | Result | Evidence and boundary |
|---|---|---|
| C1 | **FAIL** | Canonical producer 的排序、`type`→`value`／`records` key 顺序、compact JSON、UTF-8 encode 与 unpadded Base64URL 位于 `reasoning_carrier.py:113-124,173-179`；独立 literal vector 在 `tests/unit/pipeline/translation_driver/test_reasoning_carrier.py:52-75`。v1 项目与 Copilot consumer 兼容由同文件 `:23-49,111-139` 及 targeted run 支持。但 strict UTF-8／JSON grammar 被 MAJOR-1 的反例推翻，因此合取判据失败。静态 v2 vector 还是全 ASCII，亦无法让 `ensure_ascii=True` 这类 UTF-8 canonical mutation 变红。
| C2 | **FAIL** | Slot-aware core 的实际顺序是 structural malformed（`reasoning_carrier.py:137-147,205-263`）→ unknown（`reasoning_bridge.py:345-350`）→ direction／profile／presentation（`:257-342`），未见 malformed／unknown 恢复为 summary-only；但 MAJOR-2 证明共享 classification surface 并不统一，compat path 将四类折叠为 `project_v2`，且 mandated profile／cross-path vectors 缺失。
| C3 | **PASS** | Summary reader 保留每个 part 与 extensions：`reasoning_bridge.py:52-75`；layout 用 UTF-8 byte lengths 并精确切分：`:353-389`；presence 由 `ReasoningState | None` 区分，present-empty 可编码：`:231-254` 与 `content.py:43-84`。Buffered value-exact 正控在 `test_reasoning_bridge.py:21-75`、完整 response roundtrip 在 `test_translation_driver.py:514-541`；streaming authority／empty／Unicode／extensions 在 `delivery/formats/openai_responses.py:564-695,797-835` 及 `test_sse_assembly.py:266-427`。该 PASS 限于合法 JSON value；MAJOR-1 的非法 JSON 输入不计入本项合法域。
| C4 | **PASS** | Anthropic native thinking／redacted reader、client carrier producer 与 Responses-slot recovery 分别在 `reasoning_bridge.py:77-111,205-254,293-342`；provider writer 只有 source format 与 native state format 匹配才写入，cross-provider native state 在 `:185-228` 抛 `ReasoningNotPortable`。Value-exact tests 在 `test_reasoning_bridge.py:78-106`、streaming Responses client 在 `test_openai_responses_format.py:176-207`、buffered response roundtrip 在 `test_translation_driver.py:544-568`。
| C5 | **FAIL** | 正确接缝可见：request writers 传 `bridge_for_client=False`（`translation_driver/anthropic_messages.py:216-230`；`translation_driver/openai_responses.py:555-599,646-651`），response/client writers 传 `True`（前者 `:148-151`、后者 `:583-590`；`delivery/formats/openai_responses.py:328-341`）；not-portable 在 `anthropic_messages.py:193-213` 与 `openai_responses.py:732-752` 记录 `REASONING_STATE_NOT_PORTABLE`。但 resident guard 的 provider-leak 全称被 MAJOR-3 推翻，故整体 FAIL。
| C6 | **FAIL** | Production readers／writers 与 streaming `CompletedBlock.reasoning` 使用 `ReasoningContent`（`content.py:58-84,87-107`；`delivery/blocks.py:68-76`），源码搜索只找到 `reasoning_carrier.py` 一份 v2 structural decoder，summary accumulator 仅在 Responses assembler；legacy facade 的转换主体也委托 bridge（`responses_reasoning.py:51-96`）。然而 MAJOR-2 显示 facade 又预解码并维护一个与 bridge error classification 分叉的 truth，故“同一 classifier／薄委托”仍不成立。
| C7 | **FAIL** | bool-as-int 在 layout lengths 与 streaming indices 被显式拒绝（`reasoning_carrier.py:252-255`；`delivery/formats/openai_responses.py:664-672`），duplicate JSON key 由 recursive `object_pairs_hook` 拒绝（`reasoning_carrier.py:182-189,289-295`），duplicate record type／empty records 由 `:205-231` 拒绝，Base64 canonical check 在 `:276-286`。但 MAJOR-1 证明非 UTF-8、非 JSON number 与 non-namespaced type 获得稳定的错误分类之前已经被错误接受，因此 FAIL。
| C8 | **PASS** | Static expected 是 literal，不调用 product encoder：`test_reasoning_carrier.py:52-75`；辅助 vector script 明确不 import product code：`exp/reasoning-carrier-v2/gen_vectors.py:1-10`。`test_reasoning_bridge.py:21-37` 与 `test_translation_driver.py:514-541` 直接断言三 part（含空 part、Unicode、extension）的恢复列表，旧 flatten-to-one-part 实现会变红。该 PASS 不替代 C1／C7 所缺的 strict-boundary discrimination。

## Commands and observed results

1. Targeted carrier／bridge／facade／guard／streaming／framer tests：

```text
cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2 && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/pipeline/translation_driver/test_reasoning_carrier.py tests/unit/pipeline/translation_driver/test_reasoning_bridge.py tests/unit/anthropic/test_responses_reasoning.py tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_openai_responses_format.py
122 passed in 5.45s
```

2. Translation／compat／subscriber wiring selection：

```text
cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2 && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/pipeline/translation_driver/test_translation_driver.py -k 'reasoning or signature or carrier' tests/unit/anthropic/test_anthropic_responses_request.py -k 'reasoning or carrier' tests/unit/pipeline/subscribers/test_builtin_subscribers.py -k 'reasoning or order or registered'
24 passed, 119 deselected in 2.22s
```

3. All adversarial probes used the target interpreter and source exactly：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/.venv/bin/python -c '<probe>'
UTF-16LE: project_v2; recovered []
NaN: raw contains NaN == True; recovered math.isnan(value) == True
Classification core/facade: unsupported project_v2_unsupported_record project_v2; direction project_v2_direction_mismatch project_v2; profile project_v2_profile_mismatch project_v2; presentation project_v2_presentation_mismatch project_v2
Non-namespaced type: project_v2 ('x',)
Same-format redacted carrier after guard: {'type': 'redacted_thinking', 'data': 'ghc-api-proxy:synthetic-reasoning:v2'}
```

## Closeout

本轮只读目标源码与测试，未修改／新建／删除目标 worktree 内容，未执行 git add／commit／checkout／stash。唯一写入产物是本报告。未执行清理、合并、发布或 worktree 生命周期操作。作为叶子 reviewer 无权派生独立 reviewer，因此本报告没有额外的 reviewer-of-review 放行；这不改变上述直接反例的证据强度，也不把 verdict 提升为 PASS。
