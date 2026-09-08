# GHE data residency Device Flow 独立复核 R2

- report_id: `ghe-device-flow-review-gpt-r2`
- attempt_id: `260828-review-gpt-r2-01`
- status: `in-review`
- reviewed_at_rev: 主仓 `HEAD 74b9dde5585e009064f21a7721a8fce5ac8dd742`，限定 8 文件的未提交 diff SHA-256 为 `40d56bd40b54bb02bdbb89f19d886fb6d7d4f0666537bc8949a5e4cb7cef4f1f`；`.dev` 仓 `HEAD f78b1680a44126ce536371f2127ffcae167aa911`，`spec.md` SHA-256 为 `10d8a49880f2e764b2483d3d6633fa7ba3b762c2d2c1cd500628103405f476c2`，`status.md` 为 `2c74a42969dc759fc0dc5fac6694eccf6626b1ece708eb4f29c9f74c773e0cc8`，`deferred.md` 为 `c208c27ab57319a1c4fabab7ea8199bdccd89bf58d41628370b3b4c221c709d0`，处置记录为 `59818c013be470947577619141ff599145c12d4b4704ab0cef6b554ea520f19f`

## 评审范围

本轮先读 `.dev/docs/ghe-device-flow/reports/260828-review-disposition.md`，再复核相对上一轮有变化的 `.dev/docs/ghe-device-flow/spec.md`、`status.md`、`deferred.md`，并把两份上一轮报告作为逐条完成度的来源。代码范围仍严格限于调用方列出的 8 个文件；为核接缝，仅读取了既有的 `src/app/config/loading.py`、`src/app/config/bundled-config.yaml`、`src/app/model_provider/registry.py`、`src/app/model_provider/ghc_client/auth/providers.py`、`src/app/server/composition.py` 与已有 auth service tests。

明确不在范围内：工作树中其他人的改动或未跟踪文件、真实 GHE tenant、生产部署、提交、生产代码与测试修复。除本报告外未修改项目文件。

## 总体 verdict

`needs-fix`。上一轮三条具体缺陷中，F-01 与 F-03 已闭合，F-02 报告点名的三个输入也全部闭合；新入口的控制流与失败前状态没有发现新的静默错误。不过 R2 把“裸 `auth/logout` 一律读取三级配置发现链”定成了新的公共行为，而处置记录用一个只能证明“默认 provider 不会因 bundled merge 变得歧义”的事实，外推成“既有部署行为逐字不变”，不足以越过首轮明确下发的兼容性判据。这个范围变化需要用户裁决，故本轮有 1 条 blocker。

## Blocker 数

1。

## 上一轮三条的逐条完成度

| 上一轮发现 | 状态 | 独立复核结果 |
|---|---|---|
| `ghe-device-flow-review-gpt-01` | `closed` | 执行 `auth --provider tenant` 且三级发现链没有该 provider，现为 exit 2、列出 configured `ghc`、网络入口调用 0 次；provider 不再被静默吞掉。裸 `auth` 也确实读取环境变量与默认位置的 tenant config。替代方案引出的范围裁决是本轮 R2-01，不把旧缺陷伪装成未修。 |
| `ghe-device-flow-review-gpt-02` | `closed`（对上一轮点名的三个场景） | `api..ghe.com` 与 `api.foo..ghe.com` 均在边界抛含原值与期望形状的 `ValueError`；`api.github.com////` 按新 Spec 明定归一到 dotcom；非法端口与坏 IPv6 均被统一改写且保留 `__cause__`。同一边界另有此前未点名的空 userinfo 缺口，见 R2-02。 |
| `ghe-device-flow-review-gpt-03` | `closed` | 用 `auth_base_url: http://127.0.0.1:8080` 与自定义 token 文件运行真实 `logout --config ...`，观察到 exit 0、文件被删除；说明 logout 没有错误地复用 OAuth origin 推导。provider 歧义时 exit 1、文件保持原文且不打印成功。 |

## 新发现

### R2-01：`bundled default + _deep_merge` 不能证明裸命令的既有行为逐字不变，配置发现链的范围变化仍需用户裁决

