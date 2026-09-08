# 备用端口关键主路径 smoke R2 独立快速复核

## 评审范围与 verdict

- **评审范围**：只读复核 `docs/tmp/260807-final-backup-port-smoke-r2.md`，目标内容 SHA-256 为 `dc36632f79e84bbff363762b7b2e295aaab8f68389899a14ab2425b93c49e961`；每次有效 shell 调用均在同一调用内断言主树 `/home/xp/src/ghc-api-proxy-py`、branch `main` 与完整 HEAD `e9fb2771d6e040c761bb4074e3fcf2547caece28`。检查仅限实际进程／端口终态、credential isolation、process incarnation、wait／reap、点名主路径 `PASS`、stream request facts 唯一缺口、未验证边界与 `NO_CUTOVER`。
- **总体 verdict**：**可归纳。0 blocker／0 major／1 minor。** 报告可以作为 `main@e9fb277…` 的 scoped 备用端口关键主路径证据归纳；不能归纳为完整 bridge／Acceptance 通过，也不产生部署或 cutover 授权。
- **执行边界**：本轮未重跑服务、fake、smoke或测试，未扩展矩阵，未发送 signal，未读取 credential value，未操作 systemd／manager／cgroup、生产 `4141`、数据或 Git refs。唯一仓库写入为本评审文件。

## 双视角覆盖证据

### 机械核对

- 完整通读目标报告并逐项对账判定、验收矩阵、有效运行证据、进程终态、发现、未验证边界与最终结论。`docs/tmp/260807-final-backup-port-smoke-r2.md:5-25,27-44,56-66,77-89` 对 candidate identity、固定 `4142／4143` 拓扑、credential／config 隔离、主路径结果、pidfd incarnation、原 handle wait／reap、旧 Bun 零 signal、最终清理、测试数量口径和结论上限前后一致。
- 只读现场探针再次确认：`4142／4143` 当前均无 listener；历史 fake PID `1708442` 与 app PID `1708447` 均无 `/proc` 项；旧 Bun 仍为 PID `818465`、starttime `2138402`、cwd `/home/xp/src/copilot-api-js`、cgroup `0::/init.scope`、argc `5`，并继续持有 IPv4 inode `16023105` 与 IPv6 inode `15964765`。这独立支持报告的最终端口释放、历史 child 消失与旧 Bun incarnation 未漂移；它不冒充对已结束运行中间态的重放。
- credential isolation 的封存证据在 `docs/tmp/260807-final-backup-port-smoke-r2.md:15-17,29` 一致要求隔离 `HOME／XDG_CONFIG_HOME／XDG_DATA_HOME／TMPDIR`、显式一次性 config、六个 credential／config presence 为 false、从空字典按 allowlist 构造 child env、argv 无 `--github-token／-g`，且不记录 credential value 或 hash。报告没有把“未提供真实 credential”误写成“真实 credential 已验证”。
- 唯一缺口有 current source 旁证：`src/app/pipeline/executor.py:361-376` 仅在 nonstream response body 分支发布 request conversion facts；`src/app/history/consumer.py:145-165` 的 stream usage projection固定输出空 `conversion_facts`。这与报告中 nonstream fact存在、stream fact缺失的真实 History 观察方向一致。
- 扫描 `docs/tmp/260807-final-backup-port-smoke-r2.md:8,44,77-89`，未验证项始终保留为 `UNVERIFIED`；部署与生产 `4141` 始终不获授权，没有 scoped `PASS` 外推为完整产品或 cutover `PASS`。

### 第一人称执行模拟

- 作为 smoke 执行者，沿报告的顺序执行时，会先固定 current main与产品路径无diff，再要求备用端口空闲、隔离环境与显式 config，随后启动两个 direct child并立即绑定 pidfd／incarnation；完成 nonstream、stream withholding、Anthropic SSE／唯一 terminal、cancel cleanup后，只能通过绑定的 app pidfd发送一次 `SIGTERM`，最后必须由原 `Popen` handle wait／reap两个 child并验证历史 `/proc` 项、临时根和 `4142／4143` listener消失。端口空闲、shutdown日志或 PID相同均不能单独替代 wait／reap与incarnation判据，执行顺序没有留下模糊认领或误杀旧 Bun的分支。
- 作为结果使用者，主路径可读取为 `PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`：nonstream、stream首成功字节 withholding、Responses SSE→Anthropic SSE、唯一 `message_stop`、cancel、SIGTERM lifespan cleanup与资源回收均通过；History只能读取为 nonstream request facts通过、stream request conversion fact偏差，不能把 History整项读成全 `PASS`。
- 作为部署／cutover执行者，遇到 retry、quota／resident backpressure、真实 partial-write／RST、完整 terminal／usage矩阵、真实 credential／upstream、systemd manager／effective cgroup、完整 Acceptance或生产 `4141` 时必须停止外推。目标报告明确把这些列为未验证，并保持 **`NO_CUTOVER`**；本复核不改变该边界。

## 事实性发现

[minor] `docs/tmp/260807-final-backup-port-smoke-r2.md:7,21,48-54` — stream History未承载 final attempt 的 typed request conversion fact — 同一 metadata输入在 nonstream History usage中产生 `metadata.smoke_extra／metadata_not_allowlisted／attempt=0`，stream usage却缺失该fact；current `src/app/pipeline/executor.py:361-376` 与 `src/app/history/consumer.py:145-165` 显示该语义分别被放在nonstream-only发布点和stream固定空投影中 — 该缺口降低stream History的可审计性，但不改变本轮点名外部stream、cancel、cleanup主路径，且本轮验收将History request facts限定为“若可”，因此定为minor而非major；后续在共享context事实层修复，并在修复后单独验证，不在本轮扩展矩阵。

除上述唯一minor外，**未发现其他事实性问题，未发现阻断性问题或major。**

## 主观建议

无。

## 最终结论

`docs/tmp/260807-final-backup-port-smoke-r2.md` 对 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 的 scoped 结论可归纳为：**关键备用端口主路径 PASS，伴随唯一 stream request facts缺口；0 blocker／0 major／1 minor。** 实际进程／端口终态、credential isolation叙述、incarnation与wait／reap证据未见矛盾；未验证边界保持完整；整体继续为 **`NO_CUTOVER`**。
