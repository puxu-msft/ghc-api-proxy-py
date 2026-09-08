# GHE Device Flow 切片独立评审（claude）

- 日期：2026-08-28
- 评审者：独立评审 subagent（Opus 5）
- 被评基线：工作树未提交改动，相对 `74b9dde`

## 结论

**verdict: needs-fix**

- **blocker: 0**
- **major: 4**（F1、F2、F3、F4）
- **minor: 6**（F5–F10）
- 主观建议 3 条、nit 1 条，单列，不占严重级别档位。

一句话：**推导本身是对的，测试也扎实；问题全部集中在「这个能力挂在哪个入口上」。** `--config` 是一道自愿门，而它要修的那个失效（在租户机器上登录却拿到 dotcom token，且看起来成功）恰好发生在不敲这道门的那条命令上。

### 为什么 0 个 blocker

本次改动是严格追加式的：不给新选项时行为逐字不变（已实测），没有任何在 HEAD 上能算对的输入现在算错了。F1/F2/F3 的共同形状是「修好了，但只在你主动说出口时才生效」，不是「把对的弄坏了」。

**F1 的定级我保留一处分歧并交回裁决**：如果调用方按 `src/app/cli.py:308-309` 自己写下的那条尺度——「an option that is accepted and then ignored is worse than one that is refused, because nothing distinguishes it from having worked」——来量，F1 就是这条尺度点名的那个形态，且它会**静默覆盖掉一个正在工作的 token 文件**。按影响我记 major；按仓库自己的措辞它够得上 blocker。这个我不替调用方定。

---

## 评审范围

**看了：**

- Spec：`.dev/docs/ghe-device-flow/spec.md`（全文）
- 生产代码 diff：`src/app/cli.py`、`src/app/model_provider/ghc_client/__init__.py`、`.../ghc_client/auth/service.py`、`.../ghc_client/config.py`、`.../ghc_client/device_flow.py`
- 测试 diff：`tests/component/model_provider/ghc_client/test_config.py`、`.../test_device_flow.py`、`tests/unit/test_cli.py`
- 改动落地后的最终状态（不只是 diff）：`src/app/cli.py` 的 `_read_config` / `debug_models` 全段

**判据来源（在读被评对象之前取的）：**

- `CLAUDE.md`、`.claude/rules/00-development-workflow.md`、`~/.claude/rules/00-user/`
- `src/app/server/composition.py:339-411`（`resolve_provider_base_urls`，2026-08-22「两条路没有第三条」）、`:309-336`（`github_token_path` / `build_github_token_source`）
- `src/app/model_provider/registry.py:67-77`（`resolve_default_name`）
- `src/app/config/schema.py:34-55`（`NOT_HOT_RELOADABLE`）、`:93-116`（`ModelProviderConfig`）
- `src/app/config/loading.py`（五层加载、`_deep_merge`、`resolve_config_path`）、`src/app/config/bundled-config.yaml`
- `src/app/model_provider/ghc_client/auth/providers.py`（token 三级链）
- `docs/.human-controlled/cli.md`（**空文件**，故不存在与用户亲笔 CLI 契约的冲突）、`docs/.human-controlled/config.example.yaml`
- `.dev/docs/cli-commands/debug-models/decision.md`（`--provider` 的既有语义）
- 上游 PR sxwxs/ghc-api#34 页面、docs.github.com 两页（见 S2）

**明确没看（不在范围）：**

- 同伴的未提交改动：`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/message-translation.md`、`Dockerfile`、`docker-compose.yml`、`.dockerignore`、`exp/260820-h2-stream-cap/`、`.claude/worktrees/`。**未修改、未暂存、未提交任何文件**，只新建了本报告及其所在目录。
- 端到端实测（用户已裁定无需，本机无 GHE 租户）。
- `ruff` / `pyright` / 全量 `pytest`：采信调用方给出的既成事实，未重跑。