- finding_id: `ghe-device-flow-review-gpt-r2-01`
- severity: `blocker`
- primary_location: `.dev/docs/ghe-device-flow/reports/260828-review-disposition.md:27-33`
- related_locations: `.dev/docs/ghe-device-flow/spec.md:54-72,108-114`；`src/app/cli.py:345-408,442-450`；`src/app/config/bundled-config.yaml:51-56`；`src/app/config/loading.py:37-53,86-107`
- 判据：首轮下发的明确兼容性判据是“不带 `--config` 的老调用必须逐字不变”。把裸 `auth/logout` 从“完全不读取 config”改成读取显式路径之外的环境变量与默认路径，是公共 CLI 行为变化；只有用户裁决或能覆盖所有受影响输入的等价性证明，才能推翻该判据。
- 被质疑的承重前提与结论：处置记录的前提是 bundled 无条件提供 `default_model_provider: ghc` 且 `_deep_merge` 没有删除语义；它据此支撑“既有部署行为逐字不变，所以拆掉门不需要用户裁决”。若这个前提不足以支撑全称结论，下一动作就不能是直接收口，而应把裸命令是否采用配置发现链交用户裁决。
- 独立核实：这个前提能证明的窄命题成立——对有效的普通配置，新增 provider 不会单凭数量让 `resolve_default_name` 进入“未指定默认”分支，因为 inherited default 仍是 `ghc`；我逐条执行 bundled-only、环境 config、默认位置 config、显式 config、configured default、显式 provider、未知 provider、显式空 default + 多 provider、dangling default，分支结果均与当前 Spec 的 provider 选择规则一致。
- 反例与失败场景：该前提没有约束 `auth_base_url`、`github_token_file`、坏配置或 token 环境变量，因此不能证明整个命令等价。基线 `HEAD` 的裸 `_authenticate()` 只执行 `authenticate_device(notify)`，当前裸命令会读取 config。直接探针观察到：①默认位置或 `GHC_API_PROXY_CONFIG` 指向 tenant config 时，裸 auth 从旧版 dotcom／默认文件变为 tenant／provider 文件；②dotcom config 只配置自定义 `github_token_file` 时，裸 auth 从默认文件改写为该文件；③合法 local stand-in `auth_base_url: http://127.0.0.1:8080` 时，裸 auth 从旧版 dotcom 登录变为 exit 1；④没有 config 文件但设置 `GHC_API_PROXY_GITHUB_TOKEN` 时，host 与 token 路径虽仍为 dotcom／默认值，成功输出也新增 warning，已不再“逐字”；⑤默认位置是坏配置时，auth/logout 从忽略它变为在网络或删除前失败。Spec 自己在 §3.5 第 69-72 行承认至少两处行为变化，也与“既有部署逐字不变”的全称表述冲突。
- 影响与定级：新行为有充分产品理由，我的倾向是**保留三级发现链并请用户明确追认这些裸命令变化**，因为 tenant 机器上的自然入口确实是裸 `auth`，而只认显式 `--config` 会让功能再次不可达。但这不是 reviewer 或实现者可以用不成立的等价性证明替用户做掉的 fork。当前不知道该恢复旧门还是正式改合同，正确修复依赖用户裁决，所以定 blocker。
- 建议：把裁决问题精确写成：“`auth/logout` 不带 `--config` 时，是否与 `start/debug models` 一样读取 `GHC_API_PROXY_CONFIG` 和默认配置，并相应采用 tenant origin、provider token 文件与坏配置拒绝？”若用户同意，保留当前实现，改写 §3.5 与处置记录，把“逐字不变”收窄为“在没有发现外部 config、provider 保持 bundled defaults、且不存在 env token warning 的 dotcom 环境，网络目标与文件路径不变”，并逐项列出现有行为变化；若用户不同意，则恢复显式门并另定 tenant 裸入口。

### R2-02：空 userinfo 通过 truthiness 校验，仍违反 §3.2 的“不得带 userinfo”

