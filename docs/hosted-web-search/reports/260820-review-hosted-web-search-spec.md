# 评审报告：`hosted-web-search-spec.md`（2026-08-20 第三批裁决落文后）

- **被评审对象**：`docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md`（未提交工作区文件，评审时 450 行）
- **评审范围**：① 三条用户裁决落进 §3.4／§5／§9.3 之后，全文其余章节是否仍自洽；② 新写条款的可实现性与正确性；③ 规范性「必须」是否有依据。
- **不在范围**：三条裁决本身（§0 已定案，不重开）。
- **verdict**：`needs-fix`。blocker 3、major 9、minor 7。
- **一手核对**：读了在产摊平实现 `src/app/pipeline/subscribers/server_tools.py` 全文；解析了 `tests/cassettes/responses_web_search_stream.json` 的 18 个 chunk（合并后 16 个事件）确认事件时序；核对了 `spec.md` 的 `:8/:136/:159/:181/:261/:326/:537/:582` 与 `src/app/protocols/anthropic_responses.py` 的 `:409/:538-540` 行号引用（**全部准确，无引用漂移**）；核对了 `docs/.human-controlled/config.example.yaml` 的现行配置词汇。

---

## Blocker

### BL-1 §6.3 的成块时点与 §5.3 的 content 判据互斥，流式下无法同时满足

§5.3 的 `web_search_tool_result.content` 三分支依赖两项信息：

1. **本次响应中 `web_search_call` 的总数**（「恰好一个」／「多于一个」）；
2. **后续 message 的 `annotations` 里有没有 `url_citation`**。

而 §6.3 规定「搜索块**必须**且**只能**在 `output_item.done` 此刻一次性完成，随后……按序提交」。这两条在流式路径上不能同时为真——**这是实测，不是推断**。`tests/cassettes/responses_web_search_stream.json` 合并后的事件序列为：

```
response.output_item.added        oi=0  item=web_search_call (无 action)
response.web_search_call.in_progress / .searching / .completed   oi=0
response.output_item.done         oi=0  item=web_search_call (有 action)
response.output_item.added        oi=1  item=message
response.content_part.added       oi=1  annotations=[]
response.output_text.delta ×3     oi=1
response.output_text.done         oi=1
response.content_part.done        oi=1  annotations=[]   ← 引用只在这里才权威
response.output_item.done         oi=1
response.completed                       ← call 总数只在这里才确定
```

即：`web_search_call` 的 `done` 到达时，(2) 尚未出现，(1) 也无法排除后面还会再出现一个 `web_search_call`。按 §6.3 提交，只能永远走第三分支（`unavailable`），第一分支成为死代码，而 §5.2「result 块尽力且不编造」的裁决意图落空；按 §5.3 提交，就违反 §6.3 的「只能在此刻」。同时 §6.3 末条要求「非流式与流式必须对同一语义样本产出等价结果」——非流式一次拿到整个 `output`，两分支都可达，所以现文本下两条路径**必然不等价**。

**修法方向**（规格必须选定一条并写死，不能留给实现者在两条「必须」之间自选）：

- (a) 把这对块的**提交时点**后移：`added` 仍登记 `output_index` 冻结 block index，`done` 时构造 `server_tool_use` 并暂存，`content` 在「响应终态（`response.completed`）」才定稿并整对提交。代价必须一并写出：按 `spec.md` 的「只有最早未提交 block 及其后连续已完成前缀可进入 sink」，扣住 index 0 会把其后的答案文本块一起扣到响应结束，**等于整轮响应在终态才交付**。这个代价是本设计的固有后果，规格应当明说而不是让实现者撞上。
- (b) 或把 content 规则改成不依赖全局信息：例如只依赖「本 item 的 `status`」+「截至提交时刻已见的 citation」，接受第一分支在流式下命中率低。
- (c) 或只对 `server_tool_use` 用 `done` 成块，`web_search_tool_result` 单独延后到 message 结束——但这会破坏 §5.3「两者必须相邻」的约束，除非同时改写该约束。

