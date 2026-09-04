# `origin/dotdev` 内容导入候选窄复评

日期：2026-09-04。

复评对象：当前 `/home/xp/src/ghc-api-proxy-py/.dev`、首轮报告 `docs/git-housekeeping/reports/260904-dotdev-remote-import-review-gpt-opus.md` 与处置账 `260904-dotdev-remote-import-review-disposition.md`。范围严格限于首轮 F-01～F-03、相邻 README topic index 及报告原件是否保持不变；全程只读，没有写文件、暂存、提交或修改 human-controlled 文档。

## Verdict

**pass。** F-01、F-02、F-03 全部 closed；remaining blocker=0、major=0、minor=0。整改未引入新的 blocker／major。

## 首轮 findings 逐条复评

### F-01　closed

`docs/upstream/retry-and-continuation/status.md:4-10` 现在把 HTTP 499 段明确标为从 `origin/dotdev` 导入的另一 source clone snapshot，逐字说明当前 checkout 的人写 requirement 与 `RETRYABLE_STATUSES` 均不含 499、source history 尚未装位、不得宣称 current／complete；恢复条件是对应用户控制提交和 reviewed source history 在当前主仓可达，并重新对账实现、测试与 authority，本次合并不授权代用户修改人写文档。

`http-499-retry.md:2-8` 使用 `imported-external-clone-snapshot`，把 recorded requirement／implementation 与当前 checkout 分开；`:20-38` 的“当前实现”已改称 source clone 当时的实现。`review-disposition.md:2-4` 也明确全文件的 fixed／closed 只属于 source clone，当前 checkout 不得据其声称实现，恢复 current 地位须服从 status 条件。底部“当前共识状态”虽保留原点时正文，但由文件级 banner 统一限定，不再反向覆盖本仓 authority。

当前人写文件 `docs/.human-controlled/upstream-retry-and-continuation.md:13-18` 仍无 499，当前 `src/app/model_provider/ghc_client/errors.py:31-35` 的集合仍不含 499，证明整改没有偷偷把外部记录写成当前 requirement／实现。F-01 的 authority 冲突已闭合。

### F-02　closed

`docs/timeout-408/status.md:2-6` 将 completed／mainline／archive／验证全部限定为另一 source clone snapshot，明确当前 inference 仍无 listener／cleanup、source/archive refs 不可达，并给出“先让 reviewed source 与 archive 在当前主仓可达，再重新对账代码、测试与人写 authority”的恢复条件。`docs/timeout-408/spec.md:2-8` 保留行为规格作为待实现 authority，同时明确后文“当前实现”只属于 source clone，当前实现状态由 status 顶部注记裁决。

`docs/xingchen/status.md:2-10` 同样将 main/archive／实现／验证限定为 source clone，明确当前 checkout 没有实现；`docs/xingchen/spec.md:2-5` 保留目标行为规格但禁止由 Spec 或 PASS 反推 current main；`docs/xingchen/review-disposition.md:2-6` 把 closed／PASS 限定为外部 candidate，并标记当前 checkout 尚未实现。原 source commit 与验证数字继续作为点时证据，而非本仓状态。

整改没有删除目标规格或评审链，也没有把另一 clone 的 PASS 投影成 current。F-02 closed。

### F-03　closed

`docs/reasoning-carrier/tracking.md:2-8` 现标为 `source-unreachable`，明确原 worktree／branch 在当前主仓不存在、dotdev 只保存文档、原报告没有 commit token，因此不存在可执行的重新定位命令；`:40-48` 把原 source clone 终态与当前恢复状态分开，明确不能继续 squash／merge，只有找回 ref、bundle 或另一 clone 后，才能重建 feature／archive 身份、复跑验证并重新评审集成候选。

`docs/reasoning-carrier/spec.md:2-6` 保留为 imported living target specification，同时明确当前 checkout 未集成且 source 不可达，恢复条件归 tracking。任务表中的 done 与评审 PASS 因 tracking 文件级 banner 被限定为 source clone 点时记录，不再冒充当前可执行候选。F-03 closed。

## 相邻检查

- 根 `README.md:71-73` 与三个 topic 的新边界同义：reasoning-carrier 是 source-ref 不可达的导入规格／评审，timeout-408 与 Xingchen 是另一 clone 的记录且当前 checkout 尚未装位实现。索引没有继续使用旧“current implementation”措辞。
- 对 remote tip 的 54 个文件重新做 blob 对账：当前相对 remote 改动恰为 README 与 10 份 living／disposition 文件；`/reports/` 下原件变化数为 `0`。报告 originals 未被为迎合复评而改写。
- HTTP 499、timeout-408、Xingchen 与 reasoning-carrier 的恢复条件分别要求当前 requirement／source／archive/ref 可达后重新核验，没有把“文档存在”当作恢复完成，也没有建立新的 proof framework。
- 未发现整改引入的 blocker、major 或仅需拖轮次处理的 minor。

## 未采纳建议

无。三条首轮 finding 均按原因果修复，当前不需要追加删除、改写报告原件、修改 human-controlled 文档或扩大验证机制。
