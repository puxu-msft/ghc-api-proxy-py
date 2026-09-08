# Responses stream route current WIP 独立定向复评

- **评审范围**：严格只读评审 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 current `feat/anthropic-responses-stream-route`。现场 `HEAD` 仍为 `bc436af647507df4ea45f3b01ca8942fade4f036`，因此按要求评审未暂存 WIP 相对该 HEAD；WIP `git diff --binary` SHA-256 为 `15cd380f95e44da8234101be97afe4b0c681ec9805c7b93716bca9ebb782c992`，status 快照 SHA-256 为 `711f2d221de6c5036acafce446c33b26d9d293f95a829b28a93dd3f5ff5b2ff0`。本轮只复核上一 R2 五项 major：cancel-resilient cleanup、authoritative text 冲突、missing usage／`max_tokens`、delivery-uncertain History、terminal identity／seal；不扩张到 R1 其他范围。候选 worktree、Git refs、服务、进程与环境均未修改；唯一主树写入为本报告。
- **总体 verdict**：**修复 major 后可进入；当前 WIP 不可提交或 squash。** 0 blocker／3 major。五项中，missing usage／`max_tokens`、delivery-uncertain History、terminal identity／seal 的生产路径已关闭；cancel-resilient cleanup 与 authoritative text 仍有可复现缺陷；另有一组修复后未同步的测试 fixture 使定向门保持红。
- **blocker 数**：0。
- **major 数**：3。
- **稳定性判定**：最终进程扫描未发现以候选路径为 cwd 或参数目标的 pytest／Ruff／Pyright；候选最终仍为同一 HEAD、同一 status SHA-256 与同一 diff SHA-256。因此本报告不是 `PENDING`，可以给出 verdict。
- **双视角覆盖证据——机械核对**：每条承载结论的 shell 均在同一调用内打印并校验候选物理 cwd、Git top-level 与完整 HEAD；测试进程扫描在评审前后均为零。逐项读取 current route→delayed ASGI response→parser→delivery frontier→History 最终代码及三份定向测试。借用主树虚拟环境时显式设置候选 `PYTHONPATH`，同一 Python 进程打印的 parser、adapter 与 SSE 模块均解析到候选 worktree。三文件定向 pytest 自报 `3 failed, 76 passed`；该数量未以第二种收集算法交叉验证，仅作为现场输出而非验收阈值。随后 M3／M4／M5 四个具名节点自报 `4 passed`，同样不以数量作为阈值；承载结论的是节点退出码、失败栈、生产探针与候选 diff 前后相同。
- **双视角覆盖证据——第一人称执行**：实际模拟了 disconnect 在首个 `anext()` 内取消且 source `finally` 含两个 cancellation checkpoint；空 text delta 后到达非空 content-part done与item done；缺失 usage 的 `incomplete/max_output_tokens`；首 body send outcome uncertain并进入 route／History；`response.created` 与 terminal id 不同、以及 terminal 后追加 event。另模拟 response-start send失败，观测到只有 headers 为 uncertain，未尝试发送的 `message_start`与block仍为`not_started`，History projection没有夸大客户端可能看到的body。

## R2 五项状态

| R2 major | current 状态 | 证据与判定 |
|---|---|---|
| cancel-resilient cleanup | **未关闭，见 M1** | shield只包住 `body_iterator.aclose()`，但首次 `anext()` 被取消时，source `finally` 已在进入shield前运行并可再次被取消；新增正控现场失败。 |
| authoritative text冲突 | **未关闭，见 M2** | 常规`FIRST／SECOND／THIRD`冲突已有拒绝，但空delta使累计串为空时，content-part done与item done仍可改成任意非空authoritative值并成功产出block。 |
| missing usage／`max_tokens` | **已关闭** | 缺失usage被归一为零值、`usage_estimated=True`，wire成功产生`stop_reason=max_tokens`，History与response observer均记录`usage_facts.estimated=true`；具名route测试退出码为0。 |
| delivery-uncertain History | **已关闭本项** | `committed_response`在无accepted block但frontier uncertain时仍生成immutable delivery projection；首body不确定的route测试保存headers／message_start／block frontier与`delivery_uncertain` error。独立response-start probe又确认未尝试的body保持`not_started`。 |
| terminal identity／seal | **生产路径已关闭；测试残留见 M3** | parser绑定created id并拒绝terminal id漂移；adapter暂存success terminal，只有输入流到达结束边界后才提交`message_stop`，terminal后事件先转Anthropic error而不会先发success terminal。四个参数化具名节点退出码为0；但一个旧smoke fixture没有同步id，导致全组仍红。 |

