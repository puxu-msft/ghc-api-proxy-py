# GHE Device Flow 切片复核（claude, R2）

- 日期：2026-08-28
- 复核者：独立评审 subagent（Opus 5），同一人复核第一轮
- 基线：工作树未提交改动，相对 `74b9dde`
- 上一轮：[260828-review-claude.md](260828-review-claude.md)；处置记录：[260828-review-disposition.md](260828-review-disposition.md)

## 结论

**verdict: needs-fix**

- **本轮新增 blocker: 0**
- **本轮新增 major: 1**（R2-1）
- **本轮新增 minor: 7**（R2-2 … R2-8）
- 上一轮 14 条（4 major / 6 minor / 3 建议 / 1 nit）：**闭合 12，延后 2（登记正确）**，无一条退化。

一句话：**入口这一层真的修好了，四条 major 是同一个修法一起闭合的，`_selected_provider` 没有重造第二个答案。** 本轮的问题降了一档，集中在两处：一处**规范性依据写错了**（结论对、理由假，且反证就在本轮新写的测试里），以及 `logout` 这条对称边只做了「同一套解析」，没有同步 `auth` 刚获得的那些「说出来」的义务。

**唯一需要你现在就处理的是 R2-1**，因为它是一条会被将来的人当依据引用的假陈述。其余七条都是文档措辞与消息内容，不改代码行为也能收。

---

## 复核范围

**看了：** `spec.md`（全文，含修订记录 R2）、`status.md`、`deferred.md`、`260828-review-disposition.md`；`src/app/cli.py`、`.../ghc_client/config.py`、`.../ghc_client/auth/service.py`、`.../ghc_client/device_flow.py`、`.../ghc_client/__init__.py` 的 diff 与最终状态；`tests/unit/test_cli.py` diff；`tests/unit/conftest.py` 的 `XDG_DATA_HOME` 隔离（为核实测试 docstring 的一处承重断言）。

**判据来源（沿用第一轮，本轮新增核实的）：** `src/app/server/composition.py:319-336`（`build_github_token_source` 的三级链构造）、`:469-472`（`build_chain` 的前置校验）、`src/app/config/paths.py:59-70`（`expand_user_path`）、`src/app/config/loading.py:121-166`、`contrib/systemd/ghc-api-proxy.service`（确认发行的 unit 不传 `--config`）。

**没看 / 没做：** 同伴的未提交改动（`docs/.human-controlled/*`、`Dockerfile` 等）一律未读入判断、未修改；`260828-review-gpt.md` 原文我**没有读**——处置记录里对它的转述我按转述采信，不冒充复核它；未重跑 `ruff` / `pyright` / 全量 `pytest`（采信既成事实）；**未做变异**（共享树上有同伴未提交改动，本轮亦未被要求）。

**跑过的命令：** 6 组只读探针（`uv run python`，进程内 `CliRunner`，`authenticate_device` 全部替换为记录函数，不发网络请求）。有一组会写文件，**全部写在 `/tmp/ghe-r2/` 下的一次性目录**，不触碰仓库与 `~/.local/share/ghc-api-proxy/`。

**未修改任何生产代码或测试。** 本轮只新建了这一份报告。

---

## 第一问：上一轮逐条完成度

