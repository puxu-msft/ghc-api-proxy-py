# proxy 优先级独立评审

> **落盘说明**：本报告由评审 agent（异源模型）产出，但该 agent 被 harness 约束禁止创建评审 Markdown，故由主会话代为落盘，正文为其两次返回的全文，仅修正了传输过程中被转义的尖括号。
>
> **一处需要记下的过程错误**：主会话在请求第二轮定向复核时，对评审员声称「报告已由我代为落盘」，而当时**文件并不存在**，实际是在第二轮结论返回之后才写的。同一形状的错误（声称已记录而未记录）本次会话已出现四次。

## 评审范围与结论

评审对象为提交 `b83d84eaf3a62303da30ec349b426cb38806d373`，工作树为 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`，分支为 `worktree-proxy-priority`。所有承重命令均核对了工作树路径、HEAD 和实际加载的 `composition.py` 路径。工作树最终保持干净。

**结论：不能合入 `main`。**

存在一条 Major 路由缺陷：设置档有 `proxy` 时，`NO_PROXY=*` 不再直连，而是让全部请求走设置档代理。这直接违反「`NO_PROXY` 维持原生 httpx 语义」的裁决，并且正好落在现有回归没有覆盖的边界上。

另有一个空 CLI 值导致环境重新渗入的问题，以及 `_warn_about_socks` 的确定性误报。

## 发现

### F-1【严重度：Major；把握：高】设置档吞掉 `NO_PROXY=*`

证据强度：**足以阻止合入**。这是 httpx 0.28.1 真实 `AsyncClient` 的逐 URL 路由结果，不是静态推断或手写 stand-in。

在同时设置以下条件时：

- 设置档 `proxy = http://setting.invalid:9000`
- `HTTPS_PROXY=http://https-env.invalid:8002`
- `NO_PROXY=*`

原生 `httpx.AsyncClient()` 对 HTTP、HTTPS、IPv4 目的地全部选择 `direct`。被评 `build_http_client(..., proxy_from_cli=False)` 却对同一批目的地全部选择设置档代理 `http://setting.invalid:9000`。

设置档为空时，被评实现与原生 httpx 都全部直连。因此，差异确定来自新增的设置档 overlay。

根因位于 `src/app/server/composition.py:271-277`。httpx 的 `get_environment_proxies()` 遇到 `NO_PROXY=*` 时用空字典 `{}` 表达「忽略所有代理并始终直连」。`_proxy_mounts()` 无法区分这个有语义的空字典与「环境根本没有代理配置」，随后又添加 `all:// → setting_proxy`，把直连意图反转成了全量代理。

因此，「`all://<host>` 比 `all://` 更具体」只证明普通 host 规则，不覆盖 `*`。`*` 根本不会生成 `all://<host>` mount。

现有 `test_no_proxy_reaches_past_the_setting` 只覆盖精确 host，完整套件仍然全绿。需要先修复该语义，并增加「设置档有值＋`NO_PROXY=*`」的回归，才能合入。

### F-2【严重度：Medium；把握：高】显式空 `--proxy` 不屏蔽环境，且不同于原生 httpx

证据强度：**足以作为修复项**。它是 CLI parser、`partial(...)` 接线和真实 client 三层联合探针的结果。

Typer 接受 `start --proxy ""`，并正确把 `proxy_from_cli=True` 传给 `serve_inherited`。但 `transport_options()` 先执行 `proxy = config.proxy or None`，空字符串因此变成 `None`。随后 `_proxy_mounts()` 不是根据 `proxy_from_cli`，而是根据 `cli_proxy is not None` 决定是否屏蔽环境。

结果是：在 `ALL_PROXY=http://all-env.invalid:8003` 下，`--proxy ""` 虽然被 CLI 判定为「给过」，实际请求仍走 `ALL_PROXY`。

原生 `httpx.AsyncClient(proxy="")` 则立即抛出 `ValueError: Unknown scheme for proxy URL URL('')`。所以当前行为既不满足「给出 `--proxy` 就完全屏蔽环境」，也不与原生显式 `proxy=` 一致。

这不推翻「一个 provenance bit 理论上足够」的设计判断。问题在于实现取得这个 bit 后，又用代理 URL 是否非空重新推导了一次 tier。可选择拒绝空 CLI 值，或让屏蔽环境的判断直接使用 bit，但当前行为不能称为完整实现三档规则。

### F-3【严重度：Low；把握：高】`_warn_about_socks` 会警告实际没有承载 HTTP／HTTPS 流量的 SOCKS 代理

证据强度：**足以确认误报，但不单独阻止合入**。

