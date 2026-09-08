# 事实核查：`260822-beta-flag-strip-implementation.md` 与 `hosted-web-search/status.md` §4.5

- 日期：2026-08-22
- 核查对象：
  - 文档一 `.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`（新建，未提交）
  - 文档二 `.dev/docs/hosted-web-search/status.md` §4.5 的新增段（`.dev` 独立仓工作树改动）
- 核查者身份：只读。除本文件外未修改任何文件，未运行测试，未改动 `docs/.human-controlled/`。
- 仓库状态：主仓 HEAD `f191e4d`（`git log --oneline -6`），实现改动**尚未提交**（`src/app/config/schema.py`、`server/handler.py`、`pipeline/request_headers.py`、`observability/metrics.py` 等均为工作树 `M`）。共享树，同伴有并行改动。

## 裁定总表

| # | 声称 | 裁定 |
|---|---|---|
| 1 | `beta_strip_headers` 从未出现在 `docs/.human-controlled/config.example.yaml` | **不属实** |
| 2 | 改名前 `beta_strip_headers` 与 `strip_attribution_header` 都零消费者 | 属实 |
| 3 | `settings.py` 的 `beta_strip_headers` 是 `--fd`(systemd) 路径的旧配置面、与 `ProxyConfig` 两套 | **前半不属实**，后半属实 |
| 4 | `build_anthropic_beta_headers` 的 `strip` 形参没有任何调用方传过 | **作为绝对陈述不属实**（生产调用方成立，单测传了） |
| 5 | legacy = `app.routes`/`app_factory`/`AnthropicClient`；新链路 = `pipeline_app`；`test_anthropic_responses_route.py` 走 legacy | 属实 |
| 6 | `streamReplay` 已从 `config.example.yaml` 撤下 | 属实 |
| 7 | 文档一 §1 表格三处引文与出处 | 7b、7c 属实；**7a 引文内容属实但出处标错** |
| 8 | 文档一全部相对路径链接可解析 | 属实 |
| 9 | 两条腿都过 `shape_request`，都从 `direct_driver/base.py::_send` 发 `client_headers` | 属实 |
| 10 | §6 所列均为时点记录（report/tmp）而非活文档 | 属实 |

---

## 1. 「`beta_strip_headers` 从未出现在 `config.example.yaml` 里」——**不属实**

这是本次核查最重的一条，因为文档一 §2.1 把整个「改名而非新增」的论证建立在它上面。

事实：**2026-08-20 的 `docs/.human-controlled/config.example.yaml` 里写的就是 `beta_strip_headers`**，而且带着同样那四个 flag。

```
$ git log --all --oneline -S 'beta_strip_headers' -- docs/.human-controlled/config.example.yaml
53fec22 docs: settle what forensic recording is for, and what it costs

$ git show 53fec22:docs/.human-controlled/config.example.yaml | rg -n 'beta_strip_headers|streamReplay'
337:    streamReplay:
486:  beta_strip_headers:
```

`53fec22`（2026-08-20 14:02）中该文件 455-493 行是完整的 `hook_strip_anthropic_request_headers` 节：`strip_attribution_header: true`（482 行）、`beta_strip_headers:`（486 行）、其下 `claude-sonnet-4.6` 的四个 flag 与 `# 400 invalid beta flag` 注释。这正是 schema 里 `beta_strip_headers` 名字的来源——它不是「只存在于 schema 的名字」，它当初与用户亲笔文件是**一致**的。

两条独立旁证：

- `.dev/docs/hooks-subscription-migration/reports/260820-external-rewrite-surface.md:36` 说 `config.example.yaml:455-490` 那一节是用户亲笔写的完整配置——行号与 `53fec22` 的 blob 精确吻合；同报告 233-234 行的表格把 `beta_strip_headers` 记为「`{}`（example.yaml 里有实测内容）」。
- `.dev/docs/sync-refs/sxwxs-ghc-api/260821-round-disposition.md:97` 记录 2026-08-21 时文件里已改成 `strip_anthropic_beta_flags`。

