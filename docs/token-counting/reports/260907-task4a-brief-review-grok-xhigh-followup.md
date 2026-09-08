# Task 4A brief review follow-up

## 评审范围

- 被评对象：修订后 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-4a-brief.md`（SHA-256 `7fb755930f4427405137f058ca323d7135b2a8682a4fefa8dbe677209c86d76b`，237 行；上一轮为 `7bb1f48b…`）。
- 判据不变：Spec `5d9477dd…`、Plan `bea5e753…`、main `6044919a` 3B carriers、旧 SUPERSEDED brief 及其 2 Blocker／6 Major、上一轮 `260907-task4a-brief-review-grok-xhigh.md` 的 T4A-F-01～04。
- 只读：未改 brief／authority／source；未启动 4A source、4141、shared main。未跑 source tests。
- 复核两问分开答。

## 总体 verdict

**READY。** blocker=0，本轮新发现 major=0／minor=0。上轮 4 条均 `closed`。按 brief 自己的「0 Blocker／Major 才启动 source」闸门，**可以派 Task 4A source**。

## 上轮条目完成度

| ID | 状态 | 证据 |
|---|---|---|
| T4A-F-01 | **closed** | §7 C13 改为只断言 `build_prediction_record()` 产出；mutation 只改 `prediction.py`；DTO 注入／validator-relaxation 标明由 Task 3／3A 拥有且不得改 `types.py`。原「手工注入 + 放松 types validator」路径已删除。 |
| T4A-F-02 | **closed** | §1 把 A5／A8／A15 收成 4A 子集；A20 只取 exact／deterministic／cold cardinality、champion、exact-selected 仍留 shorter prefix；A36 只取 `PredictionDecision`／intent／purity，排除 Task 5 queue／store。 |
| T4A-F-03 | **closed** | §5.2 写明 v1 系数全 0、contribution `prior_residual_tokens` 是唯一聚合载体、不从 FeatureVector 再乘系数、不双计；非零 prior 须先改 authority 与 estimator generation。 |
| T4A-F-04 | **closed** | C14 改为 output boundary：`prediction.py` 不 import／构造 Replace／Delete；predictor 只出 decision／record／evaluations；`LearningUpdate` fixture 若出现只作 caller seam，不是 4A DTO mutation。Oracle 为字面量 command type + AST／import 检查。 |

## 当前系统状态（抛开上轮清单）

未发现新的 blocker／major。独立再扫：

- **Scope／non-goals**：仍限 cold-start、exact、strictly-shorter deterministic prefix、prequential、finalization；§6 仍排除 4B-P formulas／pair index／newest31、4B 16／8／profile、4C、Task 5、4141、旧 whole-visual 与 records 重放。
- **3B 消费**：allowed paths 未扩大；stop rule 仍禁止改 carrier。`6044919a` 上 `EstimateFeatures` contributions、`PrefixAnchor`／`ExactAnchor`、`PredictionDecision`、`NoPrefixCheckpointChange` 仍够用。`prediction.py` 仍不存在（预期）。
- **C01–C12**：正文未改，仍覆盖旧 BR-01 suffix、BR-03 exact+prefix、median／tie、actual0、Decimal 终态、wrapper 0→1。
- **C13／C14**：现可在 `prediction.py`／`test_prediction.py` 内执行，不再要求改 `types.py`。
- **Lineage**：Spec／Plan hash 与磁盘一致；base／parent `6044919a`／`42fb2329` 未改；3B squash 非祖先关系仍写明。

残余（不升 finding）：C13 mutation 列表仍含「漏 champion／exact·cold false／selected 非 first eligible」。这些状态在 `6044919a` DTO 上不可表示，实施时若硬做会先撞 `types.py` 异常。C13 已禁止用该异常冒充 control。可执行的 producer mutation 是 candidate／champion **错序**（DTO 不强制 canonical 顺序）和 **exact-hit early return**（与 C04 重叠）。实施者按 C03／C04 的 tuple 断言即可，不必再造不可表示的 record。

## Findings

未发现新问题。

## 未采用建议

- 从 C13 mutation 句删掉 DTO 不可表示的三项，只留错序与 exact-hit：能减少实施歧义，但不改变正向 producer 断言，不阻止 READY。
- 为「snapshot 已有 demoted checkpoint 时 4A 仍选 prefix」加 mutation：4B 尚未生产 demoted rows；§4 已禁止读 checkpoint。仍不采用。

## 未验证边界

- 未跑 pytest／Ruff／Pyright（brief 评审，无 4A source）。
- `scale_local_estimate` 对现网 `driver.py` 的数值差仍留 source／merged seam。
- Formula-level A45 两项仍属 Task 4B-P，不得用未来 4A 绿灯冒充。

## 搜索面

`sha256sum` 新 brief／Spec／Plan；`rg` C13／C14／A20／A36／prior／coefficient；通读 §1、§3–§7、§10。对照上一轮报告与 `6044919a` DTO 记忆（本轮未再 `git show` types.py）。未改文件。

## 派 source 前机械注意（非本轮缺陷）

隔离 worktree 从 `6044919a` 起手；启动时重算 Spec／Plan／status／HANDOVER hash；只碰四个 allowed paths；C13 不要去改 `types.py`。

## Verdict

**READY。**
