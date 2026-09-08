# Stream request conversion facts 独立定向终审 R2

## 评审范围与总体 verdict

- **评审范围**：只复核 `/home/xp/src/ghc-api-proxy-py-stream-facts` 的 `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b` 相对 base `e9fb2771d6e040c761bb4074e3fcf2547caece28`，并且只处理原 main major 与 `docs/tmp/260807-arbitrate-stream-request-facts.md` 的窄裁决：最终 selected attempt 的 request conversion degradation facts 是否在 completed、post-commit partial failure、delivery-uncertain History 中保留；早期失败 attempt 是否排除；original payload 是否不变；nonstream 是否不回退；无显式 projection 的普通失败是否不扩张。
- **总体 verdict**：**可进入下一阶段；原 major 已按裁决关闭。Blocker：0。Major：0。可以 squash。**
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **候选状态**：候选为单提交 `4fa7a87 fix: persist stream request conversion facts`，累计改动限于 `src/app/history/consumer.py`、`src/app/pipeline/executor.py`、`tests/component/test_history_store.py`、`tests/component/test_pipeline_executor.py`；终审前后候选工作树均干净，`git diff --check e9fb277…4fa7a87` 通过。

## 双视角覆盖证据

### 机械核对

- 对账裁决：request conversion degradation 是在 upstream request 实际发出前已经成立的 observation，不是只有 stream 成功 terminal 才成立的 response-side success fact；裁决明确要求 completed、post-commit partial failure 与 delivery-uncertain 三类显式 stream projection 均保留最终 selected attempt 的 request facts，同时要求早期 attempt reset、无 projection 普通失败不扩张。
- 对账最终 owner：`src/app/pipeline/executor.py:294-303` 只在当前 HTTP attempt 成为成功 selected attempt 时，以覆盖方式写入 `RequestConversionFactRecord`，并写入该 attempt 的真实编号；早期 `429` attempt 不进入 context facts。`src/app/pipeline/executor.py:370-379` 的 nonstream 路径只向同一组 request facts 追加 response facts，没有另建回退 owner。
- 对账 History projection：`src/app/history/consumer.py:36-46,125-148,150-173` 仅在调用方提供显式 response 与 usage 时构造 stream usage summary，并无条件按 typed provenance 序列化该 context 的 request facts；`response is None` 的失败不会走该 projection。
- 对账真实 route 接缝：`src/app/routes/anthropic.py:100-124` 只在 `responses_state.committed_response` 存在时向 History 传 response／usage；partial 与 delivery-uncertain 会在该 projection 上附 error 后保留 request facts，没有 committed projection 时传 `None`，因此普通失败不扩张。
- 对账 original payload 与 retry：`tests/component/test_pipeline_executor.py:1112-1186` 真实执行两次 Responses attempt，断言状态码为 `[429, 200]`、History 只含 attempt `1` 的两个 request degradation facts，并断言 `entry.request_payload == original_payload`。
- 对账 completed／partial／uncertain 与普通失败：`tests/component/test_history_store.py:138-255` 覆盖 completed、post-commit partial failure、delivery-uncertain 三个显式 projection，三者均断言保留 typed request fact；`tests/component/test_history_store.py:258-289` 单独断言无 projection 的 failed History 仍为 `response is None`、`usage is None`，但该 case 未向 context 注入 request fact，判别力缺口见下方 minor。
- 对账 nonstream：`tests/component/test_pipeline_executor.py:1070-1109` 的 retry nonstream 路径断言两次 attempt 后只有 attempt `1`，provenance 顺序为 request、response、response；候选没有把 nonstream 改成 stream-only owner，也没有退回早期 attempt。

### 第一人称执行模拟

1. **retry 后 completed stream**：attempt `0` 返回 `429`，不会发布 request facts；attempt `1` 返回成功 HTTP response，executor 覆盖写入 attempt `1` 的 request degradation；stream terminal accepted 后 route 传 committed response，History 保留 attempt `1` facts 与原始 request payload。
2. **post-commit partial failure**：最终 selected attempt 已按有损 converted wire 发往 upstream，随后至少有 committed prefix，再发生 stream conversion／protocol error。Route 仍传 committed response 并附 error；History 状态为 failed，但保留该 attempt 已经成立的 request-side degradation，不把失败伪装成“请求无损”。
3. **delivery-uncertain**：不确定的是 downstream 写入是否被客户端观察，不是 upstream converted request 是否已经发出。Route 传 uncertain committed projection 并附 `delivery_uncertain` error；History 同时保留 delivery frontier 与 request provenance，两类事实不互相抹除。
4. **nonstream selected attempt**：request facts 在 selected HTTP attempt 的共享 owner 写入，随后 nonstream 只追加同 attempt response facts；早期失败 attempt 不会因 nonstream 路径重新进入。
5. **无 projection 普通失败**：approval／pre-send／HTTP failure，或成功 HTTP 后在形成 committed stream projection 前失败时，History 调用得到 `response=None`、`usage=None`；context 即使暂存 request observation，也不会被扩张成 History usage／conversion facts。

