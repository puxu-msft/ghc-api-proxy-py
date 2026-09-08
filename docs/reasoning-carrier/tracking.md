# Reasoning carrier v2 实施状态

> 2026-09-08 审计基线为当时 checkout 的 `main`、HEAD `d7e71c19`；这不是对未来 checkout HEAD 的持续声明。旧的“source unreachable／main 未集成”快照已移入 [`history/260904-orphaned-source-snapshot.md`](history/260904-orphaned-source-snapshot.md)，仅作历史记录，不再作为当前状态。

目标规范：[`spec.md`](spec.md)。

## 当前结论

- **main 已集成 v2 实现**：在 2026-09-08 审计基线中，提交 `b9b0a9bf501f1ce58bb19967dd8cc5670ec0505c`（2026-09-04，`feat: preserve cross-protocol reasoning structure`）是该基线 HEAD `d7e71c19` 的祖先；当时执行的 `git merge-base --is-ancestor b9b0a9bf HEAD` 返回 0。该证据不声称未来 HEAD 仍为 `d7e71c19`。
- 当前源码中存在并被调用的 canonical core 是 [`src/app/pipeline/translation_driver/reasoning_carrier.py`](../../../src/app/pipeline/translation_driver/reasoning_carrier.py) 与 [`reasoning_bridge.py`](../../../src/app/pipeline/translation_driver/reasoning_bridge.py)。
- **production 部署状态未由本次审计验证**；本账不把源码集成推断为部署完成。

## 已在 main 中实现的 v2 行为

| 范围 | 当前证据 |
|---|---|
| typed `CarrierRecord`、canonical v2 envelope 编解码、strict UTF-8／JSON／base64url 校验与分类 | `reasoning_carrier.py` 的 `CarrierRecord`、`encode_reasoning_carrier_v2`、`decode_reasoning_carrier` |
| Anthropic、Responses、Chat Completions 间的 typed reasoning bridge，以及 summary layout／opaque state 回送 | `reasoning_bridge.py` 的 `read_*_reasoning`、`reasoning_to_*`、`_carrier_for_*` |
| slot-aware classification（unsupported／direction／profile／presentation mismatch） | `reasoning_bridge.py` 的 `classify_anthropic_carrier`、`classify_responses_carrier` |
| provider last-mile guard 与 Anthropic destack/layout | `src/app/pipeline/subscribers/reasoning_carrier.py` 的 `guard_and_layout_reasoning`；由 `src/app/anthropic/thinking/responses_reasoning.py` 等调用点接入 |
| streaming、buffered projection、redacted thinking 与 legacy facade 委托 | `b9b0a9bf` 的 31-file diff；相关调用点见 `src/app/pipeline/delivery/`、`src/app/pipeline/translation_driver/`、`src/app/anthropic/thinking/` |

原任务列表 P1–P6 的“已完成”现在可解释为已落入 main 的实现范围；不再解释为不可达 worktree 的点时状态。

## 已验证与未验证

本次直接运行：

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run pytest \
  tests/unit/pipeline/translation_driver/test_reasoning_carrier.py \
  tests/unit/pipeline/translation_driver/test_reasoning_bridge.py \
  tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py \
  tests/unit/anthropic/test_responses_reasoning.py -q
```

结果：`61 passed in 3.40s`。

仍未由本次刷新验证的事项：

- 全量 `ruff`、`pyright`、全量 `pytest` 与 coverage 快照未重跑；旧快照中的 `2244 passed／2 skipped／91.46%` 仍是历史数字。
- production 服务、真实 upstream wire/canary、部署版本与运行时配置未核对。
- 本次未重新执行完整 streaming／真实 provider 端到端矩阵；仅确认其实现与调用点已在 main 中。

这些是验证范围，不是“main 未集成”的证据。

## 当前 test follow-up

- **RC-TF-01 — `reasoning_encrypted_include` default 的 e2e 分辨力；状态：open，待独立复验。** 来源是点时独立评审 [`history/260908-reasoning-encrypted-include-review.md`](history/260908-reasoning-encrypted-include-review.md) 的 `include-01`，不是用户裁决或 current Spec 的修订。该评审指出：默认 `passthrough` 的 e2e control 若没有客户端明确请求 `reasoning.encrypted_content`，把默认值或 composition binding 漂移成 `always_strip` 仍可能全绿，进而静默丢失跨轮所需的 opaque seal。
- 当前源码已可见部分 integration cover，包括 default 的 `reasoning.encrypted_content` request case 及 `ProxyConfig().reasoning_encrypted_include == "passthrough"` 断言；这只是本账登记时的工作树观察，**尚未进行独立复验**，不据此关闭 `RC-TF-01`，也不把历史 review 反写成 current authority。
- 后续独立复验应以 test discriminability 为对象：确认 default 或 composition binding 被受控地变异为 `always_strip` 时，native `/responses` 且客户端请求 `reasoning.encrypted_content` 的 e2e control 必定变红；同时保留正常配置的通过证据。该工作只验证测试护栏，不改写 reasoning-carrier 的产品 contract、配置策略或用户归属。

## 历史计划与当前未采纳事项

- “先找回原 source ref／bundle，再重建 feature／archive 身份、复跑验证并评审集成候选”是旧快照的恢复计划；由于实现已由 `b9b0a9bf` 进入 main，该计划不再是当前行动项。
- 未发现需要把当前代码事实交给用户裁决的事项。Spec 中的规范与此前评审处置仍以本主题文档为准；本次没有把“未重跑”写成失败，也没有把历史 PASS 扩大为当前部署证明。
- 不在本次范围内：修改源码、测试、配置、其他主题文档，或执行 git add／commit／push。