| 编号 | 级别 | 状态 | 核实方式 |
|---|---|---|---|
| F1 `--provider` 被静默吞掉 | major | **closed** | 入口形态整体重写，`_selected_provider` 无条件读配置，`--provider` 不存在时 `BadParameter`；探针 `auth --config <dangling> --provider absent` → 非 0 且消息含 `absent` |
| F2 绕过配置发现链 | major | **closed**，但依据有误 → **R2-1** | 探针：`GHC_API_PROXY_CONFIG` 指向租户配置时裸 `auth` 已解析到租户 origin 与 token 文件 |
| F3 自造「默认 provider 是谁」 | major | **closed** | `_selected_provider` 直接调 `resolve_default_name`；`test_auth_follows_default_model_provider_rather_than_counting_providers` 钉的正是「不数个数」 |
| F4 Spec 级事实寄存在别处 | major | **closed**（bundled `ghc` 删不掉那条已进 §3.5 第 68 行；help 文案已改成真话）——但新开了两处同类空缺 → **R2-4**、**R2-2** | 逐句比对 Spec §3.5 与测试 docstring；测试里保留的是**带指向的复述**，符合 `one-authority-allows-contextual-restatement` |
| F5「与 `debug models` 逐条一致」为假 | minor | **closed** | 该句已删；会漂的行号引用一并去掉 |
| F6「零个 provider」死分支 | minor | **closed** | 随 F3 的规则删除而消失，新代码无该分支 |
| F7 `_read_config` 作用域声明陈旧 | minor | **closed** | 新 docstring 明写 `debug models` + `auth` + `logout`，并说明为何 `auth`/`logout` 不属于「已发布路径」那条例外 |
| F8 §3.6 措辞过强 | minor | **closed**，且做了「由调用方定」那一半——但反向边缺失 → **R2-2** | §3.6 补了三级链限定；`auth` 侧警告已实测生效（设了 env 有警告、清了 env 没有） |
| F9 GHES 未登记 | minor | **closed** | §4 第三条 + `deferred.md` D-1，两处都写了「不做的理由」与「不做的代价」 |
| F10 `.txt` 不同名 | minor | **closed**（`auth` 侧） | 现场路径随 F2 消失；剩余的文档不一致登记进 D-3.3，属用户亲笔文档，只报告 |
| S1 `GhcClientConfig` 构造点收拢 | 建议 | **延后，登记正确** | D-2 声称的 `composition.py:357/423/491` 我逐行核过，属实；第四处 `:396` 从 `account_type` 构造、不从 `ModelProviderConfig` 取字段，按 D-2 自己的措辞排除它是对的 |
| S2 §4 证据权重拆两半 | 建议 | **closed** | 拆得准确，一手来源那一半与我提供的原文一致，旁证那一半保留了「不得改写成已验证」的约束 |
| S3 新增 `status.md` / `deferred.md` | 建议 | **closed** | 两份都建了；`deferred.md` 开头「只放未闭合项、不留空号」的自我约束写得对 |
| N1 只为 `del` 而收的参数 | nit | **closed** | 该测试已重写，不再收 `tmp_path` |

**退化检查：无。** 上一轮已修好的任何一条，本轮都没有被新改动重新打开。

---

## 第二问：抛开上轮清单，现在这份产物是什么状态

以下八条是**本轮引入或本轮才可见**的，与上一轮清单无关。

### R2-1 · §3.5 用来支撑「不需要用户裁决」的那条依据是假的，反证就在本轮新写的测试里 — **major**

**这是你点名要我重点复核的那一条。结论：你的判断（不需要交用户）是对的，但你写下的依据不成立，必须换掉。**

**判据。** `.claude/rules/00-development-workflow.md`：Spec 是规范性的、要被引用的；一条写进 Spec 正文并被修订记录援引为决策依据的陈述，将来会被当作既定事实使用。第一轮 F5 报的就是同一形状——「一句可核查的断言被核查出是假的，之后这份 Spec 的其它断言也就得逐条重核」。

**位置。**

- `primary_location`: `.dev/docs/ghe-device-flow/spec.md:66`——「因此经 `load_proxy_config` 出来的配置**永远**解析得出一个 provider 名」
- `related_locations`: `spec.md:114`（修订记录 R2 的「依据」栏，把这条判断记为「本人复核」）；`260828-review-disposition.md:32`（同一句的原始表述）；`tests/unit/test_cli.py` 的 `test_auth_refuses_an_open_choice_and_a_dangling_default`

**它为什么是假的（实测）。**

```
providers: ['ghc', 'tenant'] default: ''
resolve_default_name: raises ProviderNotConfigured( '' )
```

`resolve_default_name` 并非「永远」解析得出。更要紧的是：**你本轮新写的测试 `test_auth_refuses_an_open_choice_and_a_dangling_default` 的 `ambiguous.yaml` 分支，走的正是这条你在 Spec 里称之为「永远不会」的路。** Spec 与同一次提交里的测试互相矛盾，而 Spec 是被引用的那一方。

同一段接着写「那条报错路径只有在运营者显式把该键写成空串时才可达」——这句也比事实窄。实测：不改配置文件，只把环境变量置空即可到达：

