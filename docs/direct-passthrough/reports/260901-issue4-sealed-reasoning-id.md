# issue #4：sealed reasoning item 的 id 被改写，导致下一轮起持续 400

日期：2026-09-01
性质：**实测报告**（point-in-time 记录）。结论已落入 [`../spec.md`](../spec.md) §6.2／§6.4 与该规格 §11 的 **O-2**；以那两处为准，本文只保留证据。

姊妹文档：

- [`260901-issue4-passthrough-400-trace.md`](260901-issue4-passthrough-400-trace.md)——另一位 agent 的代码路径追踪，独立得出同一根因。
- [`260901-review-issue4-artifacts.md`](260901-review-issue4-artifacts.md)——对本文与相应 Spec 修订的独立评审（5 major／2 minor，全部采纳）。**本文第 5、6 节是按该评审改写后的版本。**

## 1. 报告的现象

GitHub issue #4，标题为上游原话 `ChatGPT: The resource you requested was not found.`，附一份 400 捕获（`20260901T163208.536-400-0981e604-…json`，901,008 字节 body）。捕获字段：

```
status              400
upstream            {"error":{"message":"The resource you requested was not found.","code":"invalid_request_body"}}
requested_model     gpt-5.6-sol
resolved_model      gpt-5.6-sol
provider            ghc-msft
endpoint            /responses
translation_required False
route_reason        inbound_format_supported
attempts            1
```

客户端是 Codex CLI（payload 带 `client_metadata.x-codex-*`）。`input` 359 项：function_call 102、function_call_output 102、reasoning 66、message 78（assistant 54／user 16／developer 8）、custom_tool_call 5、custom_tool_call_output 5、additional_tools 1。

## 2. 根因

`ResponsesFramer._item_id()`（`src/app/pipeline/delivery/formats/openai_responses.py`）：

```python
def _item_id(self, prefix: str) -> str:
    return f"{prefix}_{self._response_id}_{self._output_index}"
```

同一个类的 `_reasoning()` 把这个自铸 id 与**上游的** `encrypted_content` 装进同一个 item：

```python
item_id = self._item_id("rs")
...
carrier = decode_reasoning_carrier(str(block.payload.get("signature", "")))
if carrier.encrypted_content:
    item["encrypted_content"] = carrier.encrypted_content
```

`_response_id` 追到 `RequestContext.id` 的 `uuid4()`（链路：`request.py` → `inference.py` → `delivery_policy.py` → `openai_responses.py`）。

**密文与它被签发时的 item id 绑定，上游在回传时校验这个绑定。** id 是我们的，密文是上游的，这一对从写出来的那一刻就自相矛盾。

reasoning carrier（`src/app/pipeline/translation_driver/reasoning_carrier.py`）只保存 `encrypted_content`，**不保存上游的 item id**——原始 id 在 Anthropic 往返里已经丢了，这是结构性成因而非疏漏。

## 3. 实测

除 §3.4 标注者外，全部打真实 Copilot 上游。

### 3.1 排除模型不存在

`GET /v1/models` 返回 57 个模型，`gpt-5.6-sol` **在目录里**（同族还有 `gpt-5.6-luna`／`-sol-fast`／`-terra`）。当日 `requests-20260901.jsonl` 另有 37 次 `haiku → gpt-5.6-luna` 全部 200。所以 400 不是模型问题，与 `code: invalid_request_body` 一致。

### 3.2 逐字段探针：列出的单个字段全部无罪

对 `gpt-5.6-sol` 发最小 Responses 请求，把捕获里可疑的字段逐个单独加回：baseline、`tool_choice`＋`parallel_tool_calls`、`reasoning.effort`、`reasoning.context`、`include:["reasoning.encrypted_content"]`、`prompt_cache_key`、`text.verbosity`、`client_metadata`、`additional_tools`（含嵌套 `namespace`／`custom` 工具）——**这九项全部 200**。

同样 200 的还有：带自铸 id 的 message item、function_call／function_call_output 对、custom_tool_call／custom_tool_call_output 对（带与不带 `additional_tools` 两种）。

**限定**：这些是**单变量**探针，只排除「该字段单独即可致 400」，不排除字段间的组合效应。

### 3.3 命中：带 `encrypted_content` 的 reasoning item

取捕获里那个真实的 reasoning item（`encrypted_content` 10,960 字节），只改 `id`：

