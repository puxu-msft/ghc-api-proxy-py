# GHE data residency Device Flow 独立评审

- report_id: `ghe-device-flow-review-gpt`
- attempt_id: `260828-review-gpt-01`
- status: `in-review`
- reviewed_at_rev: 主仓 `HEAD 74b9dde5585e009064f21a7721a8fce5ac8dd742`，限定 8 文件的未提交 diff SHA-256 为 `c8854bff8626719e30d5a9a813ea8ecacedfbab4842e6daf98c455c8320cdf28`；`.dev` 仓 `HEAD f78b1680a44126ce536371f2127ffcae167aa911`，Spec SHA-256 为 `40c42d1a4197ca25dda21eb2a4c5e5d28782a66c0a9640f57bfb3ea0e80d9a91`

## 评审范围

本轮评审 `.dev/docs/ghe-device-flow/spec.md`，以及调用方限定的 8 个未提交文件：`src/app/cli.py`、`src/app/model_provider/ghc_client/__init__.py`、`src/app/model_provider/ghc_client/auth/service.py`、`src/app/model_provider/ghc_client/config.py`、`src/app/model_provider/ghc_client/device_flow.py`、`tests/component/model_provider/ghc_client/test_config.py`、`tests/component/model_provider/ghc_client/test_device_flow.py`、`tests/unit/test_cli.py`。为核实接线，仅读取了相邻既有实现 `src/app/config/loading.py`、`src/app/config/schema.py`、`src/app/config/bundled-config.yaml`、`src/app/config/paths.py`、`src/app/model_provider/ghc_client/auth/providers.py` 与 `src/app/server/composition.py`；它们不是被评改动。

明确不在范围内：工作树里其他人的任何改动或未跟踪文件、生产部署、真实 GHE 租户调用、端到端实测、提交与修复。未修改任何生产代码或测试。

## 总体 verdict

`needs-fix`。主接线是通的：`auth/login --config ...` 选择 provider 后，从它的 `auth_base_url` 推出 tenant web origin，把 origin 传到 `DeviceFlowClient` 的两次请求，并把 token 写到该 provider 的 `github_token_file`；不带新增选项的旧调用仍走 dotcom 和默认 token 文件。不能按当前形态进入提交候选，因为新增的 `--provider` 存在一条会把用户静默送回 dotcom 的可达分支。

## Blocker 数

0。

## 判据来源与权重

