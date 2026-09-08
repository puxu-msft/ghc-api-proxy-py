# Living docs after main replay 定向复评 R2

- **评审范围**：稳定读取并只读核对 current `docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/systemd-runtime/plan.md` 与 `docs/agents/service-cutover/readiness.md`。本轮只裁定 foundations／systemd 已进入 `main`、archive refs、happy／usage 尚待进入 `main`、产品 `UNVERIFIED`、`NO_CUTOVER` 与 living 不收口六项状态，以及这三份文档能否形成 checkpoint；不重新评审产品代码、运行态、Spec／Acceptance，也不把 `README.md` 或三份目标之外仍旧陈旧的其他 Plan 纳入 verdict。
- **总体 verdict**：**可进入下一阶段。三份 current living 文档可作为同一 checkpoint 提交。** 本轮未发现 blocker 或 major；唯一 non-blocking minor 是 Readiness 内嵌的 Implementation SHA-256 未同步到本轮稳定 bytes。该 identity 漂移不反转六项核心状态，也不授权产品、部署或 cutover 升级。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **checkpoint 结论**：`implementation.md`、`systemd-runtime/plan.md`、`service-cutover/readiness.md` **明确可 checkpoint 提交**。这里的 `0 blocker／0 major` 只放行这三份 living 文档的当前状态 checkpoint，不表示 Implementation／Plan 收口、完整 bridge 产品通过、unit 已安装、服务已部署或生产切换获授权。
- **评审基线**：每次 shell 调用均在同一调用内验证物理 root `/home/xp/src/ghc-api-proxy-py`、当前目录、分支 `main` 与 `HEAD == refs/heads/main`；稳定基线为 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。三份 current 工作树内容的 SHA-256 分别为 Implementation `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a`、Systemd Plan `6646cb727e1bc92ce02ec2bd76f825bb8c9b7d190dbd907ed9f9a6e776f156e6`、Readiness `a8abccf4ffd3168c5b3eaa5531de24f24f423948d72235a383e7a220e8101270`；由 Python `hashlib.sha256` 与 `sha256sum` 两种方法交叉验证一致，并在连续读取中保持不变。

## 双视角覆盖证据

### 机械核对视角

1. 完整读取三份 current bytes，并扫描 `main`／archive／happy／usage／`UNVERIFIED`／`NO_CUTOVER`／living／checkpoint／收口相关语句；对账顶部状态、进度表、下一步与尾部总结，没有发现六项状态互相矛盾。
2. 机械验证 `d274f584219f8ae32f59d15d08ac007c45058c8d`、`798ba3e7653b513c3c9c732019e793f828ae0890`、`1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`、`cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 均为 current `main` 祖先；这支持 foundations 三片与 systemd runtime 已进入 `main`。
3. 机械验证五个 archive refs 精确指向文档声明的 reviewed source：reasoning `d90c90d7…`、reasoning cardinality `b876e626…`、liveness `f27a8c04…`、request `fdd2f75f…`、systemd `49fb1988…`。对 liveness 额外以共同基线累计 diff 与最终 blob 比较，确认 archive source 和 main squash 的两个变更文件及 patch 一致，避免把多提交 source HEAD 与单提交 squash 直接比较造成假红。
4. 机械验证 happy integration `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 与 usage `aca3ced6e38efabf13ffe43d5935697801c74857` 均不是 current `main` 祖先；文档把二者写成“happy 先回放、usage 后继再回放”与 Git 事实一致。
5. 交叉引用核对发现 Readiness 第 9 行记录 Implementation current SHA-256 `4ace3022…`，而本轮稳定 current Implementation SHA-256 是 `60e09d3b…`；这是唯一事实性偏差。

### 第一人称执行视角

1. 以接手者身份从 current `main@cf53334…` 依次执行文档给出的后续路径：已完成 foundations 与 systemd M1 checkpoint后，不重复回放；下一代码动作先消费 happy 四片，再消费其 child usage，最后进入 route wiring。该顺序与 Git 祖先关系及 Implementation 进度表一致，没有丢失依赖分支。
2. 以部署执行者身份沿 Systemd Plan 与 Readiness 走到运行门：M1 只代表仓库 checkpoint，仍需 graceful timeout、install helper、真实 user-manager／cgroup smoke；当前不能安装 unit、抢占 `4141` 或触碰 `cc-daemon`。Readiness 始终停在 `NO_CUTOVER／FOUNDATIONS_ONLY`，没有可被误读为当前切换授权的分支。
3. 以产品验收者身份从局部 review／main-side gate 追到完整产品结论：Implementation 明确保持产品 `UNVERIFIED`，Readiness 明确缺少同一完整候选的 P0～P3 证据；局部 `0／0`、375 tests、archive refs 与 main replay 均不会升级为产品 `PASS`。
4. 以文档维护者身份执行 checkpoint 后续：Implementation 和 Systemd Plan 都明确 checkpoint 不等于收口，Readiness 是持续更新的实时矩阵；提交这三份文档不会终止后续更新循环。即使范围外的 `README.md` 或其他 Plan 仍旧，其陈旧状态也不应被本报告静默解释为已复评或已关闭。

## 事实性发现

[minor] `docs/agents/service-cutover/readiness.md:9` — Readiness 声称 bridge Implementation 的 current SHA-256 为 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2`，但连续稳定读取并由两种哈希方法交叉验证的 current `implementation.md` SHA-256 为 `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a` — 执行者若按该字段定位被汇总的 Implementation bytes，会得到错误内容身份；不过同段及 Readiness 总览仍正确陈述 foundations／systemd 已进 main、完整 P0 缺口、未安装与不得外推，因此不改变 checkpoint、产品或 cutover verdict — 建议下次同步 Readiness 时把内嵌哈希更新为 `60e09d3b…`，并继续让任何后续 Implementation bytes 变化触发重绑。

除上述 identity minor 外，**未发现其他问题；未发现阻断性问题。**

## 主观建议

[建议] `docs/agents/service-cutover/readiness.md:9` — 当前把易变 Implementation 全量 SHA 手工嵌入另一份 living 文档，容易在并行修订时再次漂移 — 预期影响是增加复评噪声并削弱 provenance 的可信度，但不影响当前功能状态 — 推荐保留哈希绑定，同时在文档 checkpoint 流程中加入“三份目标内容身份同轮重算并交叉引用”的机械检查，而不是取消身份绑定。

## 结构怪味扫描

- `docs/agents/service-cutover/readiness.md:9` — **跨 living 文档手工复制易变 identity** — 本轮登记为 non-blocking minor；后续同步修正并增加同轮重算检查。
- 扫描范围：三份目标文档的状态头、当前事实、进度／readiness 表、下一步、不可声称边界与尾部总结。除上述重复 identity 漂移外，未发现状态职责错位、相互矛盾的下一动作或把局部 checkpoint 重复升级为产品／部署结论的结构问题。
