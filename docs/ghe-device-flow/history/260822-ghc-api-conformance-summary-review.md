# 评审：`260822-ghc-api-conformance-summary.md`

日期：2026-08-22
评审对象：`.dev/docs/tmp/260822-ghc-api-conformance-summary.md`
权威文档：`docs/.human-controlled/ghc-api.md`（用户亲笔）
评审基线：仓库 HEAD 在评审时为 `8f654b4`（2026-08-22 09:45:13）；被评审总评自称锁定 `51196e2`（09:38:24）
方法：所有针对提交的核对一律用 `git show 51196e2:<path>` / `git grep <pat> 51196e2`，不用工作树内容证实或证伪针对提交的主张。历史归因用 `git show --stat` / `git log --diff-filter=A|D`。全程只读，未修改、未暂存、未提交任何仓库文件（本报告除外）。

## 总体裁决

**需修订后交付。**

总评的四条核心结论我逐条独立核过，**全部成立**：`/chat/completions` 流式零字节交付的三层机制、`--ghc-api-base-url` 的静默空操作、`run_refresh_loop` 未接生产链路、生产链路 `account_type` 恒为 `individual`。判定表 15 行里 13 行的代码侧证据（文件与行号）在 `51196e2` 上逐条对得上。

但有 8 条需要改，其中 3 条（发现 1、2、5）会直接误导用户在他自己亲笔的文档上做裁决——用户按 D1 去看 `ghc-api.md:16` 会看到 enterprise 行而不是 self-hosted 行；F6 的历史归因与 git 历史相反，会让「该改文档还是该把模块搬回去」这个裁决点朝错误方向倾斜。

---

## major

### 1. 权威文档的行号引用整体错位一行（判定表第 4-7 行 + D1）

`docs/.human-controlled/ghc-api.md` 里账户类型表的实际行号是：L12 表头、L13 分隔行、**L14 individual、L15 business、L16 enterprise、L17 self-hosted**。总评的第 4-7 行分别引 L13/L14/L15/L16，整体少一行——第 4 行引的 L13 是 Markdown 分隔行，第 5 行「business」引的 L14 其实是 individual 行。

最要命的是 **D1**：正文写「`ghc-api.md:16` 把 `msft.ghe.com` 列为 self-hosted 的 API Base URL 值」，但 L16 是 enterprise 行，压根没有 `msft.ghe.com`。D1 是唯一一条请用户在他自己文件上动笔的裁决点，行号指错的代价最高。

同一份文档里直连路径表的引用（L25/L26/L27/L28/L29/L31）与 L3、L7、L8、L19 我都核过，**没有偏移**，所以这是一处局部的表格读数错误，不是全局系统性偏移。

**改法**：第 4-7 行改为 L14/L15/L16/L17；D1 的 `ghc-api.md:16` 改为 `ghc-api.md:17`。

### 2. 权威文档在 `51196e2` 里并不存在，而所有行号只对工作树版本成立

总评开头声明「下文所有判定都锁定在 `51196e2` 这个提交上，不采信工作树的叠加态」。但：

```
$ git cat-file -e 51196e2:docs/.human-controlled/ghc-api.md
fatal: path 'docs/.human-controlled/ghc-api.md' exists on disk, but not in '51196e2'
```

`docs/.human-controlled/*` 当前是 `A`（已暂存未提交），且 `ghc-api.md` 还有一处**未暂存**的工作树改动：索引版本写「GHC API 根据账户类型**可能**使用不同的 API Base URL」且**没有**「如未配置，根据用户订阅自动识别选择。」这一句；工作树版本删掉了「可能」、增补了那一句。因此索引版本里直连路径表整体比工作树前移 2 行（ws 行在 L26 而非 L28，2026-08-16 那条在 L29 而非 L31）。

后果有二：其一，总评所有 `ghc-api.md:Lnn` 只对**未提交的工作树**成立，与自称的基准相反；其二，判定表**第 8 行这条最重的负面判定（「未满足」）所依据的那句要求（L19），只存在于工作树，连索引里都没有**。这不影响判定的正确性——用户亲笔的最新文本当然是权威——但必须写明，否则任何按 `51196e2` 复现的人都找不到 L19，也无从判断「可能使用」与「使用」的差别是否改变了第 5、6 行的标准。

**改法**：基准段落改成两行——代码侧基准 `51196e2`；权威侧基准「`docs/.human-controlled/ghc-api.md` 已暂存未提交，且工作树另有未暂存改动，行号按工作树版本计；索引版本 L10 措辞为『可能使用』且无 L19」。