1. 当前任务里用户的逐字裁决「做，无需验证」是本轮范围与验证强度的一手权威；若该前提为假，本轮就必须补真实 GHE 验证，因此它直接支撑“不以无租户实测为缺陷”的结论。
2. [sxwxs/ghc-api PR #34](https://github.com/sxwxs/ghc-api/pull/34) 及其 merge commit `02e73d2dc332430d08cf44d7cf7368388787040b` 是用户点名的功能参照。其实现把 `https://api.<tenant>.ghe.com` 映射到 `https://<tenant>.ghe.com`，两条 Device Flow 请求共用该 web origin，无法安全推导时不回落；权重足以支撑本切片的映射方向，但不是本项目 CLI 形态或 client ID 的权威。
3. GitHub Docs revision `1beae09958f6eac6a4d82e5ee902d67f28dddda6` 的 [REST API 入门](https://github.com/github/docs/blob/1beae09958f6eac6a4d82e5ee902d67f28dddda6/content/rest/using-the-rest-api/getting-started-with-the-rest-api.md) 给出 `https://api.octocorp.ghe.com/` 与登录 hostname `octocorp.ghe.com`；[GHE.com Copilot 认证](https://github.com/github/docs/blob/1beae09958f6eac6a4d82e5ee902d67f28dddda6/content/copilot/how-tos/configure-personal-settings/authenticate-to-ghecom.md) 要求选择 `github-enterprise` 并提供 tenant URL。权重足以确认 host 角色与单租户示例，不足以证明任意多级 tenant label 或当前 `GITHUB_CLIENT_ID`。
4. 项目 `CLAUDE.md` 与 `.claude/rules/00-development-workflow.md` 是工程判据，尤其采用“Spec 先于行为”“不能让接线守卫孤立”“测试覆盖当前切片真实失效面”“不为本任务另建验证基建”。

## 发现

### F-01：`--provider` 在缺少 `--config` 时被静默忽略，并实际登录 dotcom

- finding_id: `ghe-device-flow-review-gpt-01`
- severity: `major`
- primary_location: `src/app/cli.py:351-368`
- related_locations: `src/app/cli.py:394-396`；`.dev/docs/ghe-device-flow/spec.md:49-55`；`tests/unit/test_cli.py:110-200`
- 判据：CLI 声明 `--provider` “Requires --config”，而本切片的核心正确性要求是不能接受一个 tenant 选择后仍悄悄把 Device Flow 发到 `github.com`。Spec §3.5 还称其语义与 `debug models` “逐条一致”；该命令不会在收到 `--provider` 后跳过 provider 解析。
- 证据：`_authenticate()` 仅在 `config is not None` 时调用 `_resolve_auth_provider()`，所以 `provider` 在 `config is None` 时从未读取。执行探针以 `AsyncMock` 替换网络入口后调用 `auth --provider tenant`，观察到 `exit_code == 0`、无诊断，且调用为 `authenticate_device(notify, None, web_base_url='https://github.com')`。这不是仅凭阅读推断，证据权重足够直接行动。
- 失败场景：用户运行 `ghc-api-proxy auth --provider tenant`，可能意图选择默认位置或环境配置中的 `tenant` provider；命令接受该参数，却向 `https://github.com/login/device/code` 发请求并把 token 写到默认文件。即使 provider 根本不存在，结果也相同。用户看到的是可完成的 dotcom 登录，而不是“`--provider` requires `--config`”的拒绝。
- 影响与定级：这是本功能专门要消除的“选择了 tenant，但登录打到 dotcom”失效形态，并且发生在用户可达 CLI 入口、成功退出。虽然补上 `--config` 可绕行，公共参数契约与核心 host 选择仍被破坏，因此定为 major，而非只把它当帮助文字问题。
- 建议：先在 Spec §3.5 明定这一组合的行为，再让实现执行它。按当前 option help，最窄且不改变旧调用的规则是：仅当 `provider is not None and config is None` 时以 `typer.BadParameter` 拒绝；若项目希望它读取默认／环境配置，则应改写 Spec 与 help，并像 `debug models` 一样实际调用 `_read_config(None)`。补一条从 CLI 入口断言“未调用 authenticate_device”的回归测试。

### F-02：URL 解析边界不是 Spec 所写的完整判定，既接受缺失 tenant 的 host，也让部分 `ValueError` 绕过规定诊断

- finding_id: `ghe-device-flow-review-gpt-02`
- severity: `minor`
- primary_location: `src/app/model_provider/ghc_client/config.py:64-90`
- related_locations: `.dev/docs/ghe-device-flow/spec.md:23-39`；`tests/component/model_provider/ghc_client/test_config.py:51-95`
- 判据：Spec §3.2 只接受 dotcom 或 `api.<tenant>.ghe.com` 且 `<tenant>` 非空，path 只能为空或 `/`；§3.3 要求每个推导错误同时包含收到的值与期望形状。函数是这个边界的单一实现，不应把不满足 grammar 的值送到网络层才失败。
- 证据：直接执行当前函数得到：`https://api..ghe.com` 返回 `https://.ghe.com`，`https://api.foo.ghe.com//` 返回 `https://foo.ghe.com`，而 `https://api.octocorp.ghe.com:not-a-port` 抛出 Python 自带的 `ValueError: Port could not be cast to integer value as 'not-a-port'`，`https://[bad` 抛出 `ValueError: Invalid IPv6 URL`。前两项分别违反“tenant 非空”和 path 只允许空或单个 `/`；后两项没有同时报告原值与期望形状。证据权重足够直接行动。
- 失败场景：配置 `auth_base_url: https://api..ghe.com` 时，CLI 不在配置边界拒绝，而会尝试 `https://.ghe.com/login/device/code`，最终以 DNS／transport 层错误结束；配置一个非数字端口时虽然会响亮失败，用户只得到 Python 端口解析文案，不知道本命令接受的完整 URL 形状。两者都不会回落 dotcom，因此没有上调为 major。
- 额外一致性问题：正向测试把 `https://api.eu-west.octocorp.ghe.com` 当作合法输入，但 Spec 没有定义 `<tenant>` 可含多个 label，GitHub Docs 的权威例子只支持单个 enterprise subdomain `octocorp`。这不足以断言多 label 必然非法，却足以说明测试替 Spec 扩张了行为；应由 Spec 明定后再保留或删除该样例。
- 建议：在 Spec 先明确 tenant 的 DNS label grammar 与是否有意把多个尾斜杠归一化；实现中在一个受控 `try` 内完成 `urlsplit` 与 `.port` 读取，把 parser 自身的 `ValueError` 统一改写成 §3.3 规定的文案，并显式拒绝空 label。测试至少加入 `api..ghe.com`、非法 port 和重复斜杠三个有区分力的输入。

### F-03：`auth --config` 新增的自定义 token 写入位置没有对应的 `logout` 清理入口

- finding_id: `ghe-device-flow-review-gpt-03`
- severity: `minor`
- primary_location: `src/app/cli.py:418-421`
- related_locations: `src/app/cli.py:351-368`；`src/app/model_provider/ghc_client/auth/service.py:49-50`；`src/app/server/composition.py:309-316,333`；`.dev/docs/ghe-device-flow/spec.md:57-61`
- 判据：Spec §3.6 正确要求登录把 token 写到 provider 真正读取的 `github_token_file`。一旦 `auth` 能创建该认证状态，现有公开命令 `logout` 的契约“Remove locally stored authentication state”就不能在未清理它时仍报告成功；这是同一 token 路径接线的反向边。
- 证据：`logout()` 无参数调用 `clear_stored_token()`，后者构造默认路径的 `FileTokenProvider`；服务却从 `FileTokenProvider(github_token_path(config, provider_name))` 读取自定义文件。隔离临时目录探针中同时创建默认 token 与 `tenant-token`，执行 `logout` 后观察到退出码 0、输出 `Stored GitHub token removed`、默认文件消失而 `tenant-token` 原文仍在。证据权重足够直接行动。
- 失败场景：用户通过 `auth --config tenant.yaml --provider tenant` 成功把 token 写入 `tenant.yaml` 指定的文件，随后运行 `ghc-api-proxy logout`；命令报告已移除认证状态，但服务重启后仍从自定义文件读取原 token，用户实际仍处于登录状态。
- 影响与定级：核心 tenant 登录本身可用，且用户可手工删除自定义文件，因此这是有明确绕行的局部生命周期缺口，定为 minor。它仍是静默错误，不能仅因 `logout` 的代码行未在 diff 中变化而忽略。
- 建议：把 logout 的配置／provider 选择规则写进本 Spec，并复用同一 `_resolve_auth_provider()` 与 `github_token_path()`；若本切片明确不承担 logout，则至少改成不会声称清除了自定义认证状态，并把后续工作记录在本 topic 的活文档中，而不是静默省略。

## Spec 与实现逐条对照

- §3.1：通过。第三个角色被表达为派生属性而非新增配置项，调用层没有另造可漂移字段。
- §3.2：主映射通过，输入边界部分不通过，见 F-02。大小写 host 经 `urlsplit().hostname` 归一为小写；默认 port 443 被移除；单个尾斜杠可用。IDN 没有权威项目契约，本轮不把“接受 Unicode label”单独报成缺陷。
- §3.3：不回落的设计裁决成立，且 CLI 的已覆盖推导失败会在网络调用前退出；错误文案的全覆盖不成立，见 F-02。这个裁决在本项目语境下站得住：`auth_base_url` 的本地 stand-in 是合法服务配置，但本地 stand-in 不提供 Device Flow，回落 dotcom 只会制造错误来源的 token，不是兼容路径。
- §3.4：实现与 Spec 一致地不改 client ID；现有 `raise_for_status()` 能让 endpoint 拒绝响亮失败。是否真正被 GHE.com 接受仍未验证，但用户已经明确免除真实租户验证，当前没有足够反证把它提升为缺陷。
- §3.5：带 `--config` 的 provider 存在／不存在／多 provider 分支均接到真实入口；不带任何新增参数的旧调用仍保持 dotcom 与默认文件。`--provider` 单独出现时不符合可解码的 CLI 合同，见 F-01。
- §3.6：正向写入接线通过，既有 `github_token_path()` 与服务读取端共源；认证生命周期的反向清理缺口见 F-03。
- §4：不复制 `resolve_ghe_endpoints()` 有充分的本项目架构理由，因为推理 endpoint 已有显式配置与订阅探测两个权威来源；不复制 PR 的 YAML 逐行改写实现也合理。PR 的行内注释缺陷只足以否决那种具体改写法，单独并不足以永久否决任何 `--ghe-endpoint` 帮助命令；本轮不把它报成缺陷，是因为用户要求的是对应能力而非逐功能克隆，当前 `--config` 路径已让能力可达。

## 测试评价

已有测试不是只钉名字：Device Flow component test 同时观测两次实际请求 URL，CLI test 同时观测派生 origin 与 token 文件，默认调用还由既有 exact request body 测试守住。调用方提供的两次控制变异分别击中 CLI host 传递与 `DeviceFlowClient` 的 origin 使用，足以证明这两条绿灯不是孤立原语的自证；本轮直接采信该一手执行记录，没有重复做破坏性变异。

缺口与发现一一对应：没有 `--provider` 单独使用的负例；resolver 负例只覆盖手选形状，没有覆盖 parser 自己先抛异常、空 tenant label 与重复斜杠；没有从自定义 token 文件登录后执行 logout 的生命周期测试。除此之外，本轮未发现为了覆盖率预建无关状态空间的问题。

## 搜索面与执行记录

- 在读取被评对象前加载 `my-skills:as-reviewer`，先从用户点名 PR、GitHub Docs、项目规则建立独立判据；随后读取完整 Spec、限定 8 文件 diff 与最终文件内容。
- 通过 GitHub API 读取 PR #34 的 metadata、merge commit 与 `api_helpers.py`、`main.py`、`token_manager.py`、两份测试的完整 patch；GitHub 页面懒加载不完整时没有据此猜测。
- 追踪入口到 `_authenticate` → `authenticate_device` → `DeviceFlowClient`，以及 token 路径到 `github_token_path` → `FileTokenProvider`；同时核对 `load_proxy_config` 的 bundled／file／environment merge 与 provider schema。
- 执行了三个隔离探针：CLI `auth --provider tenant` 的 mock 入口；resolver 的大小写、非法 port、坏 IPv6、IDN、空 label、非法 DNS label、percent encoding、尾点与重复斜杠；临时目录内 `logout` 对默认／自定义 token 文件的实际影响。
- 未执行真实网络认证、生产服务、GHE tenant E2E、全套测试或重复控制变异。前者受用户“无需验证”裁决约束；后两者已有调用方给出的新鲜一手结果。

## 我考虑过但否决的路线

1. **把“推导失败必须硬报错”报成兼容性缺陷**：否决。本地 `auth_base_url` stand-in 的确不能登录，但 Device Flow 并不存在于该 stand-in；回落 dotcom 会生成来源错误的 token。前提是“本地 stand-in 不提供 Device Flow”，它支撑“不保留 fallback”的结论；若前提为假，应扩展 Spec 让 web origin 可明确配置，而仍不应静默回落。当前代码注释、Spec 与任务边界一致，权重足够行动。
2. **要求照搬 PR #34 的 `resolve_ghe_endpoints()` 或 `--ghe-endpoint`**：否决。用户说“参考”而非“逐项复制”，本项目已有 endpoint 配置与订阅探测的权威路径。PR 的注释丢失问题只否决其具体文本改写器，不是拒绝所有未来 convenience command 的充分理由；这属于可选产品决策，不冒充当前缺陷。
3. **因没有真实 GHE E2E 而报 blocker／major**：否决。用户逐字裁定“无需验证”，且本地没有租户。mock 只能证明接线和 URL 构造，不能冒充 upstream 验证；报告保留这一证据边界即可。
4. **断言当前 `GITHUB_CLIENT_ID` 一定不能用于 GHE.com**：否决。PR #34 复用的是另一个 client ID `01ab8ac9400c4e429b23`，所以它不能证明本项目的 `Iv1.b507a08c87ecfe98`；GitHub Docs 也未给出 client ID 契约。另一方面，公开实现 OpenClaw 已将同一 `Iv1...` 固定用于 `acme.ghe.com` 形态，这只是旁证，不是权威验证。结论权重仅为“保持未验证状态，尚不足以报缺陷”；若租户返回 4xx，现有 `raise_for_status()` 会响亮失败，且那时应按真实响应重新裁决是否需要可配置 ID。
5. **把大小写 host、默认 `:443`、单个尾斜杠或 dotcom legacy 报错**：否决。直接探针与测试都确认它们规范化到预期 origin，且默认请求 URL／body 保持原值。
6. **把所有 IDN 或多 label 一概判非法**：否决。GitHub Docs 没有公开完整 subdomain 字符规则，现有证据只足以指出 Spec 未定义而测试先行扩张，不能把未掌握的服务端约束伪装成事实。F-02 依赖的是更窄且确定的 `api..ghe.com` 空 label 与 parser error 文案，不依赖这个未决判断。

## 整体判定

当前候选的主功能不是孤立守卫，关键 happy path 已经从用户 CLI 入口贯穿到两条 OAuth 请求与 provider token 文件；无 config 的历史调用也没有被 tenant 配置逻辑接管。修复 F-01 后可消除唯一 major；F-02 与 F-03 是应在同一切片收口的局部契约缺口。由于存在 1 条 major，verdict 为 `needs-fix`，不是 `blocked`。

## 我最没把握的三个判断

1. **F-01 定为 major 而非 minor**：最不确定处在于用户有明确绕行方式，即补 `--config`。我仍定 major，因为命令成功接受一个公开参数后走到本功能专门要避免的 dotcom host，影响的是核心正确性而不是辅助体验；调用方若按“有明确绕行即 minor”更严格套级，可重定级但不应否决事实。
2. **多 label tenant 的合法性**：GitHub Docs 只给单 label 示例，网络文档又明确存在 tenant 下多级服务子域，无法从公开资料证明 `eu-west.octocorp` 是合法 enterprise subdomain。故只把它记为 Spec／测试权威顺序问题，没有断言服务端必拒绝。
3. **固定 client ID 可否跨 GHE.com**：没有租户实测或 GitHub 一手 client ID 契约。PR 的不同 ID 与第三方同 ID 实现方向相反，都不足以定案；本轮按用户免验证裁决保留未知，不据此阻断。

## 执行本契约时遇到的摩擦

GitHub PR 的网页 files view 没有完整加载全部 diff，WebSearch 也临时不可用；我改用 `gh api repos/sxwxs/ghc-api/pulls/34/files` 与固定 GitHub Docs revision 的 raw/blob 内容取得可审计源码，因此没有留下内容缺口。检查本机 `copilot` CLI 的辅助 shell 调用在确认“未安装”后因一段无关的版本输出脚本退出 127；这个失败不承重，也未用于任何结论。

## 交付声明

- delivery_complete: true
- completed_at: `2026-08-28T13:35:02+00:00`
- finding_total: 3
- blocker_count: 0
- major_count: 1
- minor_count: 2
- nit_count: 0
