# 保活两侧工作：裁决落实与文档一致性的独立证伪评审

> **落盘位置说明**：本次派发要求写入 `/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-review-keepalive-rulings.md`。该写入被 harness 拒绝——本会话被隔离在 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`，不允许写共享 checkout 的路径。故落在本 worktree 的同名相对路径下，**需要主会话把它搬到主工作树**（内容与目标路径无关，可直接 `cp`）。

- 日期：2026-08-20
- 角色：独立证伪者。评审对象是**裁决落实情况与文档一致性**，不是代码正确性（代码另有评审）。
- 基线：`main` = `f3c9de7`（`chore: update .gitignore …`）。所有仓库内文件一律以 `git show main:<path>` 读取，不读工作树，因为主工作树有并行会话的未提交改动。
- 例外并已注明：`docs/.human-controlled/` 与 `docs/tmp/260820-downstream-keepalive-defect.md` 等三份文件**在 `main` 上根本不存在**，只能从磁盘读，见 F-2、F-8。
- 提交定位说明：任务给出的 `e12003a` 不在 `main` 上，它是 `worktree-delivery-keepalive` 上的源提交。`main` 上对应的是 `52d877c`，二者 **tree 与提交信息逐字节相同**（`git diff 52d877c e12003a` 空输出）。下文一律称 `52d877c`，结论对 `e12003a` 同样成立。`dbb6104` 确在 `main` 上（第 45 位）。`783f023` 在 `main` 上（第 34 位），即**晚于 `dbb6104`、早于 `52d877c`**——这个顺序是 F-1、F-4、F-6 的关键。

---

## 一、结论

**verdict：needs-fix。**

八条用户裁决**全部被正确落实到实现里**，没有一条被越权扩大或收窄；我逐条找了反例，没找到。这一半是干净的。

问题全部集中在**文档侧**，且集中在同一个机制上：`spec.md` 与 `deferred.md` 都是在 `dbb6104` 那一轮写成的，此后 `783f023`（上游三个超时的接线修复）和用户对人写文档的修订都动了它们赖以成立的事实，而 `52d877c` 修订这两份文档时只覆盖了自己那一段，没有回头复核被别人推翻的段落。`spec.md` §4 结尾自己写下的那句警告——「本文里每一条关于『某处有没有接线』的断言都有保质期」——在同一份文档的 §2.2 与 §4 上就已经击发了两次。

严重项 2 条、中等 6 条、次要 6 条，共 14 条。

---

## 二、八条裁决的逐条核实

| # | 裁决 | 落实 | 记录 | 证据 |
|---|---|---|---|---|
| 1 | 清晰区分 client ↔ proxy 与 proxy ↔ upstream 两侧 | ✅ | ✅ | `spec.md` 标题与 §1 原样引用裁决原文；`stream.py` 模块 docstring 明写「The upstream-facing keep-alive is a separate mechanism with separate settings and shares no timer with this one」；`_LastWrite.at` 只在 `stream_delivery` 的 `yield` 恢复后被写，`_events_with_ping` 只读不写，上游事件确实无法重置它 |
| 2 | 人写文档由用户自行修订，本项目侧不动实现 | ✅ | ⚠️ | 实现确实没动。但 `spec.md` §2.2 仍以【需用户裁决】立着，且引用的原文已被用户改过——见 F-2 |
| 3 | `client_delivery.hedge` 未来做、目前暂缓 | ✅ | ✅ | `rg -n hedge src` 在 `main` 上仍只命中 `schema.py:213` 与 `:266`，与 `spec.md` §2.3 的断言逐字相符；`deferred.md` D-4 与 `status.md` 裁决表两处一致 |
| 4 | D-5 / D-6 是缺陷不是裁决点 | ✅ | ⚠️ | `deferred.md` 开头新增了「分类口径」段并自陈「初版把若干缺陷错写成裁决项，已更正」。但 `status.md` 把这条修正登记在标题为「用户已裁决」的表格里，而 `deferred.md` 的状态文字已过期——见 F-4、F-5 |
| 5 | `tcp_keepalive_interval` 走 A1，实现成真的 `SO_KEEPALIVE` | ✅ | ✅ | `composition.py:_keepalive_socket_options` 给出 `SO_KEEPALIVE=1` + `TCP_KEEPIDLE/TCP_KEEPALIVE` + `TCP_KEEPINTVL` + `TCP_KEEPCNT=4`；`_keep_proxy_connections_alive` 补回 httpcore 在 `AsyncHTTPProxy.create_connection` 丢掉的那一份。**三条真实 socket 回读测试**：direct、forward proxy（`test_the_keepalive_is_on_the_socket_that_carries_the_request`，参数化）、CONNECT 隧道（`test_the_keepalive_is_on_the_socket_of_a_connect_tunnel`），断言 `1 / 25 / 25 / 4`，并有 `tcp_keepalive_interval: 0` 的关闭对照断言 `0` 且 `TCP_KEEPIDLE != 25`。这是「参数投影」以外的真判据 |
| 6 | SOCKS 路径走 S2，接受限制并告警 | ✅ | ✅ | `_warn_about_socks` 同时看 `options.proxy` 与 `get_environment_proxies()`（覆盖 `ALL_PROXY`），只输出 `_origin_of(url)`。三条测试钉住：配置 SOCKS 告警、环境 SOCKS 告警、告警不含 `hunter2` 也不含 `user`。非 SOCKS 路径有反向对照 `test_a_direct_proxy_says_nothing_of_the_sort` |
| 7 | `upstream_keepalive` / `upstream_h2_ping`：被取代就删，没取代就说清 | ✅ | ✅ | `git show main:src/app/config/settings.py` 全文已无这两个键；`git grep upstream_keepalive main -- src tests` 无命中。`schema.py:137` 的 `http2_ping_interval` 注释以 `NOT IMPLEMENTED, and it cannot be from here` 开头，给了 httpcore 1.0.9 无 PING 接口、无后台读循环的具体理由，并说明它不是 HTTP/1.1 开关 |
| 8 | 不得为「连接池保留时长」新造配置键 | ✅ | ✅ | `git grep pool_idle_expiry main` 全仓零命中。`build_http_client` 的 `transport()` 内明确写「No `limits`」，`test_pooling_is_left_to_httpx` 断言池读回 `(100, 20, 5.0)`——我用 `uv run python` 复核 httpx 0.28.1 / httpcore 1.0.9 的默认，与之相符。`deferred.md` D-3a 声称「核对过用户亲笔 `docs/.human-controlled/` 里从未出现 `keepalive_expiry` / 池相关的任何裁决」，我复核了：`rg -i 'pool|keepalive_expiry|max_connections|连接池' docs/.human-controlled/` 零命中，该声称成立 |

**没有发现任何一条裁决被记成了别的东西，也没有发现实现比裁决多做或少做。** 裁决 2 与 4 打 ⚠️ 的原因全在文档陈述，不在实现范围。

---

## 三、发现

### F-1【严重｜把握：高】`spec.md` §2.2 关于 `upstream_request_deadline` 射程的整段，已被 `783f023` 作废

`spec.md` §2.2 现文：

> **用户描述的那个窗口（请求受理 → 上游首字节）目前确实没有任何保活**，但**它有上限**：`upstream_request_timeouts.upstream_request_deadline`（默认 **1200**，`src/app/server/handler.py:99-104` → `src/app/pipeline/direct_driver/base.py:233-241` 的 `asyncio.timeout`）**恰好且仅仅覆盖这一段**（流式请求拿到响应头就退出该上下文，body 在上下文之外消费）。

并在段末写：

> 它之所以恰好退化成这一段的静默上界，是因为 `deferred.md` D-6 记的那个缺陷……**D-6 一旦修好，这个上限就会扩大成砍断整次流式回答，届时上面这条「不提议调低」的理由只会更强。**

`783f023 fix: make each of the three upstream timeouts guard the phase it names` 已经在 `main` 上，**而且早于 `52d877c`**。当前事实：

- `src/app/server/pipeline_app.py:389-395` 把 `with_deadline_at(..., deadline_at=attempt.deadline_at)` 套在 body 流上，注释原文「The second place `upstream_request_deadline` is enforced from — one bound, not two」。
- `src/app/pipeline/direct_driver/base.py:132` 把 `attempt.deadline_at` 固定成一个时刻，`:240-256` 用 `asyncio.timeout_at` 读它。
- `base.py:228` 的 docstring 已改成「a streaming body outlives this function, and the delivery chain holds it to the same instant」。

所以「恰好且仅仅覆盖这一段」现在是**假的**，D-6 已修，1200s 现在就是整次流式回答的上界。`spec.md` 用将来时描述一件已经发生的事，并据此推出「所以这个上限对客户端毫无意义」——这个推论的前提没了。这是本轮最实质的失效断言：一个正在读 spec 决定要不要调 `upstream_request_deadline` 的人，会按「它只管首字节前那一段」去理解，而实际调低它会砍断长思考的正文。

两处行号也一并失效：`handler.py:99-104` 现在是 `shape_request` 的路由段，实际读取点是 `handler.py:130-131`；`base.py:233-241` 现在是 docstring 与分支头，实际是 `:240-256`。

**这一条同时是 F-6 的同源病：`52d877c` 修订 `spec.md` 时只改了 §3，没有回头核 §2.2 与 §4 里被 `783f023` 推翻的段落。**

### F-2【严重｜把握：高】`spec.md` §2.2 引用的人写文档原文已被用户改写，其中一条冲突已经不存在

`spec.md` §2.2 的【需用户裁决】块引用 `docs/.human-controlled/config.example.yaml:404-409`，并断言：

> 用户描述的窗口是「上游还没有响应头」，……**合成物不同。** 用户写的是「半块」，实现只发 `message_start`。

磁盘上该文件当前（mtime 2026-08-20 20:33，晚于 `e12003a` 的 20:01）第 406 行是：

> 客户端发起流式请求时，若很久上游都没有响应头，合成 HTTP 200 以及一个 `message_start` 给客户端。

**用户已经把「半块」改成了「合成 HTTP 200 以及一个 `message_start`」**，即裁决 2 已经落地在人写文档上。两条冲突里的第二条（合成物不同）**已经消失**，`spec.md` 却仍把它当成待裁事项列着。第一条（窗口定义反了）还在：中文行仍写「若很久上游都没有响应头」。

补充两点，都能独立核实：

1. **英文半句还没同步。** 第 409 行仍是「synthesize a half-block to the client」。所以人写文档目前中英不一致，这归用户，但我方 spec 至少不该把已被改掉的中文原文当现行文本引用。
2. **行号已失效。** `:404-409` 现在覆盖的是 `buffer_cap_bytes: 16777216` 与合成注释的开头两行；另一处引用 `:280-289`（spec 称其「写明用户冻结的不变量是绝不误杀合法长思考」）现在指向的是 `max_streams_per_connection: 1` 与 `tcp_keepalive_interval: 15`，那段不变量的正文已移到 `:296-302`。

同时，`spec.md` 前言写着「**§2.2 与 §3 各有一条需要用户裁决，未裁之前不得当作已定**」——§3 那条是 A1，**早已裁决**，§3 正文自己就写着「2026-08-20 用户裁决 A1 之后，`tcp_keepalive_interval` 已经实现」。前言与正文自相矛盾。

**为什么判严重**：这是「人写文档是最终权威」这条规矩的直接受体。一个读者按 spec 去看 `:404-409`，会读到与 spec 引文不符的内容，然后无法判断到底哪一份陈旧。而且 spec 把一条**已经由用户处理掉**的冲突继续挂在【需用户裁决】下，等于向用户重复索要一次已经给过的裁决。

### F-3【中｜把握：高】`deferred.md` 点名的护栏测试在 `main` 上不存在，而且它正是评审判为「无分辨力」、已被替换掉的那一个

`deferred.md:25`：

> ……所以环境变量代理映射在 `composition.py` 里重建并挂载，由 `test_environment_proxies_are_still_honoured` 保证 httpx 改动这个私有辅助时会**红**，而不是代理支持静默消失。

`git grep -rn 'environment_proxies_are_still_honoured' main` 在 `tests/` 下**零命中**；全仓仅两处命中，都在文档里：`deferred.md:25` 本身，和 `review-transport-keepalive.md:87`。后者原文是：

> `test_environment_proxies_are_still_honoured` 只设置一个 `HTTPS_PROXY`，随后断言任意非空 transport 能匹配 HTTPS URL；它不检查实际 proxy URL，不隔离 `ALL_PROXY／NO_PROXY`，不检查 direct mounts，不覆盖 SOCKS，也不比较原生 httpx。

也就是说：**`deferred.md` 把一个被评审判定为几乎没有分辨力、并因此被删掉重写的测试，作为「已补偿并钉住」的证据挂在那里。** 实际生效的护栏是 `test_environment_routing_matches_native_httpx`（`tests/unit/server/test_http_client_build.py:135`），它对四个目标 URL 逐个与原生 httpx 的路由结果比对，确实有分辨力——`52d877c` 的提交信息把这件事说对了（「a test compares every destination against native httpx rather than asserting some transport matched — which passes for a great many wrong answers」），只有 `deferred.md` 没跟上。

后果不是「记错一个名字」：一个后来者想确认 A1 的已知陷阱确实被钉住，会去找这个测试，找不到，然后要么以为护栏没了，要么以为文档整体不可信。

### F-4【中｜把握：高】「已记入 `deferred.md`」再次落空：proxy 优先级 provenance 缺口至今没有落盘

这正是任务里点名的那种模式，而且是**同一件事第三次落空**。

`tests/unit/server/test_http_client_build.py:83-90` 的 docstring 明写：

> `docs/.human-controlled/config.example.yaml` puts `HTTP_PROXY` / `HTTPS_PROXY` *above* the config file's `proxy`, but `load_proxy_config()` flattens CLI, `GHC_PROXY` and YAML into one field with no provenance, so nothing downstream can tell them apart. That predates this change and is not fixed here; naming this test after the rule would freeze the wrong half of it. **Recorded in `docs/agents/delivery-keepalive/deferred.md`.**

`git show main:docs/agents/delivery-keepalive/deferred.md | rg -i 'proxy|优先级|load_proxy_config'` 只命中两行，都是别的话题（A1 环境变量陷阱、SOCKS）。**`deferred.md` 里没有这一条。** 它实际只写在 `review-transport-keepalive.md:79`。

而 `review-transport-keepalive-r3.md` 的 R3-F2 早就点过名，原文：

> 协调消息再次声称这个待裁项已经写入 `deferred.md`，实际 commit tree 与工作树都没有这项……当前 `docs/agents/delivery-keepalive/deferred.md` 没有 SOCKS 自建 network backend／pool 的待裁项，没有「proxy 路径允许只 warning 吗」的产品岔路，**也没有产品 proxy 优先级 provenance 缺口**。

R3 列的三项里，前两项后来都靠用户 S2 裁决消解掉了（`deferred.md` D-3f 有了），**第三项至今没有任何归宿**，而现在连生产测试的 docstring 都在替它作证。人写文档 `config.example.yaml:253-269` 确实写着优先级是 CLI `--proxy` > `HTTP_PROXY`/`HTTPS_PROXY` > 配置文件 `proxy`，所以这是一条与人写文档冲突的真实缺口，不是理论问题。

**建议**：在 `deferred.md` 新增一条（缺陷，非裁决点），说明 `load_proxy_config()` 压平三个来源导致无法实现人写文档的优先级，并把 `review-transport-keepalive.md:79` 与那条测试 docstring 一起指过去。

### F-5【中｜把握：高】`status.md` 完全没跟上上游 slice，其「排期修」清单里有四项已经做完

`status.md` 最后一次更新在 `dbb6104` 那一轮，`52d877c` 没有动它。当前失效之处：

1. 首行「**已合入 `main`**：squash 提交 `dbb6104`」——`52d877c` 也已合入，文档只字未提。
2. 「主线侧闸门……全量 `pytest` **1504 passed、3 skipped**」——这是 `dbb6104` 时刻的数。我数了测试函数定义（`rg '^ *(async )?def test_'`，parametrize 未展开，故只作为**下界方向**的证据）：`dbb6104` 1277 个，`main` 1331 个，**净增 54 个**。所以 1504 一定不是当前值。**我没有跑全量套件**——主工作树是共享 checkout 且有并行会话的未提交改动，我这棵隔离树与 `main` 有 6 个文件的差异（含 `pipeline_app.py`），在任一处跑出来的数都不能代表 `main`。这一条的判据是「1504 已确定过时」，不是「新数字是多少」。
3. 归档分支只列了两条 delivery 的，没有 `archive/260820-upstream-keepalive`（7 个源提交，tip `2705281`）与 `archive/260820-upstream-keepalive-onmain`。
4. **末节「排期修（不需要输入）」仍写着「D-3b、D-3c、D-3d、D-3e、D-5、D-6」——这六条现在一条不剩全都做完了**（D-3b/c/d/e 见 `deferred.md` 自己的「已实现」「已由并行会话接手」「已删除」三节，D-5/D-6 见 `783f023`）。一个照 `status.md` 接手的人会去重做六件已完成的事。
5. 「代码改动集中在 `src/app/pipeline/delivery/stream.py` 一个文件」——对 `dbb6104` 成立，对本主题当前状态不成立（`composition.py`、`schema.py`、`settings.py`、`stream_cap.py`）。
6. `tests/unit/test_stream_delivery.py` 这个路径已被 `876998a` / `0c1524f` 的测试树重组改成 `tests/unit/pipeline/delivery/test_stream_delivery.py`。（评审报告里的旧路径属历史件，不必改；`status.md` 是活文档，应当改。）

另外一处措辞问题：裁决表标题是「用户已裁决」，而 D-5/D-6 那一行记的恰恰是「用户指出这两条**不是**裁决点」。把「这不是裁决」登记进「已裁决」表里，是同一个错误的轻微复发。

### F-6【中｜把握：高】`spec.md` §4 的 `stream_idle_overrides` 已随 `783f023` 删除，两处行号也过期

`spec.md` §4 现文：

> `src/app/server/handler.py:429-437` 的 `stream_idle_seconds` 读的正是 `upstream_request_timeouts.stream_idle` 与 `stream_idle_overrides`，并由 `src/app/server/pipeline_app.py:289-291` 经 `with_idle_timeout` 接到生产流式路径上。

当前事实：

- `stream_idle_seconds` 在 `handler.py:510-515`，函数体只有一行 `return chain.config.upstream_request_timeouts.stream_idle`，**没有 overrides**。
- `UpstreamRequestTimeoutsConfig`（`schema.py:146-152`）只有 `response_header` / `stream_idle` / `upstream_request_deadline` 三个字段，**`stream_idle_overrides` 与 `response_header_overrides` 都已不在**。`783f023` 的提交信息就写着「The two override maps go with the config keys the user removed」。（`settings.py` 的 legacy `TimeoutConfig` 里还留着同名字段，那是旧链路，与 spec 引用的 `upstream_request_timeouts.*` 不是同一个。）
- 接线点在 `pipeline_app.py:389-395`，不是 `:289-291`。
- 「默认值 0（禁用）」✅ 成立，`schema.py:151` 确为 `Field(default=0, ge=0)`。

同节末句「`response_header` / `response_header_overrides` 的问题另见 `deferred.md` D-5」也随之半失效：`response_header_overrides` 已删，而 `deferred.md` 的 D-5 条目通篇只有一句「并行会话正在做」，并没有任何关于 `response_header` 的内容可供「另见」。

### F-7【中｜把握：高】`deferred.md` 把「已实现」归到 `1a2daac`，那正是被推翻的第一版

`deferred.md` 的三级标题是「## 已实现（`1a2daac`，本轮）」。

`1a2daac` 不在 `main` 上，也不在 `worktree-delivery-keepalive` 上，只存在于 `archive/260820-upstream-keepalive`，而且是那条链的**第一个**提交。读它的提交信息：

> What the key used to configure is now `pool_idle_expiry`, defaulted to the value that mapping produced……
> The limits are passed whole……100 and 20 are what the design doc and httpx both say.
> `settings.py`'s `upstream_keepalive` and `upstream_h2_ping` are **annotated rather than deleted**……

**这正是裁决 8 推翻的那一版、以及裁决 7 要求改掉的那一版。** 把「已实现」标题挂在它上面，等于把读者指向被否决的形态。它后面还有六个提交（`efe25d3`、`09f75dd`、`12a65ed`、`ac676b0`、`52d722c`、`2705281`）才是真正落地的东西，而 `main` 上的载体是 `52d877c`。

同一节的正文倒是把撤销讲清楚了（「已撤销：`pool_idle_expiry` 删除……」），所以这不是内容错误，是**指针指错**。但对一个想 `git show` 去看实现的人，它是彻底误导的。

### F-8【中｜把握：事实高，定性中】`spec.md` 的全部实测依据不在 `main` 上

`spec.md` 是标注为「规范」的文档，已提交进 `main`。它的证据链指向：

- 前言：`docs/tmp/260820-downstream-keepalive-defect.md`、`docs/tmp/260820-review-downstream-keepalive-defect.md`
- §2.1、§2.2：`docs/tmp/260820-review-synthetic-start-fix.md`

`git ls-tree -r --name-only main -- docs/tmp` 里**这三份都没有**（同目录下 `260820-deferred-d3-d5-d6.md` 倒是被 `dbb6104` 一起提交了）。三份文件在磁盘上存在，但只在分支 `a/2026-08-20-split-53fec22` 的 `53fec22` 里被提交过，那条分支不在 `main` 的祖先里。`.gitignore` 没有排除它们，所以是「没提交」而不是「被忽略」。

同样地，`docs/.human-controlled/` **整个目录在 `main` 上不存在**，而 `spec.md` 与 `deferred.md` 都以行号引用它。

定性打「中」而不是「高」，是因为这可能是并行会话待提交的状态，而不是一次遗漏；但从 `main` 的一份干净 checkout 出发，spec 里「实测 10.46s 内 173125 次已到期却被跳过」「`block` 3 个 ping、`full` 0 个 ping、首字节 3.22s」这些数字**目前无法追溯到任何可读的来源**，而它们正是 §2「到期就发」判据的全部经验基础。

### F-9【次要｜把握：高】`spec.md` 前言的评审沿革严重滞后

前言写「本文经**两轮**独立评审：`review-async-correctness.md`（pass）、`review-contract.md`（needs-fix；本版按其 F1–F11 修订）」。

同目录下实际躺着：async 8 轮（`review-async-correctness.md` + r2–r8）、contract 3 轮（+ r2、r3）、`review-reconciliation.md`、transport 3 轮。`status.md` 的说法反而更准（「契约评审三轮……asyncio 正确性评审八轮」），两份文档对同一件事给出不同数字。

另外值得记一笔：**`52d877c` 对 `spec.md` §3 的那 33 行修订，没有任何一份评审报告覆盖过**——三份 transport 评审都是代码评审，且都早于这次 spec 改写。前言若照实写，应当说明这一点。

### F-10【次要｜把握：高】`spec.md` §3 的「连接池……不是本项目的配置」是个过宽的全称句

原文：

> 连接池的保留时长与连接数上限**不是本项目的配置**。

`src/app/config/settings.py:22-24` 的 `UpstreamConfig` 有 `max_connections: int = 100`、`max_keepalive_connections: int = 20`、`keepalive_expiry: int = 30`，并被 `src/app/upstream/client.py:29` 的 `create_http_client()` 原样传给 `httpx.Limits(...)`；该函数经 `upstream/bootstrap.py:110` 被 `server/app_factory.py:99` 使用。

那确实是旧链路（新链路是 `cli.py` → `composition.build_http_client`），但**旧链路并没有被删**，而按项目规则孤儿模块可以留着。所以准确的说法是「**新链路**不再配置连接池」，正如 `52d877c` 的提交信息自己写的「Nothing **here** configures pooling any more」——提交信息的射程是对的，spec 把它扩成了全称。

### F-11【次要｜把握：高】R3 判 `needs-fix` 之后又落了三个提交，没有复评，也没有任何文档说明为何可以放行

`review-transport-keepalive-r3.md` 的最终裁决是「整体 slice 仍是 `needs-fix`」，并列三个前置条件：① 用户裁决 SOCKS 是否只告警；② 把该待裁项、F-2 兼容范围与迁移规则写进 `deferred.md`；③ 为 HTTPS tunnel 补提交内 fd 回归。

R3 评的是 `12a65ed`。此后归档链上还有 `ac676b0`（tunnel fd 回归，对应 ③）、`52d722c`（撤销 `pool_idle_expiry`，对应裁决 8）、`2705281`（删两个 legacy 键，对应裁决 7），才压成 `52d877c`。**这三个提交没有任何 R4。**

按项目规则「Re-review only when the candidate changes in a way that can invalidate the verdict」，这不必然是错的：① 由用户裁决消解，③ 我已核实 `test_the_keepalive_is_on_the_socket_of_a_connect_tunnel` 存在且断言 `SO_KEEPALIVE == 1`，②的兼容范围部分因为 `pool_idle_expiry` 整个删掉而自然消失（`deferred.md` D-3a 写「不新增任何配置键，也没有兼容范围要谈」，这是诚实的收口）。**但②的第三项至今未落盘，见 F-4。** 而这三条前置条件的处置结论没有写在任何地方——`status.md` 没提上游 slice，`deferred.md` 也没有一节说「R3 的三条如何关闭」。一个 `needs-fix` 判决被无声地关掉了。

### F-12【次要｜把握：中，属规则解读】`archive/260820-upstream-keepalive-onmain` 指向的是一个 squash 提交

项目规则写「preserve its reviewed source commit under an immutable `archive/YYMMDD-<topic>` branch. **Do not point the archive at the squash commit.**」

- `archive/260820-upstream-keepalive` = `2705281`，7 个源提交，符合规则 ✅。
- `archive/260820-upstream-keepalive-onmain` = `0176e93`，提交信息字面就是 `feat: upstream keepalive slice (squashed for rebase)`，父提交是 `1ba1d10`，一个 rebase 中转产物。

对比 delivery 那一侧，`status.md` 说 `-onmain` 存的是「调和后的 **4 个提交**」。所以 `-onmain` 这个后缀在两个 slice 里含义不同：一个是调和后的多提交源，一个是 rebase 用的单个 squash。打「中」把握是因为规则原文针对的显然是集成 squash（这里是 `52d877c`），而 `0176e93` 是中间态；但它确实是个 squash，而且这个不一致没有写在任何地方。

### F-13【次要｜把握：高】人写文档新增的一条合成代价，我方文档没有对应记录

`config.example.yaml:407`（用户新写的，与「半块 → `message_start`」同一次修订）：

> 一旦合成，就无法再转发真正的上游 HTTP 状态码了，无法使用原生的客户端重试/退避机制。

`spec.md` §2.2 花了很大篇幅讨论合成的代价，但讨论的是**另一种**代价（多发一次 `message_start` 会把零字节请求变成客户端可见的截断报错）。用户点出的这一条——合成即锁死 HTTP 200，客户端原生的 retry/backoff 从此失效——在 `spec.md` 与 `deferred.md` 里都没有对应句子。

这不是错误陈述，是**遗漏**。按「不得静默削减潜在需求」的规矩，它至少该在 §2.2 里记一笔，因为它直接影响 `synthesized_response_headers_after_sec` 该不该开、开多大。

### F-14【次要｜把握：高】人写文档仍把 `http2_ping_interval` 描述成生效的保活，`deferred.md` 的「文档侧顺手项」没提

`config.example.yaml:289-291`：

```yaml
  # HTTP/2 PING 保活间隔（0 = 禁用）。
  # HTTP/2 PING keepalive interval in seconds (0 = disabled).
  http2_ping_interval: 15