```
env GHC_API_PROXY_DEFAULT_MODEL_PROVIDER= + 两个 provider -> ProviderNotConfigured
```

（`loading.py:133-143` 对空值不做过滤，`raw` 为空串照样 `_assign`。）

**为什么结论仍然成立——正确的依据在这里。** 我实测了同一份 `ambiguous.yaml` 在服务侧的结果：

```
build_chain: ProviderNotConfigured -> no model provider named '' is configured
```

`build_chain`（`composition.py:472`）在构造任何东西之前就调 `resolve_default_name`。**也就是说：凡是 `auth` 现在会拒绝的那个配置状态，`start` 本来就起不来。** 该状态下不存在「原本能跑的部署」，因此不存在需要用户取舍的退化。

这条依据比你写的那条强，因为它不依赖「这个状态可不可达」——它直接说明**即使可达，那里也没有工作中的部署可退化**。

**处置建议。** 把 §3.5:66 那段的论证换成 `build_chain` 这一条，并顺手让 R2 修订记录的「依据」栏跟着改（那一栏现在替一句假陈述背书）。**这属于修正你自己推导出来的表以匹配实测，按项目规则不需要用户裁决，当场改即可。**

**证据权重：够拿来行动。** 三次直接执行观测，无推断成分。

---

### R2-2 · `logout` 在环境变量遮蔽时照旧宣布「已移除」，§3.6 刚建立的义务没有同步到 §3.7 — **minor**（可争议为 major，见下）

**判据。** Spec §3.7:85 自己立的规矩：「`logout` 那句『Remove locally stored authentication state』就不能在没清掉它的情况下仍报告成功」。以及 §3.6:81 引用的本仓尺度（`cli.py:308-309`）：被接受然后被忽略比被拒绝更糟。

**位置。**

- `primary_location`: `src/app/cli.py:446-450`（`logout` 体，删完直接 `typer.echo("Stored GitHub token removed")`）
- `related_locations`: `spec.md:83-87`（§3.7 只规定了「同一套解析」，没规定同一套告知义务）；`src/app/cli.py:399-405`（`auth` 侧已有的警告，可直接对称照搬）

**失败场景（已实测）。** `GHC_API_PROXY_GITHUB_TOKEN=ghu_from_env` 时：

```
[logout-env-shadow] exit=0 out='Stored GitHub token removed'  token file still there? False
```

文件确实删了，服务照旧拿环境变量里那一枚跑。运营者读到的是「本地存的认证状态已移除」，实际上凭据一枚未少。这与 §3.6 刚刚花一整段消灭的形态同形，只是换到了反向边。

**定级说明。** 我记 **minor**，理由是与我上一轮给 `auth` 侧同一问题（F8）的定级保持一致——**为了显得严格而在复核轮给同类问题升档，本身就是评审失效的一种**。但有一个加重情节，交你裁决：`auth` 只是默默成功，`logout` 是**主动断言完成**（"removed"），而用户在意的恰恰是「我到底登出了没有」。若你按这个权重量，它是 major。

**证据权重：够拿来行动。**

---

### R2-3 · `auth` 现在真的会写 `github_token_file` 了，于是一个相对路径会写到它当时的 cwd，而它不说写到了哪 — **minor**

**这是本切片新开的失效面**：改动之前 `auth` 从不理会 `github_token_file`（永远写默认路径），所以这个字段只被**读**过；读一个不存在的路径是无害的（`FileTokenProvider.get_token` 吞 `OSError` 返回 `None`）。写不是。

**位置。**

- `primary_location`: `src/app/cli.py:394`（`token_path = github_token_path(proxy_config, provider_name)`，结果直接交给 `FileTokenProvider.save_token`）
- `related_locations`: `src/app/config/paths.py:59-70`（`expand_user_path` 只对 `$XDG_DATA_HOME/ghc-api-proxy` 这一个确切前缀兜底，其余交给 `os.path.expandvars`，未定义的变量原样留在路径里）；`src/app/model_provider/ghc_client/auth/providers.py:111-114`（`save_token` 会 `mkdir(parents=True)`，不会因为路径古怪而失败）

**失败场景（已实测）。** 配置写 `github_token_file: "tokens/github_token"`，在 `/tmp/ghe-r2/cwdtest` 下执行：

