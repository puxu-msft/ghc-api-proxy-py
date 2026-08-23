# Azure 与 Gemini 路由入口：评审处置

**这份是处置记录**，答「评审提了什么、采纳了哪些、为什么」。两份评审原件是点时点记录，不改：

- [260823-azure-gemini-route-entry-review-gpt.md](260823-azure-gemini-route-entry-review-gpt.md) —— 实现选择的正面质疑（`blocker=0`、`major=2`、`minor=1`、`nit=2`）。
- [260823-azure-gemini-route-entry-review-regression.md](260823-azure-gemini-route-entry-review-regression.md) —— 回归风险与旧链对照（`blocker=0`、`major=1`、`minor=4`、`nit=2`）。

当前实现状态见 [../status.md](../status.md)，未闭合项见 [../deferred.md](../deferred.md)。

**时点**：2026-08-23，主仓 `af40e9b` 之上的未提交工作树（同伴在此期间推进过 `main`，两份报告记的快照 SHA 不同，受审 diff 未变）。

## 一句话

两份评审合计 `blocker=0`、`major=3`、`minor=5`、`nit=4`，**三条 major 全部采纳并修完**，其余采纳 8 条、登记待裁 1 条、明确保留 1 条。每条 major 我都先自己复现判据再动手，没有照单全收。

## 三条 major

### M1（评审一 F1）Gemini catch-all 把未追认的路径也当成已实现入口 —— 采纳

原实现是一条 `/v1beta/models/{model_and_method}`，只约束「一个非空 segment」，没有约束 `api.md:10` 列出的三个 method。

**自己复现的判据**：同一组 URL 分别打到 catch-all 与三条显式模板上。

| URL | catch-all | 三条显式模板 |
|---|---|---|
| `…/gemini-pro:generateContent` | 200 | 200，`model=gemini-pro` |
| `…/gemini-pro:streamGenerateContent` | 200 | 200，命中 `:streamGenerateContent` 而非 `:generateContent` |
| `…/gemini-pro:countTokens` | 200 | 200 |
| `…/gemini-pro:unknownMethod` | **200** | 404 |
| `…/gemini-pro`（无 method） | **200** | 404 |
| `…/something-else` | **200** | 404 |
| `…/vendor:family:generateContent` | 200 | 200，`model=vendor:family` |

最后一行是采纳前必须确认的：收紧 method 边界**不能**以牺牲含冒号的模型名为代价。贪婪段仍然把冒号之前的全部吃进 `model`，所以代价为零。评审二独立复测了同一组（另加大小写、空 model、URL 编码、GET、尾斜杠六种），结论一致。

改法：`table.py` 换成三条显式模板，均 `implemented=False`。新增 `test_a_gemini_method_api_md_does_not_name_is_not_served_at_all`（三个负例）与一条含冒号模型名的正例。

**评审对「测试为何没发现」的诊断是对的**：三个合法 suffix 只是同一个 catch-all 的三个正样本，把其中任何一个换成 `unknownMethod` 测试照样绿。这正是项目记忆里「模式不等于判据」的形状。

### M2（评审一 F2）「Azure 未挂前缀」测试会因 `_BY_PATH` 缺项而假绿 —— 采纳，并按更强的那一版改

原测试只断言 HTTP 404 与 `seen == []`。评审用探针证明：若 `build_router` 错挂了前缀模板而 `_BY_PATH` 不知道它，请求会真的走进 `serve`，再由 `_dispatch` 的 defensive 分支返回**同样的 404**、且不访问上游——两条断言全过。

评审同时诚实地界定了自己证据的边界：当前快照里两套展开规则确实一致，发现针对的是**测试守不住这个事实**，不是声称已经 split-brain。这个区分是对的，我按它采纳。

采纳「更稳妥」那一版而不是只补断言：抽出 `expanded_paths(route)`，`build_router` 与 `_BY_PATH` 共用，规则从写两遍变成写一遍。再补两层测试：

- `test_the_azure_paths_are_not_mounted_under_the_openai_prefixes` 现在同时断言 HTTP 404 **与** `route_for_path(...) is None`，两层事实分开钉。
- 新增 `test_what_is_mounted_and_what_can_be_looked_up_are_the_same_set`，把「已注册 POST template 集合」与「可 lookup 的 template 集合」的相等作为结构守卫。

**评审对变异证据边界的批评也是对的**：原变异把 `openai_prefixed` 从 `False` 改成 `True`，两个消费者一起变，所以打红不能证明测试能辨别「只漏改一个」。新增的第 8 条变异专门制造单边失配——只在 `build_router` 里多挂一条 `_BY_PATH` 不知道的路径——已确认打红。

评审二独立核对了这次重构的行为保持：把 HEAD 版与工作树版 `table.py` 分别 import 成两个模块逐键对比 `_BY_PATH`，得到 `removed: []`、`changed: []`、`added` 恰为新增六条。**纯增量。**

