# 评审：reasoning_encrypted_include

- 评审时刻：2026-09-08
- 被评对象：工作区指定变更集（非单一 commit；实现多未提交，e2e 已在 HEAD）
- 对照点：当前工作树 vs HEAD，仅下列文件

## 评审范围

**在范围内**

1. `src/app/config/schema.py` — `ReasoningEncryptedIncludePolicy` 与 `ProxyConfig.reasoning_encrypted_include`
2. `src/app/pipeline/subscribers/reasoning_encrypted_include.py`（新）
3. `src/app/pipeline/subscribers/__init__.py` — 注册、文档表、导出
4. `src/app/server/composition.py` — wiring
5. `tests/unit/pipeline/subscribers/test_reasoning_encrypted_include.py`（新）
6. `tests/unit/pipeline/subscribers/test_builtin_subscribers.py` — lock 更新
7. `tests/int/test_pipeline_app.py` — `test_the_encrypted_reasoning_include_is_configured_end_to_end`（相对 HEAD 无 diff；该测试已随 `3097c5cb` 进 HEAD，实现当时不在树上）
8. `.dev/human-controlled-docs-candidates/260908-reasoning-encrypted-include.md`

**明确不在范围内**

- 同工作树里其他未暂存改动（同伴会话）
- 翻译器本体、直连 driver 循环、除本 subscriber 外的其他 subscriber 实现（只作为契约对照，不当被检对象）
- `config.example.yaml` 是否已写入（候选文档明确还待追认）

**判据来源**（读被检实现之前取的，不从实现反推）

1. 调用方硬要求：默认值必须原样保持现有可观察行为——翻译 Anthropic 腿今天不发 `include`；原生 `/responses` 腿把客户端 `include` 原样转发。
2. `to_openai_responses`（`src/app/pipeline/translation_driver/openai_responses.py:983-1024`）从 SemanticRequest 现组 body：`model`/`input`/`instructions`/`tools`/`stream`/`max_output_tokens`/`temperature`/`reasoning`/`tool_choice` 及 extensions；全文无 `include`。因此翻译腿今天没有该键。
3. Direct driver 模块契约（`direct_driver/base.py` 模块 docstring）：直连路径 payload 原样发出，除 subscriber 改动外。`_prepare_and_send`（约 300-338 行）：`_prepared_payload is None` 时先 `await self._publish(EVENT_ATTEMPT_PREPARE, context)`，再 `attempt.payload = deepcopy(dict(source_payload))`，`source_payload` 默认即 `context.payload`。因此 `attempt.prepare` 必须改 `context.payload`，且发生在 deepcopy 之前。
4. `_prepared_payload` 非空时跳过 `attempt.prepare`（`replay_prepared` 路径，不是普通 transport retry）。普通 retry 循环每次 `begin_attempt` 再走 `_prepare_and_send`，会再次 publish `attempt.prepare`。always_add / always_strip 必须对「同一 body 再跑一遍」幂等。
5. 既有空列表处理先例：`blank_text` 在 system 清空时删键而不是发 `[]`。
6. 既有 subscriber 包契约（HEAD `__init__.py`）：兼容性 reshape 必须有声明开关；默认行为由 Spec/默认值决定；`test_builtin_subscribers.py` 锁住注册集与冻结顺序。
7. 配置先例：同类 Literal 策略默认 `passthrough`（如 thinking.display）；`extra="forbid"` 的 Section 新字段必须有默认。
8. 测试分辨力：默认改掉或 wiring 断开必须变红。

## 总体 verdict

**request-changes**。生产路径本身对齐判据：默认 `passthrough` 不改今天的两条腿，编辑的是 `context.payload` 且发生在 deepcopy 之前，非 list 与空 list 删键也按契约处理。不能批准合入的原因是调用方列为硬检查的测试分辨力没盖住「默认从 passthrough 改成 always_strip」——那条变红不了。

## Blocker 数

0

---

## Findings

### include-01：e2e 默认用例分辨不出 passthrough 与 always_strip

- `severity`：should-fix
- `finding_id`：include-01
- `primary_location`：`tests/int/test_pipeline_app.py:5278-5305`
- `related_locations`：
  - `tests/int/test_pipeline_app.py:5313-5315`（声称要锁住 shipped default 真是 passthrough）
  - `tests/unit/pipeline/subscribers/test_reasoning_encrypted_include.py:5-7`（明确把 default 推给 schema / composition，本文件不测）
  - `src/app/config/schema.py:643`（schema 默认）

**问题**：调用方要求「默认改掉或 wiring 断开必须变红」。wiring 断开确实会被第 3、4 组抓住（`always_add` 配 `overrides` 后上游收不到条目；`always_strip` 配 `overrides` 后条目还在）。默认改成 `always_add` 也会被第 1、2 组抓住。

默认改成 `always_strip` 则两组默认用例都仍绿：

- 第 1 组：`overrides=None`、客户端无 `include`、期望 `None`。`always_strip` 对缺键是 no-op。
- 第 2 组：`overrides=None`、客户端 `include=["file_search_call.results"]`、期望原样。why 写着「strips nothing」，但数组里根本没有 `reasoning.encrypted_content`，`always_strip` 同样不动。

没有一组是「默认策略 + 客户端已经点名了加密推理条目，期望原样上送」。schema 默认也没有单独的单元断言。于是「shipped default really is passthrough」只锁住了「不加」，没锁住「不剥」。