```
github_token_path -> tokens/github_token | absolute? False
written to: /tmp/ghe-r2/cwdtest/tokens/github_token
```

即：**token 写进了「运营者当时恰好在哪个目录」**，并顺手创建了目录树。服务在 systemd 下 cwd 不同，按同一相对路径找不到它——登录报告成功，服务无凭据。同样的形状也适用于 `"$SOME_UNSET_VAR/token"`。

**为什么现在才暴露：** 这条路径此前不可达。它不是 `expand_user_path` 的缺陷（那个函数的 docstring 明说它只处理 spec 写法那一种拼法），是**新增了一个写入方**之后才产生的组合。

**处置建议（两条都很便宜，选一或都做）：** ①`auth` 成功后把实际写入的绝对路径 echo 出来——这一条顺带解决 R2-7，且与 `start` 打印生效配置的习惯一致；②在 `_selected_provider` 里对非绝对路径给一条警告或拒绝。**要不要把「`github_token_file` 必须是绝对路径」定成规范，是 Spec 级取舍，归你定，不归我。**

**证据权重：够拿来行动。** 直接执行观测；写入发生在 `/tmp` 的一次性目录内。

---

### R2-4 · 为什么不检查 `CLITokenProvider` 那一级，这个判据的真正理由没有落在任何地方 — **minor**

**这是你问题 3 的答案：判据选对了，理由写错了，而且理由没写下来。**

**你的判据是对的。** 实测依据：`build_github_token_source`（`composition.py:328-336`）把第一级硬编码成 `CLITokenProvider(None)`——**它永远拿不到 token**；而 `--github-token` 早已在失效选项表里（`cli.py:72`：「the spec takes `model_providers.<name>.github_token_file`, not a token」）。所以 CLI 那一级**在生产里恒为不可用**，不检查它不会漏。三级链里唯一能遮蔽文件的只有 env，`EnvTokenProvider().is_available()` 正是它。**没有漏。**

**但你在处置记录里给的理由不是这条。** 你写的是「`noninteractive_token_available` 会把 CLI 与 file 两级也算进去，而 file 正是刚写的那个」——这解释了为什么不用那个 helper，**没有解释为什么可以不查 CLI**。这两个是不同的问题，而后者才是判据成不成立的那一半。

**位置。** `spec.md:79`（§3.6 把链写成 `CLITokenProvider` → `EnvTokenProvider` → `FileTokenProvider`，紧接着只要求检查「环境变量那一级」，中间那步「为什么第一级可以跳过」是空的）；`src/app/cli.py:399-405`（代码注释同样只说文件是第三级，没说第一级为何不查）。

**失败场景。** 不是现在的错误答案，是**将来的静默不完整**：若哪天 `--github-token` 被启用、或 `CLITokenProvider` 被喂上真值，这个检查就少了一级，而现场没有任何一句话提醒改的人去补。这正是本仓「守卫被留在了 legacy 链路上」那条教训的镜像——**一个守卫的完整性依赖于另一处的硬编码，而那个依赖没有被写下来。**

**处置建议。** §3.6 加一句：只检查 env，因为 `build_github_token_source` 把 CLI 级硬编码为 `None`、`--github-token` 在失效选项表里，故该级在生产中恒不可用；一旦该前提改变，此检查须同步扩展。

**证据权重：够拿来行动。**

---

### R2-5 · §3.3 与 `config.py` 的 docstring 都说推导失败「影响 `auth` / `logout` 两条命令」，实测 `logout` 不受影响 — **minor**

**位置。**

- `primary_location`: `.dev/docs/ghe-device-flow/spec.md:47`——「这只影响 `auth` / `logout` 两条命令」
- `related_locations`: `src/app/model_provider/ghc_client/config.py`，`resolve_github_web_base_url` docstring 第四段——「that only reaches `auth` and `logout`」

**失败场景（已实测）。** 同一份 `auth_base_url: "http://127.0.0.1:8080"` 的配置：

```
[logout-local] exit=0 out='Stored GitHub token removed'   token file still there? False
[auth-local]   exit=1 out="error: cannot derive the Device Flow OAuth origin ..."
```