- finding_id: `ghe-device-flow-review-gpt-r2-02`
- severity: `minor`
- primary_location: `src/app/model_provider/ghc_client/config.py:67-82`
- related_locations: `.dev/docs/ghe-device-flow/spec.md:22-40`；`tests/component/model_provider/ghc_client/test_config.py:75-106`
- 判据：Spec §3.2 明定任何 userinfo 都应 `ValueError`。presence 与 value 是两个事实；空字符串 userinfo 仍由 URL 的 `@` authority syntax 明确表达，不能用字段 truthiness 代替 presence。
- 证据：直接执行 `resolve_github_web_base_url('https://@api.github.com')` 与 `resolve_github_web_base_url('https://:@api.github.com')`，两者都返回 `https://github.com`。原因是 `parts.username`／`parts.password` 分别为 `''`，当前 `or parts.username or parts.password` 判定为假。现有负例只有 `https://user:pw@api.github.com`，因此会绿。证据权重足够直接行动。
- 失败场景：配置写成 `auth_base_url: https://@api.github.com` 时，本应在配置边界按 §3.2 拒绝，实际登录继续发往 dotcom。构造出的最终 host 仍正确且 userinfo 被重建过程移除，没有错发或秘密泄露，因此定 minor，而不是把它包装成安全问题。
- 建议：先由 Spec 决定空 userinfo 是否也允许被规范化；按当前明确文本，应按 netloc 中是否存在 userinfo delimiter 检查 presence，并补空 username／空 password 的负例。相邻的空 query／fragment delimiter 与尾部空 port delimiter也会被规范化，应在同一次 Spec 判定里明确是允许归一化还是按“带组件”拒绝，不要继续由 `urlsplit` 的空字符串投影替项目做决定。

### R2-03：`_read_config` 没有接住 loader 自己定义的坏配置异常，auth/logout 会输出 Rich traceback

- finding_id: `ghe-device-flow-review-gpt-r2-03`
- severity: `minor`
- primary_location: `src/app/cli.py:477-488`
- related_locations: `src/app/config/loading.py:56-62`；`.dev/docs/ghe-device-flow/spec.md:69-72`
- 判据：`_read_config` 的公开目的与 docstring 是把普通 operator config 错误报告成一条错误而不是 traceback；R2 又把该 helper 新接到裸 auth/logout。Spec §3.5 明写坏配置应打印 schema／配置消息并 exit 1。
- 证据：`loading._read_yaml()` 对 YAML 根为 list 或 scalar 明确抛 `ValueError`，但 `_read_config` 只 catch `FileNotFoundError`、`ValidationError` 与 `YAMLError`。真实执行 `uv run ghc-api-proxy auth --config list.yaml`，文件内容为 `- one\n- two\n`，观察到 return code 1、stdout 空、stderr 是从 `auth` 到 `_read_yaml` 的完整 Rich traceback，末尾才是 `ValueError: configuration file must contain a mapping`；`logout` 同样。非法 UTF-8 还会以未翻译的 `UnicodeDecodeError` 走同一形态。证据权重足够直接行动。
- 失败场景：运营者把 config 根误写成 YAML list 后执行 auth 或 logout，得到内部调用栈而不是当前命令其余坏配置统一采用的 `error: ...`；logout 也不会清 token。失败是响亮的、修正 config 可绕行，不会打错 host 或删错文件，故定 minor。
- 建议：让 config loading 层产生一个统一、窄作用域的配置读取异常，或在 `_read_config` 精确覆盖 `_read_yaml` 的非 mapping／decode 错误；仍保留 cause，不要 catch 所有 `Exception`。补一条 root list 的 CLI 回归即可同时守住 auth 与 logout 的共享 helper。

### R2-04：Spec 声称无法推导 origin 会影响 logout，实际且正确的实现是不做推导也照常清理

- finding_id: `ghe-device-flow-review-gpt-r2-04`
- severity: `minor`
- primary_location: `.dev/docs/ghe-device-flow/spec.md:42-47`
- related_locations: `.dev/docs/ghe-device-flow/spec.md:82-87`；`src/app/cli.py:442-450`；`tests/unit/test_cli.py:289-309`
- 判据：Never bypass the Spec 双向成立。logout 只需选中 provider 与 token path，不应因无关的 OAuth web origin 无法推导而阻止用户删除凭据；如果实现有意比 auth 少做这一步，Spec 必须明写，不能让读者按 §3.3 把硬错误接到 logout。
- 证据：§3.3 说 `http://127.0.0.1:8080` 推不出 web 源，“这只影响 `auth` / `logout` 两条命令”；§3.7 只写同一套配置/provider/path 解析，没有排除 origin 推导。当前 `logout()` 实际不构造 `GhcClientConfig`，探针用该非法 origin 与自定义 token 文件执行，结果 exit 0、文件删除、无网络；这正是应有行为。现有 logout test 的 config 不带非法 origin，尚未把这个差异钉住。证据权重足够直接行动。
- 失败场景：后续实现者按 §3.3 对齐 logout，在删除前调用 `github_web_base_url`；一个 auth URL 已坏或刻意指向 local stand-in 的部署将无法用 CLI 删除 token，虽然删除文件完全不需要 OAuth host。当前代码没有这个 runtime bug，因此定 minor，缺陷位于规范与回归保护。
- 建议：把 §3.3 的代价收窄为 auth，并在 §3.7 明定 logout 必须忽略 origin 是否可推导；把本轮非法 origin 的成功清理探针固化成测试。