构造设置档为 `socks5://setting.invalid:1080`，同时设置 `ALL_PROXY=http://all.invalid:8000`。真实路由对 HTTP 和 HTTPS 均走 `http://all.invalid:8000`，设置档已被同一个 `all://` 键整体覆盖，但 `_warn_about_socks` 仍警告设置档 SOCKS 代理不应用 keep-alive。

另一个反例是：

- `ALL_PROXY=socks5://all.invalid:1083`
- `HTTP_PROXY=http://http.invalid:8001`
- `HTTPS_PROXY=http://https.invalid:8002`

HTTP 和 HTTPS 实际分别走两个 HTTP 代理，没有请求走 SOCKS，仍会为 `ALL_PROXY` 发出 SOCKS warning。

这是候选集直接取「环境值与设置值之和」、未按最终 mount 解析去除被覆盖候选造成的。没有发现漏报：CLI SOCKS、设置档 SOCKS、环境 SOCKS，以及设置档与环境分别承载不同 scheme 的两个 SOCKS 都能被报告。

凭据保护正确。设置档和环境变量中的 username、password 均未进入 warning；相同 origin 使用不同凭据时只输出一条去凭据后的 origin。

## 路由矩阵复验

证据强度：**足以确认除上述边界外，逐 scheme overlay 与 httpx 排序相符**。

所有场景都分别在设置档为空和设置档有值时构造真实 `httpx.AsyncClient`，并逐 URL 调用 client 的实际 transport selector。

- 仅 `HTTP_PROXY`：HTTP 走环境；HTTPS 在设置档有值时回落设置档，否则直连。
- 仅 `HTTPS_PROXY`：HTTPS 走环境；HTTP 在设置档有值时回落设置档，否则直连。
- 同时设置 `HTTP_PROXY` 与 `HTTPS_PROXY`：两个 scheme 分别走各自环境代理，设置档不抢占。
- 仅 `ALL_PROXY`：设置档为空或有值都由 `ALL_PROXY` 全量接管。
- `ALL_PROXY` 与 `HTTPS_PROXY` 并存：HTTPS 走更具体的 `HTTPS_PROXY`，HTTP 走 `ALL_PROXY`。
- 大小写混用：仅大写、按 scheme 混合大小写均有效；同一变量同时存在大小写版本时，lowercase 值与原生 httpx 一样胜出。
- 精确 host：设置档存在时，命中 host 仍直连，未命中 HTTP 回落设置档，未命中 HTTPS 走 `HTTPS_PROXY`。
- 子域规则 `.example.com`：子域直连但 apex 不匹配，与原生 httpx 一致。
- IPv4 与 IPv6：精确地址规则在设置档存在时仍直连。
- `NO_PROXY=*`：设置档为空时全直连；设置档存在时错误地全走设置档，见 F-1。
- CIDR `10.0.0.0/8`：httpx 0.28.1 实际不将 `10.1.2.3` 判为 bypass，尽管其源码注释列举了 CIDR。被评实现沿用了这一原生结果。按 D-7「维持 httpx 现有语义」的裁决，这不是本提交回归，但不能对外声称当前依赖支持 CIDR bypass。

## CLI 完全屏蔽环境

对非空且可解析的 CLI proxy，结论成立。

在同时存在 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 和 `NO_PROXY=*` 时，被评 client 对 HTTP、HTTPS、IPv4 三类目的地全部走 CLI proxy。原生 `httpx.AsyncClient(proxy=CLI_PROXY)` 得到相同路由，`NO_PROXY` 同样不生效。

空 CLI 值是唯一查出的反例，见 F-2。

## 一个 bit 与配置装配

对非空代理值，**一个 bit 足够**，没有发现需要完整 provenance 树的配置组合。

真实 loader 探针得到：

- bundled proxy 被 YAML proxy 覆盖。
- YAML proxy 被 `GHC_PROXY` 覆盖。
- `GHC_PROXY` 与 `HTTP_PROXY` 同时存在时，HTTP 走 `HTTP_PROXY`，HTTPS 回落 `GHC_PROXY`。
- 再提供 CLI proxy 后，HTTP 与 HTTPS 都走 CLI proxy。

这与文档可以自洽：`GHC_PROXY` 是「本设置」的环境写法，在第 3 档内部覆盖 YAML；proxy 专节明确点名的 `HTTP_PROXY`／`HTTPS_PROXY` 位于其上。全局配置优先级也只要求 `GHC_PROXY` 高于配置文件，没有规定它必须高于标准 proxy 环境变量。

## 必填参数与入口扫描

先全仓运行了 `rg 'build_http_client|transport_options'`，再用 AST 枚举 Python call，检查 keyword 与 `**kwargs`。