`logout` 根本不调 `github_web_base_url`（它只要 `github_token_path`），因此完全不受推导失败影响。两处陈述都把代价说大了一倍。这是 §3.7 新增之后没有回头修订 §3.3 造成的，方向无害但同样是可核查而为假的断言——与第一轮 F5 同类。

**证据权重：够拿来行动。**

---

### R2-6 · §3.5「确实改变的行为有两处」漏了第三处，而只有它能把原本能用的部署弄坏 — **minor**

**位置。** `.dev/docs/ghe-device-flow/spec.md:70-73`（那份两条的清单）。

**失败场景（已实测）。** 服务以 `start --config /path/served.yaml` 启动（该文件不设 `github_token_file`，故服务读默认路径），而默认位置另有一份配置设了 `github_token_file`：

```
service reads token file: None (default path)
bare `auth` -> calls: [('/tmp/ghe-r2/discovered-token', 'https://github.com')]
```

改动前裸 `auth` 写默认路径、服务读默认路径，**能用**；改动后裸 `auth` 按发现链找到的那份配置写，服务仍读默认路径，**断开**。清单里的两条（坏配置 exit 1、按配置写 token 文件）都不覆盖它。

**范围限定，我不把它说大。** 发行的 systemd unit（`contrib/systemd/ghc-api-proxy.service`）**不传 `--config`**，走的就是发现链，所以官方部署路径上 `start` 与 `auth` 天然一致；要触发得运营者自己改 unit 加 `--config` 且默认位置另有一份配置。而且 `debug models` 早就有同样的歧义，所以这不是本次引入的不一致，是本次让 `auth` 也进入了这个既有的歧义面。

**因此我的建议只是补一句 Spec，不是改代码**：清单加第三条，说明 `start --config` 与发现链可能指向不同文件，且这是与 `debug models` 一致的既有形态。

**证据权重：够拿来行动**（行为为实测；「难以触发」的判断基于发行 unit 的实际内容，也是一手）。

---

### R2-7 · `logout` 只清选中 provider 的那一个文件，消息却是无条件的完成宣告 — **minor**

**位置。** `src/app/cli.py:446-450`；`spec.md:83-87`（§3.7 未定义多 provider 与迁移情形）。

**失败场景。** 两种，都不需要构造异常配置：

1. 配置有两个 provider、各自 `github_token_file` 不同。`logout` 只清默认那个，输出仍是「Stored GitHub token removed」，另一枚原封不动留在盘上。
2. 运营者在本次改动**之前**登录过（token 在默认路径），之后往配置里加了 `github_token_file`。现在 `logout` 清的是新文件（不存在，`unlink(missing_ok=True)` 静默通过），旧的那枚仍在默认路径——依然报告「removed」。

命令的 docstring 说的是「Remove locally stored authentication state」（全部），做的是「清掉选中 provider 的那一个文件」。二者的差距在输出里读不出来。

**处置建议。** 与 R2-3 同一条补救：把实际操作的路径印出来（`Stored GitHub token removed: <path>`）。这一条同时让 R2-3、R2-7 变得可观测，且不改变任何行为。要不要让 `logout` 清「所有 provider 的文件」是行为取舍，归你定。

**证据权重：情形 1 与 2 由 `logout` 的代码路径与 `clear_token` 的 `missing_ok=True` 直接得出，我实测过单 provider 的删除与消息，未逐一构造这两种配置。够拿来行动，但比上面几条弱一档。**

---

### R2-8 · `status.md`「走过的弯路」诚实，但漏了那一轮最贵的一半：测试把错误契约钉成了断言 — **minor**

**这是你问题 5 的答案：写对了，不是自我开脱，但停早了一步。**

先说它对在哪，这部分我认可，且认为值得留：它没有把锅推给「测试不够多」；它承认两次控制变异**确实**通过、并说清了为什么通过（「变异钉的是『origin 有没有传下去』，而那一层确实是对的」）；它给出的教训——「问的不是它对不对，而是用户实际会敲的那条命令走不走到它」——是准确且可迁移的。

**漏掉的一半。** 第一版的 CLI 测试不只是「没覆盖入口」，它**主动把错误的契约写成了断言**：旧的 `test_auth_names_the_providers_when_several_are_configured` 断言 `auth --config <两个 provider>` **必须**失败（`ambiguous.exit_code != 0`）。也就是说，那条自造的「恰好一个就用它」规则不是缺乏测试保护，而是**有一条测试在保护它**。任何后来者想把 provider 选择改回 `resolve_default_name`，都会先撞红这条测试，然后很可能认为「Spec 就是这么定的」而退回去。

