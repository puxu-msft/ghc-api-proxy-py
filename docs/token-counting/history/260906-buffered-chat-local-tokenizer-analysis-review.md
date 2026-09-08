---
report_id: buffered-chat-local-tokenizer-analysis-review
attempt_id: 260906-buffered-chat-local-tokenizer-analysis-review-a35f5a6a923ecb566
status: in-review
reviewed_at: 2026-09-06
reviewed_at_rev: target sha256 e8ab762a0d9d922f6d6bfe9f487f56a1df15b54667cda4b1c25fcdd5a5670303；transcript evidence sha256 3680fc7a612755274a786a2d992891363d9cde3180e4c300c93dcba267b1782c；erratum sha256 ecc91d06588daebcf1aca51163c0a0706199b0eacf3038c1d2c122033951b84c；code audit sha256 cf3dd02bea9b04649c51d39f4c01e0bcdafa0325b70f8e1e0a0cad1d3cf6d191
---

# “buffered chat local tokenizer analysis”独立文档评审

## Verdict

**pass，可定稿。** Blocker 0，major 0，minor 2。C1～C9 均通过；C10 为 WARN，因为最终“足以／不能支持”列表没有完整重述本文已经成立的正向事故链与若干独立 code-audit 处置，但正文保留了这些内容，且列表自身无冲突。两条 minor 都不改变技术结论、因果判断或建议顺序。

## 评审范围

