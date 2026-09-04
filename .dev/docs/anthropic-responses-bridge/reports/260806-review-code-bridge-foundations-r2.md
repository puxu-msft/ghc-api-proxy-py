# Bridge foundations merged-state 代码定向复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-bridge` 分支 `integrate/260806-bridge-foundations`，amended `HEAD 6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，相对 base `ed77c9d191df81c451c25161420515cca52ce6a4`；只逐条复核上一轮 `docs/tmp/260806-review-code-bridge-foundations.md` 的两个 major，以及 amended 第三提交为关闭它们而直接修改的生产代码与测试。对照裁决 `docs/tmp/260806-arbitrate-empty-content-turn.md`。未重开其余已评审 foundation 行为，目标树严格只读，唯一写入为主树本报告。
- **总体 verdict**：**可进入下一阶段**。上一轮两个 major 均已关闭，定向复评未发现修复引入的新问题；可以按当前三个 squash commits 的既有顺序回放 `main`。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对视角

- 每次 shell 调用均在同一调用内验证物理 root、分支、精确 HEAD，并执行 `git merge-base --is-ancestor ed77c9d191df81c451c25161420515cca52ce6a4 HEAD`；写报告前后均验证目标 worktree 为 clean。主树另有既存未提交文档工作，本轮未触碰，唯一归属明确的新路径是本报告。
- 对账旧第三提交 `614cacde72568d53170be714ea5c9a9b4d889a05` 到 amended HEAD 的增量：仅 `src/app/protocols/anthropic_responses.py` 增加 6 行 guard，`tests/unit/test_anthropic_responses_request.py` 增加 78 行双角色空 turn 负样本与真实 forward→converter 组合测试；没有夹带其他生产行为。`git diff --check ed77c9d..6a00f6f` 通过，未发现 conflict marker。
- 核对 M1 的最终实现与裁决逐项一致：`src/app/protocols/anthropic_responses.py:374-390` 在 message 遍历边界识别空 list，在 `_convert_blocks()` 前抛 `RequestConversionError`，`code="invalid_content"`，`field_path="messages[i].content"`，稳定 message 不包含用户内容；没有修改共享 Pydantic 模型、没有 drop／merge／占位／degrade。
- 核对 M1 的回归门：`tests/unit/test_anthropic_responses_request.py:82-103` 参数化覆盖 user／assistant 两种空 turn，并把空 turn 夹在相反角色的两个非空 turns 之间；精确断言 typed error code 与原始 index path。既有 `tests/unit/test_anthropic_responses_request.py:19-79` 非空 list 正样本继续通过，防止 guard 误拒合法内容。
- 核对 M2 的组合门：`tests/unit/test_anthropic_responses_request.py:716-766` 导入并调用真实 `responses_reasoning_to_anthropic()`，将产生的 blocks 经 `MessagesRequest.model_validate()` 送入公开 `convert_messages_request_to_responses()`，精确断言 3→3 cardinality、source order、item-local multi-part summary 合成、各 item ciphertext 与 encrypted-only item。
- 在上述精确 HEAD 上以 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-integrate-bridge/src`、`PYTHONDONTWRITEBYTECODE=1`、`pytest -p no:cacheprovider -q` 运行 `tests/unit/test_responses_reasoning.py`、`tests/unit/test_anthropic_responses_request.py`、`tests/unit/test_streaming_resilience.py`，结果为 **85 passed in 1.33s**。独立 `--collect-only -q` 得到 **85 tests collected**，逐 node ID 计数亦为 **85**；该数字口径为上述三个测试文件、`HEAD 6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。
- `base..HEAD` 提交数由 `git rev-list --count` 与 `git log --format=%H | awk` 两种方法独立核对，均为 3；顺序为 `9e5f874d5b547bd9d733b0ee134e165f818de205`、`cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`、`6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。

### 第一人称执行视角

- 执行 `assistant("first") → user([]) → assistant("second")` 与镜像的 `user("first") → assistant([]) → user("second")`：converter 在处理原始 `messages[1]` 时立即以 `invalid_content @ messages[1].content` 失败，不生成可返回的 Responses input，不再可能形成相邻同角色 items；M1 的 silent drop 已关闭。
- 执行三类 Responses reasoning items：summary＋ciphertext、multi-part summary＋ciphertext、encrypted-only。真实 forward helper 产生三个独立 thinking blocks，Pydantic request 保留三个 blocks，公开 converter 依次恢复三个 reasoning wire items；第二项 summary 只在该 item 内合成为 `second + detail`，三个 ciphertext 分别为 `ENC-1`、`ENC-2`、`ENC-ONLY`；M2 的跨片接缝已成为自动回归门。
- 以内存 monkeypatch 做不落盘正控：模拟 pre-fix silent drop 时 user／assistant 两个参数化样本都转红；模拟 producer 把多个 forward blocks 聚合为一个时组合测试转红；模拟 consumer 仅保留最后一个 decoded reasoning item 时组合测试转红。四个正控均因目标断言失败，执行后目标 worktree 仍为 clean。
- 按回放者视角检查提交链：三个提交相对 base 线性排列，当前 amended 第三提交父提交仍为 `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`，修复与测试已包含在第三个 squash commit 中，不需要额外补丁提交。

## 事实性发现

未发现问题。上一轮两个 major 均已关闭，未发现阻断性问题或修复引入的新回归。

## 主观建议

无。

## 结构怪味与方案反思

- **扫描范围与判据**：定向扫描 amended 增量的 converter message 边界、双角色错误合同、forward producer→Pydantic model→公开 converter consumer 三段组合接缝，以及测试对旧 silent-drop／聚合／last-decode 缺陷的判别力；未发现新增的重复实现、职责错位、抽象泄漏或弱一档的平行路径。
- **更好的内部替代方案**：全局收紧 `AnthropicMessage.content` 会改变其他 Anthropic legs 的公共接受域，与裁决冲突；converter-local reject 仍是边界最准确的内部方案。
- **判据判别力**：targeted tests 的正确样本为绿，四项目标缺陷正控均为红；失败分别落在 typed-error 断言、3→3 cardinality／精确 wire 断言，没有依赖无关旁路。
- **成熟第三方方案**：空 turn 的处理是跨协议合同裁决，reasoning cardinality 是项目自有 carrier 接缝；Pydantic 与 pytest 已用于模型校验及回归门，没有缺失可替代这些领域决策的成熟第三方组件。

## 回放结论

**可以**按以下三个 squash commits 的现有顺序回放 `main`：

1. `9e5f874d5b547bd9d733b0ee134e165f818de205` — `fix: preserve reasoning item cardinality`
2. `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` — `feat: add session liveness coordinator`
3. `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` — `feat: convert Anthropic requests to Responses`
