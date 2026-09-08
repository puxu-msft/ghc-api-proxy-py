# systemd living Plan current R2 定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/systemd-runtime/plan.md`，SHA-256 `f5704171f674579b3865bf5466593411c08d4f70cff59b9e3ec4421cfbaefc80`；主树固定为 `main@b91e58a29324b11840002efc53ed6f869b800c39`。定向核对 new-main rebuild `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` → `d3fabfadfba57af6c2d63e543e3198444777df54`、current merged-state code review `0 blocker／0 major`、两份独立 verify `PASS`、旧 `862f4cfa…`／`2ec0cb8…` 与 `91f95f7…`／`0a93e7f…` 的历史边界、Plan `LIVING` 不收口、逐片 main-side gate 后 fresh Plan update、S5 真实 manager／cgroup、S7 rolling、既有 non-blocking minors 与 `NO CUTOVER`。未重审候选代码，不执行测试、回放、安装、manager 操作、服务／端口变更或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**修复 major 后可进入下一阶段；当前不可 checkpoint。** Current Plan 已准确消费 new-main identity 与两份 verify `PASS`，但没有消费或引用同一 exact candidate 的 merged-state code review `docs/tmp/260807-resume-review-systemd-rebuild.md` 及其 `0 blocker／0 major` verdict。Plan 因而尚未满足本轮明确要求的“review 0 major／verify PASS 均进入 living truth source”证据门。
- **blocker 数**：0。
- **major 数**：1。
- **报告自身评审状态**：本会话处于叶子 reviewer 模式，不能派生独立 reviewer；主会话仍须安排对本报告文本的独立复核。该待复核状态不改变本轮已取得的底层 Git／文档证据，也不能被表述为报告自身已经二次评审。

## 双视角覆盖证据

### 机械核对视角