所以真实时间线是：用户在 2026-08-20 之后、2026-08-21 之前把这个键**从 `beta_strip_headers` 改名为 `strip_anthropic_beta_flags`**（同一轮里还删掉了 `strip_attribution_header` 与整段黑/白名单注释块——索引里 08-22 08:26 的版本已无 `strip_attribution_header`，`git show :docs/.human-controlled/config.example.yaml | rg strip_attribution_header` 无命中）。

补充说明为什么 `git log HEAD` 看不到：`docs/.human-controlled/config.example.yaml` **不在 HEAD 里**（`git cat-file -e HEAD:...` 报 "exists on disk, but not in 'HEAD'"），当前是 index 中的 `AM` 状态；唯一收录过它的提交 `53fec22` 只存在于分支 `a/2026-08-20-split-53fec22`，不是 HEAD 的祖先。用 `git log --all` 才看得见。**只查工作树或只查 HEAD 都会得出「从未出现」这个错误结论**——这与项目记忆 `grep-the-commit-not-the-worktree` 是同一形状的坑。

### 正确表述（建议替换文档一 §2.1 第二段）

> 这是改名而非新增：`beta_strip_headers` 这个拼法**曾经**与用户亲笔的 `config.example.yaml` 一致（`53fec22:docs/.human-controlled/config.example.yaml:486`，2026-08-20），用户随后在 2026-08-21 之前把该键改名为 `strip_anthropic_beta_flags`（`sync-refs/sxwxs-ghc-api/260821-round-disposition.md:97` 记录了改名后的状态）。schema 这次是**跟上用户的改名**，不是发明新名字。由于该键当前在用户亲笔文件里已是新拼法、且旧拼法零消费者，改名不会让任何在用的配置失效。

顺带一条同源提醒（不在你列的清单里，但与 §2.1 直接相关）：用户在同一轮编辑里把 `strip_attribution_header` **整条从 example config 里删掉了**，`message-format-reshape.md:31` 也写着「现在我认为这是应该常驻的」。文档一 §2.1 用「运维手上可能写了 `strip_attribution_header: false`」来论证保留该 schema 字段——这个论证仍然可能成立（存量运维配置文件不等于 example config），但文档没有提到用户已把它撤下这一事实，读者会以为它还在权威示例里。建议至少补一句现状。

## 2. 「两个字段改名前都零消费者」——属实

在 HEAD（改名前）与基线 `ec8b2a5` 上分别跑 `git grep`：

```
$ git grep -n 'beta_strip_headers' HEAD -- src tests
HEAD:src/app/config/schema.py:313:    beta_strip_headers: dict[str, list[str]] = Field(
HEAD:src/app/config/settings.py:81:    beta_strip_headers: dict[str, list[str]] = Field(default_factory=dict)

$ git grep -n 'strip_attribution_header' HEAD -- src tests
HEAD:src/app/config/schema.py:312:    strip_attribution_header: bool = True
HEAD:src/app/pipeline/anthropic_request_hook.py:59:    ...（docstring，明写 "has never had a consumer"）
```

`ec8b2a5` 上结果完全相同。两处命中都是定义本身（`schema.py` 与另一套 `settings.py`），第三处是 docstring 而非读取点。

另外查了间接消费的可能：`git grep 'StripRequestHeadersHook\|hook_strip_anthropic_request_headers' HEAD -- src tests` 只命中 `schema.py:311`（类定义）与 `schema.py:405-406`（挂到 `ProxyConfig` 的字段），没有任何遍历/`model_dump` 式的间接读取。零消费者成立。

## 3. 「`settings.py` 的那份是 `--fd`(systemd) 路径的旧配置面」——前半不属实

**后半属实**：`AppSettings`（`src/app/config/settings.py:157`）与 `ProxyConfig`（`src/app/config/schema.py`）确实是两套独立 schema，各有各的 loader，`loading.py:1-8` 与 `loader.py:1-6` 的 docstring 互相点名说「一个字母之差、不可互换」。`AppSettings.beta_strip_headers` 零消费者也属实（见 §2）。

**前半不属实**：`--fd` 路径今天走的是 `ProxyConfig` 和新链路，不是 `AppSettings`。