### 3. F1「在锁定提交 `51196e2` 上实测」——探针不可能跑在这个提交上

时间线（`git log --date=iso` 与文件 mtime）：

| 事件 | 时刻 |
|---|---|
| `a68672c` 提交 | 09:27:55 |
| 探针报告 `260822-chat-completions-block-delivery-probe.md` 落盘 | 09:34 |
| 交叉复核报告落盘（自称基线 `a68672c`，与事实相符） | 09:37 |
| **`51196e2` 提交** | **09:38:24** |
| 总评落盘 | 09:42 |
| `8f654b4` 提交 | 09:45:13 |

探针在 `51196e2` 存在之前四分钟就跑完了。它实际跑的是 `a68672c` **加上同伴当时的工作树叠加态**——而 `handler.py`、`pipeline_app.py`、`request.py` 正在被同伴改（这三个文件后来成了 `8f654b4`）。也就是说 F1 犯的恰好是总评开头声明要回避的那件事。

我独立核了这个偏差会不会推翻结论：`git diff a68672c 51196e2` 只碰 4 个文件，其中唯一与 F1 相关的是 `pipeline/delivery/stream.py` +13 行，而那 13 行整体门控在 `isinstance(torn, ClientDeadlineError) and client_has_bytes.is_set()` 之下，chat-completions 这条路径两个条件都不满足。**结论成立，出处写错了。** F2 同理：它的实测来自交叉复核，基线是 `a68672c`；`cli.py`、`config/schema.py`、`config.example.yaml` 在 `a68672c..51196e2` 之间未变动，所以结论同样成立。

**改法**：F1 与 F2 的「在锁定提交 `51196e2` 上」删掉，改成「探针基线 `a68672c` + 当时工作树；已核 `a68672c..51196e2` 的 delta（仅 `stream.py` 加 13 行，且被 `ClientDeadlineError and client_has_bytes` 双重门控）不触及本结论」。这句话本身就是把「实测」与「推断」分开写的正确形态。

### 4. F2 对 `a8a7f87` 的归因错误：不是「只改了 `schema.py`」

`git show --stat a8a7f87` 是 **17 个文件、+338/-95**，包括 `ghc_client/config.py`、`ghc_client/account.py`、`ghc_client/tokens.py`、`server/composition.py`、`upstream/ghc_settings.py`、`upstream/urls.py`、systemd unit、以及 8 个测试文件。总评写的「（那次只改了 `schema.py`）」是假的。

这是**删限定词造成的**：交叉复核原文是「`git show --stat a8a7f87` 显示该提交只动了 `src/app/config/schema.py`**（在本次相关的三个文件里）**」——一句有明确范围的真陈述。总评转述时把括号丢了，升级成了一句无范围的假陈述。

顺带补一条总评和分项都没写、但对理解这个 bug 有用的时序：`cli.py:132` 那行由 `52b01a2`（2026-08-17）写入，**早于** `a8a7f87`（2026-08-19）的改名，且 `52b01a2` 不是 `a8a7f87` 的后代。写这行的时候 `base_url` 是对的；是改名没跟到 `cli.py`，不是有人凭空写错了字段名。

**改法**：恢复限定词（「该提交没有跟到 `cli.py`」），并补一句时序。

### 5. F6 的历史归因与 git 历史相反

F6 写「`auth/` 自诞生起只有 `providers.py`（token 来源抽象）与 `service.py`（交互式登录编排）」，据此得出「文档描述的层次结构与代码不一致」。git 历史说的是反面：

| 文件 | 加入 `src/app/auth/` | 迁出 |
|---|---|---|
| `device_flow.py` | `5ae8413` 2026-07-15 `feat(auth): implement GitHub device flow` | `0d349c2` 2026-08-15 `feat: align ghc_client with the human-controlled requirements` |
| `copilot.py`（copilot token 兑换/刷新） | `9679e31` 2026-07-15 `feat(auth): manage Copilot token refresh` | `aa7320b` 2026-08-15 `refactor: extract Copilot API access into ghc_client library` |
| `github.py` | `fd607a0` 2026-07-15 | `aa7320b` 2026-08-15 |
| `providers.py` / `service.py` | 2026-07-15 | `b9939ca` 2026-08-21 搬到 `ghc_client/auth/`（纯改路径） |