## 测试与判别力

- 使用主树虚拟环境 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`，但设置候选绝对 `PYTHONPATH`；进程内 load oracle 显示 `app` 来自 `/home/xp/src/ghc-api-proxy-py-stream-facts/src/app/__init__.py`。
- 最小相关集合只选择 4 个 pytest node，参数化后实际收集并执行 6 个 case：三种显式 stream projection、无 projection failure、stream retry＋original payload、nonstream retry provenance。结果为 **6 passed**。`pytest --collect-only` 独立确认 **6 tests collected**；没有扩展到完整 route 或全套测试矩阵。
- 正样本对照：保持候选测试不变，改为加载 base `main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 的实现，只运行与修复直接相关的两个 node，参数化后结果为 **4 failed**；四个失败均明确是实际 `conversion_facts == []` 与预期 request facts 不符。该对照证明新增断言会在原缺陷实现上按目标机制转红，而不是因同源 oracle 或未加载候选实现产生假绿。
- 候选测试执行前后 `git status --short --untracked-files=all` 均为空；base 正样本对照前后主树 status digest 保持一致，证明该对照没有新增主树变化。两轮测试均禁用 pytest cache 与 Python bytecode 写入。

## 原 major 处置

原 major **关闭**。其事实部分正确识别了 stream FAILED projection 会携带 request conversion facts，但把这些 request-side observations 归类为 success-only facts，并据此要求失败态固定清空；该归类已经被 `docs/tmp/260807-arbitrate-stream-request-facts.md` 的窄裁决明确驳回。候选现在实现的是裁决要求的边界，而不是扩大失败 History：有 committed／uncertain projection 时保留最终 selected attempt 的 request degradation；没有 projection 的普通失败仍不产生 usage／conversion facts。

## 事实性发现

[minor] `tests/component/test_history_store.py:258-289` — “无 projection 普通失败不扩张”测试没有向 `context.conversion_facts` 注入非空 `RequestConversionFactRecord` — 全测试树中只有 `tests/component/test_history_store.py:199-206` 的显式 projection case 设置了 context request facts；当前无 projection case 即使未来实现错误地按失败 context facts构造 usage／conversion projection，也未必因这条输入转红。当前产品代码 `src/app/history/consumer.py:36-46` 的分支确实在 `response is None` 且 state 为 failed 时跳过 usage 构造，因此这不是现存行为错误，不阻断 squash — 在现有 case 中注入一个 request fact，继续断言 persisted `usage is None`；不新增测试矩阵。

未发现 blocker 或 major；按本轮定向范围，候选可以 squash。

## 主观建议

无。

## 结构怪味扫描

未发现本轮需要修复或记 backlog 的结构怪味。扫描范围为本提交四个变更文件及真实 route 接缝 `src/app/routes/anthropic.py:35-125`；判据为重复事实 owner、stream／nonstream 分叉职责错位、attempt provenance 丢失、projection 条件复制且强弱不一、以及为测试另造产品路径。候选把 request facts 放在 stream／nonstream 共享的 selected-attempt owner，History 只负责 typed projection，真实 route 仍独占 committed projection 判定，没有新增平行实现。

## 方法复盘

1. **更好的内部替代方案**：按 `RequestState.COMPLETED` 限制 facts 会违背裁决，并错误耦合 downstream terminal 与 upstream request provenance；当前“selected attempt 共享 owner＋显式 projection gate”是项目内更准确的分层。
2. **判据判别力**：候选绿测之外，base 正样本对照按同一目标机制转红，证明 completed／partial／uncertain 的保留断言与 retry-stream 断言能够区分误清空；真实 route 与 `HistoryConsumer` 分支的代码对账支持当前无 projection 行为正确，但对应测试未注入非空 context facts，尚不能独立区分未来的边界扩张，已列为 minor。
3. **成熟第三方方案**：本轮是项目内部 typed facts 与 History projection 的语义接线，不存在可替换该领域合同的成熟第三方组件；继续复用现有 `RequestConversionFactRecord`、`HistoryConsumer` 与 route frontier，而不是引入新抽象。

## 范围边界

本终审不重做完整 stream route、response conversion facts、usage 数值、History schema 拆分或其他既有 major 的评审；也不把 6 个定向 case 外推为全量测试通过。结论仅为：原 main major 在既有裁决下已经关闭，且候选对指定五条边界达到 blocker 0、major 0，可以 squash。
