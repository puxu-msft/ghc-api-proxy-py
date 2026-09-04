# Systemd 与 Bridge 三片路径／hunk 重叠只读预检

- **评审范围**：固定 `main@b91e58a29324b11840002efc53ed6f869b800c39`，只读对账 capability `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`、History `b1df8f910c590033e83d5cafcd5e514f12bab937`、stream `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，以及 systemd rebuild `8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`。本报告只列路径／hunk 重叠、推荐集成顺序、最小 tests 与 reviewed-source archive targets；不重审行为，不建立验收矩阵，不执行 squash、commit、ref、测试、部署或运行态动作。唯一主树写入为本报告。
- **总体 verdict**：**可进入下一阶段，但 bridge 三片必须按 `capability → History → stream` 在逐次前进的 new main 上重建／适配，不能串接三份相对旧 `b91e58a…` 的原始聚合补丁。Systemd 应在 bridge 三片完成后，从届时 new main 按 `S3 → S4` 逐片 squash 重建。**
- **blocker 数**：0。
- **双视角覆盖证据——机械核对**：每个承载结论的 shell 都在同一次调用内验证物理 cwd、Git top-level、`main` 分支与 exact `HEAD=b91e58a…`；从 Git commit objects 重算各片 parent、pathset 与 `--unified=0` hunk；在一次性 `git archive` 副本中尝试 bridge 三片的全部排列；查询全部 archive refs 对五个 reviewed-source objects 的命中；一次被共享终端输出污染的 pathset 调用与一次 marker 不完整的 archive 调用均整组作废并重跑。
- **双视角覆盖证据——第一人称执行**：模拟 living checkpoint 后先 squash capability，再以其 main 结果为基线重建 History，再以 capability＋History main 结果为基线重建 stream；随后模拟从该 new main 重建 systemd S3、完成 gate／Plan checkpoint，再重建 S4。任何一步若仍要求旧 `b91e58a…` preimage、覆盖前片结果或跳过片间停止点，均停止。

## 路径与 hunk 重叠

### Bridge 三片

- `src/app/anthropic/client.py`：capability、History、stream 三片共同修改，是唯一三方共享生产路径。
  - capability 与 History 在 base 行约 `20` 的 import hunk 相交。
  - capability 与 stream 在 `_send_responses()` base 行约 `225～227` 的 conversion／stream 分支 hunk 相交。
  - History 与 stream 在 `_send_responses()` base 行约 `241` 的 upstream result／转换载体 hunk 相交。
  - 一次性副本中，无论先应用哪一片，下一份相对 `b91e58a…` 的原始聚合补丁都会在该文件停止。因此不存在可直接串接原始补丁的 bridge 排列；后片必须在包含前片结果的 new main 上重建并重新核对组合结果。
- `src/app/pipeline/executor.py`：History 与 stream 同路径，但共同 base 的零上下文 hunk 不相交。History 修改 response lifecycle／facts 区域；stream 删除旧 stream reject 分支。它仍是组合态复核路径，但不是本轮检测到的直接同行冲突。
- `tests/smoke/test_anthropic_responses_route.py`：capability 与 stream 同路径，零上下文 hunk 不相交。Capability 扩展 reasoning／effort harness 与用例；stream 删除旧 fail-closed stream 测试。重建 stream 时必须保留 capability 新增测试。
- `src/app/routes/anthropic.py`、`tests/http/test_anthropic_routes.py`、`tests/smoke/test_anthropic_responses_stream_route.py`：只由 stream 三片中的最终聚合载荷修改；与 capability／History 无路径重叠。
- `tests/component/test_pipeline_executor.py`：只由 History 修改；与 capability／stream 无路径重叠。

### Systemd 与 Bridge

- Systemd S3 的 `src/app/config/settings.py`、`src/app/config/loader.py`、`src/app/cli.py`、`src/app/graceful_timeout.py`、system unit、deployment README 及其 config／CLI／systemd tests，与 capability、History、stream 的聚合 pathsets **无共同路径**。
- 重点路径中，`src/app/config/settings.py` 只属于 systemd S3；`src/app/anthropic/client.py` 只属于 bridge 三片；`src/app/routes/anthropic.py` 只属于 stream；`src/app/pipeline/executor.py` 只属于 History／stream。Systemd 不触碰后三者。
- Systemd tests `tests/smoke/test_systemd_units.py`、`tests/smoke/test_systemd_user_install.py`、`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py` 与 bridge tests 无共同路径。
- 因此，把 systemd 放在 bridge 三片之后不是为规避 path／hunk 冲突，而是为了遵守 living 文档已冻结的收敛顺序，并确保 systemd 两片都从最终 bridge new main 取得真实 parent、preimage 与 main-side gate。

### Systemd 两片内部

- S3 与 S4 唯一共同路径是 `docs/agents/deployment-systemd/README.md`。S4 的 README patch 以 S3 result 为 preimage，故顺序严格为 `S3 → S4`，不可交换，也不可压成一个 squash。
- `src/app/config/settings.py` 与 `tests/smoke/test_systemd_units.py` 只在 S3；`contrib/systemd/install-user.py` 与 `tests/smoke/test_systemd_user_install.py` 只在 S4。

## 推荐集成顺序

1. 先完成并固定获准的 living checkpoint；记录实际 new main HEAD。
2. **Capability**：从该 main 集成 `8bff1c3…` 的两路径语义，完成 main-side gate后形成独立 non-merge squash commit；随后同步 living facts并归档 reviewed source。
3. **History**：不得直接把 `b1df8f9…` 的旧-base聚合补丁套到 capability 后。以 capability 后 new main 为 parent重建／适配 History，重点人工合成 `src/app/anthropic/client.py`，保留 capability reasoning facts与 History attempt／conversion facts；完成 main-side gate与 merged-state复核后独立 squash、同步 living facts并归档。
4. **Stream**：不得直接把 `f3922a9…` 的旧-base聚合补丁套到 capability＋History 后。以 History 后 new main 为 parent重建／适配 stream，重点合成 `src/app/anthropic/client.py`，并保留 History 的 `AnthropicAttemptResult`／normalized facts；同时复核同路径但 hunk 分离的 `executor.py` 与 route smoke。完成 stream 最小 gate与 merged-state复核后独立 squash、同步 living facts并归档。
5. **Systemd S3 graceful timeout**：**应当在 bridge 三片之后从届时 new main 重建。** `8cae6c2…`只作为 reviewed／verified patch、path与result oracle，不作为可直接写入 main ancestry 的最终 identity。形成独立 S3 squash，完成最小 gate后 fresh 更新并 checkpoint Systemd Plan，再归档 S3 reviewed source。
6. **Systemd S4 rootless installer**：从“S3 squash＋S3 Plan checkpoint”后的 new main 重建 `d3fabfa…` 的 parent-adapted三路径载荷；README preimage必须是实际 S3 result。完成最小 gate、fresh Plan checkpoint与组合态复核后独立 squash并归档 S4 reviewed source。

结论是：**是，systemd 应在 bridge 三片后从 new main 按 S3、S4 逐片 squash 重建。** 路径正交只说明它理论上可提前，不构成调整既有已决顺序的理由；bridge 三片自身存在 `client.py` 实际 hunk 冲突，更不能调整或直接串接旧补丁。

## 最小 tests

以下是每片进入下一片前的最小定向集合；它们不替代各片既有审计已冻结的全仓 pytest、Ruff、Pyright或 main-side identity／blob gate。

### Capability

- `tests/smoke/test_anthropic_responses_route.py` 与 `tests/unit/test_anthropic_responses_request.py` 的 `reasoning or effort or dual_capability` selector。
- 必须从 actual main 导入；完成后至少复核 `src/app/anthropic/client.py` 与 route smoke 的组合结果。

### History

- `tests/component/test_pipeline_executor.py::test_throwing_success_strategy_publishes_only_failure_lifecycle`
- `tests/component/test_pipeline_executor.py::test_success_callbacks_precede_response_commit_once`
- `tests/component/test_pipeline_executor.py::test_valid_final_response_calibrates_once_after_success_facts`
- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_invalid_hooked_responses_body_persists_no_success_facts`