## 事实性发现

[major] `src/app/streaming/sse.py:90-103,148-152`、`tests/unit/test_streaming_sse.py:88-118` — cancel-resilient cleanup仍未成立，shield进入时机晚于被取消async generator的`finally` — disconnect取消发生在`first = await anext(body_iterator)`内部，source先进入自身`finally`，其checkpoint仍处于外层cancel scope；只有`anext()`完全退出后才会执行`stream_response()`的finally与shield。新增生产正控实际得到`cleanup_finished.is_set() == False`，三文件定向pytest也在该节点失败；这正是R2反例，不是测试环境噪声 — 让首个读取操作本身运行在可被owner等待的独立task中，并把close／History finalize／observer finalize放进有界shielded cleanup task；外层取消后等待该task结束，再传播原cancel。保留带真实checkpoint的首block前、首block后disconnect正控，断言upstream close、History与FINALIZE均恰好一次且无orphan task。

[major] `src/app/openai/responses_stream_parser.py:334-337,350-355,722-729` — authoritative text一致性仍可由空delta绕过 — content-part added只在text非空时追加draft；content-part done与item done又使用`if accumulated and accumulated != authoritative`，把“已收到delta但累计值为空”与“从未收到delta”混为一类。生产探针分别发送一个`output_text.delta=""`，随后给content-part done或item done的authoritative=`"NONEMPTY"`，两条路径都成功返回`CompletedBlock(TextBlock("NONEMPTY"))`。冻结Spec要求累计delta与authoritative final value一致，空串不等于非空串 — 统一以“是否观察过delta事件”而非拼接结果truthiness判断；保存显式`delta_seen`或始终追加空delta，并用`if draft.deltas and accumulated != authoritative`。补三层authoritative任意顺序、空delta／无delta、等值重复与冲突的正反控制。

[major] `tests/smoke/test_anthropic_responses_stream_route.py:327-346,1290-1314`、`tests/unit/test_responses_stream_parser.py:683-725` — terminal identity修复与authoritative text新增测试没有同步fixture，导致R2定向suite确定性红，且红因并非目标行为 — empty-message smoke先创建`resp_semantic_bad`，terminal fixture却仍用`resp_empty`，因此在预期`empty_response_content`前先得到正确的`response_id_mismatch`；reverse-order text正样本已对`msg_reverse`成功发送一次item done，随后又向同一output index发送第二个item done并把id改成`msg_equal`，正确实现必然报`item_id_mismatch`。三文件定向pytest现场的另外两条失败栈与这两个fixture逐字对应 — 把empty terminal id改为created id；删除reverse-order测试尾部第二次错误done，或把它拆成独立parser／独立item。修复后重跑三文件定向suite；不得放宽生产id校验或duplicate-done校验来迎合旧fixture。

## 主观建议

未提出额外主观建议。本轮只处理五项R2 major及其直接测试门，不把完整Acceptance未覆盖范围重报为current缺陷。

## 测试与只读性

- 首次尝试候选本地`.venv/bin/pytest`因候选没有独立`.venv`而退出127；这只是环境事实，不计入产品红绿。随后借用主树虚拟环境，并以候选`PYTHONPATH`与模块绝对路径oracle证明执行的是候选WIP。
- 三文件定向suite退出码为1，现场自报`3 failed, 76 passed`；失败分别是cleanup生产正控、empty-message id fixture和reverse-order duplicate-done fixture。
- M3／M4／M5具名节点退出码为0，现场自报`4 passed`；这只关闭本报告对应路径，不外推完整bridge Acceptance。
- 两个独立只读生产探针退出码均为0：response-start failure只把headers标为uncertain；空delta后非空authoritative在两条路径均被错误接受。
- 每轮测试／探针前后候选status与binary diff SHA-256完全相同；最终相关测试进程扫描为零。候选没有被修改。

## 结论

Current WIP确实关闭了missing usage／`max_tokens`、delivery-uncertain History和terminal identity／seal的生产缺口，但cancel cleanup仍被真实checkpoint正控证伪，authoritative text仍有空delta绕过，且两处陈旧测试fixture使定向门保持红。最终判定为**0 blocker／3 major，修复后再复评；当前不可提交或squash**。
