# 生命周期模块重组评审

## 评审范围

`29d242d`、`c5a540a`、`40965d8`，最终对象为 `40965d8`；比较基线为 `5fd9c16`。

## 已读取／执行的证据

- 逐 hunk 核对 `git diff --find-renames=1% 5fd9c16..40965d8 -- src`，特别复核了相似度为 99%、98%、97% 和 81% 的重命名／拆分。
- 对原 `generation.py` 与 `phases.py`、`admission.py` 的所有七个顶层定义做 AST 比较；七个定义均逐一相同，且 Uvicorn ASGI 类型仅留在 `admission.py`。
- 执行用户给定的旧 import 正则，`src`、`tests`、`contrib` 均无命中；另外检查了所有非 Python 文件中的同类 dotted import，unit 与 launcher 均使用新路径。
- 绘制 `core`／`lifecycle` import 边，并实际 import 17 个搬迁模块；`core` 无 `lifecycle` 依赖，也未发现循环。`activation`／`adapter` 由 standalone 与 rolling 共用，位于 `lifecycle/` 正确。
- `uv run pytest --collect-only -q` 收集 1208 项；测试 basename 无重名。`uv run pytest -q` 为 1208 passed；搬迁相关定向集为 167 passed。
- 核对 `contrib/systemd/` unit 的 `ExecStart`、launcher 的 import 和 CLI 入口；核对候选部署模块表及 `existing-rulings.md` 的实质引用目标。

## 核验结果

- C1：确认。生产源码 diff 只有路径替换、包初始化说明，以及完整移出的 middleware；未见默认值、分支、调用顺序或异常处理改变。
- C2：确认。`phases.py` 保留相位机六个定义，`admission.py` 保留 middleware；ASGI import 仅为后者所需，两个文件以单向 `admission -> phases` 连接。
- C3：确认可执行路径无旧 dotted import。历史计划 `docs/agents/systemd-rolling/plan.md` 仍提到旧的物理文件路径，但不是 unit、脚本、README 或运行时引用。
- C4：确认。方向为 `core <- {tokenization, lifecycle}`；`rolling -> {generation, systemd, activation, adapter}`；未发现反向边或循环。
- C5：确认。收集成功，且 `tests/` 下所有 `test_*.py` basename 唯一。
- C6：确认。两个 launcher／service 入口与 `app.cli` 子命令一致，launcher 的 identity parser import 已迁至 `app.core`。

## 总体 verdict

可进入下一阶段（可定稿）。blocker：0。

## 事实性发现

未发现 blocker 或 major。

## 主观建议

无。
