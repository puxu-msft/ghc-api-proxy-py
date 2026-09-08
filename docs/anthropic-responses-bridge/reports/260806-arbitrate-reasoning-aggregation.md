# 主线 reasoning aggregation 独立裁决

## 评审结论

- **评审范围**：主仓 `/home/xp/src/ghc-api-proxy-py` 固定 `main HEAD=ed77c9d191df81c451c25161420515cca52ce6a4` 的 `src/app/anthropic/thinking/responses_reasoning.py` 与 `tests/unit/test_responses_reasoning.py`；主仓当前工作树中的 `docs/agents/anthropic-responses-bridge/{spec,architecture,research,implementation}.md` 及三份 R2 评审报告；参考仓 `/home/xp/src/copilot-api-js` 固定当前 commit `ccb645f5ea58a17fa6977f47367564b8babb5bba` 的 carrier、nonstream converter、stream converter、reverse consumer、Responses codec 与对应测试。按要求不评 route 实现。
- **总体 verdict**：**修复实现 major 后可进入下一阶段；规格与架构的 reasoning 合同不应为迁就当前聚合 helper而改写。** 当前实现只有 carrier codec与 reverse per-block consumer是正确基础 primitive；forward `responses_reasoning_to_anthropic()` 作为目标 bridge reasoning 实现是错误的。
- **blocker 数**：0。
- **major 数**：2。
- **核心裁决**：用户最高裁决要求兼容 `copilot-api-js` 现有处理**格式**。这冻结的是 synthetic carrier wire grammar与 echo consumer互操作，不等于复制参考仓 nonstream的有损聚合，也不等于复制参考仓 stream的单槽状态机。规格要求一对一、non-empty encrypted-only no-loss、stream按 source identity组装，可以继续使用完全相同的 carrier bytes，因此与最高裁决不冲突。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 均在同一调用内校验主仓完整 HEAD `ed77c9d…` 与参考仓完整 HEAD `ccb645f…`。主仓实现和测试的 worktree blob分别等于该 HEAD blob。规格、架构、研究、实施与 R2报告是当前工作树证据，本轮另记录其 Git status与 blob id，没有误称为 `ed77c9d…` commit tree内容。
- 直接读取参考仓固定 commit object：`synthetic-reasoning.ts:31-67` 定义 wire codec；`responses-to-anthropic.ts:163-173,210-218` 定义 nonstream聚合；`responses-to-anthropic-stream.ts:99-202,228-294` 定义 stream状态；`anthropic-to-responses-request.ts:253-275` 对每个 synthetic thinking block分别重建一个 Responses reasoning item；`codec.ts:239-279` 将 stream translator接到 Messages leg。评审报告只作为线索，不作为事实权威。
- 对账主仓：`spec.md:181-182,203-209,301,305,500-501,526` 明确要求一对一、encrypted-only no-loss、顺序与 provenance；`architecture.md:323-342,366,514-516` 将 source semantic identity与目标 block identity分开建模；`research.md:99-102` 已准确记录参考 nonstream的聚合／错配缺陷；`implementation.md:33-37` 也明确已集成 helper只符合当时冻结的聚合行为，不自动满足目标规格。
- 定向测试 `tests/unit/test_responses_reasoning.py` 在主仓固定 HEAD上得到 `8 passed`。这个绿灯只证明代码符合自身聚合测试，不证明符合目标规格；测试 oracle正是本轮争议对象。

### 第一人称执行模拟

