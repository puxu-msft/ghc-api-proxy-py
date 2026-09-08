# systemd code-only 合并态独立评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-code` 的 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，精确 base／current main 为 `80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖严格线性的两条 non-merge commits：`862f4cfa55b124ef9ad21ff2ded2b944ee3307bc feat: configure graceful shutdown timeout` 与 `2ec0cb81832691685bfe8d98ad03071d2d5e5316 feat: add rootless systemd user installer`。按用户要求排除 `docs/agents/systemd-runtime/plan.md`，重点核验 code-only 重建相对旧 reviewed integration `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的非 Plan bytes、user unit timeout parent adaptation、tests、真实 `systemd-analyze`、installer dry-run 与 worktree clean；未安装 unit、未调用 `systemctl`、未修改 manager、服务、端口、数据或 refs。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major 明确允许按当前顺序逐片回放到 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。** 回放顺序必须为 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316`；每片在 main-side identity／preimage／tests gate 通过后才进入下一片，失败即停。本 verdict 不表示 unit 已安装、真实 user manager／effective cgroup 已验证、部署／cutover 或 rolling 已完成。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：2，均继承自旧 reviewed `0a93e7f…` 的已知后补边界，本轮未发现新增 minor：S3 配置优先级测试对中间 YAML／env 层判别力不足；S4 installer 只保证逐文件原子替换、文档措辞与失败恢复回归仍待后补。二者均已有独立运行时／故障证据证明不构成当前运行时错误，不阻塞逐片回放。
- **archive provenance**：两片成功回放并分别通过 main-side gate 后，reviewed source archive targets 固定为 graceful `865a5b71210e2436b36786b5de67146939d1e0f5` 与 installer `e16c2a700f23f66535e7347ab7357518eb8e56bd`。它们保留 source provenance，不改指 code-only integration commits；本轮不创建、更新或删除任何 ref／worktree。

## 双视角覆盖证据

### 机械核对视角

- 每次采用为证据的 shell 调用均在同一调用内打印并验证目标物理 root、`integrate/260807-systemd-code-only`、exact HEAD 与 clean 状态；测试进程另用目标 `PYTHONPATH`，import oracle 返回 `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code/src/app/__init__.py`。
- 独立确认提交图严格为 `80bc8f2… → 862f4cf… → 2ec0cb8…`，范围内恰有两条 non-merge commits、零 merge commit；第一片只包含 S3 graceful timeout 的 9 个非 Plan paths，第二片只包含 S4 installer 的 3 个非 Plan paths。两条提交均未修改 `docs/agents/systemd-runtime/plan.md`，目标 Plan blob 与 base 相同。
- 用两种不同原理核验旧 reviewed 等价性：`git diff --quiet 0a93e7f… HEAD -- . ':(exclude)docs/agents/systemd-runtime/plan.md'` 为零差异；独立 Python blob-map 对 HEAD tree 的 305 个非 Plan paths逐个比较 `0a93e7f…` 与 `2ec0cb8…` blob identity，结果无 mismatch。旧 reviewed integration 与当前 code-only integration 的最终差异仅为 Plan。
- 完整读取最终 implementation、tests、deployment README、旧 merged review、独立 verification、final replay gate、两份 source review 与 installer atomicity 裁决。没有直接转述旧 verdict：本轮重新运行测试、parser 和黑盒副作用 probe。
- 对账最终 timeout facts：system service 与 rendered user service 均为 application `300s`、manager `330s`、严格正余量 `30s`；两类 service 均保留 `KillSignal=SIGTERM`、`KillMode=control-group`、fd 3、socket `Accept=no` 与 slice 合同。把 manager deadline 独立变异为与 application 相等后，oracle 按“manager deadline must strictly exceed app timeout”目标原因转红。
- 检查 installer 全部副作用面：默认／`--check` 不进入 `_apply()`；只有显式 `--apply` 写 `$XDG_CONFIG_HOME/systemd/user`；代码无 `systemctl`、reload、enable、start、restart 或 stop 路径。`--check` 在 parser 存在时执行真实 `systemd-analyze --user verify`，工具缺失时只报告 text validation，不冒充 parser 通过。

### 第一人称执行视角

- 作为 main 回放执行者，从 `main@80bc8f2…` 先应用 `862f4cf…`，该片建立共享 graceful timeout 常量、配置／CLI／Uvicorn 接线和 system unit deadline；只有第一片 main-side gate 通过后，才应用 parent 指向第一片的 `2ec0cb8…`。反向回放会让 installer tests 对 `app.graceful_timeout` 的依赖失去合法 parent，因此禁止调序。
- 作为 system service 使用者，从 fd 3 启动时 CLI 的 `--graceful-timeout 300` 进入 Uvicorn `timeout_graceful_shutdown`，systemd 在 `330s` 才达到 manager hard deadline；短 timeout production-path smoke 会阻塞真实 `/v1/messages`，SIGTERM 后命中 Uvicorn timeout，继续执行 FastAPI lifespan cleanup 并有界退出。
- 作为普通用户首次运行 helper，默认 `--check` 只渲染并验证三份 user units；全新临时 HOME／XDG 根在真实 parser 通过后仍没有 config／state 持久目录。显式 `--apply` 才逐文件写 service／socket／slice，重复 apply 相同 bytes 不改 mtime，且任何路径都不操作 manager。
- 作为归档执行者，两片回放并各自通过 gate 后分别归档 reviewed source `865a5b7…`／`e16c2a7…`；第二片是适配 S3 parent 后的 integration commit，不能替代 installer source provenance。
- 作为后续部署执行者，不会把本次 code-only 0 major 外推为真实 user manager activation、effective cgroup、双 fd／双栈、unit 安装、`localhost:4141` cutover、rolling 或完整产品 `PASS`。