**跑过的命令：** 4 次只读探针（`uv run python` + `typer.testing.CliRunner`，把 `app.cli.authenticate_device` 替换为记录用的假函数，全部在进程内，不发网络请求、不写 token 文件）。**没有做变异**：主工作树里有同伴的未提交改动，在共享树上改生产代码去打红不是我能自行授权的操作。

---

## 发现

### F1 · `--provider` 不给 `--config` 时被静默吞掉，连不存在的名字也照收 — **major**

**判据。** `src/app/cli.py:308-309` 是本仓自己写下的尺度：

> an option that is accepted and then ignored is worse than one that is refused, because nothing distinguishes it from having worked.

另外新选项自己的 help 文本就写着 `"Which configured provider to log in for. Requires --config."`——**"Requires" 是一句没有任何代码执行的断言**。

**位置。**

- `primary_location`: `src/app/cli.py:351`（`if config is not None:` 这道门把整个 provider 解析包在里面）
- `related_locations`: `src/app/cli.py:390-392`（`_AUTH_PROVIDER_OPTION` 的 help 文本）；`.dev/docs/ghe-device-flow/spec.md:51-56`（§3.5 三条分支里没有这一条）

**失败场景（已实测）。**

```
ghc-api-proxy auth --provider does-not-exist
```

→ `exit 0`，无任何输出，设备码发往 `https://github.com`，token 写入默认路径 `~/.local/share/ghc-api-proxy/github_token`。

探针输出逐字：`exit: 0` / `stdout:` （空） / `calls: [(None, 'https://github.com')]`。

真实运营者的形态是：租户部署上想给 provider `tenant` 登录，敲了 `auth --provider tenant` 而漏了 `--config`。结果是**一次看起来成功的 dotcom 登录，并且用 dotcom 的 token 覆盖掉了原本能用的那个文件**。这正是 Spec §3.3 与 `resolve_github_web_base_url` 的 docstring 花了整段去消灭的失效形态——只不过它被消灭在了推导函数里，而这条路径根本走不到那个函数。

**证据权重：够拿来行动。** 直接执行观测，非推断。

---

### F2 · `auth` 绕过了本项目唯一的配置发现链，只认 `--config` — **major**

**判据。** `src/app/config/loading.py:86-107` 的 `resolve_config_path` 是本仓关于「配置文件在哪」的权威，它有三级：显式 `--config` → 环境变量 `GHC_API_PROXY_CONFIG` → `spec_config_file_path()`。该函数的 docstring 明确记着 2026-08-22 的裁决，且注明「This is the loader **every** entry point uses」（`loading.py:6`）。`auth` 现在是个例外：`_authenticate` 只在 `config is not None` 时才去读配置，后两级完全够不着。

**位置。**

- `primary_location`: `src/app/cli.py:349-363`
- `related_locations`: `.dev/docs/ghe-device-flow/spec.md:53`（§3.5 第一条，正是它给这道门做的辩护）；`src/app/config/loading.py:86-107`

**失败场景（已实测）。** systemd unit 里设了 `GHC_API_PROXY_CONFIG=/etc/ghc-api-proxy/tenant.yaml`（租户配置），运营者在同一个 shell 里敲 `ghc-api-proxy auth`：

探针输出逐字：`exit: 0 | out: | calls: [('None', 'https://github.com')]`。

即：**服务端读租户配置、登录端读 dotcom**，两边对不上，且没有一个字提示。同理，配置文件放在默认位置 `~/.local/share/ghc-api-proxy/config.yaml`（本机就存在这个文件）的部署也一样。

**§3.5 用来支撑这道门的理由，我实测后认为只成立一半。** Spec 说「不给 `--config`：行为与本次改动前逐字相同……既有部署不受影响」。但我实测了「假如 `auth` 走完整发现链、且现场没有配置文件」的结果：

```
bundled-only providers: ['ghc'] default: 'ghc'
ghc auth_base_url: ''  github_token_file: ''
derived web: https://github.com
github_token_path: None
```

——**逐字相同**。也就是说，兼容性这个理由并不要求这道门存在；无配置文件的部署走不走发现链结果一样。