我的偏好是 (a) 并把交付延迟写进规格；(b) 会让流式与非流式的 content 系统性不同，与 §6.3 的等价要求再次冲突。

### BL-2 §11 覆盖清单仍写「不合成 Anthropic 原生 server block」，与 D6 正相反

- §11 第二行「本规格」栏：「仅 `web_search_call` 改为降级成**一个 Anthropic text block**……**不合成 Anthropic 原生 server block** —— no-revive 的实质在此仍然成立」。
- §11 末段：把 `spec.md:8` 与 `:537` 列为「**未被覆盖，且本规格与之一致**」，理由是「代理仍然……不合成 Anthropic 原生 server block」。

D6 之后这两句都是假的：§5.3 合成的正是 `server_tool_use` + `web_search_tool_result`，即 `spec.md:181` 逐字禁止的「不得合成 Anthropic 原生 server block」，也触及 `spec.md:8`／`:537` 的「不得恢复 Anthropic 原生 server-tool 编排」冻结轴。后果不是措辞难看：**§11 是「本规格覆盖了 `spec.md` 哪几条」的唯一清单，实现者据此判断哪条冻结仍然有效**，现文本会让人按 §11 做出与 §5 相反的东西，或反过来认为 §5 越权而拒绝实现。

**修法方向**：改写第二行，明确「合成 Anthropic 原生 `server_tool_use` + `web_search_tool_result` 一对块」；新增覆盖行覆盖 `spec.md:181`（响应矩阵）与 `:8`／`:537`（冻结轴），并援引 `spec.md:582` M4 的「任何白名单必须另行取得用户裁决」说明 D6 就是那份裁决。同时说清 no-revive 中**仍然成立**的部分（代理不执行搜索、不合成服务端签名结果、`encrypted_content` 不伪造）与**已被定点突破**的部分（原生 server block 的合成）。

### BL-3 §14 仍把 D1／D4／D6 列为待裁决，且「我的偏好」栏是被推翻的那一侧

§0 文档状态写「D1／D4／D6 已裁决」，正文 §3.4／§5／§9.3 已按新裁决重写，但 §14 的表格原封未动：

- D1 偏好栏写 **(a) `REJECT`**，而裁决是「可配置，默认 error」；
- D4 偏好栏写 **(a) 硬编码前缀常量**，并给出「配置键还会碰到 `docs/.human-controlled/config.example.yaml` 的亲笔权威」作为反对配置键的理由，而裁决恰恰选了配置键；
- D6 偏好栏写 **(a) 降级成一个 text block**，并断言「(b) 会产生一个内容为空、且与事实相反的结果块」，而裁决选了 (b)。

§14 标题是「待用户裁决」，是这份规格的裁决账本。任何从 §14 入手的读者（或下一个接手的 agent）会读到与正文相反的三条结论，并可能据此「纠正」正文。

**另有 D5 被新 §5.3 实质推翻**：D5 的选项 (a)「丢弃 + `DEGRADE` fact」是原偏好，而 §5.3 现在**用 `url_citation` 填充 `content`**——既不是丢弃，也不是 (b) 追加正文尾部，也不是 (c) 合成 `citations`。D5 的选项集已不覆盖现行行为。§5.3 那条「不得再重复以 Anthropic `citations` / `web_search_result_location` 形式附加到文本块上」其实已经把 D5 剩下的问题答了一半，那么 D5 真正未决的是什么，必须重新表述；§12 探针表里 P10「决定 D5」的挂钩也随之失效（P10 现在决定的是「是否需要在文本块上补引用」，而 §5.3 已先行给了「不得」）。

**修法方向**：把 D1／D4／D6 移出 §14，改成「已裁决」小节（保留原选项与被否决的理由，符合 `record-what-not-adopted`），偏好栏改写为「用户裁决为 X；起草稿偏好 Y，未被采纳，理由 Z 在新语境下是否仍成立」。D5 重写选项集或标注为「已由 §5.3 部分回答，剩余问题为 …」。