### M3（评审二 §5.1）新增的 `WireFormat` 成员让主产品路径从 400 退化成 502 —— 采纳，这是本次改动直接造成的回归

**这条最重要，而且是我自己没看见的。**

我给 `WireFormat` 加了 `GEMINI_GENERATE_CONTENT`，但 `FORMAT_ENDPOINTS`（`request.py`）没有、也不可能有对应条目。`routing.py` 的 `split_format_suffix` 用 `WireFormat(suffix)` 判断「这个 `@format` 后缀认不认识」，`decide_route` 随后无保护地 `FORMAT_ENDPOINTS[explicit_format]`。于是枚举里多出一个「认识但没有 endpoint」的值。

**自己复现的判据**（`POST /v1/messages`，主产品路径）：

| `model` | 修之前 | 修之后 |
|---|---|---|
| `claude-model@gemini-generate-content` | **502**，body 是 `{"error":{"type":"KeyError","message":"<WireFormat.GEMINI_GENERATE_CONTENT: 'gemini-generate-content'>"}}` | 400 `RoutingError`：`target format '…' has no endpoint on this proxy` |
| `claude-model@nope` | 400 `RoutingError` | 不变 |
| `claude-model@openai-responses` | 400 `EndpointNotSupported` | 不变 |

改法采纳评审倾向的第一个方案：在 `split_format_suffix` 里把「不在 `FORMAT_ENDPOINTS` 里」也算作不可路由，与未知后缀走同一条 `RoutingError`（但给不同措辞——一个是拼写错误，一个是本代理没建的能力，读者要去的地方不同）。判据放在一处、由同一张表决定，将来再加多少个 `implemented=False` 的格式都不用再动它。

**测试按评审的提醒钉结构而不是钉名字**：参数化在 `set(WireFormat) - set(FORMAT_ENDPOINTS)` 这个差集上。钉 `gemini-generate-content` 这个名字的话，Gemini 一旦实现它就会进 `FORMAT_ENDPOINTS`，测试会静默失去分辨力。

**关于越界**：修改落在 `src/app/pipeline/{routing,request}.py`，不在被点名的 6 个文件里。仍然做了——这是本次改动引入的、落在主产品路径上的回归，修它属于「把任务做完」而不是扩大范围。

## 其余采纳项

| 出处 | 内容 | 处置 |
|---|---|---|
| 一 F3 | 注释把 `adapt_azure_payload` 的窄事实扩大成「整条旧链只做这一件事」 | 改为只声称 adapter 那一层，其余归共享 pipeline。评审二逐行核对归档源码后确认改后的措辞准确 |
| 一 F4 | 「Azure body carries no model at all」被我自己新增的 `test_the_deployment_in_the_path_wins_over_a_model_in_the_body` 打脸 | 改为「may omit `model`；路径两种情况下都权威」 |
| 一 F4 | 「404 reads as never」过强——404 不承诺永久性（那更接近 410） | **选 501 的理由仍然成立，但成立的理由要换**：404 会让一条已追认的端点与「本代理根本没有的端点」同形。已按此改写 |
| 一 F5 | 测试文件末尾多余空行（`git diff --check` 报 `new blank line at EOF`） | 已删，复跑干净 |
| 二 §5.2 前半 | 501 的 message 吐的是路由表模板 `/v1beta/models/{model}:generateContent`，客户端拿到花括号什么也做不了 | 改为 `request.url.path` |
| 二 §5.3 | 三条 Gemini 路由上的 `streamable` 编码了一个对 Gemini 不成立的机制——`build_context` 读 body 的 `stream` 字段，而 Gemini 的流式由方法段决定 | 删掉三处 `streamable`，保留 `count_tokens` 与 `model_from_path`（两者都正确、且是实现时要用的），并写明哪几个字段在 `implemented=False` 下不可达 |
| 二 §5.4 | Gemini 留空的知识没有落点 | 新建 [../deferred.md](../deferred.md) §D-A 登记四件事 |
| 二 §5.5 | `src/.archived/README.md`、`status.md`、`decisions.md` 三处已被本切片证伪 | 三处均已同步 |
| 二 §5.6 | `route_for_path` 的 docstring 把读 scope 的动作记在 `serve` 名下（实际是 `_dispatch`），且「必须传模板」这句绝对陈述比事实强（对字面路径路由两种拼写同形） | 两处都改 |
| 二 §5.7 | `getattr(scope.get("route"), "path", url.path)` 把两种缺失压成一条表达式 | 评审说「纯风格，可不动」，仍改成显式形式——读起来像只给 `None` 兜底、实际连「有 route 对象但无 `path` 属性」也兜了 |
| 二 §2.2 | `scope["route"]` 完全由 FastAPI 提供，Starlette 从不写它 | 登记为 [../deferred.md](../deferred.md) §D-C：升级 FastAPI 时含参数的 6 条路由是要实测的判据 |