**但我不把话说满。** 这道门确实挡住了一种真实的行为变化：**默认位置已经有配置文件、且里面配了多于一个 provider** 的既有部署，一旦 `auth` 去读它，就会从「能跑」变成「报错要你指定 `--provider`」（见 F3）。所以这不是「白送」，是一次真实取舍。我的倾向是本仓的一贯立场应当胜出——响亮拒绝优于静默走错——但**这是范围变更，按 `ask-if-scope-shrink` 应交调用方（乃至用户）裁决，不由评审代定**。

**证据权重：够拿来行动**（两个方向都是直接执行观测）。**倾向性结论（该不该拆掉这道门）权重较低，属主观建议**。

---

### F3 · `_resolve_auth_provider` 造出了「默认 provider 是谁」的第二个答案，且与既有权威不一致 — **major**

**判据。** `src/app/model_provider/registry.py:67-77` 的 `resolve_default_name` 是本仓对这个问题的既有答案，顺序是：`default_model_provider` 优先 → 只有一个时用它 → 否则报错。Spec §3.1 自己援引的「两条路没有第三条」讲的正是不要为同一事实制造第二个真相来源。

**位置。**

- `primary_location`: `src/app/cli.py:371-385`（`_resolve_auth_provider`，跳过了 `default_model_provider` 这一级）
- `related_locations`: `src/app/model_provider/registry.py:67-77`；`.dev/docs/ghe-device-flow/spec.md:55`（§3.5 第三条）；`src/app/config/loading.py:37-53`（`_deep_merge`）

**失败场景（已实测）。** 配置：

```yaml
model_providers:
  ghe:
    type: github_copilot
    auth_base_url: "https://api.acme.ghe.com"
    github_token_file: "/tmp/ghe-token.txt"
default_model_provider: ghe
```

- `auth --config <该文件>` → **exit 2**（BadParameter，要求指定 `--provider`）
- 同一份配置，`resolve_default_name(cfg)` → **`'ghe'`**

配置文件已经明明白白写着默认是谁，`auth` 却说「你没说清楚」。

**而且这不是边缘情形，是唯一情形。** `_deep_merge`（`loading.py:37-53`）只合并、不删除键，bundled 配置又无条件带一个 `ghc`（`bundled-config.yaml:52-56`），所以**任何**「加一个租户 provider」的配置都必然 ≥2 个 provider。结论：

- §3.5「恰好一个 provider 时用它」这条便利分支，**对本功能存在的每一种部署形态都不会触发**——它只在纯 dotcom 部署上触发，而那里 `--provider` 本来就无关紧要；
- 运营者只剩下一条路：每次登录都手敲 `--provider`，尽管配置里已经有答案。

唯一能落进「恰好一个」的形态是运营者把租户设置直接覆写到 `ghc` 这个键上——这也正是新测试 `test_auth_for_a_tenant_provider_derives_its_origin_and_token_file` 采用的形态。它是可行的，但它是**一个只在测试 docstring 里说过的运营前提**（见 F4）。

**修复方向（供裁决，我不动手）：** 让 `_resolve_auth_provider` 在 `--provider` 缺席时先走 `resolve_default_name(config)`，`ProviderNotConfigured("")` 再翻译成现在这条列出全部名字的 `BadParameter`——`debug_models`（`cli.py:488-498`）已经有这个翻译的先例，可以照抄。

**证据权重：够拿来行动。** 探针 A 与 D 是同一份配置的两次直接观测。

---

### F4 · 有 Spec 级事实寄存在测试 docstring 与 help 字符串里 — **major**

**判据。** `.claude/rules/00-development-workflow.md`「Never bypass the Spec」的 (b) 半，逐字：

> A Spec-level fact must not come to rest anywhere except the Spec: not a deferred ledger, not a review report, **not a code comment**, not a status document, not a message to the user. … **The destination never excuses it, and neither does the reason.**

**位置与两处实例。**

