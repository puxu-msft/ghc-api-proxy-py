# 实施计划评审 01

> 日期：2026-07-15
> 对象：[IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md)、[PHASE_0_KICKOFF](PHASE_0_KICKOFF.md)

## 首轮 verdict

无 blocker，6 个 major，修复 major 后可执行。主要问题是计划覆盖用户已裁决的 D1/D2、缺失 wire JSON 实施步骤、Phase 7/8 没有真正 TDD 分解，以及部分 live docs 仍写 argparse。

## 已采纳修订

1. OTel beta instrumentation 改为正式依赖、运行时默认关闭；不再重新询问用户。
2. AnyIO 有限采用落到 lifespan task group、idle timeout、tokenization offload、取消传播门禁、shutdown 和 approval。
3. OTel core/contrib 明确作为同批次在实施当日解析和锁定，取消“注释依赖等于默认关闭”的错误做法。
4. 核对发现仓库根 [TODO_CURRENT.md](../../../TODO_CURRENT.md) 实际存在；修正计划中的断链相对路径，而非新建重复文件。
5. 新增 Phase 0.8 `wire_json.py` 与 differential tests，明确热路径/低频可读 JSON 边界。
6. Phase 7 拆成 ApprovalGate 状态机和 REST/WS API，补 approve/reject/modify/timeout/shutdown/TUI 广播测试与黑盒验收。
7. Textual 作为正式依赖和完整实现任务，运行时配置可关闭。
8. 修正 Phase 0 服务“立即退出”的矛盾、补 `setup-codex` 和 `login` alias。
9. kick-off 的“所有 I/O 都用 aiofiles”改为按场景 off-loop；配置 startup source 不被错误异步化。
10. Phase 8 拆分 Gemini 模型/路径、Gemini 转换/路由、Azure deployment/v1 三个 TDD 步骤与黑盒验收。
11. KMP 从 shutdown commit 拆出，增加 property-based/differential oracle 测试。
12. 增加 uvloop 的本项目 SSE/WS/cancel/shutdown 对照门禁。
13. DESIGN、project-structure、config-system 与 TODO_CURRENT 从 argparse/asyncio Event 同步到 Typer/AnyIO 决策。
14. 删除计划中重复且已漂移的 codec/kickoff/工时附录；独立 kickoff 为单一执行入口。
15. PoC 资产明确保留在 `exp/<topic>/`，无论成功失败都写结论并 commit。

## 额外强化

- token-limit cache 的用户裁决落实为 24h TTL + 仅规范化 model key，并记录未来出现跨路由反例时的迁移要求。
- OTel 测试补默认关闭、单次注册、HTTPX 不消费 stream、structlog 单向 trace 注入。
- Phase 5/6 并行需先冻结公共 context/bus 契约；Phase 7/8 在各自前置接口稳定后可并行。

## 第二轮复审

第二轮只剩 1 个 major：实施计划已经落实 AnyIO，但 DESIGN、project-structure 的 lifespan 示例和 approval-system 仍保留 `asyncio.Event`/`create_task`，会诱导实现者复制冲突模式。现已全部同步为 AnyIO Event/task group/cancel scope，并注明 asyncio-only transport task 必须保存、取消、await 和通过集成门禁。计划可进入最终复核。

## 最终复审

最终 verdict：**0 blocker / 0 major，可定稿进入实施**。P1、P6、unknown 保真、单一 retry owner、AnyIO 结构化取消、OTel 默认关闭、wire JSON differential tests、sse-starlette/httpx-ws PoC 门禁均在主计划和 Phase 0 kick-off 中有明确落点。