这一半比现有的教训更难被下次避免，因为它长得完全像「测试覆盖良好」。本仓的记忆里已经有它的近亲——「变异结果证明了什么、没证明什么：打红只证明它打到的那一层」——现有文字引用了这条的一半（变异的盲区），漏了另一半（**断言本身可能钉错了对象；一条有分辨力的测试仍然可以在为错误契约站岗**）。

**处置建议。** 那一节加两句：第一版不是缺测试，是有一条测试在为错误规则站岗；因此「测试有分辨力」与「测试钉对了东西」是两个独立的问题，控制变异只能回答前一个。

**证据权重：够拿来行动。** 旧断言的原文出自我第一轮读到的同一份 diff。

---

## 逐项回答你的五个问题

**1 · F1/F2/F3/F6 是否真的一起闭合，`_selected_provider` 有没有重造第二个答案。**
一起闭合了，**没有重造**。`_selected_provider` 里关于「默认 provider 是谁」的唯一答案来自 `resolve_default_name`；它自己只做三件不重叠的事：`--provider` 命名校验（与 `debug models` 同文案）、把 `ProviderNotConfigured("")` 翻成人话（`debug models` 已有先例）、以及 dangling default 的兜底（这一条是**新增校验**而非新答案——`resolve_default_name` 返回的名字可能不在 `model_providers` 里，见下）。F6 那条死分支随规则删除而消失，新代码里没有等价物。

**2 · F4 那半清干净了没有。**
清干净了：bundled `ghc` 删不掉、以及它如何决定运营者该怎么写配置，现在在 `spec.md:68` 正文；测试 docstring 里留下的是带指向的复述，不是唯一来源；`--provider` 的 help 从「Requires --config.」（假）改成「Act on this provider instead of the config's default.」（真）。`status.md` / `deferred.md` 里**没有**规范性内容越位——D-1 的规范半句（不支持 GHES）在 Spec §4，D-3.3 明确指回 §3.5，`status.md` 开头就写了「冲突时以 Spec 为准」。
**但本轮新开了两处同类空缺**：R2-4（CLI 级为何不查，哪儿都没写）与 R2-2（`logout` 的告知义务，§3.7 未定义）。

**3 · 环境变量遮蔽的判据选得对不对，有没有漏 `CLITokenProvider`。**
**判据对，没有漏。** 但成立的理由不是你写的那条——见 R2-4：真正的理由是 `build_github_token_source` 把第一级硬编码成 `CLITokenProvider(None)`，且 `--github-token` 在失效选项表里，所以 CLI 级在生产中恒不可用。这条依赖需要写进 §3.6，否则将来启用 `--github-token` 时这个守卫会静默变得不完整。

**4 · 新入口有没有别的静默失效面。**
你自己抓到的 dangling default 我复核了：`build_chain` 确实拒它、`auth`/`logout` 确实不走 `build_chain`，所以那条兜底必须自带，代码注释和测试都说对了。**另有三条你没提到**：R2-3（相对/未展开的 `github_token_file` 写到 cwd，且不报告写到哪——这是本切片新开的写入面）、R2-6（`start --config` 与发现链指向不同文件时裸 `auth` 写错文件）、R2-7（`logout` 只清一个文件却宣告全部完成）。
**`logout` 各分支实测结果**：坏配置 → exit 1 并打印 pydantic 消息；provider 有歧义 → exit 1 并要求 `--provider`；dangling default → exit 1 并同时列出坏名字与已配置的名字；推不出 origin 的本地 host → **exit 0，正常删除**（故 R2-5 那两处陈述有误）；env 遮蔽 → exit 0 且**无警告**（R2-2）。

**5 · `status.md` 的教训写对了没有。**
写对了，不是自我开脱——它没把问题推给「测试不够」，还主动说清了自己的变异为何给了假安心。但停早一步：漏了「第一版有一条测试在为错误规则站岗」这一半，而那一半更难被下次避免。见 R2-8。

---

## 我考虑过但否决的路线

