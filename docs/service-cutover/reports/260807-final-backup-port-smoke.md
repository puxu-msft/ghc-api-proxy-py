# 备用端口 smoke 最终执行记录

## 总体判定

- **执行 verdict**：`INCONCLUSIVE_PHASE0`。
- **入口 PASS**：未取得。不得报告 `PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`。
- **门控结论**：已在任何临时根、fake、app、测试请求或 signal 产生前按 R3 fail closed。current `main` 缺少 R3 要求纳入完整 candidate 的 safety harness 与 tests，也没有绑定 current 完整 `HEAD` 的独立代码复评 `0 blocker／0 major`；现场 code-tree 亦非 clean。
- **运行态影响**：未创建 smoke 临时根，未启动 app，未启动 fake，未占用 `4142／4143`，未向旧 Bun 或其他进程发送 signal，未安装 unit／manager，未执行 cutover。
- **结论边界**：`4142／4143` 空闲与旧 Bun 在短观察窗口内 identity 一致，只证明停止点安全；不证明 nonstream、stream、History、cancel、shutdown 或完整产品行为通过。

## 冻结输入与现场身份

- 执行计划：`docs/tmp/260807-resume-backup-port-smoke-r3.md`。
- 计划独立复评：`docs/tmp/260807-resume-review-backup-port-smoke-r3.md`。该报告给计划本身 `0 blocker／0 major`，但在 `:5,19,40,51` 明确声明这不等于任一现有 stream candidate 已取得 Phase 0 代码 `0／0`，也不授权直接启动服务。
- 物理工作树：`/home/xp/src/ghc-api-proxy-py`。
- Git top-level：`/home/xp/src/ghc-api-proxy-py`。
- 分支：`main`。
- 现场解析的完整 `HEAD`：`e9fb2771d6e040c761bb4074e3fcf2547caece28`。
- `refs/heads/main`：`e9fb2771d6e040c761bb4074e3fcf2547caece28`，与现场 `HEAD` 相等。
- 报告写入前工作树非 clean。该结论由 `git status --short` 的非空输出直接证明；下列逐路径投影用于说明可见状态，不作为第二种独立 cleanliness oracle。
- 报告写入前可见状态包括：
  - `docs/agents/anthropic-responses-bridge/implementation.md` 已修改。
  - `docs/agents/service-cutover/readiness.md` 已修改。
  - `docs/agents/systemd-runtime/plan.md` 已修改。
  - `docs/tmp/` 含未跟踪内容。
  - `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` 未跟踪。
  - `verification/PHASE3_ACCEPTANCE_REPORT.md` 未跟踪。
  - `verification/phase3_acceptance.py` 未跟踪。
- 本轮唯一主动创建的仓库文件是本报告。既存 dirty／untracked 内容未修改、未暂存、未删除。

## 从 R3 与本轮边界推导的验收矩阵

| 验收项 | 用户可观察 oracle | 本轮结果 | 证据／原因 |
|---|---|---|---|
| Phase 0 完整 candidate | 同一完整 candidate 包含 stream 实现、safety harness 与 tests，并由独立复评明确给出 `0 blocker／0 major` | **阻断** | current `HEAD` 中 `verification/backup_port_stream_smoke.py` 与 `tests/unit/test_backup_port_stream_smoke_safety.py` 均不存在；在 `docs/tmp` 中搜索 current 完整 `HEAD` 无报告命中；工作树非 clean。违反 R3 `:207-235,363` 的前置顺序 |
| LaunchSpec credential／config／CLI 封闭 | app／fake 由不可变 `LaunchSpec` 生成精确 argv；preflight 与 spawn 共用同一 spec；拒绝 credential 与额外 override；输出 hash-free 脱敏 | **未验证** | 缺少已纳入 candidate 并经 Phase 0 复评的 harness；不得临时手写 spawn 路径绕过 R3 `:17,63-105,216` |
| app／fake process safety | 直接 child、pidfd、完整 incarnation、精确信号、原 handle 有界 wait／reap | **未验证** | app／fake 均未 spawn；R3 `:180-203` 所需 child 终态无法产生，不能用端口空闲替代 |
| `4142` app／`4143` fake | 两个 listener 由本轮直接 child 精确拥有 | **未执行** | Phase 0 前停止；只读 preflight 观察到两端口空闲 |
| nonstream 主路径 | 真实 `/v1/messages` nonstream 只产生一次 Responses exchange，并返回预期 Anthropic response | **未验证** | 未启动 fake／app，未发请求 |
| stream text withholding | authoritative done 前零 success headers、零 `message_start`、零 body；完成后输出 Anthropic SSE 闭合 text block | **未验证** | 未执行 R3 `STREAM-MERGE-03`，也未运行 raw HTTP oracle |
| stream Anthropic SSE／terminal | 不泄漏 Responses event；合法完成仅一次 `message_delta → message_stop` | **未验证** | 未执行 R3 `STREAM-MERGE-02／06`，也未运行独立 strict SSE grammar consumer |
| stream error | commit 前为 Anthropic HTTP error；commit 后为 Anthropic SSE error；失败不得输出成功 `message_stop` | **未验证** | 未执行 R3 `STREAM-MERGE-07` |
| History enabled 最小投影 | 成功与失败按最终事实产生最小、类型化且不虚构完成态的 History 投影 | **未验证** | 本轮按用户边界只要求最小投影，但 Phase 0 阻断，未改变 config、未启动请求 |
| cancel cleanup | 客户端断开后关闭上游；无未完成 block 泄漏；资源归零；finalize 一次 | **未验证** | 未执行 R3 `STREAM-MERGE-09` |
| graceful shutdown | 仅对本轮 app 的 pidfd 精确发送 `SIGTERM`；lifespan cleanup 完成；app／fake 均 wait／reap；listener 释放 | **未验证** | 未启动 child，故未发送 signal；不能把“没有 child”冒充 shutdown PASS |
| 旧 Bun 不受扰动 | 不 signal；PID＋starttime＋cwd＋cgroup＋同轮 raw cmdline equality＋双栈 listener identity 前后一致 | **通过本轮只读观察窗口** | libc `pidfd_open` 成功；pidfd 前后均显示存活；完整 identity 比较均相等；`INCUMBENT_SIGNAL_SENT=false` |
| retry／quota／partial-write 矩阵 | 不属于本轮范围 | **未覆盖，符合边界** | 未扩展该矩阵，也未将其缺失计为本轮功能失败 |
| unit／manager／cutover | 不得安装或执行 | **未执行，符合边界** | 本轮没有 unit／manager 安装或 cutover 动作 |

