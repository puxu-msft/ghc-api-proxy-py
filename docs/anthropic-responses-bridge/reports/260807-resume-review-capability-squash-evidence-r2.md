# Reasoning capability squash evidence R2 快速只读复核

- **评审范围**：只复核 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997` 的 squash 可执行性；仅确认单 commit、两 path、main preimage、目标 path 无 WIP 重叠、真实 `git merge --squash` 形状、最小主线测试与 reviewed-source archive target。未重做完整 capability code review，也未外推完整 Anthropic Responses bridge。
- **总体 verdict**：**可进入下一阶段。** Exact-HEAD code review 为 `0 blocker／0 major`，independent verification 为 `PASS`；本轮独立 squash 审计未发现 blocker 或 major。`0 major` **可执行**：在 actual main 上保持下述 identity／preimage／pathset 门时，可执行且只执行 `git merge --squash 8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 每个承载结论的 shell 都在同一调用内校验 main 物理目录、Git top-level 与完整 HEAD 为 `/home/xp/src/ghc-api-proxy-py@b91e58a29324b11840002efc53ed6f869b800c39`，并校验 feature 为 `/home/xp/src/ghc-api-proxy-py-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。两次被并发终端输出污染或未实际创建专属日志的调用均作废，未用于结论。
- `git rev-list --count b91e58a…8bff1c3` 为 `1`；feature commit 的唯一 parent 精确为 `b91e58a29324b11840002efc53ed6f869b800c39`，因此它是 base 后单个非 merge commit。
- Candidate pathset 精确且仅有两项：`src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`。`git diff --check` 通过，feature worktree clean。
- Main preimage blobs 分别为 `src/app/anthropic/client.py=2c05425a2b0a90b5a03488a7919dbb5d0470c1ce`、`tests/smoke/test_anthropic_responses_route.py=54f3e6c3788463edb0d0620a31d057da88f84e80`；feature result blobs 分别为 `b9f44148215c675c76d861ac74ddf9ec848739ae` 与 `15ab87594435af6074e907cd18bf01c0e297a46e`。
- 扫描全部注册 worktree 后，candidate 两个目标路径的未提交 WIP 交集为 `0`。Actual main index 为空，目标两路径 clean，且没有进行中的 merge／rebase／cherry-pick／revert。Actual main 另有 3 份无关 tracked 文档 WIP；本报告只断言“目标路径无重叠”，不误写成“main clean”。
- `docs/tmp/260807-resume-review-reasoning-capability-r2.md:3-6,28-30` 精确绑定同一 base 与 candidate，结论为可进入 squash、`0 blocker／0 major`。`docs/tmp/260807-resume-verify-reasoning-capability.md:3-9,50-52` 精确绑定同一对象，结论为 `PASS`，并明确不外推完整 bridge。
- 在一次性临时 clone 中从 `b91e58a…` 真实执行 `git merge --squash 8bff1c3…`。HEAD 未被 merge 更新；cached pathset 仍精确为两项，两个 staged blob 与 feature result blobs 逐项相等，`git diff --cached --check` 通过。
- 临时 squash 树的进程内 load oracle 实际加载 `/tmp/cap-squash-r2.DGtpBe/src/app/anthropic/client.py`，排除了误载其他 worktree。随后在两个相关测试文件上运行 selector `reasoning or effort or dual_capability`，结果为 `30 passed, 46 deselected in 4.09s`。该数字口径仅为本轮最小主线测试，不代表全仓测试。
- Reviewed-source archive target 必须精确为 commit object `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，不是未来 main squash commit。本轮确认该 object 存在；当前没有 `refs/archive/*` 指向它。本报告只确认 target，不创建 ref。

### 第一人称执行模拟

1. 作为 squash 执行者，我先重新 gate actual main 与 feature 的完整 SHA；要求 main index 为空、目标两路径仍 clean、无 Git operation state，并重新核对两个 main preimage blob。无关文档 WIP可以保留，但不得被暂存或覆盖；任一目标 path 漂移即停止。
2. 我只执行 `git merge --squash 8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，不使用 fast-forward、regular merge 或 cherry-pick。
3. Commit 前，我要求 cached pathset 精确等于两项，staged result blobs 精确等于上述 feature blobs，且 cached diff check 通过。出现第三条路径、冲突、空 diff 或 blob 漂移即停止。
4. 我在 squash 后的 actual main 工作树运行同一最小 reasoning 主线测试，并确认模块从 actual main 加载；绿灯后才创建一个新的 non-merge main commit。候选侧旧绿灯不能替代这次 main-side 测试。
5. Main commit 与所需 main-side gate完成后，archive ref只能保存 reviewed source `8bff1c3…`。它不得指向新 squash commit，也不得把删除 feature branch／worktree夹带成隐含动作。

## 事实性发现

未发现 blocker 或 major。

`0 major` 可执行，但“可执行”不等于“本报告已执行真实 squash”。本报告验证的是 exact candidate、actual main preimage、WIP 隔离、真实 squash 形状和最小测试路径；actual main 的 squash、commit与archive均仍未发生。

## 主观建议

无。
