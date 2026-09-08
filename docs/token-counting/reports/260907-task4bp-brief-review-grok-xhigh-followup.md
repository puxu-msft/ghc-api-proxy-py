# Task 4B-P brief review follow-up

## 评审范围

- 被评对象：修订后 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-4bp-brief.md`（SHA-256 `1177435d16d5b67f8e57eefff80d0293f834277bab8e08afdedf821fd7d71c73`，297 行；上一轮 `51d4071c…`）。
- 判据不变：Spec `5d9477dd…`、Plan `bea5e753…`、main `3badac7f`、上一轮 T4BP-F-01／F-02。
- 只读：未改 brief／authority／source；未启动 4B-P source、4141、shared main。

## 总体 verdict

**READY。** blocker=0，本轮新发现 major=0／minor=0。上轮 2 条均 `closed`。可以派 Task 4B-P source。

## 上轮条目完成度

| ID | 状态 | 证据 |
|---|---|---|
| T4BP-F-01 | **closed** | §1 写「A20 的 Task 4B-P 子集」：all-available prefix variants、candidate／champion／sample_count、exact 仍留 shorter prefix、newest31／min8／strict-better／tie；profile comparison 与 16／8 明确属 Task 4B。 |
| T4BP-F-02 | **closed** | C01 不再要求 pending `None` order；只测 reverse tuple、future base、duplicate／equal order。C07 mutation 改为 exact-hit early return、丢一个 learned candidate、交换 candidate 顺序、改 sample_count、champion 退回 deterministic。另有 mutation ownership 段：types.py validator 不由本 slice 放松或列入 source mutation。 |

## 当前系统状态（抛开上轮清单）

未发现新 blocker／major。独立快扫：

- Allowed paths 仍仅 `prediction.py`＋`test_prediction.py`；non-goals 仍排除 4B／4C／Task 5／carrier／4141。
- C04 full-baseline、C06 current-zero、C09 newest31、C10 `evaluations=()` 仍在。
- Spec／Plan hash 与磁盘一致；base `3badac7f` 未改。

残余（不升 finding）：C01 正向句不再点名「同 `observed_at_us`、committed order 1／2 仍成 pair」。§5.2 仍写 same-time 合法。实施时应用 §5.2 补该 fixture；不必为 READY 再改 brief。

## Findings

未发现新问题。

## 未验证边界

- 4B-P source 未启动；未跑 tests／Ruff／Pyright／mutations。
- Index 复杂度无生产规模 benchmark。
- Task 5 cache、4B 16／8、4C drift 仍非本 slice。

## 搜索面

`sha256sum` 新 brief／Spec／Plan；`rg` A20／C01／C07；读 §1 与 §7 C 表及 mutation ownership 段。未改文件。

## Verdict

**READY。**