```

没有 NOT IMPLEMENTED 标注，读起来就是一个开着的保活。`schema.py:137` 的长注释把「做不到、为什么做不到」写得很清楚，但那是我方 schema，不是用户会读的配置文档。

按裁决 2，这份文件归用户改，我方不该动。但 `deferred.md` 末节「文档侧顺手项（无岔路）」只提了归档件 `streaming-resilience.md` 的配置表，**没有把「人写配置文档仍宣传一个未实现的保活」提出来交还给用户**。这正是应该记下并提醒、而不是默认对方会发现的那类事。

---

## 四、两个提交信息的夸大核查

任务特别点名 `e12003a`（= `main` 上的 `52d877c`）关于 keepalive 射程、连接数上限、被删键的说法。我逐句核了，**没有发现夸大**，而且几处最容易夸大的地方它反而是主动收窄的：

| 提交信息原句 | 核实结果 |
|---|---|
| 「It is now a real `SO_KEEPALIVE`, with `TCP_KEEPIDLE` and `TCP_KEEPINTVL` at the configured value and four probes, **read back off the socket rather than off the parameters**」 | ✅ `keepalive_on_the_wire()` 用 `response.extensions["network_stream"].get_extra_info("socket")` 取真实 fd 做 `getsockopt`，断言 `1 / 25 / 25 / 4`，并有关闭对照。同文件多数断言确实仍读参数，但这句说的是 keep-alive 这一条，射程对得上 |
| 「measured with `getpeername()`, our socket's peer is the origin when direct and the proxy when tunnelling……**Direct, this probes upstream……Proxied, it probes the hop to the proxy**」 | ✅ 结论与 httpcore 的 CONNECT 语义一致，且它主动把射程限到第一跳，是收窄不是夸大。唯一遗憾：`git grep getpeername main` 在 `tests/` 下零命中，这次实测没有留下可复跑的产物，只在 `spec.md:105` 与 `deferred.md:51` 的正文里。属 F-8 的同类问题，不构成夸大 |
| 「a test compares every destination against native httpx rather than asserting some transport matched — **which passes for a great many wrong answers**」 | ✅ `test_environment_routing_matches_native_httpx` 对四个 URL 逐个与原生 httpx 比 `describe_route`。这句还顺带自我批评了旧测试——而 `deferred.md` 没跟上，见 F-3 |
| 「All `NO_PROXY` rules share one direct transport, or each would carry its own pool and its own connection cap」 | ✅ `_proxy_mounts` 对 `url is None` 一律返回同一个 `direct` 对象，`test_no_proxy_rules_share_one_pool` 钉住 |
| 「httpcore takes `socket_options` on `AsyncHTTPProxy`, stores it, hands it to `super().__init__` — and then builds the connections without it……**An earlier version of this did replace the pool, and did forget three.**」 | ✅ 与 `review-transport-keepalive-r2.md` 的 R2-F1 实测一致；「forget three」指的是归档链上的早期版本，属自陈失败，非夸大 |
| 「**Nothing here configures pooling any more.** The fifteen seconds that mapping produced was a side effect of the defect rather than a setting anyone chose, so it is not preserved and no key is minted to hold it」 | ✅ 「here」限定在 `composition.py`，射程正确。**注意 `spec.md` 把同一件事扩成了全称，见 F-10——夸大发生在 spec，不在提交信息** |
| 「they were lost because a `Limits` was passed carrying one field, and httpcore reads the other two as `sys.maxsize`. **Passing none restores httpx's own.**」 | ✅ 我核了改前代码 `6ef4b03:composition.py:82` 确为 `limits=httpx.Limits(keepalive_expiry=options.keepalive_expiry)`；`test_pooling_is_left_to_httpx` 断言 `(100, 20, 5.0)`，与 httpx 0.28.1 实际默认相符（我用 `uv run python` 复核） |
| 「`cap_streams_per_connection` now covers mounted transports too」 | ✅ `stream_cap.py` 的 `cap_streams_per_connection` 确实遍历 `client._mounts` |
| 「`timeouts.upstream_keepalive` and `timeouts.upstream_h2_ping` are deleted……The latter carries the reason it stays unimplemented」 | ✅ 两键全仓无痕；`schema.py:137` 有理由 |

`dbb6104` 的提交信息同样核过，没有发现夸大。「Seven regressions, each verified to fail against the commit before its fix」这一条我未逐条复跑（超出本轮范围，且 `review-async-correctness-r8.md` 已做过分辨力验证并给出 pass）；`status.md` 反而主动记了两处「绿灯没有分辨力」的丢弃/重写，这是加分项。

唯一一处**措辞可议**：`dbb6104` 说「Reviewed by three independent reviewers over twelve rounds」，而 `spec.md` 前言只说「两轮」（F-9）。这不是提交信息的错，是 spec 的错。

---

## 五、建议的处置顺序

按「读者会被误导的程度」排，不含实现改动（实现是对的）：

1. **F-1**：重写 `spec.md` §2.2 关于 `upstream_request_deadline` 的整段，改成 `783f023` 之后的事实，并删掉「D-6 一旦修好……」的将来时。
2. **F-2**：按人写文档当前文本重写 §2.2 的引用；把「合成物不同」标为已解决；把前言「§2.2 与 §3 各有一条需要用户裁决」改成只剩窗口定义一条；行号一律换成锚点或小节名，因为该文件正被用户持续修订。
3. **F-6**：`spec.md` §4 删掉 `stream_idle_overrides`，两处行号更新。
4. **F-5**：`status.md` 补上游 slice，清空已完成的「排期修」清单，补两条归档分支。
5. **F-3 / F-7**：`deferred.md` 把测试名改成 `test_environment_routing_matches_native_httpx`，把「已实现（`1a2daac`）」改成 `52d877c`。
6. **F-4**：新增 proxy 优先级 provenance 缺口条目。这一条是三次落空里唯一还没落地的，优先级不低。
7. **F-13 / F-14**：把两件事写进 `deferred.md` 并提醒用户，不动人写文档。
8. **F-8 / F-9 / F-10 / F-11 / F-12**：按方便处理。F-8 若确认那几份文件本就该进 `main`，提交它们即可。

一句自我限定：**我核的是「文档说的与 `main` 上的代码/文件是否一致」，以及「裁决有没有被落实」。我没有跑全量测试套件，也没有独立验证七条保活性质本身的正确性**——那属于代码评审，另有 `review-async-correctness-r8.md`（pass）与 `review-reconciliation.md` 覆盖。所有「已实现 ✅」的判断，依据是我在 `main` 上读到的源码与测试断言，不是我重跑了它们；唯一跑过的是 `uv run python -c "import httpx; print(httpx.Limits())"` 这一条查 httpx 默认值的探针。