- `primary_location`: `tests/unit/test_cli.py`，`test_auth_for_a_tenant_provider_derives_its_origin_and_token_file` 的 docstring 末段——「the loader merges over the bundled default rather than replacing it, so adding a second key would leave `ghc` behind as well」。这不是测试实现细节，**这是决定运营者必须敲什么命令的事实**（见 F3），而 Spec 全文没有一个字提到 bundled `ghc` 不可移除。同一事实的第二处副本在 `test_auth_names_the_providers_when_several_are_configured` 里的行内注释「Two providers, because the config above adds one to the `ghc` the default already defines」。
- `related_locations`: `src/app/cli.py:390-392`——`--provider` 缺 `--config` 时的行为，唯一的书面记载是 help 里那句 `"Requires --config."`，**而它是错的**（F1）。Spec §3.5 的三条分支不覆盖这个输入。

**失败场景。** 一个只读 Spec 的接手者（这正是 Spec 存在的意义）会得到两个错误认知：以为「恰好一个 provider」是常见路径、以为 `--provider` 单独给出会被拒绝。两者都要在读到测试或亲手试过之后才会被纠正。

**处置提示：** 这两条都属于「Spec 尚不知道的事实」，按同一份规则「Correcting your own derived table to match a measurement is not that, and neither is recording a fact the Spec did not yet know」，**当场修订 §3.5 即可，不需要用户裁决**。F1 的行为本身要不要改，才是需要裁决的那半。

**证据权重：够拿来行动。**

---

### F5 · Spec §3.5「语义与 `debug models` 逐条一致」不成立 — **minor**

**判据。** `src/app/debug/models.py:218-243` 与 `.dev/docs/cli-commands/debug-models/decision.md:18`：`debug models` 的 `--provider NAME` 语义是「只报告这一个」，**缺省时报告全部**（`names = [only] if only is not None else sorted(chain.providers.names)`），它从不因为「有多个」而要求你指定。

**位置。** `.dev/docs/ghe-device-flow/spec.md:51`（「语义与 `debug models`（`src/app/cli.py:404-426`）逐条一致」）。

**失败场景。** 读者按这句话去 `debug models` 找第三条分支的对应物，找不到——真正共享的只有 BadParameter 那一条（连消息措辞都对上了，`cli.py:482-486` vs `cli.py:373-377`）。一句可核查的断言被核查出是假的，之后这份 Spec 的其它断言也就得逐条重核。另附：引用的行号 `404-426` 是 HEAD 版本的，改动落地后 `debug_models` 已移到 `462-509`。

**证据权重：够拿来行动。**

---

### F6 · §3.5「零个时走默认」描述的是一个到不了的状态，对应分支是死代码 — **minor**

**判据。** `_deep_merge`（`loading.py:37-53`）无删除语义；`model_providers: {}` 会走进「两边都是 Mapping」的递归分支、原样返回 base；`model_providers: null` 则被 pydantic 拒绝。CLI 的每条路径都经过 `load_proxy_config`，必然带上 bundled 的 `ghc`。

**位置。** `.dev/docs/ghe-device-flow/spec.md:55`；`src/app/cli.py:385`（`return configured[0] if configured else ""`）与 `src/app/cli.py:354`（`if provider_name:`）。

**失败场景。** 不产生错误答案；代价是一条 Spec 条款描述了不存在的状态，两处防御分支永远不执行也无法被测试覆盖。跟 F3 是同一个根因（bundled `ghc` 拿不掉）的另一面。

**证据权重：够拿来行动**（`_deep_merge` 的语义是读代码得出的，但三种写法的结果都可由该函数直接判定）。

---

### F7 · `_read_config` 的 docstring 声称「只服务 `debug models`」，而作用域已悄悄扩大 — **minor**

**位置。** `src/app/cli.py:453`：

> Scoped to `debug models` on purpose: `start` still raises through, and changing what an already-shipped path does on a bad config was not part of implementing this command.

`_authenticate`（`cli.py:352`）现在也调它。

**失败场景。** 那句话记录的是一个**决定**（不改已发布路径在坏配置上的行为），而 `auth` 正是一条已发布路径，它在坏配置上的行为这次确实变了（从「没有这个入口」变成「打印 pydantic 消息并 exit 1」——这个新行为本身是对的）。docstring 现在描述的是一个不再成立的边界，下一个读它的人会据此以为 `auth` 不在里面。