## 独立验证结果

- **定向测试**：目标 import oracle 固定后，`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`、`tests/smoke/test_systemd_units.py` 与 `tests/smoke/test_systemd_user_install.py` 通过。定向数量只来自 pytest 输出，不作为独立计数结论。
- **全仓测试**：目标 `tests` 全量 pytest 为 `440 passed`；同一 exact HEAD、同一 `tests` 路径的独立 `--collect-only` 为 `440 tests collected`，数量口径由两种执行方式交叉一致。
- **静态检查**：Ruff 对 `src`、`tests` 与 installer 通过；Pyright 对同范围为 `0 errors, 0 warnings, 0 informations`。
- **真实 parser**：rendered user service／socket／slice 通过真实 `systemd-analyze --user verify`；system templates 仅对安装前不存在的账户、工作目录、解释器与 Documentation 路径做受控本机适配后，通过真实 `systemd-analyze verify`，未屏蔽其他诊断。
- **dry-run 黑盒**：全新临时 HOME／XDG 根运行真实 helper `--check`，返回成功、真实 user parser 通过，config／state 根均未创建。
- **工作树**：测试、静态检查、parser 与黑盒 probe 结束后，目标仍为 exact HEAD 且 `git status --porcelain` 为空；两个 archive source worktrees也分别固定在 exact source HEAD 且 clean。
- **证据取舍**：一次共享终端测试输出受到外部 `Ctrl-C`／命令文本串入，已明确弃用；上述测试结论来自随后使用独立进程组并写入专属 `/tmp` 日志的完整重跑。

## 事实性发现

[minor] `tests/unit/test_config_loader.py:92-109` — shutdown 专属用例只断言最终 CLI 值 `13`，不能独立证明 YAML `11` 与 env `12` 都被消费；两个中间 source 同时失效时该用例仍可能绿 — 独立 runtime probe 已确认当前产品链路为 default `300` → YAML `11` → env `12` → CLI `13`，因此这是测试判别力缺口而非运行时错误 — 后补拆成 default-only、YAML-only、YAML＋env、YAML＋env＋CLI 四层断言或等价参数化；不阻塞本次回放。

[minor] `contrib/systemd/install-user.py:163-189`、`docs/agents/deployment-systemd/README.md:63-77` — `_apply()` 按固定顺序逐个调用单文件 `_write_atomic()`，不提供三份 unit group all-or-nothing transaction；“三份文件原子写入”仍可被误读，仓库测试尚未固化第二／第三次 replace 失败后的恢复合同 — 既有独立故障注入证明失败显式非零、无临时残留、不触碰 manager，修复外部故障后重跑可收敛；已有裁决明确允许后补 — 把措辞统一为“按固定顺序逐文件原子替换；整组不承诺 all-or-nothing”，并增加第二／第三目标失败后显式失败、无临时残留、重跑收敛的参数化回归；不为此引入三文件事务或 rollback。

除上述两项既有 non-blocking minor 外，未发现事实性问题。尤其未发现额外 commit、merge commit、Plan 混入、非 Plan bytes 漂移、user unit timeout 适配缺失、system／user deadline 不一致、dry-run 持久写、manager side effect、parser 伪绿、测试回归或 dirty worktree。

## 主观建议

[建议] `src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21` — user renderer 独立复述 `300／330`，而不是导入应用常量 — 预期影响是未来维护者可能只改一处；当前 system／user parity regression 和本轮独立 probe 会让漂移转红，故不构成 correctness finding — 保持 installer 可独立加载的边界，长期可把公共 facts 提取到无应用依赖的轻量模块，或继续维护明确的 parity gate。

## 结构怪味与方案反思

- `contrib/systemd/install-user.py:20-21`｜跨 renderer 重复 timeout facts｜本轮不改；已有 parity 测试和独立正／负样本 gate，长期可提取轻量共享 facts。
- `contrib/systemd/install-user.py:163-189`｜逐文件原子与整组事务措辞边界｜维持已裁决 minor并后补回归。
- `tests/unit/test_config_loader.py:92-109`｜复合优先级测试对中间层判别力不足｜维持 source review minor并后补参数化。
- **更好的内部替代方案**：继续复用 Uvicorn graceful shutdown、FastAPI lifespan 与 systemd deadline／parser，优于自研 signal owner、timeout scheduler 或 unit parser；显式 user renderer也优于从 system template 做脆弱字符串删除。
- **判据判别力**：timeout 相等正控按目标机制转红；真实短 timeout 走生产 CLI／Uvicorn／lifespan；dry-run 以持久目录副作用为独立 oracle；全量测试数量由执行与 collect-only 交叉核对。已知两个薄弱面已保留为 minor，没有因全绿静默删除。
- **成熟第三方方案**：unit 语义交给官方 `systemd-analyze`；单文件 durable replace 使用 Python 标准库。当前没有引入第三方 installer framework 的事实基础。

## 最终结论

**0 blocker／0 major；可以并且应当按 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 逐片回放到 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。** 每片执行前重验 main identity／preimage／共享 worktree重叠 paths，执行后跑该片 main-side gate；失败即停。成功后 archive targets 固定为 reviewed sources `865a5b71210e2436b36786b5de67146939d1e0f5`／`e16c2a700f23f66535e7347ab7357518eb8e56bd`。两项已知 minor继续后补，不阻塞回放；本结论不授权安装、部署、manager 状态变更、cutover 或 rolling。
