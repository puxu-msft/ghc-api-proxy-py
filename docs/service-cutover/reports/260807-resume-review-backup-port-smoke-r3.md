# 备用端口 smoke R3 独立复评

- **评审范围**：只读复核主树 `main@b91e58a29324b11840002efc53ed6f869b800c39` 上的 `docs/tmp/260807-resume-backup-port-smoke-r3.md`，严格限定为 R2 两项 major：CLI `--github-token／-g` 与 proc cmdline 证据不得泄露值、preflight／spawn 必须消费同一不可变 `LaunchSpec`；Phase 0 必须绑定同一完整 stream candidate 的独立代码复评总 verdict `0 blocker／0 major`。同时定向确认 credential／config 旁路、process incarnation、精确信号、wait／reap 和 `STREAM-MERGE-00`～`10` 全部保留。未复评或放行任何现有 stream candidate 代码，未运行服务、fake、测试或 smoke，未占用端口，未读取凭据值，未发送 signal，未修改 Git refs 或运行态。唯一工作树写入为本报告。
- **被评审 bytes**：`docs/tmp/260807-resume-backup-port-smoke-r3.md` 的 SHA-256 为 `2bf1dbd5c977728be802d818b752f33a626f98b0382b3c993cd1b0ea1f061821`。该值由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉得到一致结果。
- **总体 verdict**：**可进入执行阶段。R3 为 0 blocker／0 major，可作为后续备用端口 stream smoke 执行计划。** 该放行只表示计划的安全门、执行顺序与失败边界足够明确；它不表示任一现有 stream candidate 已取得 Phase 0 的代码 `0／0`，也不授权跳过施工阶段 A、Phase 0 或直接启动服务。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 每次承载结论的 shell 调用都在同一调用内打印并断言物理 cwd、Git top-level、branch 与完整 `HEAD`；可信结果固定为 `/home/xp/src/ghc-api-proxy-py`、`main` 与 `b91e58a29324b11840002efc53ed6f869b800c39`。一次共享终端返回了其他会话的 systemd 报告输出，因为缺少本轮 nonce 与 shellgate，已明确作废；随后使用会话专属证据文件重新取得同一树、同一 HEAD 的双哈希结果。
- 对照 R2 的第一项 major：current `src/app/cli.py:62,96-109` 证实 `--github-token／-g` 会形成最高优先级的 `auth.github_token` CLI override；`src/app/config/loader.py:59-100` 证实显式 YAML 后仍合并 env 与 CLI。R3 `:63-79` 改为不可变 app／fake argv schema，精确拒绝 `--github-token secret`、`--github-token=secret`、`-g secret`、`-gsecret`、任意未批准 option、重复项、额外 positional 与 `--` 尾参；诊断只允许固定 shape／presence，不输出 value、suffix 或 hash。
- R3 `:96-105,129-134` 要求同一个已通过 gate 的 `LaunchSpec`同时产生 settings preflight 与实际 `Popen` 的 Python、cwd、env、config 和批准的 host／port 投影；两侧不得重建字典或重解析自由文本，spawn 前必须与 preflight 冻结 tuple 逐项相等，并有不同 spec／render 漂移的判红控制。这关闭了 R2 指出的“preflight 检查一个输入、spawn 使用另一个输入”接缝。
- R3 `:107-119,125-132` 将 `/proc/<pid>/cmdline` 原始 NUL tuple 限制在同一 harness 进程内瞬时比较；stdout、stderr、异常、pytest failure、临时文件、证据报告和 Git 仓库均禁止 raw、decoded、base64、截断值、digest 或 hash。可持久化内容只剩 shape、敏感槽 presence、未批准 option presence、hash-free 固定标签投影与同一 PID＋starttime 的 `equal` 布尔值；四种 token CLI 反例还要求 captured output 与序列化证据均不含 canary 或其预计算 hash。
- 对照 credential／config 实现：`src/app/auth/providers.py:52-91` 的真实非交互来源是三个通用 token env、显式或默认 token file；`src/app/config/settings.py:112-143` 使用 `GHC_` nested env；`src/app/config/loader.py:59-77` 的自动配置来源为 `GHC_CONFIG`、cwd `config.yaml` 与默认 config。R3 `:33-61,81-105,123-134` 以从空字典构造的 child env allowlist、隔离 HOME／XDG／cwd、显式唯一 config、空 `auth.github_token`、已知不存在的隔离 token path、文件 presence 门和 effective-settings preflight覆盖这些入口。
- `src/app/server.py:83-96` 证实 generic startup 仍会先调用 `noninteractive_token_available()`。R3 指定的三个 token env absent、显式隔离 token path absent、默认 XDG token absent使这次探测不能触达真实凭据；随后 `upstream.type=generic` 使用本轮 loopback fake 与非真实占位 API key，不需要 GitHub／Copilot凭据。
- 对照 R2 的第二项 major：R3 `:223-237` 明确要求施工阶段 A 后形成包含 stream 实现、harness 与 tests 的最终完整 commit，再取得绑定同一绝对 worktree、ref、完整 HEAD 与当前完整 bytes 的独立代码复评。报告必须覆盖全部实现 diff、harness／tests、known findings 以及 route／parser／delivery／History／cleanup／finalize 合并接缝，并给出总 verdict `0 blocker／0 major`；任何 blocker、任何 major、局部 scope、旧 hash、commit 不一致、报告后 bytes 漂移或 cleanliness 无法证明都在创建临时根或 spawn child 前停止。
- R3 没有把历史 stream 报告误用为现成放行。当前落盘的 `docs/tmp/260807-resume-review-code-stream-route-r2.md` 绑定 `bc436af647507df4ea45f3b01ca8942fade4f036`，实际 verdict 仍为 `0 blocker／5 major`；R3 `:233-235,325,359,363` 明确禁止旧 candidate、局部 `PASS` 或多个子范围报告拼接替代未来同一完整 candidate 的 Phase 0 `0／0`。
- 用表格行提取与独立 Python 正则集合两种方法核对 R3 `:277-287`。表中恰有 11 行，唯一集合精确为 `STREAM-MERGE-00`、`01`、`02`、`03`、`04`、`05`、`06`、`07`、`08`、`09`、`10`，没有缺号、重复或改名；R3 `:273` 又明确它们只能在同一完整 candidate 通过 Phase 0 且 Phase 1～2 全绿后执行。
- R3 `:140-203,250-269,302-319` 保留 PID＋starttime、cwd、cgroup、同轮内存 raw cmdline equality、listener inode／owner 的 incarnation；旧 Bun 双栈 owner 不变；app／fake 原 process handle＋pidfd；只对自建 child 精确信号；提前退出先 wait／reap；所有路径统一 `finally`；两个 child 有界 wait／reap、历史 `/proc` 项消失与 listener 释放均为成功必要条件。