**证据权重：够拿来行动。**

---

### F8 · §3.6「写到该 provider 真正会读的那个文件」措辞过强，env 那一级会静默挡在前面 — **minor**

**判据。** `src/app/server/composition.py:328-336`：provider 实际读 token 的链是 `CLITokenProvider` → `EnvTokenProvider` → `FileTokenProvider`，按 `priority` 排序取第一个可用的（`providers.py:181-193`）。文件是**第三级**。

**位置。** `.dev/docs/ghe-device-flow/spec.md:57-61`（§3.6 标题与理由段）；`related_locations`: `src/app/cli.py:363`、`src/app/model_provider/ghc_client/auth/providers.py:56-79`。

**失败场景。** 运营者 export 了 `GHC_API_PROXY_GITHUB_TOKEN`（dotcom 的 PAT），然后 `auth --config tenant.yaml --provider tenant` 登录成功、租户 token 正确落盘到 `github_token_file`——**而服务永远读不到它**，因为 env 那一级先答了。症状与 §3.3 要消灭的那个一模一样：一次报告成功、结果不生效的登录。Spec 与代码都没有一个字提到这一级。

**注意这不是「加个通用防护」。** 本仓已有 `noninteractive_token_available`（`providers.py:153-165`）恰好能答「有没有更高优先级的源会挡住它」，所以如果要提示，是复用既有件，不是新建。要不要提示由调用方定；**但 §3.6 那句「真正会读的那个文件」需要补上限定，这一半不用裁决**。

**证据权重：够拿来行动**（链的顺序是读代码得出的确定事实，未构造运行样本）。

---

### F9 · GHES（自托管 GitHub Enterprise Server）被 §3.2 拒掉，且没有登记 — **minor**

**判据。** `~/.claude/rules/00-user/40-dev-and-docs.md` 的 `no-silently-cut-but-defer` `[hard]`：中途发现用户从未明确取舍、又与当前任务相关的功能，应记下、提醒或延后，而不是**静默**砍掉。

**位置。** `.dev/docs/ghe-device-flow/spec.md:27-33`（§3.2 表格与前置校验）与 `:63-67`（§4「本次明确不做的」，无此条）；`related_locations`: `src/app/model_provider/ghc_client/config.py`（`AccountType` 含 `"self-hosted"`，`resolve_api_base_url` 的注释点名 `msft.ghe.com`）。

**失败场景。** GHES 部署的 `auth_base_url` 形如 `https://ghe.example.com/api/v3`，其 web/OAuth 源是 `https://ghe.example.com`——一次去 path 就能推出。当前实现在 `parts.path` 非空处直接 `ValueError`。这不是错误答案（是响亮拒绝），所以只记 minor；但「这个形态本项目决定不支持」是一个**从未被登记**的取舍，而 §4 正是为登记这种取舍而存在的那一节。补一条到 §4 或 `deferred.md` 即可。

**证据权重：够拿来行动**（判据来自代码；GHES 的 `/api/v3` 形态是通用知识，本轮未查一手文档）。

---

### F10 · 用户亲笔示例配置推荐的 token 文件名与默认路径对不上，§3.6 只在 `--config` 后面修好了它 — **minor**

**位置。** `docs/.human-controlled/config.example.yaml:163`（HEAD 与工作树一致，**不是同伴的未提交改动**）：`github_token_file: "$XDG_DATA_HOME/ghc-api-proxy/github_token.txt"`；而 `FileTokenProvider` 默认路径是 `~/.local/share/ghc-api-proxy/github_token`（无 `.txt`，`providers.py:88`，实测确认）。

**失败场景。** 运营者照示例文件写了这一行，然后敲不带 `--config` 的 `ghc-api-proxy auth`：token 写进 `github_token`，服务读 `github_token.txt`，登录报告成功而服务照旧没有凭据。§3.6 的目标——「一个把 token 写到该 provider 不去读的位置的登录……修一半等于没修」——在**不加 `--config`** 的调用上依然没修，而那是既有文档里唯一有的调用形态。