## 新入口系统状态复核

- `_selected_provider` 的显式 provider、未知 provider、缺省 configured default、缺省 bundled-only、显式空 default + 多 provider、dangling default 六类控制流均已直接执行。未知、歧义、dangling 三类都在网络前退出且说明 configured names；未发现换个地方发生的静默 provider fallback。
- 配置发现链的三层已直接执行：显式 config 胜过 `GHC_API_PROXY_CONFIG`，后者胜过默认位置；默认位置存在 tenant config 时裸 auth 真正传递 tenant origin 与自定义 token path。没有孤儿接线。
- logout 对非法／不可推导 `auth_base_url` 不做推导，仍删除正确的 provider token 文件；provider 歧义时不删文件且不打印成功。runtime 行为正确，Spec 缺口见 R2-04。
- auth 在 request／notify／poll 完成前不保存 token。用已有 `run_device_authentication` 配合“poll 抛错”的 fake 与真实 `FileTokenProvider` 探针，旧 token 保持逐字 `old`；配置选择、origin 推导与 provider 解析的失败也都发生在调用 `authenticate_device` 前。未发现失败后留下半枚新 token 的路径。`FileTokenProvider.save_token` 本身的非原子写入是既有实现，不是本轮新增。
- 环境 token warning 在 authentication 与文件保存成功后才执行；auth 失败时不会误报成功或 warning。环境变量确实遮蔽文件时会出声，闭合另一份评审 F8 的静默面。

## 关于“不需要用户裁决”的明确答案

**依据只成立一半，不足以支撑处置结论。** `default_model_provider: ghc` 与无删除 merge 足以证明“有效配置不会仅因新增 provider 而自动进入无默认的歧义分支”；它不能证明裸 auth/logout 的 host、token path、错误行为与输出逐字不变。R2-01 的四类直接反例以及 Spec 自己承认的行为变化推翻了后一个全称命题。

按调用方给出的分流，这就是范围变化，应交用户裁决。我的产品倾向是让用户追认当前三级发现链，而不是退回只认显式 `--config`，但在裁决前不能把它写成“无需取舍的等价重构”。

## Spec 修订记录的诚实性

R2 对**原方案错在哪里**的记录是诚实且足够具体的：§3.5 直说“原方案是错的”，点名裸 auth 根本到不了功能；revision row 还写明 `--provider` 被吞后仍登录 dotcom；`status.md` 的“走过的弯路”没有用“优化”或“对齐”美化失败，并解释为什么原有控制变异仍会绿。这一部分通过。

不诚实的是同一 revision row 尾部把 `bundled default + _deep_merge` 记成“不构成行为变更”的充分依据，并以“本人复核”封口。它对 provider 歧义成立，对完整 CLI 行为不成立；Spec 正文下一节还列出了实际行为变化。应按 R2-01 收窄，而不是抹掉 revision 对原错误的坦率记录。

## 搜索面与执行记录

- 读取处置记录、当前 Spec／status／deferred、另一份独立评审、限定 8 文件完整 diff 与最终文件；沿 `_selected_provider` 到 `load_proxy_config`／`resolve_config_path`／`resolve_default_name`，沿 token path 到 `FileTokenProvider`，并用 `git show HEAD:src/app/cli.py` 对照基线 auth/logout。
- 直接运行 resolver 探针覆盖上一轮 F-02 的空 label、多个尾斜杠、非法 port、坏 IPv6；另覆盖空 userinfo、空 query／fragment delimiter 与空 port delimiter。
- 直接运行 CLI 探针覆盖配置发现三层及 precedence、provider 六类分支、F-01 原命令、env token warning、local stand-in、logout 成功与歧义保护；用真实 CLI 进程确认 YAML root list 会打印 Rich traceback。
- 用临时目录与 fake DeviceFlow 验证 poll 失败不改旧 token。所有写入仅在 `TemporaryDirectory`，未访问真实 token、未发 upstream 请求。
- 没有重跑调用方已给出的 Ruff、Pyright、全量 pytest 与控制变异；其版本与当前 diff 由调用方声明，我只对本轮承重的新行为做独立探针。

