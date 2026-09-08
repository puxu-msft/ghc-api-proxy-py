# Rootless user installer 三文件原子性 minor 裁决

- **评审范围**：只读裁决 `docs/tmp/260807-review-code-systemd-user-install.md` 的唯一 minor，以及 `/home/xp/src/ghc-api-proxy-py-systemd-install` 中固定且 clean 的 `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`。核对最终 installer、smoke test、deployment README 与 living Plan；独立在临时目录注入第二、第三目标文件替换失败。未修改候选代码。
- **总体 verdict**：**可进入 squash；该 minor 可后补，不要求 squash 前修。** 三文件 group all-or-nothing 不是当前 helper 的必要合同，现状维持 minor，不升级为 major。后补只需澄清“逐文件原子替换”并固化一个最小故障恢复回归；不应为本问题引入 generation staging、整组 rollback 或 manager orchestration。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1，允许后补。

## 双视角覆盖证据

### 机械核对视角

- 固定读取 `HEAD=e16c2a700f23f66535e7347ab7357518eb8e56bd` 的 `contrib/systemd/install-user.py`、`tests/smoke/test_systemd_user_install.py`、`docs/agents/deployment-systemd/README.md` 与 `docs/agents/systemd-runtime/plan.md`；目标 worktree 在裁决前后均 clean。
- `_write_atomic()` 对单个目标执行同目录临时文件写入、flush、`fsync`、mode 设置和 `Path.replace()`，并在 `finally` 清理临时文件；`_apply()` 按 service、socket、slice 顺序逐个调用它，没有三文件 commit point 或 rollback。
- 独立故障探针分别令第二个目标 socket、第三个目标 slice 的 `Path.replace()` 抛出 `PermissionError`。两次都观察到异常显式向上传播、失败目标保留旧 bytes、已完成的前缀目标保留新 bytes、目录无临时文件残留；恢复正常 `replace` 后再次调用真实 `_apply()`，三份目标均收敛为新 bytes。
- CLI 顶层把 `OSError`、`RuntimeError` 与 `ValueError` 转成 stderr `error:` 和退出码 1。helper 的 apply 调用链没有 `systemctl`；现有 smoke 也用退出 99 的 recorder 覆盖 dry-run、apply 与重复 apply，确认不执行 reload、enable、start、restart 或 stop。
- README 的“把精确三份文件原子写入”和 Plan 的“显式 apply 原子写入”存在 group atomicity 歧义；CLI help 只承诺把 units copy 到 user unit dir，并未承诺三文件事务。

### 第一人称执行视角

- 模拟已有旧 generation 的用户执行 `--apply`：若第二或第三次替换遇到权限、空间或 I/O 故障，命令明确失败，磁盘上会暂时存在新旧 mixed generation；它不会谎报成功，也不会让 helper 自行 reload manager 或启动任何 unit。
- 在用户未另行执行 `daemon-reload` 的正常流程中，磁盘 mixed generation 不会被 helper 主动加载为 manager runtime 状态。用户修复外部故障后重跑同一命令，已更新文件报告 `UNCHANGED`，其余文件完成替换，最终收敛。
- 模拟全新安装失败：可能只留下已成功写入的前缀文件，但 helper 同样不会 enable 或 start；重跑补齐三份文件。模拟用户无视非零退出并自行 reload 的反合同操作，确实可能加载 mixed generation，但这不是当前 helper 自动造成的静默运行态切换。

## 事实性发现

[minor] `contrib/systemd/install-user.py:164-189`、`docs/agents/deployment-systemd/README.md:63-77`、`docs/agents/systemd-runtime/plan.md:230-244` — 实现只提供逐文件原子替换，文档“精确三份文件原子写入”容易被读成整组 all-or-nothing，且现有仓库测试没有固定第二／第三文件失败后的恢复合同 — 实际失败会留下磁盘 mixed generation，但失败显式、无临时残留、不触碰 manager，重跑可幂等收敛 — 后补时把措辞统一为“按固定顺序逐文件原子替换；整组不承诺 all-or-nothing”，并增加下述单个参数化回归。

未发现把该 minor 升级为 major 的事实基础。当前切片的核心目标是默认 dry-run、显式 apply、单文件安全替换、幂等更新和零 manager 状态变更；三文件事务既未被冻结为验收门，也不是避免静默运行态损坏所必需。故障还要求在很短的三次本地替换窗口内出现写入错误，其影响可由非零退出和安全重跑控制。按用户偏好的低概率最小止血路线，squash 前引入整组事务或 rollback 属过度设计。

## 后补的最小测试

只增加一个参数化测试，例如 `test_apply_failure_is_explicit_and_rerun_converges`，参数为失败目标 `ghc-api-proxy.socket` 与 `ghc-api-proxy.slice`：

1. 在临时 unit dir 预置完整旧 generation，并冻结三份新 bytes。
2. monkeypatch `Path.replace`，仅在参数目标上抛出 `PermissionError`；调用真实 `_apply()`，断言异常未被吞掉。
3. 断言失败前已完成的前缀为新 bytes，失败目标及后缀仍为旧 bytes；目录条目仍精确等于三份正式 unit，且不存在 `.<unit>.*` 临时残留。
4. 恢复真实 `replace` 后重跑 `_apply()`，断言三份均为新 bytes；再重跑一次，断言 bytes 与 `mtime_ns` 不变。

现有 smoke 已覆盖 apply 和重复 apply 的零 `systemctl`，最小故障测试不重复 manager recorder。

## 主观建议

未提出额外设计建议。唯一推荐路线是后补“措辞澄清＋一个参数化故障恢复测试”，保持 helper 不 reload／enable／start，也不新增 group transaction。

## 唯一结论

**不需 squash 前修；维持 minor，可后补。** 最小后补是明确逐文件原子合同并增加第二／第三替换失败后“显式失败、无临时残留、重跑收敛”的参数化测试；不要为此实现三文件 all-or-nothing。
