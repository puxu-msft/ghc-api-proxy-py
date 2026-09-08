# 备用端口 smoke R2 独立复评

- **评审范围**：只读复核主树 `main@b91e58a29324b11840002efc53ed6f869b800c39` 上的 `docs/tmp/260807-resume-backup-port-smoke-r2.md`，只检查上一轮两项 major 的关闭情况，并确认 `STREAM-MERGE-00`～`10` 是否完整保留且只在 stream candidate 达到独立复评 `0 blocker／0 major` 后执行。未复评 stream 产品实现、完整 Acceptance、真实凭据、真实 upstream、systemd、部署或 cutover；未启动 app／fake，未占用端口，未读取凭据值，未发送 signal，未修改 Git refs 或运行态。唯一仓库写入为本报告。
- **被评审 bytes**：`docs/tmp/260807-resume-backup-port-smoke-r2.md` 的 SHA-256 为 `50d1e36e08a42f160319eae8693fcead75f38c4ff3e6d177a7223e2c1601cb9b`。该值由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉得到一致结果。
- **总体 verdict**：**修复 2 个 major 后可进入。当前不能作为备用端口 stream 验收计划执行。** M2 的 process incarnation、pidfd／child handle、wait／reap 与旧 Bun 重启判定已关闭上一轮 major；`STREAM-MERGE-00`～`10` 的 ID、目标与红灯边界也已完整保留。但 M1 仍未封闭 CLI credential override 及其 `/proc/<pid>/cmdline` 取证泄露接缝，Phase 0 也只拒绝“相关 major”，没有机械要求完整 stream candidate 独立复评为 `0 blocker／0 major`。
- **blocker 数**：0。
- **major 数**：2。

## 双视角覆盖证据

### 机械核对

- 两次承载结论的 shellgate 均在同一调用内打印并断言物理 cwd、Git top-level、branch、`HEAD` 与 `refs/heads/main`；结果固定为 `/home/xp/src/ghc-api-proxy-py`、`main` 与完整提交 `b91e58a29324b11840002efc53ed6f869b800c39`。
- 对 `docs/tmp/260807-backup-port-smoke-resume.md` 与 R2 表格分别提取 gate ID，并用正则集合脚本和独立文本扫描两种方式交叉核对。两份表的唯一集合均精确为 `STREAM-MERGE-00`、`01`、`02`、`03`、`04`、`05`、`06`、`07`、`08`、`09`、`10`，没有缺号、重命名或额外 ID。
- 对照上一轮两项 major：R2 `:14-86` 已覆盖六个具名 env 入口、任意未批准 `GHC_*`、显式／默认 token file、cwd／XDG config 自动发现、最小 child env、effective settings 与启动前正反控制；R2 `:88-157,173-181,221-224,233-238` 已覆盖 PID＋starttime、cwd／cgroup／cmdline／listener inode、child process handle＋pidfd、提前退出、精确信号、有界 wait／reap、历史 `/proc` 项消失、旧 Bun 重启与双栈 listener identity。
- `src/app/config/loader.py:59-77,80-100` 确认显式 `config_path` 会阻止 `GHC_CONFIG`、cwd `config.yaml` 与默认 config 的路径发现，但 YAML 之后仍依次合并 env 与 CLI overrides。R2 的空环境 allowlist足以封闭 env 覆盖，却不能单靠“存在 `--config`”封闭 CLI 覆盖。
- `src/app/cli.py:50-69,81-109` 确认 app 支持 `--github-token／-g`，且该值进入最高优先级的 `cli_overrides.auth.github_token`。R2 `:48,83` 的 command construction gate只要求 `--config` 存在并指向本轮文件，没有要求 argv 精确 allowlist，也没有 `--github-token／-g` 的反控制。
- R2 `:96-103,231-234` 要求记录并封存完整规范化 `/proc/<pid>/cmdline`。一旦前述 CLI 旁路出现，secret 会作为 argv value 出现在 proc cmdline，因而与 M1 `:20,36` 的“只记录 presence，不记录 value”目标冲突。

### 第一人称执行模拟

