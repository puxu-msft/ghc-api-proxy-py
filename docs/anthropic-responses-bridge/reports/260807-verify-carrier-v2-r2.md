# Reasoning carrier v2 独立复验 R2

- **总体判定**：**PASS**。
- **候选**：`/home/xp/src/ghc-api-proxy-py-carrier-v2`，branch `feat/reasoning-carrier-v2`，HEAD `8301ee938601ad86c7f72d313abc6c976a74b2a9`。
- **base**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，已验证为候选 HEAD 祖先。
- **oracle**：主树 current `docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，状态 `FINALIZED`。
- **执行约束**：每次 tree-dependent shell 均在同一调用内打印并断言物理 root、branch、完整 HEAD 与 base；候选树全程只读，执行前后 `git status --porcelain` 均为空。唯一持久写入为本报告。

## Spec 独立验收矩阵

| 验收项 | Spec oracle | 独立实证 | 判定 |
|---|---|---|---|
| 项目主 v1 canonical producer／consumer | `spec.md:212-222,525` | 独立常量断言 `opaque-😀` 的完整 canonical signature；验证 URL-safe、无 padding、bare marker，以及 consumer value-exact 恢复 | PASS |
| `copilot-api-js` v1 合法主路径与 legacy | `spec.md:224-232,483,525` | 独立 vectors 覆盖 `ENC==`、`opaque-😀`、bare prefix 与 legacy bare sentinel；均恢复预期 summary／ciphertext 形状 | PASS |
| unknown／foreign／malformed 最低止血 | `spec.md:234-251,483,525` | 独立构造 project unknown、CAIS foreign、非法 alphabet、非 canonical base64url、非法 UTF-8、错误 tag、空 ciphertext、额外字段与 duplicate key；均不进入 Responses wire、不恢复 ciphertext、不泄漏裸异常，并产生稳定 degradation 分类 | PASS |
| 一 item 一 block／encrypted-only | `spec.md:205-210,221,525` | 三个独立 reasoning items 分别为 summary＋ciphertext、summary-only、encrypted-only；forward 产生三个有序 thinking blocks，production Responses converter 恢复三个有序 reasoning items，encrypted-only 未丢失 | PASS |
| direct Messages final wire strip，保留 CAIS | `spec.md:206,222,228,479` | 真实 `AnthropicClient.prepare()` probe 同时输入项目 bare／canonical／malformed／unknown、upstream payload／bare／legacy 与 `CAIS-real-anthropic`；最终 wire 删除前三类 synthetic 整个 block，保留 CAIS block及相邻 text | PASS |
| Responses converter 继续消费 carrier | `spec.md:198-208,525` | 通过 production `convert_messages_request_to_responses()` 验证项目 v1、upstream v1、bare／legacy 与多 item roundtrip；真实入口为 `src/app/protocols/anthropic_responses.py:527` | PASS |

## 运行证据

- **独立 here-doc probe**：从目标树加载 `app` 的路径断言为 `/home/xp/src/ghc-api-proxy-py-carrier-v2/src/app/__init__.py`；输出依次为 `PASS A` 至 `PASS F`、`OVERALL=PASS`、`POST_PROBE_STATUS=clean`。
- **producer-only 正样本变异**：仅以进程内 `mock.patch` 将 `responses_reasoning` 模块使用的 producer 改为 upstream carrier；独立项目主 v1 exact-signature 断言按预期变红，退出 patch 后同一断言恢复为绿。目标树文件未修改。
- **候选交叉回归**：在同调用 gate 下，以 `PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider` 运行五个 carrier 相关 pytest 文件，全部通过；相关生产／测试文件 Ruff 通过；相关生产文件 Pyright 为零错误、零警告。调用以 `POST_TEST_STATUS=clean` 闭合。

## 结论

候选 HEAD 在本轮指定范围内符合 current Spec：项目主 v1 为 canonical producer／consumer；upstream v1 合法主路径与 legacy 仍可消费；unknown／foreign／代表性 malformed fail closed；reasoning 保持一 item 一 block并保留 encrypted-only；direct Messages 的最终 wire 删除项目、upstream 与 legacy synthetic thinking 整个 block，同时保留真实 CAIS；Responses converter 继续消费 carrier。**未发现阻断缺陷或 Spec 偏差。**

本报告为 verifier 叶子执行单元产物，按会话规则仍需由主会话承担独立文档复核义务。