---

## Major

### MJ-1 §12 证据权重表有三条已被推翻、且新增判断全部缺条目

「属设计裁决」表里仍在的过期条目：

| 行 | 现文 | 实际 |
|---|---|---|
| §5.2 | 「**不还原**为 `server_tool_use` + `web_search_tool_result`」 | 裁决为还原 |
| §3.4 | 「域名限制 → `REJECT`；`max_uses` → `DEGRADE`」 | 域名限制现为三值配置，默认 error |
| §9.3 | 「`gpt-5.` **前缀**清单」「唯一两个实测模型都在其下」 | 新文本明确取 `vendor` 而**非**前缀，且清单由配置维护 |
| §5.3 | 「**降级文本形态**与共享渲染」 | 呈现形态已不是降级文本 |

新增的规范性判断**一条都没有进表**：`web_search_tool_result_error` + `error_code:"unavailable"` 的选取、`srvtoolu_ws_<output_index>` 的 id 派生、「多于一个 call 即不归因」、citation 的「按出现顺序 + 按 `url` 去重」、两个配置键的默认值与取值语义。§0 承诺「§12 逐条标注每项规范性要求的依据是实测、设计裁决，还是仍需探针」，该承诺当前不成立。

表里还缺一个类别：这三条是**用户裁决**，既不是实测也不是本规格作者的设计裁决。建议新增一列或一节「用户裁决（不可由实现者重开）」，把 D1／D4／D6 与其落点章节列进去。

### MJ-2 P12 未登记，且没有「核对失败」的备选分支；P6／P8 的时机标注需要升级

§5.3 写「`error_code` 取 `unavailable`，**该取值是否在 Anthropic 该块的合法枚举内，实现前必须核对**（新增探针项 P12）」，但 §12 的「仍需探针」表止于 P11，P12 不存在。两个连带问题：

- 该条同时是一条**规范性「必须」**（「必须」使用 `unavailable`）与一条「未核对」的自述，且**没有给出核对失败时的保守分支**。按 §0「凡标注为『仍需探针』的行为，实现时必须按本规格给出的保守分支执行」，这里没有保守分支可执行。
- **P6**（同一响应内多个 `web_search_call`）在起草稿里只影响论证，现在是 §5.3 第二分支**正确性的前提**，仍标「可后补」不合适；**P8**（`status: searching/failed/incomplete` 的真实形态）现在决定第三分支何时触发，同样应提到「实现前」或明确写出未探针时的行为。

### MJ-3 §3.4 的 `drop_web_search` 未规定同步清理 `tool_choice`

§4 的相关两条都写在配置化之前：

- 「被指向的 web search 声明因**能力门未通过**而被剥离时（§8.3），该 `tool_choice` **必须**同步删除」——只覆盖 §8.3；
- 「被指向的声明因 §3.4 走 **REJECT** 时不适用本节：整个请求已失败」——只覆盖 `error` 取值。

`drop_web_search` 取值下声明被剥离而请求继续，此时若客户端发了 `{"type":"tool","name":"web_search"}`，就会留下 dangling forced choice。上游对此的反应是 400（在产订阅者 `_drop_dangling_choice()` 存在的全部理由），等于用一个配置取值把整轮打挂。这是可实现性缺陷，不是措辞问题。

**修法方向**：§3.4 的 `drop_web_search` 行补一句「按 §4 同步清理指向它的 `tool_choice`」；§4 第二条改写为「因 §3.4 取 `error` 而失败时不适用本节」。

### MJ-4 §3.4 与 §9 能力门的优先级仍按旧裁决表述，且组合情形未定义

§8.3 末条：「**例外且优先**：§3.4 的 `allowed_domains` / `blocked_domains` 非空时走 `REJECT`，该条优先于本节。」两个问题：

