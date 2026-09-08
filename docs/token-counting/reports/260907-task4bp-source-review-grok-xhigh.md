# Task 4B-P 独立 source review

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction` 相对 `3badac7f6b020764cf8e30b2528ff51055dad0c2` 的未提交 diff。HEAD 即 base；无 source commit。
- 变化仅 brief 两 allowed paths：`src/app/tokenization/prediction.py`、`tests/unit/tokenization/test_prediction.py`（+889/−13）。
- 判据：修订后 Spec A45（正 known delta）、§5／§6.2、Plan Task 4B-P、READY brief。实现者 follow-up 报告不当证据。
- 只读：未改、未提交、未启动 4141／shared main。

## 总体 verdict

**APPROVED。** blocker=0，major=0，minor=0。Pair index、single canonical base、full baseline／current-zero、all-available learned variants、newest31／min8／strict-better／tie 在最终状态与探针上成立；`test_prediction.py` **36 passed in 0.40s**。未跑 brief 源码 mutation，不得把本轮绿灯当 mutation 已验证。

## 承重面

1. **Index bound／order／availability** — `PrefixPairIndex` 绑 identity／epoch／revision；mismatch `ValueError`。Builder 要求 positive unique `committed_order`，按 order＋key 排序后单向插入；lookup 只含严格 earlier。C01 reverse 相等；future order3 不能配 order2；duplicate order 拒绝。探针：同 `observed_at_us`、order 1／2 仍成 pair。
2. **Single canonical base** — 按 coverage → observed_at → boot／request bytes → attempt；lookup 同 key 只留 preferred。C02 在短／旧／newer／BINARY／numeric 竞争下只选 `numeric_winner`。
3. **Full baseline／tri-state／current-zero** — historical／current suffix 均为 appended `known+visual_or_zero+prior`。C04 三对 known 正、visual／prior 正、actual＝full → residual／ratio 0，candidate 110。C05 四 visual。C06：2 对无 variant；3 对 multiplicative；第 4 对 baseline 0 只进 additive（count 4 vs 3）；current suffix 0 时 multiplicative＝anchor actual 100。
4. **All variants／newest31／ties** — exact 仍保留 det＋add＋mul＋cold（C07），prefix champion 可为 additive，global selected／intent 仍 exact。&lt;8 条 det；8 条 strict better 才 learned；全平 det（C08）。63 条 older32 挺 additive、newest31 挺 det → PREFIX（C09，用满 63 会变成 additive）。`evaluations=()`（C10）。缺 mul 的 9 条不占共同窗口（C11）。
5. **4A 不回退／pure** — 无 prefix 时仍 cold；无 store／Replace／Delete。keyword-only `prefix_pair_index`。4A 原测试仍在同一文件中通过。
6. **测试分辨力** — C04／C06／C09 的 expected 与 known-only、current-zero gate、全 63 条会给出不同 champion／count。本轮未做源码破坏。

## Findings

未发现问题。

## 未采用建议

- 把 C01 的 same-time pair 写成正式 test（探针已过，实现已做）。
- 单独命名 C12 test（`t4a_c09`／`t4a_c14` 已覆盖 guard／AST）。

## 未验证边界

- Brief C01–C12 源码 mutation 未跑。
- 完整 `tests/unit/tokenization`、Ruff、Pyright 未跑。
- Index 复杂度无规模 benchmark。
- Task 4B 16／8、4C、Task 5 cache 不在范围。

## 搜索面

读完 `prediction.py` 终态；4BP 测试与 helpers；`git diff --name-status`；same-time／no-store 探针；pytest 36 passed。未改文件。

## Commit 前必须检查

隔离树、不碰 shared main／4141：

1. `uv run pytest tests/unit/tokenization/test_prediction.py`
2. `uv run pytest tests/unit/tokenization/`
3. `uv run ruff check` 与 `uv run pyright` 对两 allowed paths（brief 另要求 `pyright src tests`）
4. C01–C12 mutation 的 raw red／restore green
5. `git add` 仅这两路径；subject `feat: learn token prefix residuals`

本 review 只执行了第 1 项。

## Verdict

**APPROVED。**
