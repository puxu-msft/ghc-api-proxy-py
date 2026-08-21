# Readiness current 独立定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/service-cutover/readiness.md`，精确 SHA-256 `466090223e717366d20d79b4ab2393eb339f32d1a463b8face93915ff3c9255b`；固定 `main@b91e58a29324b11840002efc53ed6f869b800c39`。定向核对 43 行矩阵、main 当前状态、non-stream／typed core、stream candidate 仍未 main、systemd rebuild 仍未 main、`4141` Bun／`4142` 空闲、`NO_CUTOVER／FOUNDATIONS_ONLY` 与 `cc-daemon` 禁触碰边界。未修改 Readiness、代码、Git refs或任何运行态；唯一仓库写入为本报告。
- **总体 verdict**：**修复 major 后可进入。0 blocker／2 major，不可 checkpoint。** 总体状态边界正确，但 living 文档漏记两个已经形成但尚未进入 main 的候选，并继续把创建／重建候选写成下一动作。
- **blocker 数**：0。
- **major 数**：2。
- **双视角覆盖证据——机械核对**：验证目标 root、branch、HEAD 与文件 hash；独立计得 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43 行；确认 bridge 三片与 `cf53334…` 是 main 祖先，旧 systemd code-only 两片不是；源码确认 main 的 non-stream Responses 已接线、Responses stream 仍由 `responses_stream_not_supported` typed reject，而 parser／delivery core 已存在；refs 与祖先检查确认 stream candidate `2087f8f02516136314985f5c48bdee20b2f4b861` 已形成但未 main，new-main systemd rebuild `8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54` 已形成但未 main；只读 `ss` 确认 Bun PID 1623 双栈监听 `4141`、`4142` 无 listener，`/proc/1623/cgroup` 为 `/init.scope`。本轮全仓 pytest 被并行终端命令中断于 `121 passed`，故不把部分执行冒充新的 468 项证明；Readiness 中 468 仍只是既有 main gate 的绑定声明。
- **双视角覆盖证据——第一人称执行**：模拟 stream 实施者会按现文重复建立已有 `2087f8f…` 候选；systemd 实施者会按现文重复重建已有 `8cae6c2… → d3fabfa…`；备用端口操作者仍会避开生产 `4141`，且 `4142` 当前空闲；cutover 操作者会被 `NO_CUTOVER` 与显式授权门阻止。全文未把停止、重启、reload、改 endpoint、发信号或清理 `cc-daemon` 写成动作。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:6,9,45-46,122,147-148,156,178` — 文档把 Responses stream 仍写成下一步建立／接通 happy-path，遗漏已形成但未 main 的 `feat/anthropic-responses-stream-route@2087f8f02516136314985f5c48bdee20b2f4b861` — 该 ref 存在且不是 `main@b91e58a…` 祖先；main 仍 typed reject，所以“完整 stream 未进 main／未完成”正确，但“候选尚待形成”已过时。按现文执行会重复开发或建立第二条实现线 — **修复建议**：同步 exact candidate 及实际 gate／review 状态，保持 `FOUNDATIONS_ONLY` 与完整 stream `UNVERIFIED`；下一动作改为完成该 candidate 的验证、独立评审、main-side gate与组合复核，不得预填 `PASS`。

[major] `docs/agents/service-cutover/readiness.md:6,9,41,72,75,122,149,158-159,178` — 文档正确写明 systemd rebuild 未 main，却仍把“从 new main 重建两片”作为下一动作，遗漏已形成的 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54` — 提交图为 `b91e58a… → 8cae6c2… → d3fabfa…`，两片 patch-id 分别与旧 `862f4cfa…`、`2ec0cb8…` 相同，且均未进入 main。按现文执行会重复重建并制造第二套 identity — **修复建议**：同步 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54` 与两片 exact identities，保持“未 main、未安装、未执行真实 manager、`NO_CUTOVER`”；下一动作改为完成现有两片的 gate、fresh Plan checkpoint与 merged-state review／verification，不得再次重建或把候选存在外推为 gate 已通过。

## 结论

**0 blocker／2 major；不可 checkpoint。** 修订只同步两个已形成但未进入 main 的候选及真实后续门，不升级 P0～P3，不改写 `4141`／`4142` 的瞬时证据边界，不触碰 `cc-daemon`。修订后须对新 bytes重新定向复评。