1. 措辞过期——只有 `error` 取值才 REJECT；`drop_unsupported_fields` / `drop_web_search` 下这条「优先」是什么意思，没有答案。
2. 真正未定义的组合是：**能力门不通过 + 域名限制非空 + 配置为 `error`**。这次根本不会执行搜索，那么是「因为一条无法表达的收紧约束而失败整轮」，还是「按 §8.3 剥离即可（约束随着能力一起消失，没有语义反转）」？两条都可辩，规格必须选一条。我倾向后者：§3.4 的整个论证前提是「继续搜索且约束被放宽」，能力门不通过时这个前提不成立。

### MJ-5 §9.3 的「默认值由目录派生」两解并存

原文：「**默认值**由目录派生：`vendor == "OpenAI"` **且** `supported_endpoints` 含 `/responses`，2026-08-20 的实时目录下即 `gpt-5.3-codex`……七个。」这句同时可读作：

- (i) **运行期谓词**：每次启动／每次判定都按当前目录算 vendor；
- (ii) **冻结字面量**：把这七个 id 写进默认配置。

差别是真实的，且两解各自与本节别处冲突：(i) 会把将来任何新增的 OpenAI `/responses` 模型**自动**判为支持，与同节「两类误判代价不对称，清单宁窄勿宽」以及「**不得**用模型名做清单之外的任何启发式推断」相抵触（vendor 推断也是推断）；(ii) 则会随目录漂移而过期，而 §9.1 已实测目录会漂（`claude-sonnet-4.5` 消失、`claude-opus-5` 新增）。

**修法方向**：明写二选一。我倾向 (ii) 冻结字面量 + 在默认值旁注明推导规则与推导日期，并说明「新模型需人工加入」是有意成本；这与「假阴性是静默降级、假阳性是可见 400」的取舍一致——(i) 的自动放宽恰好制造假阳性之外的新风险面。

### MJ-6 两个新配置键与人写权威 `config.example.yaml` 的词汇不对齐，且未记账

新引入 `anthropic.hosted_web_search.unsupported_constraints` 与 `anthropic.hosted_web_search.models`。核对 `docs/.human-controlled/config.example.yaml`：该文件使用**扁平顶层键**（`server:`、`inbound:`、`model_mappings:`、`hooks:`、`hook_fix_anthropic_request:` …），**没有 `anthropic:` 顶层命名空间**，最接近的是 `inbound.anthropic_count_tokens`。而该文件是用户亲笔权威，本规格作者不得代改。

§14 D4 的旧理由栏正好点破了这个碰撞（「配置键还会碰到 `docs/.human-controlled/config.example.yaml` 的亲笔权威」）。裁决改选配置键之后，规格既没有把键名重新对齐到现行风格，也没有像 §0 为 `README.md` 记「索引待补」那样，把「需要用户在 `config.example.yaml` 增补这两个键」记成待办。落地时这会变成一次静默的越权改动，或一个读不到配置的实现。

**修法方向**：§0 增一条「配置待补」，列出两个键、建议的扁平键名（例如 `inbound.hosted_web_search:` 下挂 `models` 与 `unsupported_constraints`）与默认值，明写由用户裁定键名与落位；§3.4／§9.3 引用该条。

### MJ-7 §5.3 content 三分支存在双重命中，判定优先级未定

表格三行的条件不互斥：

- 「多于一个 call」 **且** 「无 `url_citation` 或 `status != completed`」→ 第二、三行同时命中，`content` 相同但 `DEGRADE` 编码不同（`web_search_results_unattributable` vs `web_search_results_not_representable`）；
- 「恰好一个 call + 有 citation + `status == "incomplete"`」→ 第一、三行同时命中，`content` **不同**（结果列表 vs error）。

**修法方向**：改成有序判定并写明顺序（建议：先 `status != "completed"` → error；再 call 数 > 1 → error + unattributable；再有无 citation），或给每行补齐互斥前提。顺带把 `status` 的取值面写全（`completed` / `searching` / `incomplete` / `failed` / 未来新值），现在只有 §6.3 提到它们，§5.3 靠一个 `!=` 概括。

