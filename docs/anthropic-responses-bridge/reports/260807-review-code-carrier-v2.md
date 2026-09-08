# Reasoning carrier v2 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-carrier-v2` 分支 `feat/reasoning-carrier-v2`，固定 `HEAD=f19dc32b83f744f088191cf67c21c10b5aeb329c`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。评审最终代码、base→HEAD diff、相关测试与真实 request／direct Messages 接缝；行为 oracle 为用户指定的 current Spec SHA-256 `0d81c21fb6efcc71e217b162418a89cf53cc7f392669e5b0b280651de512691e` 及 `docs/tmp/260807-review-spec-carrier-dual-format.md` 的 0 blocker／0 major 定向结论。主树文档在评审期间被并发修改，后续 SHA 漂移未被静默替换成新 oracle。
- **总体 verdict**：**修复 major 后可进入**。项目主 v1 codec、consumer 顺序、upstream v1 合法主路径、稳定 degradation、逐 item cardinality、encrypted-only、旧常量 shim 与 request converter 顺序均符合目标；但 direct Messages 最终 wire 未执行 Spec 要求的 synthetic thinking unconditional strip。
- **blocker 数**：0。该计数与下方事实性发现列表机械对账。
- **major 数**：1。该计数与下方事实性发现列表机械对账。
- **squash 判定**：当前**不可明确放行 squash**；关闭下述 major 并复评达到 0 major 后，可 squash。
- **双视角覆盖证据——机械核对**：逐行读取 6 个变更文件及 base→HEAD diff；对账 Spec 的项目 v1 canonical JSON／base64url、唯一字段与 duplicate-key gate、first-match-wins 分类、upstream 合法向量、unknown／foreign／malformed 最小止血、一 item 一 block、encrypted-only、旧 `SYNTHETIC_REASONING_*` shim 与 request converter degradation；清点候选树全部真实调用点；沿 `AnthropicClient.prepare()`→`sanitize_messages()`→`prepare_anthropic_request()`→`send_prepared()` 对账 direct Messages 最终 payload；扫描相关测试是否存在 direct-leg 双格式 strip gate。未把每个 Node malformed 边界差异升级为 major。
- **双视角覆盖证据——第一人称执行**：模拟项目主 v1 producer→client echo→Responses consumer、upstream v1／bare／legacy 输入、项目 unknown version、项目／upstream malformed、foreign signature、多 reasoning items、encrypted-only、text／reasoning／tool 交错 request converter，以及同一会话下一轮改走 direct Messages 的客户端路径。最后一路会把项目 bare／malformed／unknown 和 upstream prefix／payload／legacy carrier 原样送往 `/v1/messages`，与冻结合同冲突。
- **运行证据**：在候选 root、branch、HEAD 同调用 gate 与 `PYTHONPATH` import gate 下，carrier／reasoning／request converter 定向 pytest 通过，全量 pytest 通过，全量 Ruff 通过，定向 Pyright 为 0 errors。pytest 输出的用例计数未用第二种原理独立交叉统计，因此本报告不把具体数量作为验收断言。另以独立黑盒矩阵验证 project／upstream 分类、交错顺序和精确 degradation reason；候选树在运行前后保持 clean。

## 事实性发现

[major] `src/app/anthropic/client.py:94-129`、`src/app/anthropic/sanitize/__init__.py:7-27`、`src/app/anthropic/request_preparation.py:16-46` — direct Messages leg 未剥离项目与 upstream synthetic thinking，违反双格式合同 — `AnthropicClient.prepare()` 先调用 `sanitize_messages()`，但后者只处理 tool blocks 与空 text blocks；随后 `prepare_anthropic_request()` 只做 tool preprocessing 与 thinking destack；`send_prepared()` 最终原样发送 `prepared.wire`。真实 final-wire probe 输入项目 bare marker、项目 malformed v1、项目 unknown version、upstream bare prefix、upstream v1 payload、upstream legacy sentinel 与 `CAIS-real-anthropic`，输出仍包含全部输入 signature；`destack_content()` 插入的无 signature 分隔 block不改变该事实。冻结 Spec 要求 direct Messages sanitizer 无条件 strip 整个项目 synthetic namespace、upstream v1 prefix form 与 upstream legacy bare sentinel，同时保留真正 Anthropic signature。失败场景是客户端先收到 Responses bridge 生成的项目 carrier，下一轮因 route policy／能力变化走 direct Messages，代理 carrier 被发送给 Claude，而不是在代理边界被移除。修复建议：在 carrier 模块提供单一、无 decode fallback 的 direct-leg 分类 helper，项目侧按 namespace `ghc-api-proxy:synthetic-reasoning:` 全覆盖，upstream 侧按 `copilot-api:synthetic-reasoning:v1:` prefix form 加 legacy sentinel 精确覆盖；在 `sanitize_messages()` 或最终 payload preparation 中删除对应整个 thinking block，并保留 foreign／真正 Anthropic signature。增加经过 `AnthropicClient.prepare()` 的 final-wire 测试，至少覆盖项目 payload／bare／unknown／malformed、upstream payload／bare／legacy 和 `CAIS-*` 保留正样本，避免只测低层 codec 而再次假绿。