生产调用点完整集合为 `src/app/cli.py:139`、`src/app/cli.py:161`、`src/app/debug/models.py:230`，以及 `src/app/server/composition.py:142` 的 `transport_options`。全部显式传递 `proxy_from_cli`，没有 `**kwargs`、alias call、动态 `getattr` 或漏传入口。两个函数签名均无默认值，漏传会立即 `TypeError`。

CLI 级探针截获了真实 `partial(...)`：inherited listener 与 standalone 两条路径，在给与不给 `--proxy` 时分别得到 `True` 与 `False`，没有传反。`debug models` 没有 `--proxy` 入口，固定传 `False` 正确。

## 热重载

关于 `PrivateAttr` 的论断成立。在 `ProxyConfig` 子类上加入 `_proxy_from_cli: bool = PrivateAttr(default=False)`，设为 `True` 后执行 `model_dump(mode="python")`，dump 中没有该字段；再 `model_validate` 后恢复默认 `False`。

当前实现的热重载行为保持不变：`proxy` 确实位于 `NOT_HOT_RELOADABLE`；`pin_restart_only` 的 effective config 恢复旧值并报告 `restart_required == ("proxy",)`；用 startup config 与 effective config 分别构造 client，逐 URL 路由完全相同；实际服务 client 只在启动时构造一次。

## 回归分辨力

对 D-7 明确列出的七条 priority 回归，用进程内受控 monkeypatch 做了独立变异，每次先确认变异已经到达真实 `build_http_client`。

结果精确复现：去掉设置档 fallback `3 failed / 4 passed`；让设置档覆盖环境的 `all://` `1 failed / 6 passed`；把 CLI tier 折入 setting tier `2 failed / 5 passed`。因此文档中的 `3 / 1 / 2` 对「列出的七条 D-7 回归」这一范围准确。

没有发现恒真新增回归。普通 host 的 `NO_PROXY` 测试确实有分辨力，但它只守住该类别，没有守住 `*` 的不同表示机制。

已裁决但没有测试守住的性质至少包括：设置档存在时 `NO_PROXY=*` 仍应全直连（当前不仅无回归，而且实现错误）；CLI 完全屏蔽环境对空 CLI 值如何处理；SOCKS warning 只描述实际可能承载请求的代理。

## 基线复核

在 HEAD `b83d84e`：`uv run pytest -q` 为 `1563 passed / 3 skipped`，Ruff 通过，Pyright `22 errors`。

在父提交 `18d52cd` 的独立临时导出并确认 `app` 从该目录加载后：默认 pytest `1557 passed / 3 skipped`，Ruff 通过，Pyright `22 errors`。

因此，三组基线数字全部复核成立，Pyright 增量为 0。

---

## 定向复核（`1e4a228`）

复核对象为 `1e4a228227b734b94cf2aad464a87c39e6936695`。所有探针均确认实际加载 `src/app/server/composition.py`，复核后工作树保持干净。本轮只运行定向探针与相关测试，没有重跑完整闸门。

### F-1 修复确认

【结论：已修复；把握：高】

`composition.getproxies is httpx._utils.getproxies` 实测为 `True`。两边调用的是同一个 `urllib.request.getproxies()` 函数，读取的也都是返回映射中的 `no` 项。因此，新增 helper 与 httpx 的环境代理解析拥有同一来源，不是两套独立解析。

以下合法形式均已构造真实 client 逐目的地验证，helper、httpx 环境映射和最终路由一致：

- `NO_PROXY=*`
- `NO_PROXY="example.com,  * , localhost"`，包括列表中间的 `*` 和两侧空格
- lowercase `no_proxy=*`
- 混合大小写变量名 `No_Proxy=*`
- `NO_PROXY=*` 与 lowercase `no_proxy=secure.example` 并存时，urllib 按自身规则采用 lowercase 值，helper 返回 `False`，与 httpx 一致
- `NO_PROXY=secure.example` 与 lowercase `no_proxy=*` 并存时，lowercase `*` 生效，helper 返回 `True`

通配符本身没有大小写变体。合法的全量 bypass 表达就是去除空格后的独立列表项 `*`；`*:80`、`.*` 或编码后的 `%2A` 不具有这一语义，不应被当作遗漏。

设置档有值时，上述 wildcard 形式现在均全部直连，与原生 httpx 一致。设置档为空且 `NO_PROXY=*` 时也全部直连。

### F-2 修复与待裁决语义

【结论：机制已修复；产品语义待用户裁决；把握：高】

`TransportOptions.proxy_from_cli` 现在直接决定是否屏蔽低 tier，不再从 `cli_proxy is not None` 重新推导。新增回归在只有 `ALL_PROXY`、没有 `NO_PROXY=*` 的情况下验证了 `--proxy ""` 仍全部直连，因此上一轮发现的环境渗漏已经消失。

