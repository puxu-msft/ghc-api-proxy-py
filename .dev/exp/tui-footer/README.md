# 探针：TUI footer

这些脚本是 footer 机制选型与验收时的实测工具，保留可跑。

- `driver_rich_live.py` / `driver_decstbm.py` / `driver_naive.py` —— 三种钉底机制的对照臂，最后一个是**已知坏实现**，用于证明判据有区分力。
- `pty_probe.py` —— PTY + pyte 抓屏。
- `probe_real_startup.py` / `probe_live_footer.py` / `probe_shutdown.py` / `probe_keepalive_drain.py` / `probe_stuck_drain.py` —— 起真实进程观察启动、在飞、关闭与 drain 的表现。`probe_live_footer.py` 支持 `THINK=1`（要推理块）与 `TOOLS=1`（要工具调用）。

**它们会打真实上游**，一次一小笔调用。判据与上游真实行为无关时不要用它们，用 mock 上游写回归测试。

当时的结论已重写并归档到 `.dev/docs/tui/archive-footer/`；原始结论文件在其 `reports/` 下。

**注意路径**：这批脚本原本在仓库根的 `exp/tui-footer/`，2026-08-20 随 TUI 历史一并移入 `.dev/`。归档的原始结论文件里那些 `uv run ... exp/tui-footer/pty_probe.py ...` 命令是当时的快照，前缀要换成 `.dev/exp/tui-footer/` 才能跑。