## 已核对通过的重点

- `src/app/anthropic/thinking/reasoning_carrier.py:9-16,52-66` 的新 producer 只输出项目主 v1 bare marker或 canonical payload；固定 emoji 向量、UTF-8、紧凑 JSON 字段顺序、unpadded base64url均与 Spec 一致。
- `src/app/anthropic/thinking/reasoning_carrier.py:69-92` 按项目 bare／payload→项目 unknown version→upstream prefix／bare→upstream legacy→foreign 的顺序 first-match-wins；已识别 payload decode失败不会 fallback 成其他格式。
- `src/app/anthropic/thinking/reasoning_carrier.py:95-143` 对项目 payload执行 canonical base64url、严格 UTF-8、唯一字段、duplicate key、固定 tag与非空 ciphertext gate；upstream只承诺合法 canonical主路径。代表性 malformed收敛到稳定分类，没有裸标准库异常。
- `src/app/anthropic/thinking/responses_reasoning.py:43-80` 维持一 reasoning item一 thinking block、source order、item内 summary拼接与 non-empty encrypted-only no-loss；空／缺失 ciphertext使用项目 bare marker。
- `src/app/anthropic/thinking/responses_reasoning.py:92-119` 与 `src/app/protocols/anthropic_responses.py:526-532` 将 unknown／foreign／malformed整 block从 Responses wire丢弃，并发布精确 classification作为 degradation reason；项目／upstream合法 carrier均恢复 summary与可选 ciphertext。
- `src/app/anthropic/thinking/responses_reasoning.py:15-16,124-127` 保留旧 `SYNTHETIC_REASONING_SIGNATURE_PREFIX`／`SYNTHETIC_REASONING_SIGNATURE` 名称并继续指向 upstream v1，旧 consumer侧常量语义未被项目主 producer改写。
- 真实 forward→`MessagesRequest`→public request converter黑盒路径保持 text／reasoning／tool交错顺序，多个 reasoning items分别恢复，encrypted-only不丢失；request converter其余字段逻辑相对 base仅改变 thinking degradation reason，没有观察到无关回归。
- 未因 Python 与 Node 对每个畸形 payload 的边界不同另报 major；本轮只按冻结合同检查 upstream合法主路径与代表性 malformed最小止血。

## 结构怪味扫描

- **扫描范围**：6 个变更文件、base→HEAD diff、候选全部调用点、carrier→request converter与 direct Messages两条集成路径。
- **判据**：codec重复、producer／consumer常量混淆、跨 item可变状态、旧 API断裂、分类结果在上层被抹平、低层单测未接真实 final wire、与成熟标准库／第三方能力重复造轮子。
- **发现与处置**：`src/app/anthropic/client.py:94-129` — **集成接缝缺失／低层全绿但 final wire 未受保护** — 本轮列为 major，必须修复。除此之外未发现新的结构怪味；base64／JSON使用标准库，Pydantic与pytest继续承担模型及回归门，无需引入新第三方依赖。

## 主观建议

无。

## 结论

候选的大部分 carrier v2 核心合同已正确落地，且 request converter 未被破坏；唯一 major 位于 direct Messages sanitizer 接缝。当前不可 squash。修复该接缝并补 final-wire 回归后，应定向复评该 major；若复评为 0 major，可明确 squash。
