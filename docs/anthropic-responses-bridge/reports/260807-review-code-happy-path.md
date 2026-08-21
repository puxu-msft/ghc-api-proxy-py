# Anthropic Responses happy-path merged-state 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-happy` 分支 `integrate/260807-bridge-happy-path`，固定 `HEAD=d78b3cdc172ecad42873a70f1df31438ecca1663`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。评审四个线性 squash commits：`1ed13ad7e19385b9f86a1cd292547438f6137179` carrier v2、`80b3cfade000cd9e1626074d14b1f9c9d5294891` nonstream、`c950912ad739f85c39397ab0f2c4d25b82dddcb7` stream parser、`d78b3cdc172ecad42873a70f1df31438ecca1663` route policy＋组合 smoke。重点是项目主 carrier、direct Messages strip、nonstream 多 reasoning／public identity、stream parser semantic payload、route policy、组合 smoke 判别力及 commit 内容；usage reasoning detail按已决范围后补，不作为本 checkpoint 阻断项。
- **总体 verdict**：**修复 major 后可进入。** 当前 merged implementation 经独立硬编码 oracle 验证，未发现产品行为 blocker／major；但新增组合 smoke 没有按已冻结集成策略旁路产品 codec 绑定项目主 v1 exact bytes，合同错误的 producer／consumer 同改可以全绿。该缺口违反最终组合硬门，修复并复验前不能给出“四个 commits 可逐个回放 main”的 0-major 放行结论。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：每次采用的 shell 证据均在同一调用内 gate 目标 physical root、branch与精确 HEAD；完整读取最终 carrier codec、reasoning forward／reverse、direct Messages preparation、nonstream converter、stream parser、route policy及全部新增测试；核对四提交线性 parent与改动边界。前三个 squash 的 path集合及每个 blob分别与 reviewed source HEAD `8301ee938601ad86c7f72d313abc6c976a74b2a9`、`7ddf17364d97349638d44352bbd9a9b025723ccc`、`73a6aa114647440262691651cd17e9127785c75a` 完全相等；第4提交的 route source与tests blob等于 `84a22c07db3923768db44a1314e5ae6d5aed2e98`，并仅额外加入预定的 `tests/smoke/test_anthropic_responses_happy_path.py`。固定HEAD调用图确认nonstream真实消费共享carrier producer，parser与route仍保持未接production的checkpoint边界；route输入可由现有 `ModelInfo.supported_endpoints: list[str]` 无损构造，parser无carrier编码依赖，route无网络调用依赖。全量pytest在目标import gate下为`418 passed in 9.42s`，并以同一HEAD的collect-only独立交叉核对为`418 tests collected in 2.40s`；全量Ruff为`All checks passed!`，strict Pyright为`0 errors, 0 warnings, 0 informations`，各门后目标树均clean。
- **双视角覆盖证据——第一人称执行**：从Responses两个reasoning items执行nonstream转换，确认一item一thinking block、source order与encrypted-only保留；以Spec硬编码的`opaque-😀`项目主v1完整signature检查公开block，再经reverse consumer value-exact恢复；把同一block送入direct Messages final preparation，确认synthetic block被删除而`CAIS-native`保留。模拟stream reasoning的added draft→authoritative item done，确认`ReasoningBlock("visible", "opaque-😀")`取done payload；模拟双endpoint默认Messages以及route capability／transport正交边界。最后只把产品模块的项目carrier版本常量从v1变异为v9，再全新导入组合smoke；现有nonstream与stream carrier组合smoke仍打印`PRODUCT_ONLY_MUTATION_SURVIVED=yes`，机械证明该gate存在false-green。

## 事实性发现

[major] `tests/smoke/test_anthropic_responses_happy_path.py:96-113,147-149`——组合 smoke 的carrier expected由产品常量、产品encoder和产品decoder共同控制，未独立绑定current Spec项目主v1 wire——nonstream用例只检查`PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX`并把actual交回`decode_reasoning_carrier()`，stream用例则直接调用`encode_reasoning_carrier()`后再由同一codec decode；因此producer／consumer与测试expected可一起漂移。有效进程内变异只把产品模块的项目carrier版本常量改成错误v9，再全新导入测试模块；两条测试仍打印`PRODUCT_ONLY_MUTATION_SURVIVED=yes`；恢复真实实现后，旁路产品codec的硬编码完整signature oracle通过，说明当前产品bytes正确、缺陷位于提交内回归门而非当前实现——在组合smoke中加入独立静态项目exact vector：直接断言nonstream公开thinking block的完整signature等于Spec固定bytes，并把该block送入公开reverse consumer验证value-exact echo；stream路径应从parser的`ReasoningBlock`进入未来共享renderer／producer后对同一固定bytes断言，当前尚无renderer时至少不得用产品encoder生成expected。随后重跑该测试的正反控制，确认错误version／namespace／tag／字段集合／padding任一变化均因目标wire断言变红。

## 主观建议

无。Usage reasoning detail、完整stream grammar／framing／sequencer及route handler／transport接线均是已记录的后续required范围，本轮不把它们升级为checkpoint major，也不删除或降级这些长期要求。

## Commit内容与回放结论

- `1ed13ad`：carrier v2完整source range的精确path集合与reviewed source逐blob等价；项目主v1 producer、双格式consumer与direct Messages strip在merged state保持一致。
- `80b3cfa`：nonstream的精确path集合与reviewed source逐blob等价；真实消费前序carrier，共享producer顺序依赖已满足；多reasoning、encrypted-only、opaque public `msg_` identity与upstream identity内部保留未发现merged回归。
- `c950912`：parser的精确path集合与reviewed source逐blob等价；仍只发布immutable semantic facts，authoritative done payload与source／completion order未被其他切片改写。
- `d78b3cd`：route policy的精确source path集合与reviewed source逐blob等价，额外组合smoke属于本提交预定内容；pure route precedence、unknown fail closed与protocol／transport正交未发现实现问题，但组合smoke存在上述major。

**当前不能明确放行四个 commits逐个回放main。** 关闭上述唯一major并对新bytes完成定向复评后，若仍为blocker 0／major 0，则这四个线性squash commits可按`1ed13ad → 80b3cfa → c950912 → d78b3cd`逐个回放main；该放行仍只表示happy-path checkpoint可继续，不表示完整bridge产品PASS，产品继续为`UNVERIFIED`。