### MJ-8 `srvtoolu_ws_<output_index>` 的唯一性范围未声明，且 result 块的键集未冻结

- **同一响应内唯一**：成立，`output_index` 在一次响应内唯一。
- **跨轮次必然重复**：每一轮都从 0 开始，所以一段会话历史里会出现多个 `id: "srvtoolu_ws_0"` 的 `server_tool_use`。在本项目路径上这些块下一轮会被摊平成文本（§5.4），对上游无害；但客户端把 `id` 当 UI key／去重键时会撞，而 Anthropic 原生 id 是全局随机的，客户端没有理由防这种碰撞。
- **形状**：`srvtoolu_` 前缀对，后缀 `ws_0` 与原生的随机串明显不同。目前没有证据表明有客户端校验后缀形状，所以我不把它算作缺陷，但规格应当把「不保证与原生 id 形状一致」写成一条明示的已知偏差，而不是留白。

另外 §5.3 只给了 `server_tool_use` 的**字段表**（四个键冻结），`web_search_tool_result` 块只在正文里提了一句「同 `tool_use_id`」，键集（`type` / `tool_use_id` / `content`）没有像前者那样冻结。同一节两种严谨度，实现者会自行补键。

**修法方向**：明写「唯一性只保证在单次响应内」，或把上游 response id 的短摘要拼进 id；补一张 `web_search_tool_result` 的字段表。

### MJ-9 §5.3 的 error 分支必须写明「裸对象，不是单元素数组」——否则在产摊平实现会静默改变语义

我实际读了 `src/app/pipeline/subscribers/server_tools.py` 并逐形状核对了 §5.4 的摊平路径，结论分三条：

1. **成功分支可行**。`content = [{"type":"web_search_result","url":…,"title":…}]`（**无 `encrypted_content`**）→ `_render_results()` 走 list 分支 → `_describe_one()` 只读 `title`/`url`（`:91-110`，且注释明写 `encrypted_content` 是**故意不读**的）→ 输出 `[web_search results]\n- <title> — <url>`。**缺 `encrypted_content` 完全不影响摊平**，§5.3 的省略裁决在这条路径上无代价。
2. **`server_tool_use` 分支可行**。`name = "web_search"` → `_family()` 命中 → `[web_search] <query>`；`_call_subject()`（`:146-160`）自己也做了 `strip()`。
3. **error 分支形状敏感**。`_failure_of()`（`:113-126`）**只在 `isinstance(content, dict)` 时**判定失败。若实现者把 error 写成 `[{"type":"web_search_tool_result_error","error_code":"unavailable"}]`（单元素数组），`_failure_of` 返回 `None` → 走 list 分支 → `_describe_one` 因无 `url`/`title` 返回 `None` → 最终输出 **`[web_search results omitted]`**。「搜索结果不可得」被静默改写成「结果被省略」，且不报错、不留 fact。

Anthropic 原生形态确实是裸对象，所以现文本不算错；但这是一个**只差一层方括号就静默改变语义**的分歧点，且摊平方与合成方大概率不是同一个人写的。值得在 §5.3 表里钉一句。

---

## Minor