### Stream

- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`
- `tests/unit/test_responses_stream_parser.py::test_empty_text_delta_conflicts_with_nonempty_authoritative_text`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_max_output_tokens_without_usage_uses_estimated_zero_usage`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop`

### Systemd S3

- `tests/unit/test_config_loader.py`
- `tests/unit/test_cli.py`
- `tests/smoke/test_systemd_units.py::test_service_shutdown_and_cgroup_contract`
- `tests/smoke/test_systemd_units.py::test_service_shutdown_contract_rejects_nonpositive_manager_margin`
- `tests/smoke/test_systemd_units.py::test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan`
- 对 system unit 临时副本运行真实 `systemd-analyze verify`；不安装 unit，不连接 manager。

### Systemd S4

- `tests/smoke/test_systemd_user_install.py`
- Installer 的真实 `systemd-analyze --user verify`、默认／`--check`零持久写、临时显式 apply、重复 apply bytes／mtime不变与零 `systemctl`；全部只在临时 XDG根执行。
- S4 后重跑上述 S3 最小集合，防止 README／deadline parent adaptation 漂移。

## Archive targets

当前 archive refs 对下列五个 reviewed-source objects 的命中均为零。Archive 只能在对应 main-side gate完成后创建，且不得指向 rebuilt载体或未来main squash commit。

- Capability：`8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
- History：`b1df8f910c590033e83d5cafcd5e514f12bab937`。
- Stream：`f3922a9ba9f90e4eea598dac1d899ebbe18985e8`；既有审计推荐名称为 `refs/archive/260807-anthropic-responses-stream-route`。
- Systemd S3 reviewed source：`865a5b71210e2436b36786b5de67146939d1e0f5`，不得归档 `8cae6c2…`。
- Systemd S4 reviewed source：`e16c2a700f23f66535e7347ab7357518eb8e56bd`，不得归档 `d3fabfa…`。

Capability、History、Systemd S3与S4的 archive ref名称尚未由现有审计冻结；本报告只冻结 target object，不自行发明长期名称。

## 事实性发现

未发现 systemd 与 bridge 三片的路径或 hunk 重叠。发现 bridge 三片在 `src/app/anthropic/client.py` 有确定的直接 hunk冲突，且任意原始聚合补丁串接都会在该文件停止；因此必须按既有 `capability → History → stream` 顺序逐片从 new main重建。Systemd S3／S4内部则因 deployment README 的 parent依赖保持严格 `S3 → S4`。

## 主观建议

无。推荐顺序直接来自 current living文档的已决执行合同与本轮 Git对象／hunk证据，不另行提出替代流程。

## 报告评审状态

本会话是叶子 reviewer，不能派生另一名 reviewer。本报告包含 current-state与下一动作断言，主会话采用前仍须安排独立复核；本轮没有把自审冒充二次评审。
