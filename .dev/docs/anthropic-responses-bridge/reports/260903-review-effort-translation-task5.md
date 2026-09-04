# Task 5 独立 code review

> 本文件由coordinator从reviewer `aef76b22`完整末轮转录；reviewer因隔离guard无法写目标路径。以下正文保持原结论与证据边界。

- report_id：`task-5-review`
- reviewed_at_rev：`505d62fd2622c4ecb35e701fad33e1ca12300fb6`
- package：`618fc54..505d62f`

## 评审范围与证据边界

本轮对账Task 5 brief／report、固定review package、current Spec profile facts／ThinkingEffortIntent与Acceptance REQ-05A，并读取package涉及的production、recorder、cassette、tests及调用链。Package含`e60391d`、`bf25637`、`505d62f`三个提交，共12个文件，无Task 5 facts／recorder／real-cassette验收之外改动。

Reviewer未重跑测试。Controller绑定`505d62f`的Ruff全绿、Pyright 0 errors／warnings／informations、pytest 2175 passed／2 skipped、coverage 91.17%作为既有证据采用，不外推其他commit。若证据不实或不属于该package，“已有全量绿”结论须撤回重建。

## Verdict

- **Spec compliance：PASS。** 未发现profile fact内容、success／refusal接线、durable JSONL、loss/fact分离、direct bypass、recorder共享transport、零interaction保护或real-high cassette违反Task 5合同与Spec／REQ-05A。
- **Code quality：PASS。** 0 blocker／major／minor；1项documentation nit不阻断下一阶段。

## Finding

### task-5-review-01：`Conversion`与`TranslationRefused`类文档未随facts职责同步

- severity：nit
- primary_location：`src/app/pipeline/translation_driver/semantic.py:70-117`
- related_locations：`src/app/pipeline/driver.py:136-164`

`Conversion`现同时拥有losses与non-loss facts，但docstring仍定义为“What a translation could not carry over”；`TranslationRefused`还携带异常路径facts snapshot，docstring只列code／field_path。Runtime、types、tests与持久化均正确，不导致行为缺陷；但文字会把未来读者引回“Conversion只装loss”的旧模型。建议后续仅同步docstring，不改结构／行为。

## Spec compliance walkthrough

### Non-loss fact模型与producer

- `ConversionFactCode`只把thinking-profile-selected／rejected定义为fact；`Conversion.observe()`写独立facts，`lossless`仍等价于`not losses`。Facts不进入Loss、losses JSON或TRANSLATION_LOSSES metric。
- Profile missing只记rejected，detail含resolved model、`pattern=<none>`与稳定reason；命中后先记selected，always-on disabled、effort上限及全profile不可渲染再追加rejected。`TranslationRefused.facts=tuple(conversion.facts)`在raise前snapshot。
- Success detail含resolved model与最终pattern；拒绝detail在同一基线上追加reason。Last-fullmatch override测试同时固定不同thinking shape与最终override pattern。

### RequestContext→RequestTrace→RequestLine→JSONL

- `handle()`与`handle_count_tokens()`共用`_translate_with_facts()`；success复制`semantic.conversion.facts`，exception复制`refusal.facts`。
- `_dispatch()`的count success／exception、normal exception均在return前`trace.absorb_conversion(context)`；normal handle后在streaming／no-response／buffered共同前置点吸收，buffered response conversion后重算。Translation前早期失败没有可丢facts。
- `RequestTrace.absorb_conversion()`重算losses与facts而不append；`log_completion()`构造`RequestLine(facts=trace.facts)`；`write_request_record()`由`asdict()`把tuple写成JSON array。Direct／无profile请求得到`facts=[]`而非字段缺席。
- Console formatter不读facts；测试固定只差facts的两条RequestLine渲染相等。

### Tests与exception-copy mutation

- `/responses`公开入口固定exact profile success、last-match override、always-on reject、unrenderable reject、missing profile的完整JSONL facts；direct Responses固定原始bytes与`facts=[]`。
- `test_rejected_thinking_profile_facts_reach_jsonl`独立断言error code／param、零upstream与exact JSONL facts。只删exception `_keep_conversion_facts`时exception／message不变而JSONL facts清空，目标断言判红；controller报告实际mutation、snapshot恢复与正样本相符。
- Count测试用test-only writer注入typed fact，证明真实count route经过success copy与durable record；profile producer内容由`/responses`测试独立固定，两层不互相冒充。

## Recorder与real cassette

- `_recording_chain()`用production `build_github_token_source()`取得credential source和`CopilotTokenManager`；同一RecordingTransport http client传token manager、`build_copilot_provider()`和`build_chain()`，token／models／responses三腿同录。测试把`composition.build_http_client`替换成立即失败，能判provider-private client回归。
- `record()`drain并close后先检查interactions；零则raise，非零才write。保护测试固定existing bytes、RuntimeError与destination byte-exact不变；main另固定零interaction非零返回。没有先truncate再判断。
- `505d62f`cassette含token／models／responses三项，authenticated=true、source=live-recording、chunks非空。Responses shape model gpt-5.5、stream true、digest`9a1a408a707b2cf642b18cc408fa4ca76b65375e2680229a67f642ea5ee38c59`；31 chunks，created／in_progress／completed均`reasoning.effort=high`。
- Token／tracking id、safety_identifier为REDACTED；enterprise／organization list保持类型为空；Authorization只保留authenticated事实；headers走allowlist。组合测试扫描credential prefix／非digest 64hex并驱动跨chunk scrubber。
- Cassette自报source不能独立证明本轮live provenance；review采用controller两次明确授权、首轮零interaction失败产物保留、第二轮三interaction成功的过程证据。若该前提失效，只撤销real-calibration强度，不撤销recorder wiring／fixture结构。

## 未采纳为finding

- Task 3／4四个deferred minors按binding留给final whole-branch review。
- Profile“来源”按brief解释为resolved model＋matched pattern；没有单独bundled／user origin tag。若上级将Spec解释为必须区分来源层级，需要重开。
- Recorder／cassette虽不在brief最初production清单，但直接修复并承载real-high验收，且未改production behavior，不判Task外改动。

## 我最没把握的三个判断

1. Profile来源粒度：本轮按model＋pattern裁定满足；若要求bundled／user origin，结论改变。
2. Live cassette provenance：未再次联网，仅依赖controller过程与asset；过程锚失效只撤销live强度。
3. Full-suite green时点：按controller报告绑定`505d62f`；日志若属其他tree需重建，静态verdict不自动反转。

## 整体判定

固定package `618fc54..505d62f`可进入下一阶段。Task 5核心合同0 blocker／0 major／0 minor；唯一nit仅同步docstring。

## 交付声明

- delivery_complete：true
- completed_at：2026-09-03T20:46:33+00:00
- finding_total：1
- blocker：0
- major：0
- minor：0
- nit：1

SPEC: PASS
QUALITY: PASS
COUNTS: blocker=0 major=0 minor=0 nit=1