| id | 结果 |
|---|---|
| `rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0`（原样，即我们自铸的那个） | **400** `The encrypted content for item rs_136b08ff-… could not be verified. Reason: Encrypted content item_id did not match the target item id.` |
| `rs_resp_202608310314088f84634097214507_1` | **400**，同一句，点名换成这个 id |
| `rs_deadbeefdeadbeefdeadbeef` | **400**，同一句 |
| **删掉 `id` 字段** | **200** |

对照组：同一位置放一个**没有** `encrypted_content` 的 reasoning item（带明文 `content`），无论 id 是原样、删掉、还是补一个空 `encrypted_content`，**全部 200**。

**判据因此是「带密文且 id 对不上」，不是「id 长得奇怪」。**

### 3.4 端到端：旧构建 vs 当前 main

4141 上运行的是 **2026-08-29 的构建**（进程启动时间 `Sat Aug 29 14:25:13`），早于骨架 `01c33f1` 与接线 `1fb37cd`——正是用户当时命中的那个版本。当前 main 的候选跑在隔离 canary（4142，独立 HOME/XDG，`--no-history`）。

| 场景 | 结果 |
|---|---|
| 旧构建，最小 Responses 请求 | 交付的 item id 为 `msg_0e7adf73-6222-4808-877c-872dd1e7babc_0`，即 `_item_id()` 的拼法；response id 是代理自造的 UUID |
| 旧构建，把 issue #4 那份 901,008 字节 body 原样重放 | **400**，报文点名 `rs_136b08ff-…_0` |
| 当前 main，新会话第一轮（流式） | **200**。交付的 item id 是**上游自己的**不透明 base64（无 `rs_`／`msg_` 前缀），reasoning 带 5,240 字节 `encrypted_content` |
| 当前 main，把上一行交付的 item 原样回发（第二轮） | **200**。**正对照**：正确的 id 通得过 |
| 当前 main，同样两轮但**非流式** | 两轮均 **200**；第一轮 reasoning id 同样是上游的不透明 base64，密文 5,176 字节 |
| 当前 main，把 issue #4 那份 body 原样重放 | **400**，同一句 |
| 当前 main，同一份 body 但删掉 15 个带密文 reasoning item 的 `id` | **200** |

最后两行是 Spec §11 O-2 的事实基础：**接线阻止了新的污染，救不了已污染的历史。**

## 4. 措辞差异（未闭合，且它限定了归因的强度）

用户 16:32 收到的是 `The resource you requested was not found.`；16:50 起同一份 body 重放稳定得到 `The encrypted content for item … could not be verified.`。两句都是 400 ＋ `invalid_request_body`，且后者点名的 id 正是本代理自铸的那个。

**我没有闭合「这两句出自同一个校验分支」。** 可能是上游在这几小时内改了文案，也可能存在两个分支——若两次之间上游的行为或校验顺序不同，16:32 那次可能先命中了另一个分支。

**因此「id 缺陷就是 16:32 那次观测的根因」是高置信推断，不是直接观测。** 直接观测到的是：同一份字节今天在同一条腿上被拒，理由逐字点名本代理自铸的 id。这足以支撑处置（缺陷本身与修法都独立成立），但**不得被转述成「已观测」**。

`invalid_request_body` 这个 code 本身在这条腿上零鉴别力（本仓测试注释已记录至少四种无关失败共用它），message 文本也不稳定——**都不要拿来做分类判据**。

## 5. 回归测试（两条，各守一半）

均在 `tests/int/test_pipeline_app.py`：

| 半 | 测试 | 守什么 |
|---|---|---|
| 响应（上游 → 客户端） | `test_a_sealed_reasoning_item_keeps_the_id_its_seal_was_cut_against` | 铸新 id；**以及把上游漂移的两个 id 合并成一个** |
| 请求（客户端 → 上游） | `test_a_sealed_reasoning_item_reaches_upstream_the_way_the_client_wrote_it` | 入站 sealed item 的 id 或密文被删改，或被送进 carrier decoder |

**响应侧的夹具必须带 id 漂移。** `tests/int/cassettes/history_responses_stream.json` 的 `output_index` 0 记录着同一个 reasoning item 在 `added` 是 `id_002`、在 `done` 是 `id_003`，两处都带密文。一个「稳定化」这两个 id 的兼容层会把 `done` 的密文挂到 `added` 的 id 上——**同一种绑定失配，另一条路径**。本报告初版用的是旁边测试的 stand-in（两处拼同一个 id），对这种回归恒等；已改用 `drifting_sealed_reasoning_sse`。cassette 里两处密文都被脱敏成 `placeholder`，所以它说不出真实密文是否也不同，测试因此不断言这一点。

