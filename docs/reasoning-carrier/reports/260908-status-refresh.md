# Reasoning carrier v2 状态刷新（2026-09-08）

## 审计范围

对照主题 [`spec.md`](../spec.md)，核对旧版 [`tracking.md`](../tracking.md) 中“source unreachable／main 未集成”的陈述、当前 `main` 的源码调用链，以及主仓 git 历史。工作树在审计前已有其他主题的未提交改动；本次没有触碰这些改动。

## 改变

1. 将 `tracking.md` 从 orphaned-source snapshot 改为当前实施账：明确 `main` 已包含 v2，并区分源码实现、已运行测试、未验证的部署/端到端事项。
2. 将旧的点时状态移入 [`history/260904-orphaned-source-snapshot.md`](../history/260904-orphaned-source-snapshot.md)，保留原 worktree、branch、当时“main 未集成”结论及其适用时间，避免把历史事实继续呈现为现状。
3. 保留 P1–P6 的语义，但把它们解释为已落入当前 `main` 的实现范围，不再引用不可达 source clone 作为当前实施依据。

## 代码与 git 证据

- `src/app/pipeline/translation_driver/reasoning_carrier.py` 当前包含 `CarrierRecord`、`encode_reasoning_carrier_v2`、`decode_reasoning_carrier` 及 v2 structural classifications。
- `src/app/pipeline/translation_driver/reasoning_bridge.py` 当前包含 `read_anthropic_reasoning`、`read_responses_reasoning`、`reasoning_to_anthropic`、`reasoning_to_responses`，并实现 slot-aware `classify_anthropic_carrier`／`classify_responses_carrier`。
- `src/app/pipeline/subscribers/reasoning_carrier.py` 的 `guard_and_layout_reasoning` 接入 Anthropic last-mile guard、Responses encrypted-content guard 与 destack。
- `src/app/anthropic/thinking/responses_reasoning.py` 通过 canonical bridge 提供 legacy facade；其他 translation/delivery 调用点通过 `reasoning_to_*` 使用 v2 carrier。
- `b9b0a9bf501f1ce58bb19967dd8cc5670ec0505c`（2026-09-04，`feat: preserve cross-protocol reasoning structure`）包含上述实现及测试，涉及 31 个文件；`git merge-base --is-ancestor b9b0a9bf HEAD` 返回 0。
- 2026-09-08 审计基线 HEAD 为 `d7e71c19`（`main`）；在该基线之后没有审计未来提交是否移除 reasoning carrier 实现。审计时 `git status --short` 显示的改动均不在本主题目录，本次未修改它们。

## 本次实际验证

命令：

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run pytest \
  tests/unit/pipeline/translation_driver/test_reasoning_carrier.py \
  tests/unit/pipeline/translation_driver/test_reasoning_bridge.py \
  tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py \
  tests/unit/anthropic/test_responses_reasoning.py -q
```

结果：`61 passed in 3.40s`。

这证明相关现有单元测试在当前 checkout 通过；它不等同于 production 部署或真实 upstream wire 已验证。

## 未采纳／未做事项

- 未把旧的“main 未集成”继续保留在 current-status 段落；它已作为历史快照保存并可追溯。
- 未将旧快照中的 `2244 passed／2 skipped／91.46%` 当作当前验证数字；本次没有重跑全量 `ruff`、`pyright`、全量 `pytest` 或 coverage。
- 未验证 production 进程、部署版本、运行时配置、真实 upstream wire/canary，亦未重新执行完整 streaming／provider 端到端矩阵；tracking 已明确标为未验证。
- 未执行旧恢复计划（找回原 worktree/bundle、重建 feature/archive、squash/merge），因为当前 git 历史已证明 v2 提交在 `main` 祖先链上。
- 未把任何当前代码事实伪称为用户裁决；本次没有新增待用户裁决项。
- 未修改源码、测试、配置或其他主题；未删除、`git add`、commit、push。

## MSR-07 时间语义修正

为处理 merged-state review 的 MSR-07，本次仅修正时间语义：`tracking.md` 不再把 `HEAD d7e71c19` 写成持续的 current checkout，而明确记录它是 **2026-09-08 审计基线**。同时保留当时可验证的事实：核心实现提交 `b9b0a9bf501f1ce58bb19967dd8cc5670ec0505c` 是该基线 `main` HEAD 的祖先。文档现在不对未来 checkout 的 HEAD 作预测或持续性声明；没有改变实现状态结论，也没有新增代码或测试验证。