**范围限定（实测）：** 本机 `~/.local/share/ghc-api-proxy/config.yaml` 未设 `github_token_file`，走默认路径，因此**这台机器上不触发**。只影响采纳了示例值的部署。这是**既有缺陷**，不是本次引入；列在这里是因为它把 F2 从假设变成了一条具体的现场路径。该文件由用户亲笔控制，按 Spec §5 的做法只报告不代改，正确。

**证据权重：够拿来行动**（两侧路径均为实测输出）。

---

## 主观建议（不占严重级别档位）

- **S1 · `GhcClientConfig(auth_base_url_override=<provider>.auth_base_url)` 现在有两个构造点**：`src/app/server/composition.py:357-359` 与 `src/app/cli.py:356`。两处目的相同（从 provider 配置取一个派生 URL），一个取 `auth_base_url`，一个取 `github_web_base_url`。预期影响：将来 `GhcClientConfig` 多一个需要从 provider 配置带过去的字段时，两处会分头改、并悄悄分叉。一个 `provider_ghc_config(provider_config) -> GhcClientConfig` 之类的小函数就够。
- **S2 · §4 的证据权重可以升级一半。** 我核了一手来源：docs.github.com（enterprise-cloud@latest, REST getting-started）明写 data residency 租户的 REST API base 是 `https://api.SUBDOMAIN.ghe.com`，并给出实例 `https://api.octocorp.ghe.com/`——这是 §3.2 那张映射表方向性的**一手佐证**，比 PR #34 的实现强。**但 Device Flow 端点随租户搬家这一半仍然只是旁证**：OAuth apps 文档只列 `https://github.com/login/device/code` 与 `https://github.com/login/oauth/access_token`，并附一句通用说明「You might access GitHub at a different domain, such as `octocorp.ghe.com`」，没有给出 ghe.com 形式的端点。预期影响：§4 现在把两半打包成同一个「旁证」权重，读者无法知道其中一半其实有一手来源；分开写会让下一个人少查一遍。**§4 那句「任何下游文档不得把本条改写成已验证」的自我约束写得好，保留。**
- **S3 · 主题目录只有 `spec.md`。** 按 `.claude/rules/00-development-workflow.md`，主题根还可以有 `status.md` / `deferred.md`。F9 需要一个落点，F1/F2/F3 的裁决结果也需要一个落点。预期影响：现在这些只能塞回 Spec 或散在本报告里，而报告是时点记录、不该成为唯一真相来源。

## nit

- **N1** · `tests/unit/test_cli.py`，`test_auth_without_a_config_still_targets_dotcom_and_the_default_token_file` 收了 `tmp_path` 然后第一行 `del tmp_path`。直接不收这个参数即可。

---

## 已核查、未发现问题的面（避免「未发现」无法与「没查」区分）