**失败场景**：有人把 `ProxyConfig.reasoning_encrypted_include` 默认改成 `always_strip`（或 composition 误绑成 strip）。原生客户端带 `include: ["reasoning.encrypted_content"]` 的请求会不再把密封体要回来，跨轮推理复用静默失效；本 e2e 与 unit 全绿。

**建议**：默认组加一条 `overrides=None, client_include=["reasoning.encrypted_content"], expected=["reasoning.encrypted_content"]`。更省事的补强是再加 `assert ProxyConfig().reasoning_encrypted_include == "passthrough"`。

---

### include-02：e2e docstring 把配置键写成了不存在的 `model.` 路径

- `severity`：nit
- `finding_id`：include-02
- `primary_location`：`tests/int/test_pipeline_app.py:5313`
- `related_locations`：
  - `src/app/config/schema.py:643`（实际是 `ProxyConfig` 顶层）
  - `.dev/human-controlled-docs-candidates/260908-reasoning-encrypted-include.md`（候选文档写的是顶层）

**问题**：测试 docstring 写 `` `model.reasoning_encrypted_include` ``。实现与候选 YAML 都是顶层 `reasoning_encrypted_include`。读测试的人会去 `model.` 底下找这个键。

---

### include-03：lock 文件夹带了与本功能无关的 count_tokens extras 断言改写

- `severity`：nit
- `finding_id`：include-03
- `primary_location`：`tests/unit/pipeline/subscribers/test_builtin_subscribers.py:394-399`

**问题**：相对 HEAD，除注册 ID 锁更新外，`test_a_translated_route_is_counted_from_the_body_it_would_actually_send` 从断言 `count_tokens_attempts == ["ghc:no-counter-for-openai-responses"]` 改成了 `count_tokens_reason == "no-counter"` 且键不存在。

对照 HEAD `src/app/pipeline/driver.py:538-551`：`result.attempts` 为空时根本不写 `count_tokens_attempts`，本地估计写的是 `count_tokens_reason = "no-counter"`。所以新断言对当前 driver 是对的，HEAD 旧断言已经是红的。但它不是本切片的行为，提交说明里若只写 encrypted-include，这条会变成一次未声明的测试合同迁移。

---

### include-p1：默认透传、编辑时机、空键与非 list 守卫都落在判据上

- `severity`：praise
- `finding_id`：include-p1
- `primary_location`：`src/app/pipeline/subscribers/reasoning_encrypted_include.py:36-62`
- `related_locations`：
  - `src/app/pipeline/direct_driver/base.py:300-338`
  - `src/app/pipeline/translation_driver/openai_responses.py:983-1024`
  - `src/app/server/composition.py:687-688`
  - `src/app/pipeline/subscribers/__init__.py:19,125-135`

**事实**：`passthrough` 在读 body 之前返回，翻译腿今天不写 `include`、原生腿客户端数组原样保留。非默认策略门控 `target_format is WireFormat.OPENAI_RESPONSES`，改的是 `context.payload["include"]`，发生在 `attempt.prepare`、driver deepcopy 进 `attempt.payload` 之前。`always_add` 对已有条目不重复追加（单次与重试都幂等）；`always_strip` 在列表被剥空时 `del` 键而不是留下 `[]`；非 list 记一条 info 后原样留给上游。注册无顺序约束、文档表与 lock 同步；`register_builtin_subscribers` 与 schema 默认都是 `passthrough`，composition 把配置一次绑进闭包。`inbound.py` 对 working copy 做了 deepcopy，in-place append/remove 不会写回 `original_payload`。

---

## 搜索面

**读过**

- 判据：`translation_driver/openai_responses.py`（`to_openai_responses`）、`direct_driver/base.py`（`_prepare_and_send` / `_prepared_payload`）、`pipeline/driver.py`（翻译后写 `context.payload`、`replay_prepared`）、`server/inbound.py`（working vs original deepcopy）、`subscribers/blank_text.py` / HEAD `__init__.py` 注册表、`docs/.human-controlled/request-pipeline.md`
- 被检对象：范围所列 8 项的当前内容与 tracked 文件的 `git diff`
- 未把候选文档当规格反推实现；只在对照配置键路径时引用

**跑过**

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/pipeline/subscribers/ -q
# 165 passed in 8.75s

cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/int/test_pipeline_app.py -k encrypted_reasoning_include -q
# 4 passed, 264 deselected, 1 warning in 3.35s
```

绿的分辨力：对 wiring / `always_add` 默认漂移，现有 4 组 e2e 会红；对 `always_strip` 默认漂移，现有 4 组仍绿（见 include-01）。未做改文件的变异，依据是参数表的穷举对照。

**没看**

- 热重载是否重建 chain（与 thinking_display 等同类绑注册的键同一模式，未单开验证）
- count_tokens 路径在 `always_add` 下估计值是否因多了 `include` 键而变（估计器是否忽略未知键）
- OpenAI 上游对重复 `include` 条目的真实态度（`list.remove` 只剥第一次）

**权威归属**

候选文档标「待用户裁决追认」，并引用一条用户指令。本评审没有一手逐字来源，不传播「用户已裁定默认 passthrough / 三条策略」之外的归属；默认透传的判据来自调用方硬要求与翻译器现状，不来自该候选文档。