1. **报「`login_command` 改名会破坏引用」** —— 否决。`@app.command("login", ...)` 保留了对外命令名，全仓 grep 只有 `tests/unit/test_cli.py:55/111` 用字符串 `"login"` 调用，无人按 Python 名引用。改名是为了避开 `_authenticate` 里那个内层 `async def login`，是对的。
2. **报「`_authenticate` 里内层函数叫 `login`，与命令同名，易混」** —— 否决。作用域不重叠，且内层名字准确描述了它做的事。属纯口味，不值一条。
3. **报「`GITHUB_WEB_BASE_URL` 现在只被 `auth/service.py` 与 `device_flow.py` 用，cli.py 不再导入，是残留」** —— 否决。核过：cli.py 的新版本确实不再导入它，两处默认值用法都正当，无死导入。
4. **报「`urlsplit` 的 `try` 只包住 `hostname`/`port` 两次属性访问，`parts.path` 等在 guard 外读取，可能漏抛」** —— 否决。查过 CPython：`SplitResult` 的 `scheme`/`path`/`query`/`fragment` 是元组字段，取值不做解析；只有 `hostname`、`port`、`username`、`password` 走 `_hostinfo`/`_userinfo` 的惰性解析。`username`/`password` 与 `hostname` 走同一段代码，坏 IPv6 会在 `hostname` 那次就抛出并被接住。**但我要说明证据边界：我没有为「`username` 单独能抛而 `hostname` 不抛」构造反例，这是读实现得出的判断，权重是「够支撑不报，不够支撑写进 Spec 当保证」。**
5. **报「多 label tenant 放行有风险」** —— 否决，且认为放行的论证写得好。`config.py` docstring 那句「refusing a shape we cannot show to be illegal would dress『we did not find it documented』up as『the server rejects it』」正是 `no-imagined-security-theater` 的正确应用。我第一轮没想到这一层，gpt 那份提到了，处置也对。
6. **报「空 label 那条判据 `any(label == "" ...)` 可以更简洁地用 `""in split`」** —— 否决。等价，且现在的写法自带一句解释注释。纯口味。
7. **重做变异以复核新测试的分辨力** —— 否决并主动放弃，同第一轮：共享主树有同伴未提交改动。你已给出两次新变异（发现链退回打红 4 条、空 label 放行打红 2 条），钉的正是本轮真正变了的两层，按**采信既成事实**处理。我另用只读探针独立复现了 5 类 `logout` 分支与 2 类 `auth` 分支，与那些变异不同源。
8. **报「`logout` 在坏配置时 exit 1，等于配置坏了就登不出去」** —— 否决。核过：配置坏了服务也起不来（`_read_config` 与 `start` 共用同一个 `load_proxy_config`），此时没有「正在运行且需要登出」的部署；且运营者删文件的路总在。属于与 `auth` 一致的响亮失败，不是缺陷。
9. **复核 `260828-review-gpt.md` 的三条发现是否处置得当** —— **主动不做，并如实声明**。我没有读那份原文，只按处置记录的转述采信。要独立复核它需要先读原件，那会让我对同一份产物做两种角色，且不在本轮范围内。**若你需要 gpt 那三条的独立复核，那是一次单独的派发。**
10. **报「§4 的 client_id 段落变了（PR #34 用的是另一个 id）」为新问题** —— 否决。这是本轮新增的一手事实，且方向正确：它让 §3.4 从「PR 也没改 id，所以照做」弱化成「PR 用的是别的 id，因此既不能证明也不能否证我们这个」。**这是把依据改准了，属改进而非缺陷。**

---

## 建议处置顺序

1. **R2-1 先改**，它是唯一一条会被将来引用的假陈述，且改法是现成的（换成 `build_chain` 那条论证）。修订记录 R2 的「依据」栏一并更新。
2. R2-4、R2-5、R2-6 是同一批 Spec 措辞订正，可一次改完。
3. R2-2、R2-3、R2-7 若采纳，最小改动是让 `auth` / `logout` 各多印一行（写到哪 / 删了哪，以及 env 遮蔽时的提醒），行为不变、可观测面补齐。**是否把「`github_token_file` 必须是绝对路径」定成规范，是 Spec 级取舍，归你。**
4. R2-8 是 `status.md` 加两句。
