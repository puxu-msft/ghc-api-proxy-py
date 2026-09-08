# `systemd --user` 隔离 manager 诊断快速复核

- **评审范围**：仅复核 `docs/tmp/260807-systemd-user-manager-diagnosis.md` 中当前 WSL 上下文的无特权隔离 manager `BLOCKED` 结论、对现有 user manager／Bun／`127.0.0.1:4141` 的隔离边界、诊断进程清理，以及转可销毁 VM／container 的下一步；未重跑 manager，未扩展部署矩阵。
- **总体 verdict**：可进入下一阶段。
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据**：
  - **机械核对**：对账结论、诊断矩阵、已排除／未证明、下一最小动作和安全清理审计；只读现态确认 PID 1 仍为 systemd、调用进程仍位于 root 所有且当前用户不可写的 `/init.scope`，现有 user manager、Bun 与 `4141` 监听仍存在，且 `/proc` 命令行扫描未发现 `/tmp/ghc-systemd-*` private manager／D-Bus 残留进程。
  - **第一人称执行模拟**：按文档从当前 WSL 继续尝试、转入可销毁 VM／container、等待专用 `user@UID.service` 与 delegated cgroup v2、通过 private control socket 门后才连接专用 manager 的顺序走查；当前环境继续变换 env 不能补足 delegation，转隔离实例不会要求接管现有 manager，路径前后自洽。

## 事实性发现

[minor] `docs/tmp/260807-systemd-user-manager-diagnosis.md:53` — “所有实验日志和 runtime 树均位于 `/tmp/ghc-systemd-*` 并已删除”的范围过宽 — 当前只读扫描仍能看到该前缀下的既有测试／评审日志与目录，虽然它们均早于本诊断报告，且没有对应活进程；这不推翻本轮 private manager／D-Bus 已回收，也不影响 `BLOCKED` 结论，但按字面无法区分“本轮 probe 产物”与同前缀的其他产物 — 建议后续若修正文档，将其收窄为“本轮 private manager probe 创建的日志与 runtime 树均已删除”，或列出本轮临时根路径。

除上述措辞边界外，未发现阻断性问题。`docs/tmp/260807-systemd-user-manager-diagnosis.md:3-5,17-31,36-43` 将可观测事实与未定位的 systemd 内部失败点明确分开：它没有把 cgroup 不可写夸大为静默 `rc=1` 的唯一已证根因，同时足以支持“当前调用上下文下、在不连接现有 manager 且不使用 sudo 的约束内继续尝试为 `BLOCKED`”。`docs/tmp/260807-systemd-user-manager-diagnosis.md:47-54` 的进程回收与不触碰现有 manager／Bun／`4141` 结论未见反证；`docs/tmp/260807-systemd-user-manager-diagnosis.md:45-46` 转到可销毁、由 systemd PID 1 为专用测试 UID 建立 `user@UID.service` 与 delegated cgroup v2 的 VM／container，并保留动态 loopback 端口及 private control socket 门，是与已识别阻断点对齐的最小合理下一步。

## 主观建议

无。