```
src/app/cli.py:269-289
    if fd is not None:
        proxy_config, _ = _load_spec_config(...)      # -> ProxyConfig（cli.py:81-94）
        run(partial(serve_inherited, proxy_config, fd, proxy_from_cli=proxy is not None))

src/app/cli.py:128-140
async def serve_inherited(config: ProxyConfig, fd: int, ...) -> None:
        ... uvicorn.Config(create_pipeline_app(chain), fd=fd, ...)
```

即 `--fd` → `_load_spec_config` → `ProxyConfig` → `create_pipeline_app`（**新链路**）。`load_settings` 在 `src/` 下**没有任何调用方**（`rg -n 'load_settings' src tests` 只命中 `config/loader.py:88` 定义、`config/__init__.py:1,4` 再导出，其余全在 `tests/`）。

文档一那句话的来源是 `src/app/config/loader.py:1` 的 docstring「now serves only the `--fd` (systemd) path」——**该 docstring 已经过时**，`tests/systemd/test_systemd_units.py:191-193` 自己就写着：「It used to be asserted against `load_settings()` and the two `GHC_*__*_PATH` keys, which belong to the chain `--fd` no longer runs.」

### 正确表述（建议替换文档一 §2.1 第四段）

> `src/app/config/settings.py:81` 的 legacy `AppSettings.beta_strip_headers` **未动**。`AppSettings` 是 legacy 链路（`app.routes` / `AnthropicClient` / `deps.py`）的旧配置面，与 `ProxyConfig` 是两套互不相通的 schema，同样零消费者，本切片不碰它。（注意：`config/loader.py:1` 的 docstring 说它「只服务 `--fd` 路径」已经过时——`cli.py:269-288` 的 `--fd` 现在走 `_load_spec_config` → `ProxyConfig` → `create_pipeline_app`；`load_settings` 在 `src/` 下已无调用方。这处 docstring 值得单独修，但不属本切片。）

## 4. 「`strip` 形参没有任何调用方传过它」——作为绝对陈述不属实

- 唯一的生产调用方 `src/app/anthropic/request_preparation.py:57-61` 只传了 `tool_search=`，**没传 `strip=`**（`rg -n 'strip' src/app/anthropic/request_preparation.py` 无命中）。
- 但 `tests/unit/anthropic/test_feature_negotiation.py:55` 传了：`strip={"context-management-2025-06-27"},`，该测试断言被点名的 flag 不出现在结果头里。

所以这个形参**有测试覆盖**，不是完全无人使用的死参数。文档一 §4 用这句话支撑「该形参保持原样」的结论仍然成立，但陈述本身需要限定。

### 正确表述

> `app/anthropic/features.py:50-70::build_anthropic_beta_headers` 早就有 `strip: Iterable[str]` 形参，但**唯一的生产调用方** `anthropic/request_preparation.py:58` 从不传它（只有单测 `tests/unit/anthropic/test_feature_negotiation.py:55` 传）。那条链路不是主产品路径，本切片不扩到那里。

## 5. 链路归属——属实

- `src/app/server/app_factory.py:24-35,166-176` 装配 `app.routes` 下的全部 router（`anthropic`、`approval`、`azure`、`gemini`、`management`、`history`、`metrics`、`openai`、`responses_ws`、`health`）。
- `src/app/server/pipeline_app.py:1-4` docstring：「Separate from `app_factory`, which still serves the existing implementation. Mounting both would give one path two owners.」`pipeline_app` 不引用 `app.routes`、`AnthropicClient`、`app_factory`。
- `AnthropicClient`（`src/app/anthropic/client.py`）由 `app/routes/anthropic.py` 与 `deps.py` 使用；`pipeline.executor` 的调用方只有 `routes/anthropic.py` 与 `anthropic/client.py`（`rg -n 'pipeline\.executor' src`），`pipeline_app` 不用它。
- `tests/int/test_anthropic_responses_route.py:11-12,26,301,314` 导入 `AnthropicClient`、`AppSettings`、`from app.server.app_factory import create_app`，并在 314 行 `app = create_app(settings)`——**确为 legacy**。

## 6. 「`streamReplay` 已从 `config.example.yaml` 撤下」——属实

