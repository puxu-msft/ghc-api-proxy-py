# Current main foundations＋systemd merged-state 独立评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py` 的 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`，线性包含 `d274f584219f8ae32f59d15d08ac007c45058c8d`、`798ba3e7653b513c3c9c732019e793f828ae0890`、`1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` 与 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。不重做各 source candidate 的全量评审，只复核 reasoning cardinality＋request converter、session liveness、CLI inherited fd＋systemd units＋既有 server shutdown、living docs checkpoint，以及四个回放提交的内容与身份。
- **总体 verdict**：**修复 major 后可进入。** 四个代码提交的 merged state 未发现 blocker／major，且定向运行证据通过；但正式 living／导航文档的 current 段落仍保留“尚未进入 main”和再次回放动作，已与 current main、Implementation 顶部新状态及已同步的 readiness／systemd plan 冲突。先修复并复评该状态链，再继续 happy-path 回放。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：每次 shell 调用均在同一调用内核对物理 root、`main` 与现场 HEAD，并确认四个目标提交均为祖先；逐提交对账 subject、parent、changed paths 与 range `diff --check`；用 stable patch-id 与排序后的路径集合确认四个 current-main commits 分别等价于已评审载体 `9e5f874…`、`cae83f4…`、`6a00f6f…`、`fe9c203…`；读取最终源码而非只看 diff；扫描 README、Implementation、systemd plan、service-cutover plan 与 readiness 的 current 状态／下一动作；定向 pytest 覆盖 `test_responses_reasoning.py`、`test_anthropic_responses_request.py`、`test_streaming_resilience.py`、`test_cli.py` 与 `test_systemd_units.py` 并正常通过。定向 Ruff 显示 `All checks passed`，定向 Pyright 显示 `0 errors, 0 warnings, 0 informations`。主会话先前报告的全仓 `375` 项结果未由本轮独立交叉验证，不作为本 verdict 的必要证据。
- **双视角覆盖证据——第一人称执行模拟**：模拟三个 reasoning items 经 forward codec 生成三个独立 thinking blocks，再经 public request converter 恢复，独立 runtime probe 验证 item 数、顺序及 encrypted-only payload 均保持；沿 client cancellation、第二次 cancellation、upstream primary error 与 close secondary error走完 liveness cleanup；沿 systemd listener fd 3 → CLI `--fd` → `uvicorn.run(..., fd=3)` → 同一 `create_app()` lifespan → readiness／真实 Messages 请求 → SIGTERM cleanup走完真实 smoke；最后按 living docs 的 current 总体进度与“下一步”实际模拟执行，确认仍会再次尝试回放已在 HEAD 祖先链中的 foundations 与 systemd patch。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:44-46,69,93,213-216`、`docs/agents/anthropic-responses-bridge/README.md:28-34,197-209,274`、`docs/agents/service-cutover/plan.md:8,33,36,525` — 正式状态链内部仍同时存在“已进入 main”与“尚未进入 main／立即回放”的相反 current 指令 — 现场 `main@cf53334…` 已线性包含 `d274f58… → 798ba3e… → 1c13fda… → cf53334…`，四片 stable patch-id 与已评审载体逐一相等；当前工作树中的 Implementation 顶部、`docs/agents/service-cutover/readiness.md` 和 `docs/agents/systemd-runtime/plan.md` 已记录进入 main 的事实，但 Implementation 总体进度／下一步、README 当前快照／执行检查以及 service-cutover Plan inventory／kickoff 仍要求再次回放或声称 CLI 无 fd 入口。执行者若依据这些 current 段落，会重复 cherry-pick 已落地主体、错误保留已关闭的回放门，并在 happy-path 前置判断中使用虚假主线状态 — 在继续 happy-path 回放前，统一 current HEAD、四片 main-side gate／归档状态、下一动作及 service-cutover inventory边界；明确 systemd 只是“代码进入 main，未安装／未部署／未 cutover”，完整 bridge 仍为 `UNVERIFIED`、部署仍为 `NO_CUTOVER`。修订后对所有受影响 current bytes 做定向复评，避免只修顶部或其中两份而继续保留相互冲突的真相源。

未发现其他 blocker／major。具体而言，request converter 复用最终 reasoning decoder，没有把 cardinality API恢复成聚合；liveness helper 的 cancellation-resilient cleanup未被 request提交覆盖，其尚无 production consumer 属于已声明的 foundations 边界而非本次回放回归；CLI fd分支继续使用既有 `create_app()` 和 FastAPI lifespan，真实 inherited-listener smoke覆盖 backlog、liveness、readiness、Messages请求、状态落盘与 SIGTERM cleanup；四个 commit 的 subject、路径集合和 patch内容均与其声明及已评审载体匹配。

## 主观建议

无。本轮只报告 blocker／major；后续 timeout、双 fd／双栈、真实 user manager／cgroup、production liveness接线及完整 bridge Acceptance均已由 living plans 保留，不把这些已知后续范围误报为当前 checkpoint 缺陷。