- **`resolve_provider_base_urls` 同源性（调用方重点 1）：无问题。** 「两条路没有第三条」那条裁决的对象是 `api_base_url`；本次没有新增配置键，`github_web_base_url` 由 `auth_base_url` 单向推导，方向与那条裁决一致。cli.py 里构造 `GhcClientConfig` 的姿势与 `composition.py:357-359` 逐字同构（除 S1 的重复外）。
- **`NOT_HOT_RELOADABLE`（重点 1）：无需变更，已确认。** `model_providers.*.auth_base_url` 已在清单里（`schema.py:43`），派生值不是配置键因而无独立条目可言；且 `auth` 是一次性 CLI，不经过热重载路径。
- **`ghc_client` 不从 host 反向依赖（重点 1）：未破坏。** 新增的三条 import 全是包内（`device_flow` → `config`、`auth/service` → `config`、`__init__` → `config`）；host 侧 `cli.py` 单向引入。`ghc_client/__init__.py` 的 docstring 已列明既有的 `app.pipeline.exceptions` / `app.config` 依赖，本次没有增加新的。
- **接线是否有孤儿守卫（重点 2）：没有。** 全仓 grep `DeviceFlowClient(` 的构造点只有两个：`auth/service.py:46`（生产，已带 `web_base_url`）和 `test_device_flow.py:18-19`（测试）。`DeviceAuthProvider`（`providers.py:131`）确实是生产孤儿，但它在 HEAD 上就已经是了，且 `build_github_token_source` 不含它——本次没有把守卫留在旧链路上。**真正的问题不是守卫走空，而是入口太窄（F1/F2）。**
- **推导函数的边界（§3.2）：逐条对过，没找到错误映射。** `https://api.ghe.com` 正确落进「缺租户」分支（`"api.ghe.com".endswith(".ghe.com")` 为真，`removeprefix` 后等于 `"ghe.com"`）；`:443` 放行、`:8443` 拒绝；大小写由 `parts.hostname` 归一；`rstrip("/")` 在 `urlsplit` 之前，故 `https://api.github.com/` 的 path 为空而 `.../api/v3` 不为空；`DeviceFlowClient` 侧又 `rstrip` 一次，尾斜杠不会双写（测试已钉）。
- **测试钉的是结构还是名字（重点 6）：钉的是结构。** `test_both_endpoints_follow_a_tenant_web_origin` 断言的是两次 POST 的**完整 URL 列表与顺序**，不是函数名或常量名；`_client` 那个 `web_base_url is None` 就不传参的写法是刻意的（注释写明了理由），使断言 dotcom 的旧用例仍在测**默认值**而不是自己喂进去的值——这一条写得好，正是「测试自证」的反面。`test_config.py` 的否定用例覆盖 scheme/userinfo/query/fragment/path/port/缺租户/缺 `api.` 八种形态。
- **未覆盖的失效面：** `--provider` 无 `--config`（= F1，我用探针补了观测）；`_resolve_auth_provider` 返回 `""` 的分支（= F6，不可达）。
- **测试的分辨力：** 调用方已做两次控制变异（`cli.py` 的 `web_base_url` 常量化 → `test_cli.py` 两条红；`DeviceFlowClient` 收参不用 → `test_device_flow.py` 一条红），覆盖了「origin 有没有真的传下去」和「client 有没有真的用它」两层。**我没有重做变异**（共享主树上有同伴未提交改动，改生产代码不在我的授权内），因此这两条按**采信既成事实**处理。第三层——「`--provider` 解析选对了人」——两侧都没有变异证据，但 F3 的探针 A/D 已经直接观测到它选不出人，不需要变异来证。
- **权威归属核查：** Spec 里 `resolved-by-user` 类标注共两处。§2「用户 2026-08-28 ……裁定『做，无需验证』」与 §4 第三条「用户 2026-08-28 明示无需验证」——与调用方派发时给我的任务描述逐字一致（「做，无需验证」），一手来源可回指，言语行为是裁决，范围盖得住（只覆盖「做」与「不实测」，未被扩大解释为覆盖设计取舍）。**归属成立。** §5 关于 `docs/.human-controlled/ghc-api.md:17` 的处理（只报告、不代改）符合「人写文档是最终权威」。
- **`docs/.human-controlled/cli.md` 为空文件**，故本次 CLI 面的改动不与任何用户亲笔的 CLI 契约冲突。

---

## 我考虑过但否决的路线

按调用方要求逐条列出，包括查过之后认为不成立的。