当前工作树 `docs/.human-controlled/config.example.yaml:329-338` 的 `upstream_request_retry.strategies` 只剩 `githubTokenExpired` / `network` / `serverError`，无 `streamReplay`（`rg -n 'streamReplay' docs/.human-controlled/config.example.yaml` 无命中）。文件 mtime `2026-08-22 12:44:32`。

对照：index 中的版本（08-22 08:26 那次）第 336 行仍有 `streamReplay:`，`53fec22` 版本第 337 行也有。所以「撤下」发生在 08-22 08:26 与 12:44 之间，方向与 status.md 的描述一致。

## 7. 文档一 §1 表格三处引文

**7a `260820-external-rewrite-surface.md` —— 引文内容属实，出处标错。**

文档一写的出处是「§「`hook_strip_anthropic_request_headers` 的实现缺席」」。该标题确实存在，但它是 **§6「需要用户裁决的点」下的第 4 条列表项**（第 404 行），而文档一引用的那句话（「零消费者……`rg` 只命中 schema 定义本身与 legacy `config/settings.py`」）在**第 36 行，属于 §1.1「入站头过滤」**（§1.1 标题在 26 行，§1.2 在 38 行）。两处内容互相印证、都属实，但引文并不在被点名的那一节里。另有 §3.3 的表格（233-234 行）第三次记录了同一事实。

两处小偏差：原文写的是 `legacy config/settings.py:83`（文档一略去了行号，现值为 81）；原文同时点名了 `config/schema.py:217-221,312`。

建议出处改为：`260820-external-rewrite-surface.md:36`（§1.1），或同时点名 §3.3 表格与 §6 第 4 条。

**7b `sync-refs/sxwxs-ghc-api/260821-round-disposition.md:97` —— 属实。**行号精确。原文：

> 5. **`config.example.yaml` 与 schema 的键名不一致**：文件里是 `strip_anthropic_beta_flags`，schema 里是 `beta_strip_headers`，导致 `test_authoritative_example_config_parses` 一直红。这个失败**先于本轮工作存在**，且 `config/schema.py` 正被并行会话修改，我没有碰。

文档一转述为「记的是『键名不一致』……当作既存红绕开了」，与原文吻合。它位于 §5「待用户裁决」。

**7c `hosted-web-search/status.md` §4.5 改写前原文 —— 属实。**`rg -n '^#{2,4} '` 确认 §4.5 标题为「与本切片无关但同期发现」（第 65 行）；`git diff` 显示的上下文原句包含「**先于本切片**」与「需要用户确认要不要实现」，与文档一转述一致。

## 8. 相对路径链接——属实

文档一位于 `.dev/docs/hooks-subscription-migration/reports/`，`../../` 指向 `.dev/docs/`。逐条解析：

