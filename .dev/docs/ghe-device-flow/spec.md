# GHE data residency 的 Device Flow OAuth 源

**这份是 Spec**，答「应该是什么样」，规范性。**这是活文档，不冻结。** 新的用户裁决、实测或发现一旦与本文任何一处冲突或限定它，当场修订本文，并在文末的条款修订记录里登记。权威永远是本文的当前版本。

## 1. 问题

Device Flow 的两个端点在 `src/app/model_provider/ghc_client/device_flow.py` 曾硬编码为 `https://github.com/login/device/code` 与 `https://github.com/login/oauth/access_token`，`DeviceFlowClient.__init__` 只收 http client、sleep、monotonic，**没有任何注入点**。

而推理侧的 `api_base_url` 与换 token 侧的 `auth_base_url` 早已是两个独立可配置字段（`src/app/config/schema.py:93-99`）。于是三条腿里，推理和换 token 能指向 GHE data residency 租户（`*.ghe.com`），**只有登录这一条指不过去**：租户下跑 `ghc-api-proxy auth`，设备码会发到 dotcom，拿回来的 token 不是租户签发的。

## 2. 触发与依据

用户 2026-08-28 指定参考 [sxwxs/ghc-api PR #34](https://github.com/sxwxs/ghc-api/pull/34)（"Add GHE data residency endpoint support"），并在对照报告后裁定「做，无需验证」。对照结论见 §4。

## 3. 规范条款

### 3.1 三个 host，不是两个

在既有的 `api_base_url`（推理）与 `auth_base_url`（换 token／描述账户）之外，认第三个角色：**`github_web_base_url`，OAuth 的 web 源**，Device Flow 的两个端点挂在它下面。

它**不是新配置项**，由 `auth_base_url` 推导。理由：同一个租户的这两个 host 是同一事实的两种拼写，让运营者分别写两遍就制造了第三个真相来源——与 `src/app/server/composition.py:346` 那条「两条路没有第三条」的裁决同源。

### 3.2 推导规则

`resolve_github_web_base_url(auth_base_url: str) -> str`，输入是已解析的 `auth_base_url`（即 `auth_base_url_override or GITHUB_AUTH_BASE_URL`）：

| 输入 | 输出 |
|---|---|
| `https://api.github.com` | `https://github.com` |
| `https://api.<tenant>.ghe.com`，`<tenant>` 的每一个 DNS label 都非空 | `https://<tenant>.ghe.com` |
| `https://<host>/api/v3`（自托管 GHES） | `https://<host>` |
| 其它一切 | `ValueError` |

**前置校验按「存在」判定，不按「取值真假」判定。** 去掉尾部斜杠之后，输入必须**逐字**（大小写不敏感）等于它自身重建出的裸 origin：`https://<host>`，或 port 显式为 443 时的 `https://<host>:443`，**或该 origin 后面紧跟 `/api/v3` 这一个路径**。port 不在 `{None, 443}` 内直接拒绝。

`/api/v3` 是唯一被接受的 path，因为**它正是区分第三种形态与前两种的那个标志**：github.com 与 residency 租户都在专用的 `api.` 主机上应答、后面什么都不带，而 GHES 在浏览器用的同一主机上、挂在一段路径下应答。`/api/v4`、`/api`、`/api/v3/extra` 一律拒绝——邻近的版本号或它的前缀不是 REST 根，猜它是就会把设备码发到没人指定的主机上。

三种形态的返回值都从 hostname 重建，因此显式的 `:443` 一律归一化掉；否则同一个部署会因为配置写法不同而产生同一 origin 的两种拼写。

这条规则替换了原先逐字段检查 scheme／userinfo／path／query／fragment 的写法，原因是那种写法问错了问题：`https://@api.github.com` 的 userinfo **存在**（`@` 就在 authority 里）而**取值为空**，逐字段的真假判断把它放行了。一次整串比对同时覆盖上述全部字段与所有空分隔符形态，而且不会被某个没人想到去枚举的成分绕过。

三条被实测暴露过的边界，逐条定死：

- **`<tenant>` 允许多个 label**（`eu-west.octocorp`）。这不是主张 GitHub 一定接受它——恰恰相反，公开文档只给了单 label 的例子（`octocorp`），我们**不掌握**它完整的 subdomain 语法。拒绝一个无法证明非法的形状，是在把「我没查到」伪装成「服务端不允许」，那是凭空发明约束。放行的代价是租户不存在时得到一个 DNS 或 4xx 失败，响亮且指向明确。
- **空 label 一律拒绝。** `https://api..ghe.com` 曾被放行并推出 `https://.ghe.com`，因为判据只比对了整串等于 `ghe.com`。空 label 不可能是任何租户，必须在配置边界拒掉，不能留给网络层去失败。
- **尾部斜杠按任意数量归一化去除**，其余 path 一律拒绝。`https://api.github.com//` 与 `https://api.github.com` 等价；`https://api.github.com/v3` 拒绝。这是对既有实现行为的明文承认，不是新规则——写下来是因为它此前只存在于 `rstrip("/")` 这个动作里，Spec 说的却是「path 为空或 `/`」，两者对不上。

**解析器自己抛出的 `ValueError` 必须被改写成本条规定的文案。** `urlsplit` 对非法端口（`:not-a-port`）和坏 IPv6（`https://[bad`）会抛出它自己的消息，那些消息不含「收到了什么、期望什么形状」，而 §3.3 要求每一次推导失败都写出这两样。原异常用 `raise ... from` 挂在因果链上，不丢。

### 3.3 推不出来是硬错误，不得回落

不得在推导失败时静默回落到 `https://github.com`。理由：静默回落正是本次要修的那个缺陷本身——它把「打错了 host」变成一个没有任何观测面的成功。错误消息必须同时写出收到了什么与期望什么形状。

**代价已知并接受**：`auth_base_url` 的另一个既有用途是「把这个库架到本地服务器上」（`ghc_client/config.py` 的类 docstring 记着这个理由），一个 `http://127.0.0.1:8080` 之类的本地 host 推不出 web 源。**这只影响 `auth` 一条命令**——`logout` 只需要 token 文件路径，从不问 OAuth 端点在哪，见 §3.7。

### 3.4 client_id 不变

`GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98"`（VS Code 的 dotcom client id）在租户上是否有效**未经证实**。PR #34 用的是另一个 id（`01ab8ac9400c4e429b23`），因此它既不能证明也不能否证我们这一个；GitHub 公开文档没有给出 client id 契约。本次照旧不动它。

若租户拒绝该 id，症状是 device code 请求返回 4xx，由既有的 `response.raise_for_status()` 抛出——是响亮失败，不是静默失败。这一条不需要额外防护。

### 3.5 `auth` 与 `logout` 走本项目唯一的配置发现链

**这一条在 2026-08-28 被推翻重写过一次，原方案是错的**，见文末修订记录 R2。原方案让 `auth` 只认显式的 `--config`，不给就完全不读配置。那道门把整个功能挡在了它最该生效的那条命令外面：租户机器上的运营者敲的是裸 `ghc-api-proxy auth`。

现在的规范：

- **配置一律经 `resolve_config_path`（`src/app/config/loading.py:86-107`）解析**，三级依次为显式 `--config` → 环境变量 `GHC_API_PROXY_CONFIG` → 默认位置。这是本仓「配置文件在哪」的唯一权威，`loading.py` 自己写着「the loader **every** entry point uses」，`auth` 不做例外。
- **provider 是必填的位置参数，永不推导。** 用户 2026-08-28 裁定：`auth <provider>` 与 `logout <provider>`，不给就是用法错误。命名了但配置里没有，报 `BadParameter` 并列出已配置的名字。

  **为什么不用 `resolve_default_name`**：那个函数回答的是「一个没写限定的请求该去哪个 provider」，与「我正在以哪个身份登录」是两个问题。这两条命令写入和删除凭据，一个替你悄悄挑一个的默认值会把 token 存到运营者没有指定的身份下，而 `logout` 随后会为一个他没选的文件宣告成功。写出那个名字只多一个词，却让确认行说出一句可核对的话。

**这一条改变了一条已发布命令的行为契约，依据在此，界限也在此。**

`src/app/config/bundled-config.yaml:56` 无条件带 `default_model_provider: ghc`，而 `_deep_merge`（`loading.py:37-53`）只合并、不删除键。**但这不足以说「永远解析得出一个名字」**——运营者把该键显式写成空串，或把环境变量 `GHC_API_PROXY_DEFAULT_MODEL_PROVIDER` 置空，`resolve_default_name` 照样抛 `ProviderNotConfigured`。本文一度写着「永远」，而同一次提交里的测试 `test_auth_refuses_an_open_choice_and_a_dangling_default` 走的正是那条路；该说法作废，见修订记录 R3。

**真正成立的依据是另一条**：`build_chain`（`composition.py:472`）在构造任何东西之前就调 `resolve_default_name`。**凡是 `auth` 现在会拒绝的那个配置状态，`start` 本来就起不来**——那里不存在能被弄坏的、正在工作的部署。这条比上一条强，因为它不依赖「那个状态可不可达」。

**同一段事实还决定了运营者该怎么写配置**：bundled 的 `ghc` 这个键**删不掉**，所以任何「新增一个租户 provider」的配置都必然有 ≥2 个 provider。租户部署因此有两种正确写法，都被支持：把 `auth_base_url` 直接写到 `ghc` 键上（provider 仍只有一个），或者新增一个 provider 并同时设 `default_model_provider` 指向它。

**确实改变的行为有三处**，逐条列出而不是笼统说「不变」：

1. 默认位置或环境变量指着一份**坏配置**时，`auth` 现在会打印消息并 exit 1，而不是照旧登录。与 `debug models` 一致；配置坏了服务本来也起不来。
2. 配置里写了 `github_token_file` 时，裸 `auth` 现在写到那个文件，而不是默认路径。这修掉了一个既有缺陷——用户亲笔的 `config.example.yaml` 推荐的文件名带 `.txt` 后缀，与 `FileTokenProvider` 的默认路径不同名，照它配置的部署此前登录成功而服务读不到凭据。
3. **服务以 `start --config X` 启动、而发现链会找到另一份配置时，两边可能指向不同的 token 文件。** 改动前裸 `auth` 总写默认路径；改动后它按发现链找到的那份写。发行的 systemd unit（`contrib/systemd/ghc-api-proxy.service`）不传 `--config`，走的就是发现链，因此官方部署路径上两者天然一致；要触发得运营者自己改 unit 加 `--config` 且默认位置另有一份配置。`debug models` 早就在同一个歧义面上，本次是让 `auth` 也进来。

还有一处不改变目标、只改变输出：`auth` 与 `logout` 现在会印出实际写入／删除的绝对路径，且在环境变量会遮蔽该文件时出声警告（§3.6）。

**用户 2026-08-28 已追认这三处，保持现状。** 裁决时手上的材料包括：两位独立评审的相反结论、上面这份逐条清单，以及一条实测——用户本机的 `~/.local/share/ghc-api-proxy/config.yaml` 不含 `model_providers` 段、两个相关环境变量均未设置，因此裸 `auth` 在那台机器上的解析结果与改动前逐字相同。评审对退回显式 `--config` 的处置意见与本裁决一致（两位的产品倾向都是保留发现链）。

### 3.6 登录要写到该 provider 会去读的那个文件——但那是三级链的第三级

选中 provider 之后，token 写入 `github_token_path(config, provider)`（`composition.py:309`）。理由：一个把 token 写到该 provider 不去读的位置的登录，与打错 host 的登录一样不可用——同一类缺陷，修一半等于没修。

**没有配置 `github_token_file` 的 provider，默认文件是 `github_token-<provider>.txt`，不是共用一个。** 用户 2026-08-28 与「provider 必填」同时裁定。理由：两个 provider 若各自对着不同租户认证，手里就是两枚不同的 GitHub token，共用一个 `github_token` 意味着**后登录的那个静默变成了两者的凭据**。名字在 `github_token_path` 里派生，因为只有这一侧知道问的是哪个 provider；而 `build_github_token_source`（`composition.py:319`）读的也是这同一个函数，所以「登录写的文件」与「服务打开的文件」是同一个决定，不可能各自漂移。

**这是一次破坏性变更**：既有部署的 token 在旧的 `github_token` 上，改动后服务按新名字找不到它。失败是响亮的（首个请求抛 `NoGitHubToken`），不是静默的；迁移就是重命名一次，或重新登录一次。

**限定，必须写在这里而不是别处**：provider 实际取 token 的链是 `CLITokenProvider` → `EnvTokenProvider` → `FileTokenProvider`（`composition.py:328-336`，按 `priority` 取第一个可用的），**文件是第三级**。所以「写到它会去读的文件」只在没有更高优先级来源时等于「它会读到这个 token」。运营者若 export 了 `GHC_API_PROXY_GITHUB_TOKEN`，登录会成功、文件会写对，而服务照旧用环境变量里那一枚——症状与 §3.3 要消灭的那个同形。

因此 `auth` 在成功之后必须检查环境变量那一级是否会遮蔽刚写下的文件，会则**出声警告**（不阻断、不改变退出码）。判据是本仓自己的尺度（`cli.py:308-309`）：被接受然后被忽略比被拒绝更糟，因为它与「起作用了」无法区分。

**为什么只查环境变量那一级、不查第一级，这个依赖必须写下来**：`build_github_token_source`（`composition.py:328-336`）把第一级硬编码成 `CLITokenProvider(None)`，而喂它的 `--github-token` 早已在失效选项表里（`cli.py` 的 `_NO_HOME_IN_SPEC`）。所以 CLI 那一级在运行中的部署里**恒为不可用**，能遮蔽文件的只有环境变量。**这个结论依赖那处硬编码；一旦 CLI 级能携带真值，本检查就少了一级，必须同步扩展。**

**`auth` 与 `logout` 都必须印出实际写入／删除的那个绝对路径。** `github_token_file` 直到本次才成为「有东西会去**写**」的路径——此前只被读，而读一个不存在的路径无害（`FileTokenProvider.get_token` 吞 `OSError` 返回 `None`）。写不是：一个相对路径会落到运营者当时恰好所在的目录并顺手建出目录树，一个未展开的变量会原样留在文件名里，两者都产生「登录报告成功、服务在别处读不到」的结果。把路径印出来是这条失效面唯一的观测点。

路径怎么解析见 §3.8——用户 2026-08-28 裁定的规则让「相对路径落到运营者当时的 cwd」这一失效面在配置文件这一层不再存在。印出路径仍然必要：它同时守住环境变量层与 CLI 层写来的相对路径，以及未展开的变量。

### 3.7 `logout` 必须能清掉 `auth` 写下的那个文件

`auth` 一旦能把 token 写到 provider 的 `github_token_file`，`logout` 那句「Remove locally stored authentication state」就不能在没清掉它的情况下仍报告成功。

`logout` 因此与 `auth` 用同一套解析：同一条配置发现链、同一个必填的 `<provider>` 位置参数、同一个 `github_token_path`，并接受同样的 `--config`。这一条没有独立的裁决空间，它是 §3.6 的反向边。

**同一套解析，也同一套告知义务。** §3.6 那两项对 `logout` 同样成立且理由更强——`auth` 只是默默成功，`logout` 是**主动宣告完成**：

- 印出实际删除的绝对路径。`logout` 清的是**选中 provider 的那一个文件**，而它的说明写着「authentication state」（全部）。另一个 provider 的 token、以及本次改动之前写在默认路径上的那一枚，都会在一条宣告「已移除」的命令之后原样留在盘上（`clear_token` 用 `unlink(missing_ok=True)`，删一个不存在的文件不作声）。两者的差距只能靠印出路径来读出。
- 环境变量遮蔽时同样警告。文件删了，服务照旧拿环境变量里那一枚跑，而运营者读到的是「本地存的认证状态已移除」。

**`logout` 不推导 OAuth 源，这是有意的。** 删一个本地文件不依赖设备码从哪来；若要求先推导成功，一个 `auth_base_url` 指向本地 stand-in 的部署就再也无法用 CLI 删掉自己的 token。写明是因为 §3.3 的拒绝很响亮，后来的人可能合理地以为它对两条命令都该生效。

### 3.8 配置里的相对路径从 config.yaml 算起，不从 cwd 算起

**用户 2026-08-28 裁决。** 配置文件里声明的任何相对路径，都相对**该配置文件所在目录**解析，而不是相对进程启动时的工作目录。

理由与 `resolve_config_path` 已经立下的那条同源（`loading.py` 记着 2026-08-22 的裁决：「which directory a service was launched from should not decide what it runs」）——那条管的是**读哪份配置**，这条管的是**那份配置里写的路径指向哪**。少了这一半，运营者在哪个目录敲命令仍然决定 token 写到哪儿。

适用字段就是 `ProxyConfig` 里全部四个路径字段：`server.tls.cert`、`server.tls.key`、`model_providers.*.github_token_file`、`pidfile_dir`。清单以数据形式集中在 `loading.py` 的 `_PATH_FIELDS`，新增路径字段时加一行。

三条界限：

- **只重定基准配置文件那一层。** 环境变量或 CLI 选项送来的相对路径保持 shell 语义——敲 `--pidfile-dir ./run` 的人指的是自己当前所在的目录，把它解析到别处的配置文件旁边是同一种伏击、只是方向相反。
- **展开先于重定基准。** `~`、`$VAR` 与本项目 `$XDG_DATA_HOME/ghc-api-proxy` 那种写法本身就产生绝对路径；只有展开之后仍然是相对的，才拼到配置目录上。
- **没找到配置文件时不做任何改写。** 此时没有基准可言，相对路径照旧按 cwd 解析。

**这条规则的作用域超出了本主题。** 它是配置加载层的通用规则，本文记录它是因为裁决发生在这里；将来若建立配置加载的专属文档，权威应当迁过去，本文改为引用。条目见 `deferred.md`。

## 4. 本次明确不做的，以及为什么

- **不抄 PR #34 的 `resolve_ghe_endpoints()`**（从一个租户输入推出 web／GitHub API／Copilot API 三个端点）。与 §3.1 同源的理由反向适用：推理侧端点已经有「运营者显式配置」与「探测订阅推导」两条路，再加一条字符串推导路就是多余的真相来源，且与 2026-08-22 那条裁决直接冲突。
- **不抄 `--ghe-endpoint` 写回 `config.yaml`**。PR #34 自己的 review 已指出该实现按整行改写，会吞掉行内注释，而保留注释正是它宣称的目标。这一条只否决那个具体的改写实现，不永久否决将来任何形式的便利命令。
- **不做端到端实测**。无 GHE 租户，用户 2026-08-28 明示无需验证。

**§4 最后一条所依赖的证据，两半的权重不同，不得打包成一个「旁证」**：

- **`https://api.<tenant>.ghe.com` 是租户的 REST API base——有一手来源。** docs.github.com（enterprise-cloud@latest，REST getting-started）明写该形态并给出实例 `https://api.octocorp.ghe.com/`。这一半够硬。
- **Device Flow 的两个端点随租户搬家——只有旁证。** GitHub 的 OAuth 文档只列 `https://github.com/login/device/code` 与 `https://github.com/login/oauth/access_token`，附一句通用说明「You might access GitHub at a different domain, such as `octocorp.ghe.com`」，没有给出 ghe.com 形态的端点。支撑它的是 PR #34 的实现，加上 vscode-copilot 对 GHE MCP 端点使用 `copilot-api.${authority}` 前缀（`/home/xp/src/refs/vscode-copilot-chat/src/extension/githubMcp/common/githubMcpDefinitionProvider.ts:103-105`）与它把 capiUrl／dotcomUrl／proxyUrl／telemetryUrl 当四个独立域处理（`src/platform/endpoint/common/domainService.ts:9-14`）。

**权重：够支撑实现落地，不够支撑「已验证」这个说法。任何下游文档不得把本条改写成已验证。**

## 5. 一处待用户裁决的文档事实（本次不改）

`docs/.human-controlled/ghc-api.md:17` 写 self-hosted 的 API Base URL 是 `msft.ghe.com`。按 §4 的证据，data residency 租户的 Copilot 推理侧应当是 `copilot-api.<tenant>.ghe.com`。该文件由用户亲笔控制，本次只报告不修改。

顺带两条同类，同样只报告：`auth_base_url` 至今未在 `docs/.human-controlled/config.example.yaml` 中文档化（早前登记于 `.dev/docs/tmp/260822-ghc-api-conformance-summary.md` 的 D2）；同一文件推荐的 `github_token_file` 值带 `.txt` 后缀，与 `FileTokenProvider` 的默认路径不同名（§3.5 第 2 条行为变更已让 `auth` 侧不再受它影响，但两者仍不一致）。

## 条款修订记录

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-08-28 | 全文 | 首稿 | 用户裁定「做，无需验证」；对照 PR #34 |
| 2026-08-28 | **§3.5 推翻重写（R2）** | 原方案「不给 `--config` 就完全不读配置」作废。改为一律走 `resolve_config_path` 三级发现链，provider 选择交给既有权威 `resolve_default_name`，删除自造的「恰好一个就用它」规则。原方案把功能挡在了最该生效的那条命令（裸 `auth`）外面，且 `--provider` 单独给出时被静默吞掉、照旧登录 dotcom——正是本 Spec §3.3 要消灭的形态 | 两份独立评审 [reports/260828-review-gpt.md](reports/260828-review-gpt.md) F-01、[reports/260828-review-claude.md](reports/260828-review-claude.md) F1/F2/F3/F6，均附一手探针；「不构成行为变更」这一判断的依据是 `bundled-config.yaml:56` 与 `_deep_merge` 无删除语义，本人复核 |
| 2026-08-28 | §3.2 补三条边界与解析器异常改写 | 空 label 曾被放行推出 `https://.ghe.com`；多尾斜杠被静默归一而 Spec 说的是「空或 `/`」；`urlsplit` 自抛的 `ValueError` 不含 §3.3 规定的文案。另明定多 label tenant 合法及其理由 | [reports/260828-review-gpt.md](reports/260828-review-gpt.md) F-02，本人一手复现三种输入 |
| 2026-08-28 | §3.6 补限定 + 新增警告要求 | 原文「写到该 provider 真正会读的那个文件」措辞过强：文件是三级链的第三级，环境变量会静默遮蔽它 | [reports/260828-review-claude.md](reports/260828-review-claude.md) F8 |
| 2026-08-28 | **新增 §3.7** | `logout` 清不掉 `auth` 新能写的自定义 token 文件，却仍报告「已移除」 | [reports/260828-review-gpt.md](reports/260828-review-gpt.md) F-03，附一手探针 |
| 2026-08-28 | §4 新增 GHES 条目；证据权重拆成两半 | GHES 被 §3.2 拒掉却从未登记，触犯 `no-silently-cut-but-defer`；§4 原文把「REST base 形态」与「Device Flow 端点随租户搬家」打包成同一个旁证权重，而前者有一手文档 | [reports/260828-review-claude.md](reports/260828-review-claude.md) F9、S2 |
| 2026-08-28 | 删除原 §3.5 关于「语义与 `debug models` 逐条一致」的断言 | 该断言可核查且为假：`debug models` 的 `--provider` 是「只报告这一个」，缺省报告全部，从不因多个而要求指定。共享的只有 BadParameter 那一条 | [reports/260828-review-claude.md](reports/260828-review-claude.md) F5 |
| 2026-08-28 | **§3.5 的依据整段换掉（R3）** | 原文写「经 `load_proxy_config` 出来的配置**永远**解析得出一个 provider 名」，**这是假的**——显式把 `default_model_provider` 写成空串、或把对应环境变量置空，`resolve_default_name` 照样抛；而**同一次提交里的测试 `test_auth_refuses_an_open_choice_and_a_dangling_default` 走的正是那条路**。结论（不构成可退化的既有部署）仍成立，但依据换成更硬的一条：同一状态下 `build_chain` 也抛同一个异常，那里根本不存在能被弄坏的、正在工作的部署。同时把「行为不变」的措辞收回，改为逐条列出三处确实变了的行为，并声明是否追认属用户裁决 | [reports/260828-review-claude-r2.md](reports/260828-review-claude-r2.md) R2-1（附三次实测）、[reports/260828-review-gpt-r2.md](reports/260828-review-gpt-r2.md) R2-01（blocker，附五类反例）。两份复核结论相反，本文采两者的交集：依据换硬、断言收窄、裁决交回用户 |
| 2026-08-28 | §3.5 第 3 条行为变更（新增） | `start --config X` 与发现链可能指向不同配置文件，裸 `auth` 因此可能写到服务不读的那个文件。发行的 systemd unit 不传 `--config`，故官方部署路径不受影响 | [reports/260828-review-claude-r2.md](reports/260828-review-claude-r2.md) R2-6 |
| 2026-08-28 | §3.2 前置校验改为整串比对 | 逐字段的真假判断问错了问题：`https://@api.github.com` 的 userinfo 存在而取值为空，被放行 | [reports/260828-review-gpt-r2.md](reports/260828-review-gpt-r2.md) R2-02 |
| 2026-08-28 | §3.3 收窄为只影响 `auth`；§3.7 明写 `logout` 不推导 | 原文说推导失败「影响 `auth` / `logout` 两条命令」，实测 `logout` 根本不调推导。方向无害但同样是可核查而为假的断言，且可能诱导后来者给 `logout` 加一道不该有的门 | 两份复核同时报出：[gpt-r2](reports/260828-review-gpt-r2.md) R2-04、[claude-r2](reports/260828-review-claude-r2.md) R2-5 |
| 2026-08-28 | §3.6 补 CLI 级依赖；新增「必须印出路径」 | 「只查环境变量」成立的真正理由是 `build_github_token_source` 把 CLI 级硬编码成 `CLITokenProvider(None)`，该依赖此前没写在任何地方；`github_token_file` 本次才成为被写入的路径，相对路径会落到当时的 cwd 且无人报告写到了哪 | [reports/260828-review-claude-r2.md](reports/260828-review-claude-r2.md) R2-4、R2-3 |
| 2026-08-28 | **§3.5 三处行为变更获追认；§3.2 新增 GHES 映射；新增 §3.8** | 用户裁定：追认配置发现链的行为契约变更并保持现状；支持自托管 GHES（`https://<host>/api/v3` → `https://<host>`），原 §4「不支持 GHES」一条随之删除；配置里的相对路径改为从 `config.yaml` 所在目录解析 | 用户 2026-08-28 裁决，材料为两份复核报告的相反结论加本机实测 |
| 2026-08-29 | **§3.5 provider 改为必填位置参数；§3.6 默认 token 文件按 provider 命名** | 用户裁定 `auth|logout <provider>` 为必填项，且默认写入的文件形如 `github_token-<provider>.txt`。据此删去这两条命令对 `resolve_default_name` 的使用，以及随之而来的「歧义」与「dangling default」两条分支 | 用户 2026-08-29 裁决（回应 D-5 的澄清提问）。**含一次破坏性变更**：既有 `github_token` 需重命名或重新登录 |
| 2026-08-28 | §3.7 补告知义务 | `logout` 只清选中 provider 的一个文件却无条件宣告完成，且环境变量遮蔽时不作声——§3.6 刚立的义务没同步到反向边 | [reports/260828-review-claude-r2.md](reports/260828-review-claude-r2.md) R2-2、R2-7 |
