# Direct buffered Chat Completions 计划验证最终复评

## 评审范围

复评对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，冻结 SHA-256 为 `353e67ec8e4466414160de427612686cb5dcd60cd27a8065ca1033e995a5f3e3`，本轮`sha256sum`回执一致。先复读上一轮报告`260906-plan-verification-rereview.md`，只复核RR-01、RR-02及修订相邻处；未重新展开全计划审计，未执行尚未实现的测试。

## 总体 verdict

**pass，可定稿。** 本轮未发现blocker或major；RR-01、RR-02均已关闭。

**Blocker 数：0。**

## 原finding逐条复评

| 原finding | 结论 | 证据 |
|---|---|---|
| RR-01 | **closed** | `plan.md:252,331`为state及projection／observation定义prospective与current size接口；`plan.md:386-417`引入统一`BufferedMemoryAccount`；`plan.md:424-438`在接纳raw frame和修改state前计入raw、staging、state及并存副本，并增加raw未超cap但raw＋state越界的正例和zero-state-size控制。 |
| RR-02 | **closed** | `plan.md:343`增加choice-0收窄控制；`plan.md:642-646`增加provider重写payload/mode、error-envelope字段丢失／多出fallback、synthetic长度覆盖raw accounting的同入口具名控制，均指定目标断言；`plan.md:861`保留merged-state正反双控要求。 |

## 相邻复核

- Bounded feed仍保留同一transport chunk内`[DONE]`＋越界tail的逐frame接纳与pre-reject／append-first控制（`plan.md:298,424-438`）；统一内存账户没有撤销该已关闭边界。
- 新增state-size口径明确沿用当前`CompletedBlock.size_bytes`风格，并规定replacement/reset归零、projection／observation转移所有权或预留容量（`plan.md:331,424-426`）；没有形成第二套cap或事后检查。
- 新增缺陷控制仍落在现有unit/component／MockTransport入口，没有引入manifest、hash gate、mutation framework或真实provider门；证据层边界继续由`plan.md:22,903-914`约束。
- Task 2／3／5的文件表与精确pytest／Ruff／Pyright命令覆盖新增测试位置（`plan.md:239-248,343-351,361-366,436-438,586-599,656-664`）；未触发`tests/tui`专属suite，也未出现`ruff format`。

## 被否决建议及原因

1. **否决新增Chat cassette、运行P6或真实provider。** 两条finding只涉及本地内存计量与测试分辨力；`plan.md:22,903-914`已如实声明Chat cassette/live缺席，扩大证据层不必要。
2. **否决建立mutation manifest或proof framework。** 修订把具名单变量控制直接放回对应Task及现有测试入口，已满足判据，不需要额外治理装置。
3. **否决要求按Python对象真实heap占用逐对象测量。** Spec采用的是项目既有逻辑held-bytes口径；`plan.md:331`明确与`CompletedBlock.size_bytes`一致，并完整计入同时存活的各槽，当前复评没有依据改写该合同。

## 搜索面与限制

- 复读上一轮报告全文，并读取冻结计划中Task 2、Task 3、Task 5、Task 8及其接口／命令／self-review相邻段落；对照`direct-passthrough/spec.md:694-696`的cap合同。
- 只执行`sha256sum`与只读文件检查；未运行pytest／Ruff／Pyright，因为本轮评的是尚待实施的计划与判据，不把未存在实现的命令记为pass。

## 结论

**可定稿。** RR-01、RR-02关闭；本轮范围内为0 blocker、0 major。