也就是说：`ghc-api.md:5` 把这两件事归给 `auth` 子模块，**在文档写下的时候是准确的**；是 2026-08-15 的两次重构把它们搬出了 `auth/`，而 `0d349c2` 的提交信息偏偏叫「align ghc_client with the human-controlled requirements」。

（若 F6 的「`auth/`」是指 2026-08-21 才诞生的 `ghc_client/auth/`，那句话字面成立，但读者不会这么读，而且这个读法把最相关的那段历史整个藏起来了。）

这直接改变 D 级裁决的形态：现在的写法暗示「文档一直描述得不准，改文档即可」；实际情况是「代码从文档描述的形态漂走了」，用户完全可能选择把模块搬回去，或至少想知道那次重构为何以「对齐人写文档」为名做了相反的事。

**改法**：F6 改写为「代码漂移」，列上 `5ae8413`/`9679e31` → `0d349c2`/`aa7320b` 这条链，并把它升格为一个 D 级裁决点（改文档 vs 归位模块），而不是一条纯记录。

### 6. `ghc-api.md:31` 的后半句「如果存在陈旧可适当注释掉」没有被回答

判定表第 15 行把 L31 整条判「满足」，依据全部关于「保留、不接线」——那是 L31 的前半句。后半句是用户明确提出的一项清理请求，总评通篇没有答复。

ws 分项报告第 5 节列了 4 项陈旧候选，总评只在「本次核查未做的事」提了被交叉复核推翻的那一项（`verification/phase3_acceptance.py`，我核过：确实未被 git 跟踪，不在 `51196e2` 里，复核结论正确），另外三项整条消失。我核过它们**都被跟踪且都在 `51196e2` 里**：

- `verification/final_acceptance/probes/04_responses_websocket.py`（TRACKED，IN-COMMIT）
- `exp/httpx-ws/poc.py`（TRACKED，IN-COMMIT）
- `src/app/config/settings.py:129,131-133` 的四个孤儿字段——我用 `git grep 51196e2 -- src/` 复核过 `upstream_ws` / `max_ws_frame_bytes` / `max_client_ws_connections` / `max_upstream_ws_connections`：**唯一命中就是它们自己的声明行，全仓无读取者**

读者看到「本文采信复核结论，不列入清理候选」，会以为整张清单都作废了。

**改法**：第 15 行的判定拆两半——「保留不接线 = 满足」「陈旧清理 = 未答」；把上述三项作为候选交给用户，措辞上带明用户既有裁决（「孤儿模块可以留着」「『暂不支持』不是删代码授权」），只列不建议删，与 F5 现在的处理方式一致。

### 7. 第 5、6 行的分档与 F2 自相矛盾

第 5、6 行判「代码正确，**生产不可达**」。但 F2 第 3 点自己实测确认：YAML 里正确拼写 `api_base_url` 可用，解析出 `https://api.enterprise.githubcopilot.com`。**要求的那个 URL 在生产上是可达的**；不可达的是 `config.py:48` 那条「按 `account_type` 推导」的代码分支。

我核过 `composition.py:358` 读的正是 `provider_config.api_base_url`，`config.py:39-48` 的 override 分支排在 `account_type` 分支之前，所以显式配置确实绕过整个推导逻辑直达。

**改法**：判定改为「结果可达，推导分支不可达」，依据里写清「经显式 `api_base_url` 可达到该 URL；`config.py:48` 的 `account_type` 拼接分支在生产链路上不可达」。

### 8. 一句话结论漏掉了最要命的那一条

一句话结论列了三处「代码写对了、生产链路却够不着」：账户类型自动识别、`--ghc-api-base-url` 选项、copilot token 后台刷新。缺的是：**新 schema 的 `ModelProviderConfig` 根本没有 `account_type` 字段**（`schema.py:83-95`，我核过字段清单确无此项，且 `Section` 是 `extra="forbid"`）。

这一条比另外三条都重：它意味着 `ghc-api.md` L14-L19 那张表在生产上**只有第一行成立**，而且不是「自动识别没接线」那么轻——是连手动指定账户类型的通道都不存在。这个事实目前只出现在 F2 第 1 点和 D2 的一个从句里，没进结论。

**改法**：提到一句话结论，措辞如「账户类型在新 schema 里已无配置字段，L14-L19 那张表在生产上只有 individual 一行成立」。

---

## minor

### 9. 第 11 行判「不满足」偏强，且是全表唯一不引用自己驱动模块的行

