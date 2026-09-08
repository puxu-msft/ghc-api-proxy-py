# Responses semantic parity 独立复验

- **目标**：只读复验 `/home/xp/src/ghc-api-proxy-py-semantic-parity` 的 `fix/responses-semantic-parity@1cde3d58338eeefb3cf8040f970c3612d451668b`。候选 worktree 在复验前后均为 clean；未修改候选生产代码、测试、index、ref 或工作树文件。
- **唯一写入**：本报告 `/home/xp/src/ghc-api-proxy-py/docs/tmp/260807-verify-semantic-parity.md`。
- **行为 oracle**：主树 `docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；执行 oracle `docs/agents/anthropic-responses-bridge/acceptance.md`，SHA-256 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。两个 hash 均以 `sha256sum` 与 Python `hashlib.sha256` 两种原理交叉复核。
- **定向 verdict**：**`FAIL`。** 正常 summary／encrypted、function arguments 冲突、reasoning 两层冲突、两类 done-only 与“静默采用 done”单侧正控均通过；但空 summary＋无／空 `encrypted_content` 的 nonstream 与 stream 都产生了空 thinking block，违反 finalized Acceptance `NS-03` 的“empty payload 且无 summary 不凭空制造可恢复 block”。两路现在彼此一致，但共同采用了错误 expected，因此不能以 parity 自身放行。
- **范围边界**：本 verdict 只覆盖用户指定的 semantic-parity 修复门，不表示完整 Anthropic Responses bridge 已验收。Spec 中“一 reasoning item 一 thinking block”的广义措辞与 Acceptance `NS-03` 对“summary 与 payload 同时为空”的显式零 block expected 存在文字张力；本轮按项目声明为 `FINALIZED_ACCEPTANCE_ORACLE` 的更具体 `NS-03` 执行定向 gate。后续应把该例外同步回 Spec，避免 Acceptance 成为唯一语义来源。

## 独立验收矩阵

| ID | 从冻结合同推导的 expected | 独立输入与观测 | 结果 |
|---|---|---|---|
| SP-01 | 空 reasoning：`summary=[]` 且 `encrypted_content` 缺失时，semantic core 产生零 reasoning block；nonstream 在最终 content 为空时可由协议层补一个空 text block；stream 不产生 `CompletedBlock` | Nonstream 完整 Responses body与stream `output_item.added → output_item.done`分别走真实生产入口。实际 nonstream为`thinking=""`＋项目bare marker；stream为`ReasoningBlock("", None)` | **FAIL** |
| SP-02 | 空 reasoning：`summary=[]` 且 `encrypted_content=""` 与 absent 同义，仍不得凭空制造 reasoning block | 与 SP-01 相同，仅显式传空字符串。实际两路仍分别产生空 thinking／`ReasoningBlock("", None)` | **FAIL** |
| SP-03 | 正常 summary＋非空 encrypted payload：nonstream生成项目主v1 exact carrier；stream采用item done的authoritative summary与ciphertext | `summary="visible"`、added payload=`mid-state`、item done payload=`opaque-😀`。Nonstream signature逐字节等于Spec exact vector；stream得到`ReasoningBlock("visible", "opaque-😀")` | **PASS** |
| SP-04 | Function arguments delta与authoritative done冲突必须typed reject，不得静默采用done | delta=`{"city":"Paris"}`，arguments.done=`{"city":"London"}`。实际抛`ResponsesStreamProtocolError(code="authoritative_arguments_mismatch", event_type="response.function_call_arguments.done")` | **PASS** |
| SP-05 | Reasoning summary delta与summary done冲突必须typed reject | delta=`delta-value`，summary done=`done-value`。实际抛`authoritative_reasoning_mismatch` | **PASS** |
| SP-06 | Reasoning summary done与item done summary冲突必须typed reject，且summary part边界不可静默改写 | summary done=`part-value`，item done=`item-value`。实际抛`ResponsesStreamProtocolError(code="authoritative_reasoning_mismatch", event_type="response.output_item.done")` | **PASS** |
| SP-07 | Function call无delta时，authoritative arguments done＋item done仍是合法完成路径 | arguments.done与item done均为`{"city":"Paris"}`。实际生成`FunctionCallBlock("call_done_only", "weather", "{\"city\":\"Paris\"}")` | **PASS** |
| SP-08 | Reasoning无summary delta／summary done时，authoritative item done可独立提供完整summary与ciphertext | item done提供`summary="done-only"`与`encrypted_content="opaque-😀"`。实际生成`ReasoningBlock("done-only", "opaque-😀")` | **PASS** |
| SP-PC1 | 单侧禁用function一致性校验后，同一冲突oracle必须因“静默采用done”转红 | 仅在验证进程内 monkeypatch `_validate_function_arguments`为空操作，不写候选文件。原冲突输入不再抛错，外层oracle按目标原因转红 | **PASS** |
| SP-PC2 | 单侧禁用reasoning item-done一致性校验后，同一冲突oracle必须因“静默采用done”转红 | 仅在验证进程内 monkeypatch `_validate_reasoning_summary_parts`为空操作，不写候选文件。原冲突输入不再抛错，外层oracle按目标原因转红 | **PASS** |

独立探针共执行13项判定：9项通过、4项失败；4项失败恰好是SP-01／SP-02在nonstream与stream两个入口的观测，进程退出码为1。两个正控均先证明目标变异会让同一oracle按预期原因转红，恢复后候选HEAD与tracked worktree保持不变。

## 阻断缺陷

### F1：空 reasoning 两路共同采用错误语义

- **违反条款**：`docs/agents/anthropic-responses-bridge/acceptance.md:137-142`，尤其`NS-03`的“empty payload且无summary不凭空制造可恢复block”；同时违反living实施门`docs/agents/anthropic-responses-bridge/implementation.md:14,31,217`所冻结的零block parity修复要求。
- **实证失败证据**：固定候选HEAD与目标导入路径后，独立生产入口探针以`summary=[]`分别传入缺失和空字符串payload。关键输出为：`EMPTY_absent_NONSTREAM_ZERO_REASONING=FAIL`，actual是`thinking=""`＋`ghc-api-proxy:synthetic-reasoning:v1`；`EMPTY_absent_STREAM_ZERO_REASONING=FAIL`，actual是`ReasoningBlock(summary="", encrypted_content=None)`；空字符串向量产生同样两项FAIL。独立探针最终输出`total=13 passed=9 failed=4`并以退出码1结束。
- **根因位置**：`src/app/anthropic/thinking/responses_reasoning.py:43-75`无条件为每个结构合法的reasoning item append thinking block；`src/app/openai/responses_stream_parser.py:493-511`无条件把已完成reasoning draft构造成`ReasoningBlock`。候选提交只修改后者与其测试，没有下沉共享的“是否形成semantic block”判定；因此它让stream追随nonstream的旧空block行为，而不是让两路共同服从零block合同。
- **修复路由建议**：根因明确，建议主会话交回implementer。在stream与nonstream共同消费的semantic normalizer／constructor中定义空reasoning判定，避免继续维护两份分支；保留summary-only、非空encrypted-only、一item一block与done-only合法行为。修复后必须复跑本矩阵及单侧正控。

## 实际执行证据

1. 候选自带定向测试：`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-semantic-parity/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest -p no:cacheprovider -q tests/unit/test_responses_stream_parser.py tests/unit/test_responses_anthropic_nonstream.py`，结果`31 passed in 0.38s`，退出码0。该绿色结果未捕获F1，因为现有空reasoning测试把两路的空thinking行为当作expected。
2. 独立静态expected探针：在同一固定HEAD进程中直接调用`convert_responses_response_to_anthropic()`与`ResponsesStreamParser.process()`，不用候选测试helper生成expected；项目carrier exact bytes直接来自冻结Spec。结果`9/13 PASS`、`4/13 FAIL`，退出码1；失败仅为两个空reasoning向量乘两个入口。
3. 全仓pytest：通过唯一nonce `SEMANTIC_PARITY_PYTEST_260807_A71C`绑定物理root、完整HEAD与实际`app`导入路径后执行`python -m pytest -p no:cacheprovider -q tests`，结果`441 passed in 28.50s`，退出码0。
4. Collect-only交叉计数：独立`pytest --collect-only -q tests`被外部`SIGINT`中断，退出码130，未形成可用第二计数；因此`441`只作为本次完成的pytest运行口径，不宣称已用第二种方法交叉验证。
5. 全仓静态门：唯一nonce `SEMANTIC_PARITY_STATIC_260807_C95A`下执行`ruff check src tests`与`pyright --pythonpath <venv-python> src tests`；Ruff为`All checks passed!`，Pyright为`0 errors, 0 warnings, 0 informations`，退出码0。
6. 所有可信执行均绑定`HEAD=1cde3d58338eeefb3cf8040f970c3612d451668b`，并从运行进程内确认`app.__file__=/home/xp/src/ghc-api-proxy-py-semantic-parity/src/app/__init__.py`。候选tracked状态在执行后仍为clean。

## False-green 判别与结构怪味

- `tests/unit/test_responses_stream_parser.py`中的空reasoning测试只证明“stream和nonstream都能产生各自写死的空thinking形状”，未用Acceptance的零block expected裁决两路，属于同源expected共同偏离；候选全仓441项绿色不能覆盖独立F1。
- `src/app/anthropic/thinking/responses_reasoning.py:43-75`＋`src/app/openai/responses_stream_parser.py:493-511`：**同一semantic block形成规则双实现且已经漂移过一次**。处置为本轮阻断F1，要求修到共享normalizer，不建议继续在两路各补条件。
- `tests/unit/test_responses_stream_parser.py`新增冲突与done-only测试：**判据具备正反方向**。运行时单侧变异已证明function与reasoning item-done两条关键oracle会咬住“静默采用done”；本轮无须改生产代码或持久化额外测试资产。

## 方案反思

1. **更好的内部方案**：共享block eligibility／normalization事实优于让stream parser复制nonstream constructor行为；否则下一次empty／strip／malformed策略变化仍会两路漂移。
2. **判据判别力**：冲突与done-only判据已同时防false-green和false-red；空reasoning现有判据只比较实现选择，未绑定冻结expected，独立探针已补上这条缺口。
3. **第三方方案**：该问题是项目特有的Responses→Anthropic语义政策，不适合引入外部库。可复用成熟JSON／schema工具，但不能外包“空reasoning是否形成Anthropic block”的产品合同。

## 最终判定

**`FAIL`。** `1cde3d58338eeefb3cf8040f970c3612d451668b`已经正确拒绝function arguments与reasoning summary的冲突authoritative值，保留done-only合法路径，并通过全仓pytest、Ruff与Pyright；但它把stream修成与nonstream共同生成空thinking block，未满足明确的零block Acceptance expected。修复F1并复跑同一独立矩阵与正控前，不应进入后续route／delivery组合门。