1. **「`GITHUB_CLIENT_ID` 在租户上无效，§3.4 是在偷懒」** —— 否决。§3.4 的论证是完整的：id 无效的症状是 device code 请求 4xx，被既有的 `response.raise_for_status()` 抛出，是响亮失败。我实际去核了 docs.github.com 的 OAuth 文档，它没有给出 ghe.com 形态的端点，也就没有任何一手材料能支持「租户需要另一个 client id」。在无租户可测的前提下，「不动它 + 失败是响亮的」是正确处置，不是借口。
2. **「`GITHUB_WEB_BASE_URL` 没进 `__init__.py` 的 `__all__`，导出不一致」** —— 否决。既有的 `GITHUB_AUTH_BASE_URL`、`INDIVIDUAL_BASE_URL` 同样不在 `__all__` 里，而 `cli.py` 早就有 `from app.model_provider.ghc_client.auth.service import ...` 这样的深导入。本次完全遵循既有惯例，不构成发现。
3. **「`urlsplit` 对畸形输入会抛非 `ValueError` 的异常，`_authenticate` 只 catch `ValueError` 会漏」** —— 否决。`urllib.parse` 对畸形 URL 抛的就是 `ValueError`（含 `IPv6` 括号不匹配等），且它在 `resolve_github_web_base_url` 内部，与函数自己抛的是同一类型，catch 面是对的。构造不出反例。
4. **「应当给 `login` 加 `--web-base-url` 直接指定，绕开推导」** —— 否决，且认为提出它就是错的。这正是 §3.1 与「两条路没有第三条」共同禁止的第三个真相来源。§3.1 的论证成立，我不动它。
5. **「§3.3 不回落太严格，应当 warn + fallback」** —— 否决。§3.3 的理由（静默回落就是本次要修的缺陷本身）是本仓一贯立场，`resolve_provider_base_urls:350` 的措辞与之完全同源。**§3.3 站得住，调用方问的这一条我给的答案是「成立」。**
6. **「§4 不抄 `resolve_ghe_endpoints()` 是在偷懒」** —— 否决。理由成立且与 2026-08-22 裁决直接挂钩：推理侧已有「显式配置」与「探测订阅」两条路，再加字符串推导确实是第三条。**不抄 `--ghe-endpoint` 写回 config.yaml** 同样成立，且理由是可核的（PR #34 自己的 review 第 2 条确实指出 `update_top_level_config_values()` 整行改写会吞掉行内注释——我在 PR 页面读到了这条 suppressed comment）。**§4 的三条「不做」我逐条核过，都不是借口。唯一的缺口是 F9：漏登记了 GHES。**
7. **给 `NOT_HOT_RELOADABLE` 报一条** —— 否决，理由见「已核查」节。
8. **报「`auth` 的 `--config` 应当接受 `exists=True` 让 typer 先校验」** —— 否决。`debug models` 用的就是 `exists=False` + `_read_config` 里统一翻译 `FileNotFoundError`，本次照抄是对的；改成 `exists=True` 反而会让两条命令的错误消息分叉。
9. **在共享主树上做变异以复核测试分辨力** —— 否决并主动放弃。工作树里有同伴的未提交改动（`docs/.human-controlled/*`、`Dockerfile` 等），在这种状态下改生产代码再还原属于我无权自行授权的操作，且 `restoring-a-mutation-needs-a-snapshot-not-git` 记录过它毁过工作。改为：采信调用方已做的两次变异 + 用只读探针直接观测第三层。**这条限制已在「评审范围」里如实标注。**
10. **报「新增的 `--config` 让 `auth` 在坏配置上从无行为变成 exit 1，是行为变更」** —— 否决。这个入口在 HEAD 上根本不接受 `--config`，谈不上变更；新行为（打印 pydantic 消息、不打 traceback）与 `debug models` 一致，是对的。只有 docstring 的作用域声明陈旧，已按 F7 单列。

---

## 建议的处置顺序（不构成裁决）

1. **F4 中「Spec 尚不知道的事实」那一半当场补进 §3.5**——按项目规则这不需要用户裁决，且它是理解 F1/F3 的前提。
2. **F1 定死**：要么让 `--provider` 缺 `--config` 时报错，要么让它蕴含走配置发现链（即顺手解掉 F2）。这两条其实是同一个决定的两个出口。
3. **F2/F3 一起交裁决**：`auth` 该不该走 `resolve_config_path` 的完整三级、`--provider` 缺席时该不该认 `default_model_provider`。这两条一起改，F6 那条死分支和 F10 的现场路径也随之消失。
4. F5、F7、F8、F9 是文档/措辞级修订，可与上面任一批次同行。