## 我考虑过但否决的路线

1. **把 F-01 记成未闭合**：否决。原事实“`--provider` 被吞且调用 dotcom”已由直接反例变成 exit 2／0 次网络；R2-01 是替代设计引出的新范围裁决，不应篡改旧 finding 的状态。
2. **把 F-02 因 R2-02 整体记成未修**：否决。上一轮明确点名的空 label、重复 slash、parser `ValueError` 文案全部修复且探针通过；空 userinfo 是同一边界上的新输入，单列才保留两件事同时为真。
3. **要求 logout 也先验证 OAuth origin**：否决。删除本地文件不依赖远端 host；把无关配置错误变成清理凭据的门，只会制造无法 logout 的状态。当前代码对、Spec 需跟上。
4. **把 env token 在 logout 后仍可用另报一条**：否决。logout 能删除的是本程序存储的文件，无法修改父 shell 的环境变量；该行为在基线已存在，本次 Spec §3.7 也明确只闭合 auth 写入文件的反向边。是否新增 warning 可另议，不冒充本片回归。
5. **把 authentication poll 失败会留下半状态报成问题**：否决。执行顺序是 request → notify → poll → save，实测 poll 抛错时旧文件不变；没有证据支持该缺陷。磁盘写入过程中断的原子性是 `FileTokenProvider` 的既有独立问题，本轮不扩大范围。
6. **把 dangling default 或多 provider 继续报问题**：否决。当前入口在 network／delete 前分别给清楚诊断，且显式 `--provider` 合法时能有意覆盖 default；没有 silent `KeyError`。
7. **把多 label tenant 再次判非法**：否决。当前 Spec 已诚实声明证据边界与响亮失败代价，没有上游一手语法足以推翻它。
8. **认为 revision record 全部在美化**：否决。它对首版根因与失败形态的措辞直接、可复现；问题仅在 compatibility 依据越界，须精准纠正而不是抹掉整条历史。
9. **因没有真实 GHE E2E 报问题**：否决。用户已明确裁定无需验证，报告继续保留“接线已验证、租户成功未经证实”的边界即可。

## 整体判定

实现层的原三条修复有效，新 provider/config 入口未见静默 fallback，logout 与 auth 失败状态也按预期。当前不能进入下一阶段的唯一原因是 R2-01：公共裸命令语义发生了有意且有价值的变化，但尚未取得用户裁决，现有 disposition 的等价性论证不能代替裁决。若用户追认三级发现链，R2-01 主要变成文档收窄；其余 3 条 minor 可直接修正。

## 我最没把握的三个判断

1. **R2-01 定 blocker**：事实层我很有把握——现行为并非逐字等价；不确定的是首轮“不带 `--config` 必须不变”究竟是用户亲自裁决，还是 coordinator 当时可自行修订的派生判据。当前调用方明确说若依据不成立就交用户，故按缺裁决定 blocker；若主会话能提供一手用户授权覆盖这些变化，可降为文档 major／minor而无需再问。
2. **空 userinfo 是否应拒绝**：URL 最终被安全重建且目标正确，实际影响很低；但 Spec 用的是 presence 规则“不得带 userinfo”，`@` 的存在是可观察事实。若作者愿意将空 userinfo 明定为规范化输入，R2-02 可通过改 Spec 关闭。
3. **坏 YAML root 的定级**：它输出完整 traceback但不静默、不触网、不删 token，故我定 minor；项目若把 CLI 对普通输入的 traceback 视为公共错误契约破坏，可上调 major，事实不变。

## 执行本契约时遇到的摩擦

限定 diff 超过工具直接展示阈值，被保存为 persisted output；我没有依赖截断 preview，而是读取当前最终文件与相关调用链。除此之外无。

## 交付声明

- delivery_complete: true
- completed_at: `2026-08-28T13:58:05+00:00`
- finding_total: 4
- blocker_count: 1
- major_count: 0
- minor_count: 3
- nit_count: 0