被评对象是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-buffered-chat-local-tokenizer-analysis.md` 的上述 SHA-256 快照。判据与证据范围限于用户点名的三份报告、其中点名的 production 源码、目标 transcript、request log、首个 rejected capture、active config 与 tokenization state；只核验事实正确性、数字闭合、证据强度、因果分离和处置忠实度，不评文风，不扩展实施范围，不调用真实 upstream。

## C1～C10 核验

### C1．PASS

离线复算从首个 rejected capture 的 3,057 个 input items 删除尾部 3 项后得到 3,054 项；production `app.wire_json.dumps()` 输出 8,662,058 bytes，SHA-256 为 `724decad3e5b3cac64b8439c9aeec2621dc1b0e579fbf0c123494fe5881ed910`，`estimate_responses_input()` 返回 4,539,201。Request-log line 4468 与 transcript lines 5883～5884 以同一 `message_id=edb7df67-af83-471f-b32f-5a6925f9f9e6` 给出 upstream input 921,248。算术闭合为 `4539201 / 921248 = 4.927230235507…`、`4539201 - 921248 = 3617953`、`3617953 / 921248 = 392.723023550662…%`；正文的 4.927230× 与 392.723% 均是正确舍入。

### C2．PASS

正文没有把候选体写成 cryptographic identity。它明确说明原成功请求缺 body 与 hash，把逐字相同限定为“强烈推断、足以工程处置”，并给出可证伪条件：未来原 body hash 若不同，撤回精确倍率并重算。证据强度与结论匹配：尾部边界依次为 transcript 对应的 `reasoning`、assistant `message` 与 task-notification user `message`，删除后上一项又对应 line 5881 的 system reminder，且 production serializer 的 byte count 与成功请求日志精确相等。该证据不足以证明 cryptographic identity，却足以把已确认的 estimator 机制与数量级异常作为 major 工程缺陷处置。

### C3．PASS

离线复算得到 reasoning items 788 个，完整 contribution 3,729,865；清空 `encrypted_content` 而保留 item 的 estimate 为 823,520，故 ciphertext-only delta 为 3,715,681；删除全部 reasoning items 的 estimate 为 809,336，故结构残余为 `823520 - 809336 = 14184`，亦满足 `3729865 - 3715681 = 14184`。比例为 `3729865 / 4539201 = 82.170077949842…%` 与 `3715681 / 4539201 = 81.857600048995…%`。正文清楚地区分完整 item contribution、ciphertext-only delta 和结构残余，没有重复原报告后来勘误的混淆。

### C4．PASS

Production `estimators.py` 的 `_responses_item_text()` 只特判 `message`、`function_call` 与 `function_call_output`，其它 item 走 `dumps(item)`；`estimate_responses_input()` 再用固定 `o200k_base` 编码。Request-log line 4468 的 catalog observation 同样记录 `tokenizer=o200k_base`。因此本样本的主导失真来自把 opaque `reasoning.encrypted_content` 当 ordinary text，而不是 estimator 与 catalog 选择了不同 vocabulary。这个结论只针对主导误差机制，并未否认其它普通文本上仍可能存在 tokenizer 代际误差。

### C5．PASS

17:35～17:56 的 request-log 离线枚举得到 158 条记录，其中 `count_tokens=true` 为 0；所有 token admission observation 均为 `admitted_fast`，非空 `field_token_count` 为 0。最后成功请求 upstream input 为 921,248，而 catalog prompt cap 为 922,000；随后主请求及四个 summary requests 返回 context-window 400，第五个 summary request以 upstream input 920,760 返回 200，但只有两个 encrypted reasoning output items、`reasoning_tokens=808`、无 readable summary，并以 `max_tokens`／`max_output_tokens` 结束。正文因此把 local count defect 与本次 overflow／compaction failure 分开，并明确禁止把同时出现写成因果。

### C6．PASS

Active config 配置 `providers: [ghc, local]`，`opus → gpt-x → gpt-5.6-sol`，未设置 `local_estimate_multiplier`；运行进程环境中也未见 tokenization／multiplier override，schema 默认值为 1.0。`driver.py::handle_count_tokens()` 对 translated OpenAI Responses route 设 `upstream_counts=false`，于是 `ghc` 腿记录 no-counter 后进入 local；local 使用预先计算的 whole-request estimate，再应用 calibration 与 multiplier。Runtime `tokenization.json` 没有 `openai-responses:gpt-5.6-sol` key，而 `CalibrationEngine` 对缺项返回 factor 1.0。故在该 active state 下，同一 translated payload 的 public count path 确会暴露未经校准的 4,539,201，而不是 921,248 附近的数。

### C7．PASS

逐项对照原 code audit 后，处置忠实：LT-01 保留 upstream-before-local 的调用顺序缺陷；LT-02 只确认 direct Anthropic 图像倍率并保留 Responses 倍率待对应 usage；LT-03 保留 model-aware thinking 规则而未改成一律计入；LT-04 只把真实长会话证据提升为“强烈支持、足以行动”，并继续把精确 4.927230× 绑定于重建前提，没有把整项无条件升级为 confirmed；LT-05 保留 context-editing 与 response-field loss；LT-06 按当前书面 provider-key 合同处置，同时保留“若改成纯标签须由用户重裁”的分叉；LT-07 保留 Responses 无 production learning source 与固定 tokenizer；LT-08 保留 living Spec 前置和不得从现有实现反推合同；LT-09 只确认机制、未升级现实影响；LT-10 保留 `bool` 被当 `int` 的边界；LT-11 保留 dead alternate service 与 production 入口脱节；LT-12 明确保留公开配置地位与上限由用户裁定。未发现 likely 被偷换成无条件 confirmed，也未发现用户裁决边界被删除。

### C8．PASS

以 transcript 中 675 个唯一成功 `message.id` join 2026-09-05／06 request logs，675／675 命中，`exact.reasoning_tokens` 累计为 135,479。推导闭合为 `4539201 - 3729865 + 135479 = 944815`，与 921,248 相差 23,567。正文明确称它为探索性趋势和下一轮实验候选，并指出 output reasoning tokens 没有协议保证等于后续 input replay contribution，且累计 response 数与 788 个 candidate reasoning items 的边界不同；没有冒充修复公式。

### C9．PASS

建议顺序先建立或补齐 living token-counting Spec，再调整 provider-chain 计算时机、结构分类、Responses usage 学习与测试层级。正文同时明确用户控制文档仍是需求权威、不得从 buggy implementation 反推合同。它把 scalar calibration 限定为同分布系统偏差的辅助，而将 opaque／media／thinking 的异向结构语义错误作为根因，未把单一 multiplier 当修复。

### C10．WARN

最终列表内部没有冲突，并覆盖了本文最核心的 local-estimator 结论、public path、结构根因、same-request 限定、事故因果否定、探索公式降级和 scalar calibration 边界。不过它没有正向列出“正常增长跨越 922k cap，随后 compaction 得到无可读摘要”这一承重事故结论，也没有说明 LT-01、LT-05、LT-06、LT-08、LT-10～LT-12 等独立 code-audit 处置仍分别成立。因为这些内容在正文 §“本次 overflow 的独立因果链”和处置表中完整存在，缺口不会改变读完整文档后的结论，定为 minor，而非 major。

## Blocker／major findings

未发现 blocker 或 major。

## Minor

### buffered-chat-local-tokenizer-analysis-review-01：开头的用户归属没有随证据给出一手锚

- `severity`：minor
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-buffered-chat-local-tokenizer-analysis.md:14`
- `related_locations`：同文件 frontmatter lines 4～7；三份列名 evidence source
- **证据**：被评文档写“用户的核心判断成立”，但其 `sources` 与本次指定证据范围都没有用户逐字原话或可回指的会话锚。技术判断本身由后文充分支持；缺的是“该判断来自用户”的归属证据。
- **具体失败场景**：后续 Spec 作者把 agent 基于测量得到的诊断误读为用户已经裁决的产品立场，从而跳过本应仍可依证据修订的判断。
- **建议修正**：若没有可引用的一手原话，把“用户的核心判断成立”改成“核心判断成立”；若确有一手来源，则补精确 transcript／message 锚并保留原话的言语行为。