### 第一人称执行模拟

- **CLI credential 反例**：从一个原本合法的 app launch分别追加 `--github-token secret`、`--github-token=secret`、`-g secret` 与 `-gsecret`。最终 argv 已不再与 `LaunchSpec.render_argv()` 精确相等，敏感 option scanner也会在 spawn 前判红；诊断只能产生 `sensitive_slot_present=true`与槽类型，不能携带 `secret`、attached suffix或任何 hash。任一其他未知 option即使不是 credential，也被 schema gate拒绝，不能借 network／config override改变实际启动语义。
- **preflight／spawn 分叉反例**：让 preflight 持有 spec A，而 spawn 尝试使用 spec B，或在 preflight 后改变 render 结果。R3 要求两侧共享同一 immutable owner，并在 spawn 前再次逐项比较冻结 tuple；该反例在零 child 状态判红。执行者不能通过“effective settings 看起来正确”绕过实际 `Popen`身份。
- **credential／config 发现路径**：父进程即使存在真实 token env或用户 config，harness只记录键／文件 presence，不复制 value；child env从空字典构建，app cwd、HOME、XDG、TMPDIR和显式 config都位于一次性根。generic lifespan 的 token availability探测只能看到空 CLI token、空 token env与已知不存在的隔离 token path，无法回落到用户真实默认 token file。显式 config、cwd默认 config、XDG默认 config或默认 token位置任一被放入占位文件时，对应门都会在 spawn前判红。
- **Phase 0 错误放行反例**：独立代码报告给出 `0 blocker／1 major`，或报告只覆盖已知 findings，或报告绑定旧 commit，或报告后修改 product code／tests／harness／dependency／runtime config。R3 `:231-235` 均要求立即停止，且停止点位于 Phase 1 创建临时根和 Phase 2 spawn之前；执行者没有“与 smoke 不相关”的 disposition权限。
- **incarnation／reap 反例**：旧 Bun保持相同 PID但 starttime改变、listener inode换代或内存 cmdline comparator不等时，`SAFE-01`判红；fake关闭 listener后继续阻塞时，wait deadline仍判红；app提前退出时只通过原 handle wait／reap，不向可能复用的 PID或新 listener owner发 signal。端口空闲和 shutdown日志均不能替代两个 child的 wait／reap终态。
- **完整执行顺序**：施工阶段 A 只实现与测试无进程安全核心并形成最终完整 commit；Phase 0 在任何运行态动作前取得同一完整 candidate代码 `0／0`；Phase 1 才创建隔离根并做零 child preflight；Phase 2 才启动 fake／app；Phase 3 才依次执行 11 gates；任一 gate红灯立即停止新请求并进入 Phase 5统一 cleanup。该顺序没有把 plan review、本轮 `0 major` 或历史 `PASS_CURRENT_LAYER`误当成 candidate代码放行。

## 事实性发现

未发现问题。

## 已通过的定向复核

- **R2 CLI／cmdline major已关闭**：四种 token CLI形态与所有未批准 override均在spawn前 fail closed；证据输出统一为hash-free脱敏；preflight与spawn共享同一不可变`LaunchSpec`并有身份漂移反控制。
- **R2 Phase 0 major已关闭**：只有绑定同一完整stream candidate HEAD与当前完整bytes的独立代码总 verdict `0 blocker／0 major`可以进入Phase 1；任何major均停止，不存在“相关major”豁免。
- **credential／config旁路保留且与真实实现来源对齐**：通用token env、任意`GHC_*`、CLI override、显式／默认token file、`GHC_CONFIG`、cwd与XDG默认config均有启动前封闭路径和正反控制。
- **incarnation／wait／reap合同保留**：旧Bun只观察不signal；app与fake绑定原handle和pidfd；PID复用、listener换代、提前退出、wait超时与漏reap均不能洗绿。
- **11个STREAM-MERGE gates完整保留**：`00`～`10`精确连续，且只在Phase 0代码`0／0`和Phase 1～2全绿后执行。

## 主观建议

未发现超出上述限定范围的主观建议。

## 结论

**0 blocker／0 major。`docs/tmp/260807-resume-backup-port-smoke-r3.md` 可作为后续执行计划。** 执行者可以从施工阶段 A 开始，但在同一完整 stream candidate 的独立代码复评明确达到 `0 blocker／0 major` 前，必须停在 Phase 0，不能创建 smoke 临时根、启动 fake／app或运行 `STREAM-MERGE-00`～`10`。本 verdict 不把当前 `bc436af…` 的历史 `0 blocker／5 major`升级为通过，不把计划评审外推为完整 stream／bridge产品 `PASS`、部署完成或cutover授权。