**请求侧此前只有论证没有测试。** Spec §6.4 曾从 `translation_required` 的门推出「回传不会进入 carrier decoder」——那是论证。断言落在本代理**发出的字节**上（`make_client` 的 `seen`），不落在回复上。

**变异校验（2026-09-01，三次，各自命中对应的那一半）**：

| 变异 | 注入点 | 结果 |
|---|---|---|
| A｜退回翻译腿 | `carries_upstream_natively` 返回 `False` | 交付 id 变成 `rs_575d966a-…_0`（与 issue #4 报的同形），**响应侧红**、请求侧绿 |
| B｜统一 item id | `PassthroughFramer.block` 注入「批次内 id 统一为首见的那个」 | `done` 变成 `(id_002, seal-closed)`，**响应侧红**。**旧夹具下此变异为恒等映射、会静默变绿**（按构造，未另跑） |
| C｜请求侧剥离 | `direct_driver/base.py` 注入 §11 O-2 提的那条剥离 | **请求侧红**、响应侧绿 |

三次均以文件快照还原，还原后 `git diff` 对被变异文件为空。B 的第一次尝试因 slotted／frozen dataclass 抛异常而作废——那是崩溃不是「被测试抓到」，重写后才计数。

全量：ruff clean，pyright 0 errors；全量 pytest 见 §7。

## 6. 本报告没有证明的

- **归因**：§4 的措辞分支未闭合，16:32 那次的因果是推断。
- **修复的射程**：证明的是「新会话的 sealed reasoning item 在流式与非流式上各往返一次通得过」，样本各一次两轮对话，同一个 provider、同一个模型、同一天。**绑定行为不可无条件外推到其他 upstream**。
- **组合效应**：§3.2 是单变量探针，不排除字段组合致错。
- **测试的边界**：两条测试跑在手写 stand-in 上，不是 cassette 回放——它们钉的是本代理的行为，不是上游的真实事件序列（漂移那一项的形状取自 cassette，但事件流本身是手写的）。
- **非流式的实现路径**：`/responses` 非流式返回上游同一个 dict、不经 framer，分支在 `src/app/pipeline/reply.py`（`inference.py` 只是调用方）。**该结论现已由 §3.4 的两轮实测支持**；本报告初版把它写成「按构造推断、未实测」，且文件归属写错在 `inference.py`。
- **canary 技能的三处过时**：`.claude/skills/real-copilot-backup-canary` 称 4141 由 Bun 服务占用（现在跑的是本项目）、`--account-type` 选项已不存在、`anthropic.route_override` 配置键已不存在。三处都在本次绕过，**未修技能**。

## 7. 独立评审的处置

[`260901-review-issue4-artifacts.md`](260901-review-issue4-artifacts.md)：blocker 0、major 5、minor 2，**全部采纳，无驳回**。

| # | 发现 | 处置 |
|---|---|---|
| 01 | 响应侧夹具无 id 漂移，辨别不了「合并 id」这种回归 | 改用 `drifting_sealed_reasoning_sse`，并以变异 B 证明新夹具有鉴别力（§5） |
| 02 | 只测响应半程，未测请求半程；Spec §6.4 声称的「已有回归测试」是超范围声称 | 补 `..._reaches_upstream_the_way_the_client_wrote_it`，Spec §6.4 改为两半各一条 |
| 03 | O-2 的「自清」论据不成立（旧构建仍在跑仍在污染；不再新增≠自行清空） | 论据改写、建议置信降为「低」，并补上评审提的更窄识别形态 |
| 04 | 该条目被停在 `deferred.md`，违反该台账自己「产品分叉进 Spec §11」的规则 | D-8 删除，条目移入 Spec §11 作为 O-2 |
| 05 | 措辞分支未闭合，但别处仍把因果说成观测 | §4 重写，限定传播到 Spec §6.2、文首、测试 docstring |
| 06 | 两处全称过头 | 「本轮任何观测都看不出」→ 限定为客户端视角；「没有哪个上游会这么拼」→ 只主张本代理确实这么拼 |
| 07 | 非流式分支的文件归属写错 | 改为 `reply.py`，并顺带把该结论从推断升级为实测（§3.4） |

**评审自身的限定**（它自己声明的）：未跑全量 pytest、未测非流式、未打真实上游。这三项由本报告的 §3.4 与 §5 补上。