### buffered-chat-local-tokenizer-analysis-review-02：最终证明力列表未完整覆盖正文承重结论

- `severity`：minor
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-buffered-chat-local-tokenizer-analysis.md:104-108`
- `related_locations`：同文件 lines 14～18、60～66、68～102
- **证据**：最终列表覆盖 local tokenizer 的核心正反边界，但未列正向 overflow／compaction 链，也未概括若干与本次倍率独立的已采纳 code-audit 处置。
- **具体失败场景**：只摘录末尾列表的接手者能正确知道“local tokenizer 不是事故根因”，却看不到当前证据正向支持的事故链，或误以为未进入末尾列表的 LT 项未被采纳。
- **建议修正**：在“足以支持”中补一项正向事故链，并用一项概括其余独立 LT 处置仍按表中强度成立；或者把该节标题明确收窄为“核心 tokenizer 倍率结论的证明边界”。

## 否决过的路线及理由

1. **否决把 exact byte-length equality 当作 body identity。** 相同长度不能替代原成功 body hash；只保留强烈推断和明确 falsifier。
2. **否决用 922,000、4,539,201 或 UI 数字冒充失败请求的精确 upstream input count。** 400 body没有该数字；922,000 是 cap，4,539,201 是 local estimate。
3. **否决把 135,479 个 output reasoning tokens直接用作未来 input contribution。** 该关系没有协议保证，且累计 response 与 candidate item 边界不同。
4. **否决把 local defect与同窗出现的 overflow写成因果。** 事故窗口没有 count endpoint call，inference admission也没有运行 whole-request estimator。
5. **否决用单一 multiplier 掩盖结构语义错误。** Image／PDF、thinking 与 opaque reasoning 的误差方向和组成比例不同。
6. **否决为补证据调用真实 upstream。** 本轮全部复核均为已有 capture／log／transcript 上的离线只读探针。

## 搜索面与未覆盖面

已完整读取四份目标／来源文档；读取并核对 `estimators.py`、`driver.py`、`count_tokens.py`、`calibration.py`、`admission.py`、`schema.py`、`scaling.py`、`service.py`、Chat usage parser以及相关用户控制文档；读取 active config、完整 tokenization state、transcript 关键边界、request-log lines 4468 与 4614～4619、首个 rejected capture。离线探针复算了 candidate bytes／SHA／estimate、reasoning mutation、各 item contribution、C1／C3／C8 算术、675 个 response 的 reasoning-token 累计、事故窗口 count-token 与 admission 状态；transcript SHA、record／byte count、estimator SHA、rejected capture SHA 与 request-log 前 4,620 行 SHA 均与来源报告一致。

未执行真实 upstream 请求；未重新验证官方 image／thinking 页面，因为本次处置忠实度只需对照 code audit 原文，且 C1～C10 的承重结论不依赖重新生成这些外部样本；未证明原成功 request 的 cryptographic identity，也未求失败 request 的精确 upstream token count。

## 我最没把握的三个判断

1. **“用户的核心判断”是否在本次未提供的上级会话中有一手原话。** 本评审只能判给定证据范围内无锚，因此把它列为 minor 归属缺口，而不反推用户从未说过。
2. **C10 的“覆盖所有承重结论”是否意在要求逐项重列全部 LT 处置。** 我按最终列表会被独立摘录使用来判断，认定至少应补正向事故链；因正文没有丢失事实而仅定 minor。
3. **LT-06 的既有书面合同是否已经穷尽用户最终产品意图。** 当前 schema、配置样例和 audit 足以判实现与书面合同不一致；被评文档仍保留“改成纯标签须用户重裁”的分叉，因此本轮判 PASS，不把未提供的一手意图补写成事实。

## 执行本契约时遇到的摩擦

- CodeGraph 对 `/home/xp/src/ghc-api-proxy-py` 明确返回未索引，随后按项目规则改用绝对路径 Read 与只读 Python 探针，没有自行建索引。
- Worktree 隔离护栏拒绝两次过长的复合 Bash 探针；已拆成更小的只读命令，并先核对 worktree 与主树 `estimators.py` SHA 完全相同。没有绕过护栏。
- 本 agent 是 leaf executor，未派生 reviewer；这不影响本次指定的独立评审职责。

## 交付声明

delivery_complete: true
completed_at: 2026-09-06
finding_total: 2
blocker: 0
major: 0
minor: 2
nit: 0