- 每个承载结论的 shell 调用都在同一次调用内验证物理 root、Git top-level、`main` 分支、exact `HEAD=b91e58a29324b11840002efc53ed6f869b800c39` 与 Plan SHA-256。`sha256sum` 和 Python `hashlib.sha256` 两种实现均得到 `f5704171f674579b3865bf5466593411c08d4f70cff59b9e3ec4421cfbaefc80`。
- Git 对象证明 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` 的 parent 精确为 `b91e58a29324b11840002efc53ed6f869b800c39`，变更 9 个非 Plan paths；`d3fabfadfba57af6c2d63e543e3198444777df54` 的 parent 精确为 `8cae6c2…`，变更 3 个非 Plan paths。`d3fabfa…` 尚不是 `main` 的祖先。
- `docs/tmp/260807-resume-review-systemd-rebuild.md` 精确绑定 `base@b91e58a…` 与 `tip@d3fabfa…`，结论为 `0 blocker／0 major`，并明确允许按 `8cae6c2…` → `d3fabfa…` 顺序逐片进入 main，每片 identity／preimage gate 与 main-side tests gate 通过后才进入下一片。
- `docs/tmp/260807-verify-systemd-rebuild-resume.md` 与 `docs/tmp/260807-resume-verify-systemd-rebuild.md` 均绑定 `tip@d3fabfa…` 并给出 `PASS`。两者覆盖 474 项全仓执行／collect-only、Ruff、Pyright、配置逐层观察、两条 Uvicorn 路径、system／user deadline、四个单侧 drift 正控、短 SIGTERM cleanup、installer 默认零写／临时 apply／幂等／零 `systemctl` 与 Plan 排除；均明确不覆盖真实 user manager／cgroup、安装、部署、cutover 或 rolling。
- Plan 精确引用两份 verify 文件各 1 次，但对 `260807-resume-review-systemd-rebuild.md` 的精确引用为 0 次。页首、S6 评审段与 kick-off 都只写“两份独立验收 PASS”；页首“评审输入”仍只列旧 code-only review／verify，并明确说旧 verdict 不放行 new-main replay。因此不能把旧 `2ec0cb8…` 的 review 或两份 verify 中的严重级别字段替代为 current new-main code review 已被 Plan 消费。
- Plan 已正确把旧 `862f4cfa…`／`2ec0cb8…` 与 `91f95f7…`／`0a93e7f…` 限定为历史 provenance／oracle，禁止 direct replay、cherry-pick 或采用旧 Plan postimage；未发现旧 identity 回流为 current payload。
- Plan 在状态看板、第 7 节和 kick-off 保持逐片 main-side gate、每片 fresh Plan update 与完成每个切片后立即更新证据；S5 保留真实 user-manager／cgroup activation、lifecycle、effective limits 与 declared／effective／runtime 三层对账；S7 保留独立 rolling 设计。`LIVING`、不收口与禁止安装、manager 操作、生产 4141 接管、部署和 cutover 的边界一致。
- 两项既有 non-blocking minor——config precedence 永久测试判别力与 installer 逐文件 atomicity／恢复合同——均保留；Plan 还如实登记 new-main verify 新增的 timeout facts 重复 owner minor，三者均未被升级为当前 main 收敛门。
- 只读运行态复核确认 `127.0.0.1:4141` 与 `[::1]:4141` 仍由 Bun PID 1623 持有，命令为 `bun run ./packages/cli/src/main.ts start`，cgroup 为 `0::/init.scope`；Plan 对旧 Bun 非候选 unit、执行前重取身份和不得触碰生产 4141 的表述成立。该 PID 仅为本轮现场快照。

### 第一人称执行视角

- 作为 main 收敛执行者，从页首、S6 和 kick-off 进入时，我能识别 exact new-main 链、两份 verify `PASS`、三个 non-blocking minors、逐片 gate、fresh update 与停止条件；不会重新构造 S3／S4，也不会回放旧两条链。
- 但按 current Plan 的证据输入执行，我只会消费两份 verify 和旧 code-only review，无法从 Plan 得知 current `d3fabfa…` 已取得独立 merged-state code review `0 blocker／0 major`。这会让“review 门是否闭合”出现两种执行解释：要么错误地把 verify 当 code review，要么在进入 main 前重新发起已经完成的 merged-state review。两者都违背 living truth source 应准确记录 current gate 的目标。
- 正确流程应是：先明确消费 `260807-resume-review-systemd-rebuild.md` 的 `0 blocker／0 major` 与逐片授权，再并列消费两份 verify `PASS`；随后按 `8cae6c2…` main-side gate → fresh Plan update／checkpoint → `d3fabfa…` main-side gate → fresh Plan update／checkpoint 执行。任一 identity、preimage、pathset、Plan bytes或 gate 漂移即停。
- 两片进入 main并完成 fresh Plan checkpoint 后，执行者仍进入 S5 的备用端口、隔离状态根与可回收 user-manager fixture，不会把静态 parser或 inherited-fd smoke冒充真实 manager／cgroup；S7 rolling仍需独立冻结拓扑、readiness切流、状态隔离、drain与回滚。任何仓库绿色均不授权安装、停止旧 Bun、占用 4141、改变 manager 持久状态或 cutover。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:3,6,287-303,425-431` — Plan 未消费 current new-main merged-state code review `docs/tmp/260807-resume-review-systemd-rebuild.md`，却把“两份独立验收 PASS”写成当前 code-only 证据门已闭合 — 该 review 精确绑定 `b91e58a… → 8cae6c2… → d3fabfa…`，为 `0 blocker／0 major`，并给出逐片进入 main与每片 main-side gate 的授权；Plan 对其文件名零引用，评审输入仍停留在旧 `2ec0cb8…` code-only review，S6 与 kick-off 也只陈述两份 verify。两份 verify 即使包含 `0 blocker／0 major` 字样，也不能替代独立 code review 的角色与逐片授权 — 在页首证据摘要、评审输入、S6 评审段与 kick-off 中明确引用并消费 `docs/tmp/260807-resume-review-systemd-rebuild.md`：记录 exact base／tip、`0 blocker／0 major`、逐片顺序与每片 main-side gate；保留两份 verify 为独立 `PASS` 证据，不把三者合称为“两份验收”。修订后重算 Plan SHA并做同范围定向复评。

除上述 major 外，未发现其他 blocker 或 major。特别是未发现 new-main identity 未同步、旧链被当作 current payload、Plan 被收口、逐片 gate／fresh update 被删除、S5 真实 manager／cgroup或S7 rolling被裁切、两个既有 non-blocking minors 丢失，或仓库状态被外推为安装／部署／cutover。

## 主观建议

未提出额外主观建议。本轮唯一需要的修订是补齐 current merged-state review 的证据消费，不应借机改写候选代码、重复运行已闭合 verify或扩大 main 收敛门。

## checkpoint 裁决

Current Plan SHA-256 `f5704171f674579b3865bf5466593411c08d4f70cff59b9e3ec4421cfbaefc80` 为 **0 blocker／1 major，当前不可 checkpoint**。补齐 current new-main merged-state code review `0 blocker／0 major` 的明确引用与 disposition，并保持现有 verify `PASS`、历史链降级、逐片 gate／fresh update、`LIVING`、S5、S7、non-blocking minors 与 `NO CUTOVER` 边界后，对新 SHA 定向复评；达到 **0 blocker／0 major** 时可 checkpoint。该 checkpoint 仍不表示候选已进入 main、unit 已安装、真实 manager／cgroup已验收、服务已部署或 cutover 获授权。