- **carrier wire**：以 `ENC==`、UTF-8／emoji与 bare prefix模拟 producer→client echo→consumer。Python与参考仓都生成 `copilot-api:synthetic-reasoning:v1:` 加 unpadded base64url UTF-8 payload；legacy bare sentinel可识别但不带 payload。此层实现正确。
- **nonstream 双 item**：真实参考 converter和主线 helper都把 `A/ENC-1`、`B/ENC-2` 变成一个 `AB + ENC-2` thinking。这个实测解释了 helper来源，但也确定重现了规格要消除的错配：`A` 的 visible summary被绑定到 `B` 的 continuation payload，`ENC-1`不可恢复。
- **nonstream encrypted-only**：真实参考 converter不生成 thinking，主线 helper返回 `None`；非空 `ENC-ONLY`丢失。复制当前缺陷仍然使用“兼容格式”，但不满足 no-loss产品合同。
- **stream 双 item**：真实参考 translator对两个相邻 reasoning items只开一个 thinking block，拼成 `AB`并使用最后 `.done` 的 `ENC-2`。代码虽然有 `output_index → Anthropic index` map，但 reasoning open block不保存 item identity，ciphertext是request-global单槽。这证明参考 stream实现也不能作为目标 block identity的完整 oracle。
- **stream encrypted-only**：参考 stream可生成空 visible thinking加 `ENC-ONLY` carrier，与其nonstream行为不对称。若把当前 helper当共享语义核心，stream会错误丢失该payload；若按规格逐item组装，则既可no-loss，也不改变carrier格式。
- **reverse逐block恢复**：参考 consumer遍历Anthropic thinking blocks，并在 `anthropic-to-responses-request.ts:268-275` 对每个synthetic block分别产生一个 reasoning item。由此可直接构造两个同格式carrier并分别恢复 `ENC-1`、`ENC-2`；wire grammar没有强迫聚合。

## 三层合同裁决

| 层 | `copilot-api-js@ccb645f…` 事实 | 对目标合同的约束 | 当前主线结论 |
|---|---|---|---|
| Carrier wire格式 | 固定prefix；非空payload为UTF-8→unpadded base64url；empty／absent为bare prefix；legacy bare sentinel可识别；consumer逐block恢复 | **必须byte-compatible**；不得另造schema、tag、item id或认证信封 | `_encode_encrypted_content()`、`_decode_encrypted_content()`与reverse consumer是正确基础 |
| Nonstream聚合行为 | 全部summary拼接，只保留最后非空ciphertext；summary为空不发thinking | 只是参考实现当前行为，同时是已证实的loss／mismatch；“格式兼容”不要求复制 | forward聚合函数违反目标一对一／no-loss规格 |
| Stream block identity | 通用index map存在，但相邻reasoning共用open block和ciphertext单槽；encrypted-only与nonstream不对称 | 目标assembler必须以source identity隔离draft并按semantic order提交；可以继续使用同一carrier builder | 当前helper不是stream primitive，不能作为共享语义核心 |

## 事实性发现

### [major] `src/app/anthropic/thinking/responses_reasoning.py:55-95` — forward helper复制参考nonstream的有损聚合，违反已冻结的一对一／no-loss合同

**问题**：函数接收完整item序列，只返回至多一个block；`summary_text`跨item拼接，`encrypted_content`只保留最后一个非空值，聚合summary为空就返回`None`。因此多个reasoning item的provenance和payload不可逆丢失，encrypted-only forward也被丢弃。

**证据或失败场景**：输入`A/ENC-1`、`B/ENC-2`，实跑得到一个`thinking="AB"`且carrier解码为`ENC-2`；reverse只能重建一个`AB/ENC-2` item，无法恢复`A/ENC-1`与`B/ENC-2`。输入`summary=[]、encrypted_content="ENC-ONLY"`返回`None`。这分别违反`spec.md:203,206-207`和验收`spec.md:500-501`。参考仓得到相同结果只证明缺陷来源，不会把loss变成兼容要求。

**修复建议**：保留codec helper和`anthropic_thinking_to_responses()`；把forward边界改为“一个Responses reasoning item→一个可选／必需的Anthropic thinking block”，或输入序列→有序block列表。每个item单独拼接其summary parts并只绑定自己的ciphertext；non-empty encrypted-only生成`thinking=""`加同格式carrier；absent／empty payload且无summary才可不生成block。不要在route中临时补救。

### [major] `tests/unit/test_responses_reasoning.py:25-30,64-93` 及历史R2结论 — 测试把参考缺陷固化为正确oracle，造成false-green

**问题**：`test_encrypted_only_reasoning_does_not_create_an_empty_thinking_block`主动要求丢失非空payload；`test_reasoning_items_aggregate_into_one_leading_block`主动要求跨item聚合并取`ENC-2`。R2代码复评据“冻结upstream行为”判定两项major闭合，但它没有区分wire格式兼容与转换语义保真，因而裁决轴错误。