`OpenAIChatCompletionsDriver` 存在（`direct_driver/openai_chat_completions.py:15`）且已接线（`direct_driver/__init__.py:49`），非流式实测与上游逐字节一致。`ghc-api.md:26` 要求的是「端点 → 驱动模块」的映射，映射是成立的。第 9、12、14 行都引了各自的驱动模块与 URL 字面量，唯独第 11 行没有——读起来像映射本身缺失。

**改法**：判定改「**部分满足**：映射成立、非流式正常；流式向客户端交付 0 字节」，依据补 `direct_driver/openai_chat_completions.py:15`、`direct_driver/__init__.py:49`、`client.py` 对应的 URL 行。这样也与第 3 行「部分满足」的用法一致（同为「功能在、有一条腿断」）。

### 10. F1「生产集成测试里端到端零覆盖」字面会被证伪

`tests/int/test_openai_routes.py` 在 `51196e2` 里有 `test_chat_stream_has_sse_headers_and_bytes`，断言的正是 `response.content == b"data: chunk\n\n"`——「流式有字节」。它跑在 `app_factory.create_app` 上，而 `create_app` 在 `src/` 下零调用者（我用 `git grep create_app 51196e2 -- src/` 核过，只有它自己的 def 和一句 docstring），所以它绿着也挡不住这个缺陷。

分项报告的表格写得比总评准（「生产集成测试（`create_pipeline_app`）：**零**」）。总评转述时丢了限定词。

**改法**：改成「`tests/int/test_pipeline_app.py`（生产入口）零覆盖；`tests/int/test_openai_routes.py` 有一条断言流式字节数的测试，但跑在已无调用者的 `create_app` 上——一条常绿而无鉴别力的测试，是缺陷能存活的第二层原因」。这个补充比原句更有价值。

### 11. 第 9 行的 `pipeline_app.py:685-696` 指错

`51196e2` 上 685-693 是流式生成器的 `except Exception` / `finally`，与路由注册无关。路由注册在 `694-706`（`def build_router` → `router.add_api_route(path, _serve, methods=["POST"])`）。

**改法**：改为 `pipeline_app.py:694-706`。

### 12. 第 1 行的依据不支撑「位于模块 `app.model_provider.ghc_client`」这半句

引的两个文件（`model_provider/base.py:16-63`、`model_provider/github_copilot.py:43-191`）我都核过，内容对得上，但它们是 `ghc_client` 的**兄弟**，不是 `ghc_client` 的内容。要证明「客户端实现位于 `app.model_provider.ghc_client`」，该引 `model_provider/ghc_client/client.py`（`GhcApiClient`，五个端点的 URL 字面量都在这里）。

**改法**：依据里补 `model_provider/ghc_client/client.py`。

### 13. 路径基准在同一张表里有两套

`model_provider/github_copilot.py`、`cli.py`、`config/schema.py`、`server/handler.py` 是相对 `src/app/`；而 `ghc_client/device_flow.py`、`ghc_client/tokens.py`、`auth/providers.py`、`config.py`、`account.py` 实际都在 `src/app/model_provider/ghc_client/` 下。按前一套基准去找 `src/app/ghc_client/` 会扑空——该目录已在 `d49fe23`（2026-08-21）搬走。

**改法**：一律写全 `src/app/...`。分项报告用的就是全路径，总评是转述时截短的。

### 14. D2 后半句与 D4 只提问、不表态

按 `propose-with-preference`，交给用户的裁决点应带自己的倾向与理由。D1、D2 前半句、D3 都动用户亲笔文件，交给用户裁决**是对的，不算推卸**，而且都给了倾向。但：

- **D2 后半句**（要不要在新 schema 恢复 `account_type`）是纯工程决策，而且是 L14-L19 整张表能否成立的闸门，现在只有一句反问。
- **D4**（无 token 时是否自动触发 device flow）确实是产品级取舍，该由用户定，但同样应给倾向——现状「必须先 CLI 登录再重启」对 systemd 部署意味着什么，报告有足够信息给出判断。

**改法**：给这两条各补一句倾向与理由。

---

## nit

