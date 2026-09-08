# Task 4A 独立 source review

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-prediction` 相对 `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5` 的未提交 source。HEAD 即 base；无 source commit。
- 工作树变化恰为 brief 四个 allowed paths：`prediction.py`（untracked create）、`test_prediction.py`（untracked create）、`scaling.py`、`test_local_estimate_scaling.py`。无 types／features／store／pipeline／`.dev`。
- 判据：Spec §4.1–4.2、§6.0–6.4、§7.3、A5／A8／A15 的 4A 子集；Task 4A brief（READY follow-up）。`260907-task4a-implementation-gpt-m.md` 只作未核验 claim，不当证据。
- 只读：未改、未提交、未启动 4141／shared main。

## 总体 verdict

**APPROVED。** blocker=0，major=0，minor=0。八个承重面在最终状态与独立探针上成立；focused tests `38 passed in 0.51s`。未跑 brief 要求的源码 mutation，不得把本轮绿灯或实现者报告当成 mutation 已验证。

## 八个承重面

1. **Cold aggregate／None vs 0** — `_cold_start_unscaled` 从 fixed+items 求和；任一 item visual `None` 则 visual 项为 0，否则 sum。C01 三例 23.5／29.5／32.5 区分 None／0／known。空 input 得 0 并打 `minimum-one`。
2. **Exact median／intent** — `statistics.median`；四 actual → 100.5；intent 保留全部 source keys。重复 fingerprint group 抛 `ValueError`（探针）。
3. **Prefix total order／per-item suffix** — 自行 `min`（`-item_count, -observed_at_us, boot/request bytes, attempt`），不依赖 snapshot 顺序。Suffix 只切 query `input_item_contributions[item_count:]` 的 known+visual-or-zero+prior，**不读 source whole**。C07：fixed 100／prior 50 的 query vs 无关 source，结果 215（whole 差会得到另一数）。C08 四种 visual；其中 `None→known` 会揭穿 whole all-or-none。
4. **Exact selected 仍建 prefix** — `_build_predictions` 无条件尝试 exact 与 strictly-shorter prefix；C03／C04／C13 均为 `(EXACT, PREFIX, COLD)` 且 selected exact、request intent 只指 exact。
5. **Canonical producer** — keys 按 exact→prefix→cold；champions 按 `PredictionMethod` 枚举过滤 represented；sample_count 1～n／1／0；selected 为第一个 eligible champion。无 profile candidate。
6. **Prequential／actual0** — 已在 samples 或 records 的 key 拒绝。`evaluate`：`type(actual) is int`（拒 bool）、actual0 仅 absolute。
7. **Finalization／wrapper** — `Decimal(str)×Decimal(str)` → `ROUND_CEILING` → `max(1,·)`；拒 bool／non-finite／multiplier&lt;1。探针 `100.5*1.1=111`、`100.1*1.1=111`、`scale_local_estimate(0,1.5)=1`。C12 monkeypatch 证明 wrapper 只 delegate 一次。
8. **纯边界／paths／NoChange** — `prediction.py` 不 import store／Replace／Delete／queue。C14 AST 检查 + caller 显式 `NoPrefixCheckpointChange()`。allowed paths 无泄漏。

`predict_exact_or_prefix` 与 `build_prediction_record` 共用 `_build_predictions`。

## Findings

未发现问题。

## 未采用建议

- 给 C08 的 `0→known` 加大 fixed-context 差，避免个别参数下 whole-cold 差碰巧等于 slice（C07 已绑定该不变量）。
- 给 duplicate exact group、generation mismatch 补正向测试（实现已拒绝，非缺陷）。

## 未验证边界

- Brief §7／§8 的单变量 mutation（漏 prior、exact skip prefix、whole subtraction、先 ceil 再乘、wrapper 旧 0 等）：本轮未改生产文件做破坏实验；实现者报告中的 mutation 记录视为未核验。
- 完整 `tests/unit/tokenization`、`ruff`、`pyright src tests` 未跑。
- `scale_local_estimate` 对现网 `driver.py` 的 0／shortcut 数值差未做 ASGI 探针。
- A45 full-baseline／current-zero、pair index、16／8、drift、Task 5 接线按 non-goals 不在范围。
- C14 的 `LearningUpdate` 只是 caller seam，不是 4A 输出。

## 搜索面

读完 `prediction.py`、`scaling.py`、`test_prediction.py`、`test_local_estimate_scaling.py` diff；`git status/diff --name-status`；独立 python 探针（bool、111、duplicate exact、incompat、empty cold）；focused pytest 38 passed。未读实现者报告当证据。未改文件。

## Commit 前必须检查

隔离树、不碰 shared main／4141：

1. `uv run pytest tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py`
2. `uv run pytest tests/unit/tokenization/`
3. `uv run ruff check` 与 `uv run pyright` 针对四 allowed paths（brief 还要求 `pyright src tests`）
4. 按 brief 执行 C01–C14 源码 mutation 并保留 raw red／restore green
5. `git add` 仅四路径（含目前 untracked 的两个 create）；subject `feat: predict tokens from exact history`

本 review 只执行了第 1 项。

## Verdict

**APPROVED。**