| 链接 | 解析结果 |
|---|---|
| `260820-external-rewrite-surface.md`（同目录） | 存在 |
| `../../sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | 存在 |
| `../../hosted-web-search/status.md` | 存在 |
| `../../upstream/retry-and-continuation/reports/260822-review-*.md` | 通配命中 5 份（`260822-review-d-group.md`、`-d-group-disposition.md`、`-e-group.md`、`-e-group-disposition.md`、`-unreviewed-span.md`），另有目录 `260822-review-d-group-probes` |
| `../../tmp/260822-h2-streamreset-cancel-diagnosis.md` | 存在 |

文档二新增段里的 `../hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`（从 `.dev/docs/hosted-web-search/` 出发）也解析成功。

文档一中的非链接式文件名引用 `message-format-sanitize.md`（§2.1 括注）**指向一个不存在的文件**：`docs/.human-controlled/` 下只有 `message-format-reshape.md`，`git log --all -- 'docs/.human-controlled/message-format-sanitize.md'` 无任何提交。这是个存量问题——`src/app/pipeline/anthropic_request_hook.py:28,59,61,91`、`src/app/server/pipeline_app.py:422`、两处测试 docstring 都还在引这个旧名——但文档一复制了它。对应裁定应在 `message-format-reshape.md:31`（「曾经用 `hook_strip_anthropic_request_headers.strip_attribution_header` 配置控制生效，现在我认为这是应该常驻的」）。建议文档一改引 `message-format-reshape.md:31`，并把代码里那批陈旧引用记为一条独立待办。

## 9. 「两条腿都过 `shape_request`，都从 `_send` 发 `client_headers`」——属实

- `src/app/server/handler.py:152-153`：`handle()` 第一件事就是 `shape_request(chain, context, on_routed)`，**在 `route.translation_required` 判断之前**，所以直连腿与翻译腿都过。`handle_count_tokens`（`handler.py:231` 起）同样以 `shape_request` 开头。
- 剥离点在 `handler.py:116-124`，位于 `apply_route`（111 行）之后、`fix_anthropic_request`（127 行）之前，与后者共用 `inbound_format is WireFormat.ANTHROPIC_MESSAGES` 守卫——与文档一 §2.3 描述一致。
- `rg -n 'client_headers' src` 的读取点只有一处：`src/app/pipeline/direct_driver/base.py:244` 的 `extra_headers=context.client_headers or None`，在 `DirectDriver._send`（228 行）内。
- `handler.py:171-178` 用 `DRIVERS[route.endpoint]` 选驱动；`direct_driver/__init__.py:47-52` 的四个值 `AnthropicMessagesDriver` / `OpenAIChatCompletionsDriver` / `OpenAIResponsesDriver` / `OpenAIEmbeddingsDriver` 全部 `class X(DirectDriver)` 且**都没有覆写 `_send`**（`rg -n '^class |def _send' src/app/pipeline/direct_driver/*.py`）。直连腿走 `AnthropicMessagesDriver`、翻译腿走 `OpenAIResponsesDriver`，二者共用同一个 `_send`。

## 10. §6 所列均为时点记录——属实

| 路径 | 存在 | 性质 |
|---|---|---|
| `hooks-subscription-migration/reports/260820-external-rewrite-surface.md` | ✓ | `reports/` 下 |
| `sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | ✓ | `sync-refs/sxwxs-ghc-api/` 是一个扁平的日期前缀报告目录，13 份文件全部 `260821-` 前缀，无活文档（无 `README.md`/`status.md`/`spec.md`） |
| `upstream/retry-and-continuation/reports/260822-review-*.md` | ✓ 5 份 | `reports/` 下；该 topic 的活文档 `README.md`/`status.md`/`decisions.md`/`deferred.md` 在 topic 根，未被点名 |
| `tmp/260822-h2-streamreset-cancel-diagnosis.md` | ✓ | `docs/tmp/` 下 |

「它们对当时的描述都是准确的」这一句：我核到的三条（外部改写面报告 36 行、round-disposition 97 行、status.md §4.5 原文）在各自时点都准确，第四、五条（retry-and-continuation 的 review 报告、h2 诊断）未逐条核，属本次未覆盖范围。

---

## 附：顺手核过的其他事实（不在委托清单内，均属实）

- `rg -n 'MUTATION-PROBE' src tests` 无命中（exit 1），变异探针确已清除；`handler.py:121` 现为 `denied_by_model=chain.config.hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`，接线完好。
- §3.1「8 条单元测试」：`tests/unit/pipeline/test_client_request_headers.py` 共 17 个 `test_`，其中 77-172 行的 8 个是本切片新增的 `strip_denied_beta_flags` 测试，与文档描述的 8 项覆盖点一一对应。
- §3.2 三条接线测试均存在：`tests/int/test_pipeline_app.py:175, 194, 216`。
- `src/app/config/settings.py:81` 行号准确。

## 未能核实 / 明确不做的

- **未运行任何测试**（只读核查 + 共享树上同伴在改 `tests/int/test_pipeline_app.py`）。§3.3 变异表里「哪条红哪条绿」的结论**未复现**，只核到变异已恢复、探针无残留。
- 文档一 §5「四个 flag 当前是否仍会 400」本身就声明未测，无从核。
- 文档一头部「本次提交按 pathspec 精确到自己动的文件」：截至核查时刻，相关 `src/`、`tests/` 改动仍是工作树 `M` 状态，HEAD 为 `f191e4d`，未见对应提交。可能是尚未提交（措辞用了将来意味），也可能是描述超前，请撰写者自查。