## 登记待裁，不在本切片决定

**未实现端点的错误信封是否按 inbound 方言分化**（二 §5.2 后半）。旧链与 `copilot-api-js` 的 Gemini 路径答的都是 Gemini 信封 `{"error": {"code", "message", "status"}}`，新链答的是本代理通用信封。这是对外契约，且一旦分化就不限于 501——Gemini 路径上所有错误都要跟着分化。登记为 [../deferred.md](../deferred.md) §D-B 交用户裁决。

## 明确保留、不改

**`build_context` 里的 `working["model"] = model.strip()`**。评审一判定保留合理，且明确说「不要为了让集成测试看到这一行而增加只供测试的生产行为」。这与我自己的变异发现一致——第一轮变异它没打红，暴露的是我把断言放错了层（集成层被 `driver.py:128` 的覆写掩盖），补单元层断言即可，不是这行多余。评审二另外指出：这对 `working` / `original_payload` 字段结构性地达到了 `copilot-api-js` 的 `src/routes/azure-openai/route.ts:29-43` 用整段注释论证的同一件事，且比参考实现的「显式 override 通道 + 要求下游按顺序应用」更难写错。

## 两位评审都确认、无需改动的实现选择

- **Azure 不需要 stub**：三个 OpenAI wire format 都有 active direct driver，旧 `adapt_azure_payload` 的唯一 Azure-specific 改写确实只是写 `model`。评审二逐条对照旧链后给出「**没有发现该做而漏了的 Azure 行为**」，并把 `apply_approval_guard`（已裁决暂不支持）、history（新链整体不写，`status.md` 已登记）、pydantic 入参校验（架构差异，与无前缀路径同管线）三项判为「旧链的东西不该照抄」或「非本切片」。
- **Gemini 用 501 且在解析前拒绝**：`TranslatorNotFound` 当前被 `error_status` 映射为 400，所以让未实现格式落入 pipeline 会错误归类。评审一另外精确界定了成立的边界——`_dispatch` 仍先执行 `await request.body()`，所以成立的是「解析前返回」而非「读取 body 前返回」；注释已按此写准。

## 一条方法上的教训（评审二 §0，值得单独记）

评审期间被评审对象变动了两次，其中一次造成了**假的失败**：06:57 评审二跑 `test_the_azure_paths_are_not_mounted_under_the_openai_prefixes` 得到 `assert 200 == 404`，60 秒后同一断言稳定为 404。原因是评审一当时正在共享主树上做受控变异。评审二没有据此下缺陷结论，而是复测 + 查 `table.py` 现状 + 直接探测三条证据后判定为测量干扰——这个处理是对的，也正是项目记忆里「阻断性观察有保质期」那一条。

**可行动的后果**：本切片的最终门必须在一棵**没有并发变异**的树上跑一次，否则绿或红都读不出意义。见下。

## 最终验证（无并发变异的树上）

基线：主仓 `2d6b878`（同伴在评审期间把 h2 迁移与 `hand_over.py` 都提交了，工作树此时只剩本切片的 10 个文件）。

| 项 | 结果 |
|---|---|
| `uv run ruff check src tests` | All checks passed |
| `uv run pyright`（本切片改动的 6 个源文件 + 4 个测试文件） | 0 errors |
| `git diff --check -- src tests` | 干净 |
| `uv run pytest tests --cov=app --cov-fail-under=80` | **1506 passed, 2 skipped**，覆盖率 **89.55%** |
| 变异验证（10 条） | 全部打红；五个源文件按 sha256 核对还原一致 |

变异清单（每条括号里是它守的那件事）：

1. Azure 路由改成也挂 OpenAI 前缀（M2 的正向）
2. Gemini `generateContent` 改成已实现（501 分支真的由 `implemented` 驱动）
3. Gemini 退回 catch-all 单段模板（M1 的原缺陷）
4. 不把路径里的模型写进 `payload`（单元层断言的鉴别力）
5. 整条 `model_from_path` 分支不生效（集成层断言的鉴别力）
6. `original_payload` 记成改写后的副本（原始记录不被改写）
7. body 里有 `model` 时不让路径覆盖（路径权威）
8. `split_format_suffix` 只按枚举判断（M3 的原缺陷）
9. 501 的 message 吐路由表模板而不是客户端 URL（二 §5.2 前半）
10. router 挂了一条查表查不到的路径（M2 的 split-brain，单边失配）

⚠️ `uv run pyright src tests`（全仓）另有若干错误，全部在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`。这两个文件本次一次都没碰过，属同伴的 httpx2 迁移，与本主题不相交——与 `status.md` 里记录的是同一批。