以下组合也已确认：非空 CLI proxy 与 `NO_PROXY=*` 并存时全部走 CLI proxy；空 CLI proxy 与 `NO_PROXY=*` 并存时全部直连；设置档为空与 `NO_PROXY=*` 并存时全部直连。

当前「空 CLI 值代表第 1 档显式选择直连」的解释内部自洽，也确实完整屏蔽了环境。但我仍**倾向拒绝空值**，理由是文档描述的是 proxy URL，空字符串不属于列出的任何 URL scheme；原生 `httpx.AsyncClient(proxy="")` 也拒绝它。更实际的失败面是 `--proxy "$UNSET_VARIABLE"`：当前行为会静默改成全直连，而不是指出启动参数没有值。

因此，这不是修订代码中的剩余接线缺陷，而是尚未由用户裁决的产品 fork。若用户希望保留「CLI 可显式关闭代理」的能力，当前行为可以采用，但应写进对外配置契约；若用户优先选择 fail-fast 与原生显式 proxy 行为一致，则应拒绝空值。未裁决前，不应把任一解释写成已经冻结的合同。

### F-3 告警复核

【结论：目标误报已修复，保留的误报与记录一致；未发现漏报；把握：高】

上一轮两个反例现在分别表现为：

1. 设置档为 SOCKS、`ALL_PROXY` 为 HTTP 时，HTTP 与 HTTPS 均走环境 HTTP proxy，且不再输出设置档 SOCKS warning。该误报已修复。
2. `ALL_PROXY` 为 SOCKS，同时 `HTTP_PROXY` 与 `HTTPS_PROXY` 均为 HTTP 时，HTTP／HTTPS 没有流量走 SOCKS，但仍输出 `ALL_PROXY` 的 warning。这个保留误报与代码注释和 `deferred.md` 的记录一致。

正控也成立：设置档为 SOCKS、环境只提供 `HTTPS_PROXY` 时，HTTP 仍回落设置档 SOCKS，warning 正常发出。

没有发现新增漏报。最终 client mounts 与 warning 都由同一个 `_effective_proxies` 映射产生；任何可承载请求的非 `None` SOCKS 值都进入 warning 集合。`None` 只代表 direct exemption，不应告警。带 username 和 password 的设置档及环境 URL 也重新探测过，warning 只包含去凭据后的 origin。

### tier 1 全部改走 mounts

【结论：路由等价，cap 与 keep-alive 接线保持有效；把握：高】

在同时存在 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 和 `NO_PROXY=*` 时，非空 CLI proxy 的 mounts 只有一个 `all://`。HTTP、HTTPS 和 IPv4 三类目的地逐项都走 CLI proxy，与原生 `httpx.AsyncClient(proxy=...)` 完全一致。环境提供的 direct exemption 没有进入 mounts，这正是显式 proxy 应有的行为，不是漏接。

`NO_PROXY=*` 与非空 CLI proxy 并存时，CLI tier 先返回 `{"all://": cli_proxy}`，不会调用环境 bypass 结果覆盖 CLI。因此没有出现新旧 tier 反转。

代理池现在恒位于 mounts 后：`test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive` 的 CLI tier 与 setting tier 两个参数均通过，确认 mounted proxy pool 同时保留 `StreamCappedConnection` wrapper 和 keep-alive socket options；真实 forward proxy socket 的 keep-alive 开启与关闭正反控均通过，确认不是只读到了构造参数。

### 新缺陷攻击结果

【结论：本轮定向范围未发现新的代码缺陷；把握：高】

重点组合的最终结果为：`NO_PROXY=*` ＋非空 `--proxy` 全部走 CLI proxy，与原生显式 proxy 一致；`NO_PROXY=*` ＋空 `--proxy` 全部直连；`NO_PROXY=*` ＋设置档为空全部直连；`proxy_from_cli=True` ＋非空 `cli_proxy` 只生成 CLI 的 `all://`，环境的 scheme proxy 与 direct exemption 均被排除；设置档 SOCKS 被 `ALL_PROXY` 覆盖不再误报；设置档 SOCKS 仍承载未被环境点名的 scheme 时继续告警。

定向测试结果为相关回归 `7 passed`，另加 mounted CLI proxy 的真实 socket keep-alive 正反控 `2 passed`。

### 定向复核裁决

从代码正确性看，F-1、F-2 的环境渗漏机制和 F-3 的目标误报均已修复，结构改动没有造成路由、cap 或 keep-alive 回归。

但 `--proxy ""` 究竟应「显式直连」还是「拒绝空值」仍是尚未由用户裁决的可观察行为。按本项目「Spec 先于可观察行为」的规则，**当前不能无条件合入 `main`**。用户若明确接受「空 CLI 值代表显式直连」，则 `1e4a228` 的技术状态可以合入；若选择拒绝空值，还需先调整该入口及回归。