**证据或失败场景**：当前定向测试`8 passed`，同时上述双item与encrypted-only场景仍确定丢失信息。也就是说绿灯能与规格失败共存。规格R2和架构R2指出的实现／文档冲突成立；它们不应因参考实现同样有缺陷而被驳回。

**修复建议**：反转这两条测试oracle：encrypted-only必须产生可逐block恢复的carrier；多个items必须产生多个有序blocks且各自byte-exact恢复。保留summary parts在**同一item内部**拼接、empty payload等同absent、last empty value不伪造payload等codec测试。增加缺陷注入控制：恢复旧“全局summary＋最后ciphertext”实现时测试必须变红。

## 对规格、架构与评审分歧的处置

| 对象 | 处置 | 独立裁决理由 |
|---|---|---|
| `spec.md`的一对一、encrypted-only no-loss、顺序合同 | **保留** | 它们是产品语义和可逆性合同；不改变carrier bytes，与“兼容现有处理格式”一致 |
| `architecture.md`的`AnthropicBlockKey`与per-block drafts | **保留** | 这是修复参考stream单槽状态的正确目标；source identity不进入wire carrier，只留在内部facts |
| `research.md:99-102` | **保留** | 它准确把参考nonstream行为识别为反例，而非应照搬的规范 |
| `implementation.md:33-37` | **保留其分歧说明，后续更新实现状态** | 当前文字已避免把已集成helper冒充目标bridge完成；实现修复后再更新状态 |
| `260806-review-code-reasoning-r2.md` | **不采纳其终局判断（C级）** | 它核实的代码事实成立，但把“与参考行为相同”误当“满足目标规格”；事实保留，判断推翻 |
| `260806-review-bridge-spec-r2.md` reasoning major | **采纳** | 它指出当前实现证据与规格相反，并要求不能迁就当前测试放宽一对一／no-loss；与本轮独立oracle一致 |
| `260806-review-bridge-architecture-r2.md` reasoning冲突 | **采纳冲突事实；按目标架构方向收口** | 迁移选择现在已有裁决：保留架构，替换forward聚合实现 |
| route实现 | **不处置** | 明确不在本轮范围；不审handler、transport selection或route wiring |

## 最小处置顺序

1. **只改reasoning primitive与单测，不动route。** 保留prefix／base64url／legacy／foreign／reverse逻辑；把forward从“序列→至多一个block”改成per-item或有序list输出。
2. **先写失败测试。** 覆盖summary-only、non-empty encrypted-only、两个各有summary＋payload的items、同item多summary parts、empty payload、strip option边界；断言block数、顺序、每个carrier byte值与逐blockreverse结果。
3. **加正负控制。** 正确样本允许同item summary parts拼接；缺陷注入为跨item拼接或最后ciphertext覆盖，必须变红。stream侧另测item identity／`.done` authoritative capture，不能复用nonstream聚合expected。
4. **修实现状态引用。** `spec.md:227` 的“待回并”已过期，应改为“codec/reverse已集成，forward cardinality待修”；实现完成后同步`implementation.md`与acceptance证据。规格的行为合同和架构无需降级。
5. **后续stream assembler复用codec，不复用聚合。** 每个reasoning draft保留自己的source identity、summary parts和authoritative `.done` ciphertext；renderer仍调用同一carrier builder，保证wire-compatible。

## 主观建议

[建议] API命名 — 当前`responses_reasoning_to_anthropic`隐藏了返回cardinality — 预期影响是减少调用方把aggregate误当通用转换器 — 推荐修复时采用`responses_reasoning_item_to_anthropic`，并让序列映射由converter／assembler显式完成。

## 最终裁决

**当前实现整体作为目标reasoning bridge实现是错误的；其中carrier codec与reverse per-block consumer是正确、可保留的基础primitive。规格没有错，架构的reasoning identity方向也没有错。** `copilot-api-js` current tree提供了三类不同证据：wire carrier是必须兼容的格式oracle；nonstream聚合是已知有损行为，不是产品语义oracle；stream实现证明identity与authoritative `.done`必须由专用assembler管理，同时其相邻reasoning单槽也不应照搬。最小修法是替换forward聚合cardinality并反转两条错误测试，不改codec、不降级规格、不扩大到route。