## Phase 0 阻断实证

R3 `:223-235` 要求在任何运行态动作前，先形成包含 stream 实现、harness 与 tests 的最终完整 candidate，再取得绑定同一完整 `HEAD` 与当前完整 bytes、覆盖 route／parser／delivery／History／cleanup／finalize 合并接缝的独立代码复评 `0 blocker／0 major`。R3 `:235` 明确规定 scope 不完整、commit 不一致、报告后 bytes 变化或 cleanliness 无法证明时必须立即停止，且不得创建临时根、启动 fake／app或占用端口。

本轮对 current `main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 的机械检查得到：

- `HARNESS=ABSENT|verification/backup_port_stream_smoke.py`。
- `HARNESS=ABSENT|tests/unit/test_backup_port_stream_smoke_safety.py`。
- current 完整 `HEAD` 在 `docs/tmp` 的报告文本中无命中。
- 报告写入前 code-tree 非 clean，见上文 dirty 快照。
- `verification/final_acceptance/probes/00_cli_smoke.sh` 至 `07_gemini_azure.py` 虽存在，但 R3 已明确指出这组 probe 没有统一覆盖 argv credential gate、proc 脱敏、pidfd identity 与 fake 双 child回收，不能作为等价 harness 拼接放行。

因此 Phase 0 明确判红。按 R3 执行停止而不是继续 spawn，属于安全合同生效，不是 smoke 功能通过。

## 只读运行态证据

### 端口与旧 Bun baseline

在绑定相同物理 cwd、Git top-level、`main` 与完整 `HEAD` 的调用内，只读解析 `/proc/net/tcp`、`/proc/net/tcp6`、listener socket inode、`/proc/<pid>/fd`、`stat`、`cwd`、`cgroup` 与 `cmdline`。raw cmdline 只在同一 Python 进程内存中用于 equality 比较；本报告不保存 raw value、截断值、base64、digest 或 hash。

- `PORTS_4142_4143_EMPTY=true`。
- `INCUMBENT_DUAL_STACK=true`：`127.0.0.1:4141` 与 `[::1]:4141` 均存在。
- `INCUMBENT_UNIQUE_OWNER=true`。
- 旧 Bun PID：`818465`。该值由 listener inode → `/proc/<pid>/fd` owner 反查取得，**未用不同原理交叉验证**。
- `/proc/<pid>/stat` field 22 starttime：`2138402` ticks。口径为 Linux proc 原始 tick，不换算 wall-clock；**未用不同原理交叉验证**。
- cwd 分类：`expected-copilot-api-js`，即精确匹配 `/home/xp/src/copilot-api-js`。
- cgroup 分类：`init.scope`。
- argv 槽数：5。仅记录槽数，不记录内容；**未用不同原理交叉验证**。

### pidfd 与前后 identity

项目 `.venv` Python 的 `os` 模块没有 `pidfd_open` 属性，首次只读能力探针以 `AttributeError`、退出码 1 结束；没有发送 signal，也没有启动 child。随后使用 libc `pidfd_open` 对同一个旧 Bun PID 获取只读 pidfd，并仅用 poll 检查存活：

- `LIBC_PIDFD_OPEN_AVAILABLE=true`。
- `PIDFD_OPENED=true`。
- `PIDFD_ALIVE_BEFORE=true`。
- `PIDFD_ALIVE_AFTER=true`。
- `INCUMBENT_PID_EQUAL=true`。
- `INCUMBENT_STARTTIME_EQUAL=true`。
- `INCUMBENT_CWD_EQUAL=true`。
- `INCUMBENT_CGROUP_EQUAL=true`。
- `INCUMBENT_CMDLINE_EQUAL=true`。
- `INCUMBENT_LISTENERS_EQUAL=true`。
- `INCUMBENT_SIGNAL_SENT=false`。
- `APP_SPAWNED=false`。
- `FAKE_SPAWNED=false`。
- 最终只读 probe 退出码：0。

libc pidfd 能力只证明当前 Linux 现场可以安全打开旧 Bun pidfd用于观察；它不替代缺失的 candidate harness、safety tests 或 Phase 0 独立代码复评。

## 实际执行动作与结果

1. **读取冻结计划与计划评审**：完成。独立推导本轮主路径 oracle 后才检查 current tree 的 harness 与报告。
2. **current main provenance gate**：完成并通过。物理 cwd、Git top-level、branch、完整 `HEAD` 与 `refs/heads/main` 均一致。
3. **Phase 0 exact-path 与报告绑定检查**：完成并判红。两个规定 harness 路径不存在；没有报告绑定 current 完整 `HEAD`；code-tree 非 clean。
4. **只读端口／旧 Bun baseline**：完成。`4142／4143` 空闲；`4141` 双栈 listener 为同一 owner。
5. **项目 Python `os.pidfd_open` 探针**：失败，退出码 1；原因是属性不存在。没有产生运行态副作用。
6. **libc pidfd 只读观察**：通过，退出码 0；旧 Bun 前后完整 identity 一致且未被 signal。
7. **fake／app 启动与功能请求**：未执行。原因是 Phase 0 硬门已红。
8. **cleanup**：无本轮 child、listener或临时根需要清理。app／fake wait／reap 为不适用，不能据此报告 M2 PASS。

## 未验证项与后续解除条件

以下项目全部保持 `UNVERIFIED`：nonstream、stream text withholding、Anthropic SSE、合法 terminal、error terminal、History enabled 最小投影、cancel cleanup、graceful shutdown，以及 app／fake child wait／reap。

解除本次 Phase 0 阻断需要先完成 R3 施工阶段 A：加入最小 `LaunchSpec`／credential／config／CLI gate、hash-free cmdline、incarnation、pidfd 与 app／fake wait／reap harness及其 safety tests，形成新的完整 candidate commit；随后取得明确绑定该完整 `HEAD` 与当前 bytes、覆盖合并接缝的独立代码复评 `0 blocker／0 major`。只有该门通过后，新的执行轮次才能创建隔离根并启动 `4143` fake 与 `4142` app。

这不是建议扩大 retry／quota／partial-write 矩阵；这些矩阵继续保持本轮 scope 之外。也不授权安装 unit／manager 或执行 cutover。

## 结构怪味扫描

| `file:line`／surface | 怪味类型 | 处置 |
|---|---|---|
| `docs/tmp/260807-resume-backup-port-smoke-r3.md:207-235,363` 对 current tree | 计划要求的可执行 safety harness 尚未进入 candidate，若临时以内联脚本替代会绕过完整 candidate 复评接缝 | 本轮不补生产或 harness 文件，按 Phase 0 fail closed；后续应先完成施工阶段 A，再重评新完整 HEAD |
| `verification/final_acceptance/probes/00_cli_smoke.sh` 至 `07_gemini_azure.py` | 多个既有 probe 各自覆盖功能片段，但没有 R3 的统一 LaunchSpec／pidfd／双 child wait-reap owner；拼接报告容易产生 false-green | 本轮不拼接放行；只把它们记录为非等价资产 |
| current worktree dirty snapshot | 并行 dirty 状态使“报告绑定后 bytes 未变化／cleanliness”无法成立 | 未改、未清理任何既存内容；在新完整 candidate 与独立复评冻结后另开执行轮次 |

## 最终收口

本轮严格停在 Phase 0。唯一正确判定是 `INCONCLUSIVE_PHASE0`，不是 `FAIL_STREAM_BEHAVIOR`，因为功能路径没有执行；也不是 `PASS_CURRENT_LAYER` 或 `PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`，因为缺少经完整 candidate 复评的 R3 harness，所有用户要求的功能 smoke 项均未验证。