15. 「主树全程只有同伴的改动」无法从产物核实，且遗漏了对本次核查最关键的一项状态：`docs/.human-controlled/*` 处于「已暂存未提交」。开头列同伴在途文件时也漏了 `tests/int/test_pipeline_app.py`（`git status --porcelain` 里与那三个文件并列）。
16. 第 4 行「逐字符一致」：文档写 `api.githubcopilot.com`，代码是 `https://api.githubcopilot.com`（`config.py:6`）。说「主机名一致」更准。
17. 总评已过期一手：`8f654b4`（09:45，`feat: wire the replay, and give one client request one retry budget`）已把当时的在途改动落地，HEAD 不再是 `51196e2`。我核过它只动 `request.py` / `handler.py` / `pipeline_app.py` / `test_pipeline_app.py`，不影响任何判定；但交付时应注明「本文所述状态对应 `51196e2`，HEAD 已推进到 `8f654b4`，delta 已核不影响结论」。
18. F2 附带那句「`account_type` 在用户的 `config.example.yaml` 里没有文档化」措辞别扭——该字段在新 schema 里压根不存在，写进 yaml 会被 `extra_forbidden` 拒。应与 `auth_base_url`（已实装、确实缺文档）分开说。

---

## 核过属实、不必改的部分（供作者放心）

以下我都在 `51196e2` 上逐条验证过，**成立**：

- 判定表第 1、2、3、9、10、12、13、14、15 行的全部代码侧文件与行号（含 `base.py:16` 恰为 `class ModelProvider(Protocol):`、`github_copilot.py:31-37` 的注释与发送表、`types.py:18`/`54-60`、`client.py:141/148-154/165/196`、`direct_driver/*:15`、`__init__.py:48`、`handler.py:150`、`inbound.py:34`、`handler.py:280`、`app_factory.py:35,177`）。
- 第 8 行：`account.py:7-21` 的探测逻辑、唯一调用点 `upstream/bootstrap.py:180-189`、`composition.py:357-360` 与 `407-410` 均不传 `account_type`、`config.py:23` 默认 `"individual"`——全部属实，判「未满足（已实现，未接线）」准确。
- 第 7 行：`config.py:43-45` 确实对 self-hosted 直接 `raise ValueError`，`msft.ghe.com` 只在注释里。判定与 D1 的倾向（改文档）我同意。
- F1 的三层机制：`assembler.py` 确实只有两个 assembler；`handler.py:488-524` 在 `51196e2` 上恰为 `dialect_for` + `assembler_for`（工作树里已漂到 498/527，**作者用的是提交态的行号，正确**）；`AnthropicAssembler.push` 的 `kind = event.event or str(data.get("type", ""))` 对 Chat Completions 帧恒为空串；`stream.py:309-312` 的注释自己写明「An upstream that produced no block and no terminal still leaves the client a 200 with an empty body」。
- F3：`run_refresh_loop` 全仓唯一调用点确为 `app_factory.py:105`；`create_app` 在 `src/` 下零调用者；`pipeline_app._lifespan` 只 `start_soon(chain.tokenization.run_periodic_flush, ...)`；`tokens.py:76-80` 的懒刷新确实兜住了正确性；`bootstrap.py:177` 确有启动期 `ensure_valid_token()`。「这不是中断性缺陷」这个分档准确。
- F4：`cli.py:289` 确实 `proxy_config, _ = _load_spec_config(...)`，standalone 分支在 `cli.py:320-323` 打印 `warning: ... has no effect`，systemd unit 第 23 行确为 `-m app start --fd 3 --graceful-timeout 300`。这条是全文归因最干净的一条。
- F5：`DeviceAuthProvider` 在 `51196e2` 全仓只有定义处与 `tests/unit/.../test_auth_providers.py` 两处引用；按「孤儿模块可以留着」只记录不建议删，处理正确。
- 第 15 行「9 个测试通过」：ws 分项报告第 77-86 行有 `uv run pytest` 的实际输出（8 passed + 1 passed），是实测不是推断。
- `config.example.yaml:159` 确为注释掉的 `# base_url:`，`auth_base_url` / `account_type` / `api_base_url` 在该文件中均无出现。

**没有发现越权**：没有修改任何生产代码、配置或用户亲笔文档的痕迹；D1/D3 都涉及用户亲笔文件，交给用户裁决是对的；F5 明确援引用户既有裁决而不建议删代码，符合「孤儿模块可以留着」。唯一与「越权」相反方向的偏差是发现 6——把本该交给用户的清理裁决整条吞掉了。

**没有发现把实测写成推断**：F2 第 3 点的「实测可用」有交叉复核第 6 节的探针支撑；「9 个测试通过」有 pytest 输出。反方向（把推断写成实测）就是发现 3 的出处问题。