- **mn-1 §2 术语过期**：「**搜索块**：……产生的**那一个** Anthropic content block」与「`web_search_call` 是 item 与 Anthropic block **天然一一对应**的类型」——现在是一对二。§6.3 的同源表述同。
- **mn-2 §7.2 的论证依据过期**：「搜索块以**普通文本**回到客户端」「provenance 已经由搜索块的文本 `[web_search] <query>` 保住」。结论（不做 continuation）不受影响，但依据句已不成立，应改为「由 `server_tool_use.input.query` 保住」。
- **mn-3 §8.4 / §10 分工表措辞过期**：§8.4「**必须**按 §5.3 **降级成文本块**」、§10 表格「上游返回的 server-tool item | 本规格 §5.3 **降级成文本**」，均应改为「按 §5.3 产生 `server_tool_use` + `web_search_tool_result` 一对块」。
- **mn-4 §10 的共享渲染要求需要区分两条路径**：现文只说「rejected／degraded server-tool block → 文本」的渲染必须共享。D6 之后 Responses 腿多了一条「上游 item → Anthropic 原生块」的**合成**路径，订阅者没有对应物，**不共享也不该共享**。文字不区分，读者会以为合成也要塞进订阅者模块。
- **mn-5 §5.2 保留了起草稿的辩论叙事**：「起草时本节的裁决是……用户裁决推翻了它」。作为一份要被实现者当 oracle 读的冻结规格，推翻过程宜留在 §0，§5.2 只留「尽量」的三条边界。
- **mn-6 §5.3 的 strip 理由链条不全**：「`query` **必须**已 strip 首尾空白。上游拒收结尾带空白的 assistant 轮次」——这个块是发给**客户端**的，该理由要到下一轮摊平回上游时才成立。补全链条（并可引用 `_call_subject()` 已做同样处理）。
- **mn-7 §9.3 末段的「运行期信号」无归宿**：那条「发哨兵工具类型、从 400 错误体读回 builtin 清单」的路径既没进 §12 探针表（P1–P11 与它无关），也没进 §13「不做什么」。它是一条真正的候选判据，应当二选一登记，否则下一个人会重新发现一遍。

---

## 关于第三优先（无证据支撑的「必须」）

逐条走过全部规范性要求后，**只有一条**「必须」在没有依据且没有保守分支的情况下写成了硬要求：§5.3 的 `error_code: "unavailable"`（见 MJ-2）。其余「必须」我都能追溯到落点：

- 有实测：§3.1／§3.2／§3.3／§3.4 的「不得写入」、§4 的映射表、§5.1、§6.1、§6.2、§6.3 的「`added` 无 `action`」、§8.1、§9.1、§9.2。
- 明确设计裁决且已标注：§3.3 的五键白名单、§3.5 的去重（挂 P2）、§6.3 的「`done` 无 `added` 补登记」（挂 P7）、§7.2 的不做 continuation、§8.2 的不做反应式路径。
- 明确用户裁决：§3.4 三值配置、§5.3 的还原形态、§9.3 的配置清单——但**都没有进 §12 的权重表**（MJ-1）。
- 未标注但无害的纯设计选择：§5.3 的「按 `url` 去重、按出现顺序」、「不得设置 `stop_reason` 为 `tool_use`」（后者可引 `spec.md:260` 的「只要存在**可执行** tool call」，server tool 不可执行，链条成立）。

另有一处轻微张力，不单列为发现：§3.4 规定「两个字段**值为空数组**时……剥离并记 `DEGRADE`」，而同一段自己说「空清单不表达任何收紧」——按 `spec.md` 对 `DEGRADE` 的定义（「损失必须作为结构化 `ConversionFact`」），一个没有损失的剥离记 `DEGRADE` 略显名不副实。记 INFO 级 fact 或换一个非 `DEGRADE` 的分类更贴切。

## 我核对过但**没有**发现问题的部分（供主会话省去重查）

- `spec.md` 的 `:8`／`:136`／`:159`／`:181`／`:261`／`:326`／`:537`／`:582` 八处行号引用，逐行核对，**内容与引用相符**（`spec.md` 当前 587 行，与 §11 的自述一致）。
- `src/app/protocols/anthropic_responses.py` 的 `:409`（`server_tool_not_supported`，历史块）与 `:538`／`:539-540`（`_reject_extras` 与 typed tool 拒绝）三处引用，**逐字准确**。
- §6.1 的五个事件五个不同 id、§6.2 的三个专有事件无内容增量、§6.3 的「`added` 上只有 `id/status/type`」——我自己解析 cassette 复核，**与规格所述一致**。
- §5.4 的摊平路径对「有 url/title 但无 `encrypted_content`」形状**确实可用**（见 MJ-9 第 1 条），这一条裁决没有实现障碍。