- **M1 正向路径**：从空 env 构造 child，使用隔离 HOME／XDG／cwd、显式 smoke config、空 `auth.github_token` 与不存在的专用 token file；依据 current loader优先级，具名 env、嵌套 `GHC_*`、默认 config 与默认 token file均不能向 app 注入真实凭据。
- **M1 反例路径**：构造仍含正确 `--config <smoke-config>`、但额外带 `--github-token <secret>` 的 app argv。现文的 env presence、文件 absence和“`--config` 存在”三道门均可通过；若无服务 settings preflight只复现文中写明的“相同显式 `--config` 语义”而未复现完整 CLI overrides，它仍会报告 `auth.github_token present=false`，实际 `start` 随后却由 CLI override得到 secret。spawn后再封存完整 proc cmdline还会把该 value写入证据包。
- **M2 反例路径**：分别模拟旧 Bun保持 PID但 starttime改变、listener inode换代、fake先关闭 listener后阻塞、app在 SIGTERM前退出及 child退出后漏 `wait()`。R2 的 comparator、原 process handle、pidfd、wait deadline、reap gate与历史 `/proc` 消失要求会逐项判红；未知 owner不会被 signal，旧 Bun重启也不能被“PID相同”洗绿。此项 major已关闭。
- **stream candidate 放行路径**：模拟独立复评为 `0 blocker／1 major`，其中该 major被执行者判断为“不相关”。R2 `:163-164` 的字面条件允许继续进入 Phase 1～3，而本次派活要求只有 stream candidate整体 `0 major` 后才执行；这是实际执行顺序上的放行缺口。
- **gate 执行路径**：在满足 Phase 0～2 的前提下依次执行 R2 `:184-202`，11 个 gate仍覆盖回归、route接线、wire、首 block withholding、完整 batch、semantic order、terminal、failure terminal、lifecycle owner、cancel／cleanup与shutdown；R2 `:238` 仍要求 M1、M2及全部 gate同时通过才报告入口 PASS。除 Phase 0 的 `0 major` 门措辞外，没有发现 gate 集合提前执行或被原 `PASS_CURRENT_LAYER` 替代的路径。

## 事实性发现

[major] `docs/tmp/260807-resume-backup-port-smoke-r2.md:20-48,61-86,96-103,231-234` — M1 没有封闭 CLI credential override，且完整 cmdline 证据可记录 secret value — current CLI 的 `--github-token／-g` 在 `src/app/cli.py:62,96-109` 形成最高优先级 `auth.github_token` override；现计划只机械断言 child env／文件入口并验证 `--config` 存在，没有冻结完整 argv allowlist，也没有注入 `--github-token` 的单缺陷控制。带正确 `--config` 与额外 secret option 的 argv因此可绕过 command construction gate；若 preflight没有消费完全相同的解析后 CLI overrides，preflight与实际 spawn还会检查不同 settings。spawn后按 M2 记录完整 `/proc/<pid>/cmdline` 会进一步把 argv secret写入证据，违反“只记录 presence”边界 — 冻结 app 与 fake 的精确 argv schema，拒绝 `--github-token／-g` 及所有未批准 CLI override；让 preflight与 spawn消费同一个已解析、不可变 argv／CLI-overrides对象，或机械证明两者完全相等；增加注入 `--github-token`、短选项 `-g` 与任一未批准 override后必须在 spawn前判红的控制。身份比较可在确认 argv无敏感 option后使用稳定 digest／脱敏结构，证据包不得保存潜在 secret-bearing raw cmdline value。

[major] `docs/tmp/260807-resume-backup-port-smoke-r2.md:8,161-166,184-186,242` — stream candidate 的执行前置不是完整 `0 major` 硬门 — Phase 0 只写“若仍有 blocker或相关 major，停止”，允许执行者自行把一个现存 major判为“不相关”并继续启动 fake／app；顶部与末尾也只要求“已知缺陷修复／独立复评确认可进入”，没有冻结可机械判断的 verdict。该条件弱于本次明确要求的“只在 stream candidate 0 major 后执行” — 将 Phase 0 改成只有绑定同一完整 candidate commit与当前 bytes的独立复评明确给出 `0 blocker／0 major` 才能继续，任何 blocker或任何 major均停止；在顶部执行时机、Phase 3前置与最终证据包中复述同一硬门，删除“相关”这一执行者自判限定。minor可单独记录 disposition，但不得把局部 gate、旧 hash或上一候选 verdict拼接成 current candidate的 `0 major`。

## 已通过的定向复核

- **上一轮 M2 major已关闭**：process incarnation由 PID＋starttime定义，并辅以 cwd、cgroup、cmdline与listener inode；app／fake绑定原 child handle与pidfd，只允许精确 signal，所有路径进入统一 finally并分别 wait／reap；旧 Bun PID复用、重启或双栈 listener换代均判红。
- **`STREAM-MERGE-00`～`10` 已完整保留**：两种独立提取方法均得到精确连续的 11 个 ID；各 gate目标与失败边界没有被删减，且 gate表位于 Phase 0～2 之后。
- **结论边界保持正确**：R2没有把计划写成已执行，没有沿用 `PASS_CURRENT_LAYER` 冒充 stream candidate通过，并继续把完整 stream／bridge Acceptance、真实凭据、真实 upstream、systemd、部署与 cutover保持为 `UNVERIFIED／NO_CUTOVER`。

## 主观建议

未发现超出上述事实性问题、且属于本轮限定范围的主观建议。

## 结论

**0 blocker／2 major。当前 R2 尚不能明确作为备用端口 stream 验收计划。** 关闭 CLI override／cmdline泄露旁路，并把 candidate放行条件收紧为绑定同一完整候选的独立复评 `0 blocker／0 major` 后，再对新 bytes做定向复评。若复评达到 **0 major**，则可明确把 `docs/tmp/260807-resume-backup-port-smoke-r2.md` 作为**备用端口 stream 验收计划**执行；该放行仍只覆盖 `PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`，不等于完整 stream／bridge产品 `PASS`、部署完成或 cutover授权。
