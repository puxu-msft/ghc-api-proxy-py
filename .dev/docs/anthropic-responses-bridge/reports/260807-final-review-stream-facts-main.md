# Current main stream facts 最终定向复核

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py` 的现场 `main@d903d726baf3f15bf46ddf17384564fee154ed6a`。范围严格限定为 capability → History → stream → stream request facts 的最终合并接缝：request／response conversion facts、observer／success callback 顺序、stream History completed／partial／uncertain 投影、final client-visible response strict validator，以及真实 Anthropic ASGI 主路径。不扩展完整矩阵。
- **总体 verdict**：**可进入下一阶段。** 本限定范围未发现 blocker 或 major。
- **Blocker 数**：**0**，口径仅为上述限定合并态。
- **Major 数**：**0**，口径仅为上述限定合并态。
- **双视角覆盖证据——机械核对**：在同一调用中确认物理 cwd、Git top-level、branch 与完整 HEAD，且 `HEAD == refs/heads/main`；读取最终而非仅 diff 的 `src/app/anthropic/client.py`、`src/app/pipeline/context.py`、`src/app/pipeline/executor.py`、`src/app/history/consumer.py`、`src/app/anthropic/response_validation.py`、`src/app/delivery/responses_anthropic_stream.py`、`src/app/delivery/anthropic_sse.py`、`src/app/routes/anthropic.py` 与 `src/app/streaming/sse.py`；对账既有 stream request-facts 裁决；检查相关测试的正反样本与断言判别力；运行精确选择的最小相关 pytest 节点，退出码为 `0`。
- **双视角覆盖证据——第一人称执行**：模拟 resolved-model capability 进入每次 Responses request conversion；模拟 non-stream 成功与 strict-validation 失败；模拟 success strategy → limiter → `RESPONSE` → completed → `FINALIZE` → History；模拟 stream 的 accepted terminal、post-commit protocol failure、首 body 写入不确定三条真实 ASGI 路径；逐条确认 selected attempt 的 request facts、non-stream response facts、History status、committed prefix、possibly-visible block 与 observer lifecycle 不互相覆盖。

## 事实性发现

未发现问题。

## 主观建议

无。

## 合并态核对

| 接缝 | 结论 | 证据 |
|---|---|---|
| Capability → request conversion | PASS | `src/app/anthropic/client.py:240-269` 从 `prepared.resolved_model` 构造 capability facts，并把它传给 request converter；stream 与 non-stream 均携带该 selected attempt 的 typed request facts。真实 route 测试同时覆盖 capability 正样本与 fail-closed 分支。 |
| Request／response facts | PASS | `src/app/pipeline/executor.py:294-303` 在成功 selected HTTP attempt 的共享 owner 覆盖写入 request facts；`src/app/pipeline/executor.py:367-381` 仅在 non-stream final body 经 strict validation 后追加同 attempt 的 response facts与 typed usage。`src/app/history/consumer.py:125-148` 按 provenance 序列化，不改写 original request payload。 |
| Observer／callback 顺序 | PASS | Non-stream 最终 body 先经过 response hook 与 strict validation，并写入 final payload／facts；随后 `src/app/pipeline/executor.py:382-410` 依次执行 strategy、limiter、`RESPONSE` 与 `FINALIZE`。失败分支不发布 success `RESPONSE`。Stream 在 `src/app/routes/anthropic.py:69-99` 先确定 completed／failed state，再发布 `RESPONSE` 或 `ERROR`，最后发布 `FINALIZE`，之后才写 History。 |
| Strict validator | PASS | `src/app/anthropic/response_validation.py:10-46` 要求显式 `type=message`、`role=assistant`，以 Anthropic SDK `Message` 校验，并遍历所有 content blocks 拒绝判别联合不兼容字段。最小测试同时包含合法 SDK block 正样本与缺字段、mixed fields、unknown block、后续非法 block 反样本。 |
| Stream History completed | PASS | accepted terminal 才令 `terminal_accepted` 为真；route 将 context 转为 `COMPLETED`，History 保存完整 committed blocks、terminal stop reason、usage 与 selected attempt request facts。真实 ASGI 主路径断言最终 Anthropic SSE 与 History 投影一致。 |
| Stream History partial | PASS | post-commit protocol failure 不发送 `message_stop`，context 为 `FAILED`；History 只保存 frontier 已接受的完整 prefix，并附 typed error 与 selected attempt request facts，未把 partial 伪装成 completed。 |
| Stream History uncertain | PASS | 下游 body 写入结果不确定时，frontier 不把该 block 记为 committed；History 保存 `delivery.complete=false`、`delivery.uncertain=true`、envelope states、`possibly_visible_block` 与 `delivery_uncertain` error，同时保留已发生的 selected attempt request facts。 |
| 主路径 | PASS | 精确最小测试包含 resolved-model capability route、request／response facts、callback 顺序、strict failure、stream request facts、真实 chunked Responses SSE → Anthropic ASGI completed、post-commit partial 与 first-body uncertain。测试命令退出码为 `0`，执行前后完整 HEAD 均为 `d903d726baf3f15bf46ddf17384564fee154ed6a`。 |

## 未验证边界

**完整 retry、quota 与真实 partial-write 仍为 `UNVERIFIED`。** 本报告没有扩展 retry 状态空间、request／global quota、resident backpressure、真实 socket partial-write／RST 或完整 Acceptance 矩阵；上述 scoped PASS 不得外推为完整产品 PASS、部署授权或 cutover 授权。

## 结构与方法复核

- **结构怪味扫描**：扫描 `src/app/anthropic/client.py:240-293`、`src/app/pipeline/executor.py:294-410`、`src/app/routes/anthropic.py:35-124` 与 `src/app/history/consumer.py:26-48,125-178` 的事实 owner、stream／non-stream 分叉、重复投影与职责错位。未发现需在本轮修复或记录为 blocker／major 的结构怪味：request facts 位于共享 selected-attempt owner，response facts位于 strict-validated non-stream owner，History 仅做 typed projection，route 独占真实 delivery frontier 的终态判断。
- **更好的内部替代方案**：未发现优于当前“共享 context facts owner＋History projection＋delivery frontier owner”的内部路径；把 stream facts只补在 SQLite 或 route 会重新造成双 owner。
- **判据判别力**：所选测试同时覆盖正确状态可通过与错误状态不可通过；其中 strict validator 有合法／非法双向样本，stream 有 completed／partial／uncertain 三种可观察终态，主路径经过真实 ASGI `Send`，不是仅测试内存 renderer。
- **成熟第三方方案**：strict validator 已复用 Anthropic SDK 的 `Message` schema，而不是手写完整响应 schema；delivery frontier 是本项目特有的下游可见性状态机，未发现可直接替换且保持当前 typed commit 语义的成熟通用库。

## 最终结论

`main@d903d726baf3f15bf46ddf17384564fee154ed6a` 的 capability → History → stream → stream request facts 最后接缝在本限定范围内为 **0 blocker／0 major，明确可继续下一阶段**。完整 retry／quota／partial-write 仍为 **`UNVERIFIED`**。
