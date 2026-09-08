# Reasoning carrier v2 独立代码定向复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-carrier-v2` 分支 `feat/reasoning-carrier-v2`，固定 `HEAD=8301ee938601ad86c7f72d313abc6c976a74b2a9`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。仅复核上一轮 `docs/tmp/260807-review-code-carrier-v2.md` 的唯一 major——direct Messages final wire 未剥离 synthetic reasoning carrier——以及本次修复是否误剥 Responses leg；不重新展开 carrier v2 其余已通过项或整分支全量认证。
- **总体 verdict**：**可进入下一阶段**。上一轮唯一 major 已关闭，未发现新 blocker 或 major；本候选可 squash。
- **blocker 数**：0。
- **major 数**：0。
- **squash 判定**：**可 squash**。该结论严格限于本轮定向复评范围。
- **行为 oracle**：current Spec `docs/agents/anthropic-responses-bridge/spec.md` SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，以 `sha256sum` 与 Python `hashlib.sha256` 两种方法交叉验证。相关冻结合同是：direct Messages 无条件剥离整个项目 synthetic namespace、upstream v1 prefix form 与 upstream legacy bare sentinel；真正 Anthropic signature 保留；Responses consumer 继续按双格式识别并恢复合法 carrier。
- **双视角覆盖证据——机械核对**：对账上一轮 major、fix commit `8301ee9`、current Spec 双格式条款、base→HEAD 最终代码与调用点。`src/app/anthropic/request_preparation.py:33-48,64-71` 在最终 request preparation 删除命中的整个 thinking block，并删除剥离后为空的 message；`src/app/anthropic/thinking/reasoning_carrier.py:69-74` 对项目侧按整个 `ghc-api-proxy:synthetic-reasoning:` namespace 匹配，对 upstream 侧按 v1 prefix form 加 legacy sentinel 匹配；其他 signature 不命中。`tests/unit/test_anthropic_client.py:84-142` 经真实 `AnthropicClient.prepare()` 覆盖项目 bare／payload／malformed／unknown、upstream bare prefix／payload／legacy，并断言 `CAIS-real-anthropic` 与邻接 text 保留。调用图复核无 hooks、有 hooks及 approval modified payload 重准备路径均进入 `prepare_anthropic_request()`。
- **双视角覆盖证据——第一人称执行**：以同一 `MessagesRequest` 模拟客户端 echo 项目 v1、项目 unknown、upstream v1 payload、upstream bare、upstream legacy 与真实 `CAIS`。direct Messages leg 的 `AnthropicClient.prepare()` 只留下 `CAIS` thinking；Responses leg 的 `convert_messages_request_to_responses()` 仍恢复项目 v1 与三个合法 upstream 形态，项目 unknown 和 `CAIS` 按既有 degradation 分类丢弃。由此确认修复只作用于 direct Messages final-wire preparation，没有先剥离 Responses converter 所需 carrier。
- **运行证据**：在目标 root／branch／HEAD 与 `PYTHONPATH` import gate 下，以 `PYTHONDONTWRITEBYTECODE=1`、禁用 pytest cache 运行 `test_anthropic_client.py`、`test_anthropic_preparation.py`、`test_reasoning_carrier.py`、`test_responses_reasoning.py`、`test_anthropic_responses_request.py`，定向 suite 通过；另运行同输入双腿黑盒探针，得到 Messages strip、Responses consume 与 `CAIS` Messages preserve 全部通过。pytest 输出的具体用例数未用第二种原理交叉统计，因此不作为本报告验收数字。
- **正反向对照**：进程内 monkeypatch 关闭 synthetic helper 后，项目 carrier 确实泄漏到 Messages final wire；强制 helper 对所有 signature 返回真后，`CAIS` 确实被误剥；恢复真实 helper 后重新得到“synthetic 删除、`CAIS` 保留”。两种错误状态均被目标 final-wire 断言区分，排除了只测低层 helper或错误调用路径的假绿。
- **工作树约束**：所有目标树操作均为只读或禁缓存／禁字节码测试；测试与探针前后目标树均 clean。本报告是唯一写入主树的路径。

## 事实性发现

未发现问题。上一轮唯一 major 已关闭，Responses leg 未被本次 direct Messages sanitizer 误剥。

## 已核对通过的重点

- `is_direct_messages_synthetic_signature()` 不依赖 decode 成功，因此项目 malformed／unknown 仍按整个项目 namespace 无条件剥离，符合 direct Messages 的边界合同。
- Upstream bare prefix `copilot-api:synthetic-reasoning:v1:`、合法／malformed payload form及 legacy sentinel `copilot-api:synthetic-reasoning:v1` 均会从 Messages wire 删除。
- Foreign／真实 Anthropic signature 不命中 direct Messages helper；`CAIS-real-anthropic` 的 final-wire 正样本被保留。
- Responses 请求转换继续直接调用 `decode_anthropic_thinking()`／`decode_reasoning_carrier()`，合法项目 v1 与 upstream v1／bare／legacy 均可恢复；sanitizer 没有进入该 leg。
- 修复位于 `prepare_anthropic_request()`，因此 `apply_payload_rewrites=False` 的 hooks／approval 重准备路径也执行 synthetic strip，不会仅保护普通 `AnthropicClient.prepare()` 路径。

## 结构怪味扫描

- **扫描范围**：fix commit 的 4 个变更文件、direct Messages preparation 调用链、Responses request converter 调用链及相关定向测试。
- **判据**：低层 helper 已实现但 final wire 未接线、Messages／Responses 两腿职责混用、格式识别逻辑重复且漂移、只覆盖漏剥而未覆盖误剥、hooks／approval 分支绕过最终 sanitizer。
- **结果与处置**：未发现新的结构怪味。格式归属仍集中在 `reasoning_carrier.py`，Messages preparation 只消费布尔分类，Responses converter 继续消费完整 decode 结果，职责边界清晰。

## 主观建议

无。

## 结论

上一轮 direct Messages synthetic carrier 未 strip 的唯一 major 已按 current Spec 双格式合同关闭；Responses leg 的 carrier 恢复路径未被误剥，真实 Anthropic `CAIS` signature 在 Messages leg 保留。blocker 0、major 0，明确可 squash。
