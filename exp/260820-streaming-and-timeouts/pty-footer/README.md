# 多行栈在 live footer 之下的抓屏验证

**问题**：给日志加上完整 traceback 之后（提交 `5e2f1d5`），多行输出会不会被 `rich.Live` 的重绘吃掉——它按行数擦除自己的区域，任何绕过它写入终端的东西都会落进被擦区。

**做法**：`_trace_driver.py` 用**生产的** `setup_logging()` + `FooterTui` 起一个真 TUI，在 footer 活着时打一条带栈的错误；`_trace_run.py` 用 `pty` 分配伪终端驱动它，再用 `pyte` 把字节流解释成屏幕网格。

```bash
PYTHONPATH=src python .dev/exp/260820-streaming-and-timeouts/pty-footer/_trace_run.py \
    .dev/exp/260820-streaming-and-timeouts/pty-footer/_trace_driver.py
```

**结论（2026-08-20 实测）**：栈完整落在屏幕上，第 3–12 行是 traceback 的十行，第 13 行是紧随其后的下一条日志——没有被截断，没有与 footer 重绘交错。

**它不证明什么**：
- 只测了一条日志、一屏高度（100×30）。更长的栈、更窄的终端、滚动区跨越 scrollback 的情形都没测。
- 它证明的是「Live 的记账没有被多行打断」，**不证明**任何关于 footer 自身刷新频率或颜色降级的性质。
- 注意：项目自带的 `tests/tui/_footer_driver.py` 用的是 `logging.basicConfig`，**不走 structlog 那条格式化链**；这个探针特意用了生产的 `setup_logging()`，两者不可互相替代。
