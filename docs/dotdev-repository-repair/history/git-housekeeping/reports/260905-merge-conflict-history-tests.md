# Merge 历史与剩余测试冲突调查

- report_id: `merge-conflict-history-tests-260905`
- attempt_id: `agent-a5eba21677d0b09bb`
- status: `in-review`
- reviewed_at_rev:
  - merge base: `e1b2baa99637349d2f552343c57769a311bfb179`
  - ours: `605d42bd85d6d25bc5e4b73dada727a893742527`
  - theirs／`MERGE_HEAD`／`origin/main`: `8ac6522896cdd3a43d796c33999595c25b8f798b`
  - dotdev authority snapshot: `refs/remotes/origin/dotdev` at `862b13748cefe3e27f8a95c7885cb3a4405345bc`
- conclusion_strength: `confirmed`，但“当前 index 尚有 12 还是 13 个 unmerged path”按下文证据边界收窄。

## 1. 调查范围与证据边界

本调查是只读调查。没有修改 `/home/xp/src/ghc-api-proxy-py` 下的源代码、测试、Git index 或 refs，没有暂存、提交、合并、还原或清理。为读取 Git 对象，所有 Git 命令均在隔离 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a5eba21677d0b09bb` 中按固定 SHA 执行；临时展开件只写入 `/tmp`。本报告是唯一写入主 checkout 的产物。

调查使用的主要方法如下：

1. `git merge-base` 重新确认 merge base。
2. `git rev-list --count` 与 `git log --graph` 重建 4／50 的分叉历史。
3. `git merge-tree <base> <ours> <theirs>` 对固定对象做无副作用三方重建。
4. 对 13 个冲突路径分别读取 base／ours／theirs blob，并用三方 diff 定位 28 个 hunk。
5. 对两个重点测试文件使用题目给出的 stage blob，并与相应 commit path history 对账。
6. 从 `origin/dotdev` 读取当前活规格，核对哪些冲突是行为分叉，哪些只是 API／import 重构。

主 checkout 的 Git 操作在本 subagent 的隔离护栏下被拒绝；协调者随后明确调整为按对象 SHA 调查，不再访问主 checkout。因此，本报告不能把“当前 index 仍有多少 unmerged path”写成已独立复验的现状。能够确认的是：

- 此固定 base／ours／theirs 的新鲜三方 merge 产生 13 个带冲突标记的路径、28 个 hunk。
- 调整前只读取得的主 checkout `MERGE_MSG` 列出了同样的 13 个初始冲突路径。
- 调整前对主 checkout 的冲突标记扫描也命中了同样 13 个路径。
- 如果当前 `git diff --name-only --diff-filter=U` 确实只有 12 个，则表示其中一个路径已在 index 中被标为 resolved；工作树里仍有 marker 或 `MERGE_MSG` 仍列初始冲突，均不能反证 index 状态。

因此，题目中的“12 个冲突文件”与对象级 merge 和 marker-bearing path 数量不一致，但本报告不把这一点扩大成“当前 index 一定仍有 13 个 unmerged path”。

没有运行测试。原因不是推断测试会失败，而是当前没有一个已解决的 merge candidate；在任一单侧或含 marker 的文件上运行测试不能验证最终组合。

## 2. 核心结论

### R-01：固定对象的冲突分母是 13 个路径、28 个 hunk

八个生产文件共 19 个 hunk，五个测试文件共 9 个 hunk。文件和 hunk 计数由三方对象重建直接得出，足以用于本报告的逐 hunk 建议；它不替代当前 index 的 `diff-filter=U` 读数。

### R-02：远端并非一条简单线性“更新版”，而是在 merge base 的另一侧合入了 Responses observability 分支

`c27da611e9439f38e8df427bb4182909244b0203` 的两个 parent 是 `d9535032c8b35554b90a1f268d8d659bb62f3873` 与本次 merge base `e1b2baa99637349d2f552343c57769a311bfb179`。远端 `6200600d756803ac15a7bdd0f90db303ca605188` 与本地 `bb5783f17f8f21017010a14d00b762b49ee6cc13` 是共同基点附近的并行实现。不能仅依据“theirs 是 origin/main”就把 `bb5783f` 判为过期，也不能仅依据本地提交时间较晚就丢掉远端完整观测模型。

### R-03：`4b7d74f` 的 effort translation 必须移植到远端新架构，不是被替代的重复功能

当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/spec.md` §Request-level `ThinkingEffortIntent` 明确规定 request-level IR 使用 `ThinkingEffortIntent | None`，并把 response-level reasoning carrier 作为另一类事实。它还规定 target thinking profile、source header、send/count 同形和 conversion facts。因此应保留本地 effort 语义，同时采用远端 route-bound descriptor、tool choice、reasoning bridge、prompt admission 和 async count worker。

### R-04：`bb5783f` 的 completed／client-action 行为有当前规范支撑，不能用远端 renderer 行为覆盖

当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §7.1、§10，以及 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的“着色规则”“描述回复的用词跟随上游”“验收”，都明确承认 `bb5783f`，并规定：

- `client_action_requirement` 返回 `required`／`not_required`／`unknown` 三态。
- buffering bool 只有 `not_required` 为 `false`；`required` 和 `unknown` 均为 `true`。
- `completed` 仅在 terminal output 分类完备且没有 required／unknown action 时可着绿。
- terminal `output` 缺席或类型错误必须显示 `client_action?(unclassified)`。
- 未知 item 必须显示 `client_action?(<原生 type>)`。
- terminal `output` 是最终 action 集合、顺序、名称和 `output_index` 的 authority，不能读取 `done` 到达顺序或 buffering bool 反推。
- 重复 action 必须逐项保留；TUI Spec 的精确 oracle 是 `completed function_call(Bash) function_call(Bash) custom_tool_call`，不是 `function_call(Bash,Bash)`。

### R-05：远端 observability 基础设施更丰富，但其当前行为至少有六处与现行规范不一致

1. `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_action.py` 对缺失／未知 `tool_search_call.execution` 给出 `UNKNOWN + delivery_required=False`；规范要求 `UNKNOWN + True`。
2. 同文件把缺失 `shell_call.environment` 判为 `REQUIRED`；规范将条件类型缺失／未知 discriminator 归为 `UNKNOWN`，buffering 投影仍为 `True`。
3. `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py` 的远端 renderer 当前把所有 `completed` 着绿；规范要求同时读取 status、typed actions 与集合完备标志。
4. 远端未知 action 拼写是 `client_action(type?)`；规范精确拼写是 `client_action?(type)`。
5. `45e7cfb972b6f9df5874a8455d9961d692f2bba2` 把相邻同类调用合成一段；当前 TUI Spec 的 exact oracle 要求逐项输出。
6. `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_observation.py` 当前在 complete terminal body 上按 index upsert stream item，而不是以 terminal `output` 替换完整集合；非 object output 元素会被跳过，而规范要求生成 unknown fact，不能伪装 absent。`output` 缺失／malformed 时也缺少独立的 `client_action_classification_complete` 集合事实，已有 stream items 可能掩盖 terminal snapshot 不完备。

### R-06：两个重点测试文件的正确组合分别是“远端 fixture/API＋本地 effort 和规范 oracle”与“纯 import 并集”

`/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py` 不能整文件选边；它需要远端 provider-bound fixture、catalog/configure hook 和 observer API，同时保留本地 CATALOG 追加、effort helper、source-header tests 和 completed/client-action 的规范 oracle。

`/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_loading.py` 只有一个 import hunk；正确结果是同时导入远端 provider config classes 与本地 thinking profile helpers，测试主体没有语义二选一。

### R-07：测试冲突有一部分是生产冲突的直接转录，但不是全部

- `test_request_log.py` 与 `test_responses_passthrough.py` 是 action type ownership、classifier、renderer 和 delivery policy 冲突的直接转录。
- `test_translation_driver.py` 是 `ThinkingEffortIntent` 与 `ToolChoiceIntent`／reasoning bridge 必须共存的直接转录。
- `test_pipeline_app.py` 是混合体：前三个 hunk 是 import 并集，第四个是两个独立 helper 在同一点插入，第五个才是旧 reader 与远端 observer 的直接行为冲突。
- `test_config_loading.py` 主要是独立 import 添加相撞，不代表生产行为二选一。

### R-08：只消除 13 个 marker 文件仍会留下 clean-auto-merge 语义冲突

至少要复核 `/home/xp/src/ghc-api-proxy-py/.claude/settings.json`、`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembling.py`、`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py` 与 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log_file.py`。详见第 8 节。

## 3. 分叉历史

### 3.1 merge base

`e1b2baa99637349d2f552343c57769a311bfb179`：`feat: notice a doubly-closed output item, and offer to settle upstream's drifting ids`。

`git merge-base 605d42bd85d6d25bc5e4b73dada727a893742527 8ac6522896cdd3a43d796c33999595c25b8f798b` 返回该哈希。`git rev-list --left-right --count` 分别确认 base→ours 为 `0 4`，base→theirs 为 `0 50`。

### 3.2 本地独有 4 个提交

1. `6c6504d39f2fdd836294e480a96830595684a54d`，`chore: allow background edits to project docs`：只修改 `.claude/settings.json`，增加 `worktree.bgIsolation=none`。远端后续已包含同一字段。
2. `4b7d74f56b8b0264b481a2fefe275a233979fbb2`，`feat: translate effort between Messages and Responses`：引入 `ThinkingEffortIntent`、target thinking profile、source-header snapshot、send/count 同形、conversion facts 和大批配置／翻译／集成测试。
3. `bb5783f17f8f21017010a14d00b762b49ee6cc13`，`feat: report contextual Responses completion status`：引入 terminal status、typed client actions、classification completeness、颜色／文本规则和测试。
4. `605d42bd85d6d25bc5e4b73dada727a893742527`，`feat: update configuration and message translation documentation for clarity and accuracy`：只修改用户控制的 `config.example.yaml` 和 `message-translation.md`；不产生本报告中的 13 个源码／测试 marker 冲突。

提交链为：

```text
e1b2baa → 6c6504d → 4b7d74f → bb5783f → 605d42b
```

### 3.3 远端独有 50 个提交

以下 50 个缩写哈希均经对象历史扫描，包含两个 merge commit：

```text
8ac6522 4f01e78 2e1f3c8 3ec2ed8 40cc267 9a1ffc3 998d0f7 4d64b7d 1212d00 8d95738
bf3d1a0 4aa1e39 831885c 8e0ff3f 7b04510 76eb9c0 18347af 11bc422 d9afe1a 328ef20
c5f8a66 e04a5cd 40f51e3 883284b d2c9798 1389108 6844ffe b9b0a9b b6d3c2d fa5a001
fd12516 05e56ec 7812fd8 93467d9 b881a90 fedbe5c 04de0c5 5e73417 fcb6982 b233751
0cd1641 33cf387 2b73409 39274d7 990e377 45e7cfb c27da61 d953503 6200600 9077069
```

内容级重点读取或检查过的远端提交为：

```text
6200600d756803ac15a7bdd0f90db303ca605188  feat: preserve Responses facts through observability
c27da611e9439f38e8df427bb4182909244b0203  merge: reconcile Responses delivery changes
45e7cfb972b6f9df5874a8455d9961d692f2bba2  fix: group Responses tool calls in completion lines
b23375165ae0a72d7a5e6271f6d48c3236e55666  fix: preserve Responses reasoning order in logs
3ec2ed85e147f107098a502e8ee90032795b39e0  fix: preserve tool semantics across translation writers
831885c98d480b03d05929f2e6ff9080492482c7  feat: reject oversized responses prompts before send
9a1ffc3c5f2a6e27ba5c97ab1589019bba9eca88  perf: offload count token estimation without blocking dispatch
998d0f717adf3493958035b2eda94bdc5ec14bbe  feat: configure count-only local estimate multiplier
8d957389eb738cd9b0e9d4cf542b4707bb2c5cab  fix: stabilize prompt admission boundaries
4aa1e39eaee313dcfaada3e2843fe3bbdfb0c983  fix: align hosted search loss accounting
18347af55137b87d5d7e8680c818a3c4bb3cc3af  feat: restore hosted web search response blocks
b9b0a9bf501f1ce58bb19967dd8cc5670ec0505c  feat: preserve cross-protocol reasoning structure
c5f8a669e5bc519795a481d84d0b93e87b8f8dc4  fix: stabilize response stream ids by default
1389108e614b797da067213cc67062d4d444c143  feat: add atomic delivery batches
328ef2066e7b094b77745224a90a88c526dff564  feat: record prompt admission by attempt
b881a907b1a85084ff4f9b0d81f7e2fb9152f3f1  feat: record upstream body end timing
0cd1641aae90b4758a6ec4fc0fa053d24bf5906c  feat: add xingchen model provider
fcb6982cc4c9dcfa26eb4c82b3ecc764dc1a784d  feat: add codebuddy model provider
1212d004db8d456bdeb9afbcad20be9e7db22969  test: bind pipeline fixtures to providers
8ac6522896cdd3a43d796c33999595c25b8f798b  fix: format positional log arguments before rendering
```

`5e734173f59c784b038f6e5eecdfe7667947aed6` 汇合 Codebuddy 与 Xingchen provider 两支，解释了 config schema、composition 和测试 fixture 的 provider 类型变化。

## 4. 冲突路径、hunk 数与 blob

| 绝对路径 | hunks | base blob | ours blob | theirs blob |
|---|---:|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py` | 1 | `4d5a99798b95fcfb47850c81f32c44b88691867a` | `12f97185294ef21a193982dce97febca895f7f5a` | `6787ee285cae0081b1b22ec14660abb277840a94` |
| `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py` | 4 | `f26bd46133d643579ba99dbd928f26fcf60f9710` | `92c1116d55c64e17fb3b308da240234f53a335c7` | `8dccd6b9c5c7044f2ce7097dfca8e7049f1f56ef` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_passthrough.py` | 2 | `06e0c6b143f8d1c94fa5fae8fd78388dc7b1d4e4` | `e9679b6bec6c71f52127137b73a9374628d93ecb` | `0c59df4fbadcc4e0b1a4c306fdfb2fb7bf154f35` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py` | 4 | `0badbe7abaeaa46bb0926f623e719740e33f7812` | `57ab044454fa8a59a7d21a16ce3e3916400b0807` | `dbf4f0b74c253de7afb2f5e754d454f266d123cc` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/routing.py` | 1 | `c10b93c7418bd041062098989d0be5e499606ad7` | `74bf9bae63a9f99bcccbdb72b39fb299099e7c2b` | `f02e885b76344aeee9272483d39e1895362844fa` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/anthropic_messages.py` | 3 | `a0a2f2770bf04538bcd9b459b583257620bc3e21` | `e8ba54c07f3ffd701bb3c08f4010300341f58140` | `946594fe85986b3942864ffe12ff32c67c2e48cf` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py` | 2 | `edcb45f6ca9af84e3882094c9d314a3585e4529f` | `666888538930593e1dc3726ddf6cb9b42094d29f` | `7f393326651ce60685759feea608a851de763779` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/semantic.py` | 2 | `4ffcc4153e61124453c4b4ea9135f169e4caffd6` | `9ef4ab8bb1e6616feb1c25803f71ad62656d69fd` | `be9d5aed6a96c8eb07d2aad7ff8edb014f9074fb` |
| `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py` | 5 | `efbf16f741c2b2d9f65bd209fdf77f11150a469c` | `952694a65b3ec481fc14041b788cd0a07b856677` | `6c953ce213fd7c1fd6947582fa8ae4e25f07943e` |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_loading.py` | 1 | `d1e2ff28e54946e8e38e10af9f9d281dd811026d` | `2f83c3ed067ecab02625076902be13008ad86adb` | `d19e5c5700b57adad996a231ac5d546113f00fff` |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py` | 1 | `92d08a08f2fb92c47ec144e549e3b6bf84a954c8` | `e2175415b4f6646f924089fd2e798759aa55e470` | `820906588095ccef29e12c286f056e8684bef29e` |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py` | 1 | `d46bddb183fd93773691fa4f5811e93ef823a39c` | `e21d2fe20007b611ee6c0a40a2ffbd4d7704982a` | `6823127985dbe267506cd72f6c2eb5f034b1f90c` |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/translation_driver/test_translation_driver.py` | 1 | `5427a758cf7a6a91edecdb2d8bbba3a4181020e7` | `23b08c25b79f1c9428ec7f4ac8804a7a2fc7d693` | `f92b5b2188066a6d34bab161c44f456aa6036d4f` |

合计：生产文件 8 个、测试文件 5 个、hunk 28 个。

## 5. 逐 hunk 建议

### 5.1 `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py`，1 hunk

**H1，`format_completion_line` 的 Responses ending 分支。** 不应整段选 ours 或 theirs。保留远端 `ResponseObservation` 的原始 output 顺序与 reasoning/action 交错能力，但把 renderer 改成当前 TUI Spec 的精确合同：

- `completed` 只有 terminal output 分类完备且 action-free 时着绿。
- required／unknown／unclassified 时 `completed` 不着色。
- unknown 写成 `client_action?(type)`。
- terminal output 缺失或类型错误写 `client_action?(unclassified)`。
- 重复 action 分开输出，不采用 `45e7cfb` 的 `function_call(Bash,Bash)` 合并。
- 保留 `b233751` 带来的 reasoning／action 原始相对顺序。

`facts` 字段来自 `4b7d74f`，与此 hunk 正交，必须保留。

不建议继续让本地 `format_terminal_status` 与远端 `format_response_observation` 各自产生一份答案。推荐让 `ResponsesObserver` 成为采集 authority，再投影到 `RequestTrace`／`RequestLine` 与 renderer；这样既保留远端 richer data，又遵守本地规范。

### 5.2 `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py`，4 hunks

**H1，imports。** 合并 `ConversionFact`、`Loss` 与远端 `ClientActionRequirement`、`JsonAvailability`、`ResponseObservation`、`TokenAdmissionObservation`。`ClientActionRequirement` 只能有一个类型所有者，推荐统一到 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_action.py`；不能同时保留 assembling 中的同名 enum。

**H2，`RequestTrace` fields。** 保留本地 `facts`，并保留远端 `token_admissions`、`response_observation` 及 timing fields／methods。现行规范要求的 `terminal_status`、typed actions、classification completeness 仍需持久化，但应由最终 `ResponseObservation` 统一投影，不能由两条解析链独立计算。

**H3，absorb methods。** 保留远端 `absorb_response`、`absorb_token_admissions`；保留本地方法名 `absorb_conversion`，其 body 同时刷新 `losses` 和 `facts`。不能退回远端旧名 `absorb_losses`，因为自动合并后的 `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py` 已在所有相关返回路径调用 `absorb_conversion`。

**H4，`request_line_from_trace`。** 采用远端 defensive copy 形式，并补本地 facts：

```python
upstream_conn=dict(trace.upstream_conn),
losses=tuple(dict(loss) for loss in trace.losses),
facts=tuple(dict(fact) for fact in trace.facts),
```

同时必须把 terminal status／actions／completeness 纳入远端“replacement attempt 清空旧 projection”的同一动作。否则旧 attempt 已经吸收的本地字段会在新 attempt 失败或重开时泄漏，而远端新增的 `absorb_response` 注释正是为防这一类 stale projection。

### 5.3 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_passthrough.py`，2 hunks

**H1，旧 `_ALWAYS_CLIENT_ACTION`／`_NEVER_CLIENT_ACTION` 表。** 两边都意图删除，结果应为空；不要恢复 base 表。

**H2，`requires_client_action`。** 结构上采用远端“共享分类结果的 delivery projection”，语义上按现行 Spec 修正 canonical classifier：

- `required → True`
- `not_required → False`
- `unknown → True`
- 缺失／未知 `tool_search_call.execution → UNKNOWN + True`
- 缺失／未知 `shell_call.environment → UNKNOWN + True`

如果保留 `read_responses_client_actions`，它也必须调用同一 canonical classifier；不得继续使用 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_actions.py` 内另一份独立 taxonomy。

完整 terminal `response.output` 必须替代而非补丁式合并此前 stream items；非 object item 必须生成 unknown fact，不能被跳过。

### 5.4 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py`，4 hunks

**H1，imports。** 保留本地 `Sequence` 与远端 `deepcopy`，即 `Callable, Mapping, Sequence` 加独立 `deepcopy` import。

**H2，`handle` 翻译。** 保留本地 `_translate_with_facts`，但把 helper 的 provider 二次 lookup 改为使用远端已经由 route 固定的 `descriptor`。推荐签名为 `_translate_with_facts(chain, context, route, descriptor, source_headers)`，内部调用 `translation_target(descriptor, chain.thinking_profiles)`。

**H3，`handle_count_tokens` 开头。** 两边都保留。先 `_check_count_deadline(deadline_at)`，随后在 `shape_request` 清理 translated-path headers 前执行 `source_headers = context.source_headers_for_translation()`。

**H4，count 翻译。** 与 H2 使用同一个 `_translate_with_facts` 和同一个 descriptor＋profiles。不能让 send 与 count 走不同 target 构造。

远端 admission、async local worker、replay、observer 和 descriptor generation 全部保留；本地 conversion facts／source header／thinking profile 通过这些新接缝继续传播。

### 5.5 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/routing.py`，1 hunk

**H1。** 保留本地 `compile_thinking_profiles` 和 last-fullmatch `select_thinking_profile`；将 `translation_target` 适配成远端 descriptor snapshot API，而不是恢复 provider 二次查询：

```python
def translation_target(
    descriptor: ModelDescriptor,
    thinking_profiles: CompiledThinkingProfiles,
) -> TranslationTarget:
    selected = select_thinking_profile(thinking_profiles, descriptor.id)
    pattern, profile = selected if selected is not None else ("", None)
    return TranslationTarget(
        model_id=descriptor.id,
        reasoning_efforts=descriptor.reasoning_efforts,
        thinking_profile=profile,
        thinking_profile_pattern=pattern,
    )
```

否决 `translation_target(provider, model_id, profiles)`：它在 routing 之后重新查询 catalog，可能与 route 已绑定的 descriptor generation 不一致。

### 5.6 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/anthropic_messages.py`，3 hunks

**H1，`_PASSTHROUGH_KEYS`。** 取并集，必须同时含 `output_config` 与 `tool_choice`。

**H2，`to_anthropic_messages`。** 依次保留 `_restore_thinking(payload, request)`、`_apply_responses_thinking(payload, request, target)` 与 `_restore_tool_choice(payload, request)`；后两者作用于不同字段，不互相替代。

**H3，`_restore_thinking` 尾部。** 保留本地 `ThinkingEffortIntent`／`EffortSource.ANTHROPIC_TOP_LEVEL` 逻辑，删除远端旧 `request.reasoning`／`ReasoningIntent` body；随后完整保留远端 `_restore_tool_choice`。

原因：现行 bridge Spec 明确将 request-level IR 定为 `ThinkingEffortIntent | None`，且 response-level reasoning carrier 是另一类事实。保留旧 `request.reasoning` 会同时违反规范并与本地自动采用的 `reasoning.py` API 不兼容。

### 5.7 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py`，2 hunks

**H1，reasoning imports。** 保留本地 `RESPONSES_EFFORTS`、`EffortSource`、`ReasoningResolution`、`ThinkingEffortIntent`、`align_effort`；保留远端 `reasoning_bridge` 与 `tool_choice` imports；删除旧且合并后无调用者的 `resolve` import。

**H2，`_PASSTHROUGH_KEYS`。** 取并集，包含 `reasoning` 和 `tool_choice`。

自动合并后的 reader／writer 已能同时承载 `thinking_effort` 和 `tool_choice`；不要恢复 `request.reasoning`。

### 5.8 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/semantic.py`，2 hunks

**H1，imports。** 使用 `ThinkingEffortIntent`、`ThinkingTargetProfile` 与远端 `ToolChoiceIntent`；删除旧 `ReasoningIntent`。

**H2，`SemanticRequest` fields。** 同时保留：

```python
thinking_effort: ThinkingEffortIntent | None = None
tool_choice: ToolChoiceIntent | None = None
```

删除旧 `reasoning: ReasoningIntent | None`。`TranslationTarget` 中本地新增的 `thinking_profile`／`thinking_profile_pattern` 与远端 `reasoning_efforts` 同时保留。

这不是字段改名与字段新增二选一：effort intent 与 tool choice 是正交语义；response reasoning content 由远端 `reasoning_bridge.py` 承担。

### 5.9 `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py`，5 hunks

**H1，collections／copy imports。** 保留本地 `Mapping`，并保留远端 `deepcopy`。

**H2，terminal／driver imports。** 保留 `driver`，因为本地 send／count target tests 直接调用它；按规范保留本地颜色端到端测试时，也保留 `DIM`、`GREEN`、`RESET`、`TerminalCapabilities`。

**H3，pipeline imports。** 取完整并集。`RequestContext, WireFormat` 与本地 translator types 保留；远端 `EVENT_ATTEMPT_FAILED`、`EVENT_ATTEMPT_PREPARE`、`FrozenSubscribers`、`Subscription`、`PipelineRetry`、`ResponsesObserver` 全部保留。

**H4，helper 插入点。** 本地 `responses_observability_sse` 与远端 `responses_web_search_sse`、`incomplete_unsolicited_search_response`、`incomplete_unsolicited_search_sse` 均保留；它们覆盖不同场景。

**H5，旧 buffered reader test 名称。** 保留远端 `test_a_direct_buffered_responses_reply_is_observed_before_translation` 的新名称和 body；旧 `test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it` 的前提已被远端 whole-body observer 推翻。与此同时，本地五个 streaming terminal/action tests 不能原样丢掉，应迁移到远端 observer 接线并继续按当前 TUI Spec 断言。

fixture/API 必须采用远端版本：

- `make_provider(..., catalog=...)`。
- `GithubCopilotProviderConfig`。
- `make_client(..., catalog=..., configure_chain=...)`。
- `selected_catalog` 同时传给 provider 和 `/models` 启动响应。
- 保留本地在 `CATALOG` 新增的 `reasoning-full-model`、`reasoning-none-only-model` 与 Claude thinking capabilities。

本地 `_EXPECTED_DRIVER_THINKING_TARGET` 的 send／count 两个测试继续成立，但生产 helper 必须改成 descriptor＋compiled profile 后再满足它们。

### 5.10 `/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_loading.py`，1 hunk

**H1，imports。** 直接取并集：

```python
from app.config.schema import CodebuddyProviderConfig, GithubCopilotProviderConfig, ProxyConfig
from app.pipeline.routing import compile_thinking_profiles, select_thinking_profile
```

其余 local profile tests 与 remote provider reload／pinning tests 位于不同区域，可同时保留。这是 import-level 冲突，不是行为二选一。

### 5.11 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py`，1 hunk

**H1，imports。** 采用远端类型所有权：`ReplyDialect` 从 assembling，`SseEvent`，以及 `ClientActionBasis`／`ClientActionObservation`／`ClientActionRequirement` 从 `response_action`。不要从 assembling 导入第二套 `ClientActionRequirement`。

本地 `test_conversion_facts_do_not_add_console_fields` 与 observability 冲突无关，必须保留。

本地 terminal-status tests 需要改写到远端 observer fixture，而不是继续直接构造旧 `ClientAction`：

- 保留本地颜色与 unclassified 语义。
- 使用规范拼写 `client_action?(future_tool_call)` 和 `client_action?(unclassified)`。
- action 重复逐项输出。
- 保留远端 reasoning／action 交错顺序断言。
- 更新或移除远端要求 `function_call(Read,Read,...)` 的 grouping tests。

如果 `format_terminal_status` 不再是最终 renderer，应从 imports 和直接单元断言中移除，避免测试继续固定被替代的内部 API；行为 oracle 应留在对 `format_completion_line`／最终 aggregate 的断言上。

### 5.12 `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py`，1 hunk

**H1，imports。** 保留远端 `Terminal` 与 `DeliverySession`。三态 enum／classifier 从 canonical `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_action.py` 导入，不从 assembling 导入。

本地 `test_responses_client_action_requirement` 可改写为检查 canonical classifier 的 `.requirement` 与 `.delivery_required`，但远端 `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/test_response_observation.py` 已有更完整固定表，避免再复制一份漂移表。

本地 batch merge test 仍有价值，因为它验证跨 added／done 合并后再分类；其中 missing execution 的期望必须按 Spec 为 `True`。

本地 terminal action tests 应移到 observer／request-log 层或改为验证 canonical projection；不要继续要求 PassthroughAssembler 自己持有第二套最终 truth。远端 `DeliverySession` atomic delivery tests 必须保留。

### 5.13 `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/translation_driver/test_translation_driver.py`，1 hunk

**H1，imports。** 取并集：

- Anthropic translator 的 `from_anthropic_messages`、`render_anthropic_thinking`、`to_anthropic_messages`。
- Responses translator 的 `from_openai_responses`、`to_openai_responses`。
- reasoning 的 `EffortSource`、`ThinkingEffortIntent`、`ThinkingTargetProfile`。
- reasoning carrier 的 `RESPONSES_ENCRYPTED_CONTENT`、`decode_reasoning_carrier`。

所有本地 effort tests 与远端 reasoning bridge／tool choice／hosted search tests 均保留。它们验证不同维度，不应以“同在 translator 文件”为由择一。

## 6. 两个重点测试文件的 base／ours／theirs 深入结论

### 6.1 `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py`

stage blobs：

- base：`efbf16f741c2b2d9f65bd209fdf77f11150a469c`
- ours：`952694a65b3ec481fc14041b788cd0a07b856677`
- theirs：`6c953ce213fd7c1fd6947582fa8ae4e25f07943e`

base 是 4443 行，ours 是 5559 行，theirs 是 7612 行。三方重建产生 5 个 hunk。

#### 正确 fixture／API 组合

远端 fixture 必须作为骨架：

- `make_provider` 新增 `catalog`，使用 `GithubCopilotProviderConfig`。
- `make_client` 新增 `catalog` 与 `configure_chain`。
- `selected_catalog` 同时供 provider 初始 snapshot 和 app startup `/models` response 使用，避免 fixture 自己制造两份 catalog generation。
- `configure_chain` 是远端 admission／retry／observer tests 的可控接缝。

本地内容应叠加而非覆盖：

- `CATALOG` 对 Claude models 的 `reasoning_effort` capabilities。
- `reasoning-full-model` 与 `reasoning-none-only-model`。
- `build_thinking_profile_recording_chain`。
- source-header snapshot helper。
- send／count 共同 target 与 facts tests。
- streaming completed/client-action tests。

#### 必须同步的五组终局 assertion

这些是当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的 exact oracle，不是从旧实现倒推：

1. terminal 显式 `output=[]`，即使 stream 另含 unattributed event，也应得到 clean `completed`；开启颜色时 `completed` 为绿色。
2. terminal output 只有完整 `message` 时，同样 clean completed，不能把所有 item 都当 unknown。
3. terminal `output` 缺失或类型错误时，必须得到 `completed client_action?(unclassified)`，且 `completed` 不绿。
4. terminal output 含未知原生 type 时，必须得到 `completed client_action?(future_tool_call)`，且不绿。
5. terminal output 依次为 `function_call(Bash)`、重复 `function_call(Bash)`、无名 `custom_tool_call`，而 done events 反序且带 stale server-side tool-search facts 时，最终必须严格以 terminal output 为 authority，输出 `completed function_call(Bash) function_call(Bash) custom_tool_call`，三项恰好一次，顺序不变，`completed` 不绿。

远端 `test_a_direct_buffered_responses_reply_is_observed_before_translation` 应保留，但它暴露另一个规范问题：当前 direct-passthrough Spec §10 仍把这组新 terminal/action 展示限定为 direct Responses streaming，并把 non-stream whole-body reader 写为 deferred。解决 merge 前必须同步 Spec 或明确撤回超前行为，不能把该测试本身当作规范授权。

### 6.2 `/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_loading.py`

stage blobs：

- base：`d1e2ff28e54946e8e38e10af9f9d281dd811026d`
- ours：`2f83c3ed067ecab02625076902be13008ad86adb`
- theirs：`d19e5c5700b57adad996a231ac5d546113f00fff`

base 是 369 行，ours 是 503 行，theirs 是 599 行。只有一个 import hunk。

必须保留的本地 assertions：

- bundled regex 正确覆盖官方 model families。
- 邻近但不支持的 model 不被误命中。
- 多个 fullmatch 中最后一个用户 pattern 生效。
- 同 pattern override 使用通用 recursive deep merge，未点名 profile 字段继续继承。

必须保留的远端 assertions：

- `GithubCopilotProviderConfig`、`CodebuddyProviderConfig` 的 discriminated-union 类型。
- provider 增删、type 改变和 restart-only graph pinning。
- Xingchen／Codebuddy 路径和 selector 恢复。

正确结果仅是 import 并集；没有理由删任何一侧的测试主体。

## 7. 测试冲突是否是生产冲突的转录

| 测试冲突 | 判断 | 必须同步的生产面 |
|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py` | 部分是。前三个 hunk 是 imports，H4 是独立 helper 同点插入，H5 直接转录旧 reader 被远端 observer 替代；同文件的本地 terminal assertions 又转录现行 Spec | `request_log.py`、`request_trace.py`、`response_observation.py`、`response_action.py`、driver／routing effort 接线 |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_loading.py` | 不是行为冲突，主要是独立 import 添加相撞 | `schema.py` 的 provider union 与 thinking profile 配置，两者已干净自动合并 |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py` | 是 | action type ownership、terminal status／actions／completeness、exact rendering、颜色、reasoning order |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py` | 是 | canonical action classifier、unknown bool projection、batch 合并、DeliverySession |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/translation_driver/test_translation_driver.py` | 是，但属于两个正交功能的并集 | `ThinkingEffortIntent` 与 `ToolChoiceIntent` 同时存在，reasoning bridge 与 request effort 分层 |

还必须同步两个没有 marker 的测试文件：

1. `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/test_response_observation.py` 当前明确断言 missing／unknown `tool_search_call.execution` 的 `delivery_required=False`，与 direct-passthrough Spec §7.1 的 `unknown → True` 相反。固定表中该项及后续 unknown-execution assertions 都要更新。
2. `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log_file.py` 的自动合并会保留本地 `terminal_status`、`client_actions`、`client_action_classification_complete` JSONL assertions。若最终以 `ResponseObservation` 为唯一采集源，这些字段必须由它投影并保持；若改为只保存嵌套 v2 observation，则必须先修订现行 Spec，不能只删测试。

本地 conversion facts 的闭环 assertions 也必须保留：

- `test_conversion_facts_do_not_add_console_fields`
- `test_conversion_facts_are_durable_without_becoming_losses`
- `test_exact_thinking_profile_fact_reaches_jsonl`
- `test_last_matching_user_thinking_profile_fact_reaches_jsonl`
- `test_rejected_thinking_profile_facts_reach_jsonl`
- `test_count_path_conversion_facts_reach_jsonl`

它们分别钉住“可持久化但不污染控制台”“facts 不冒充 losses”“send／count 与拒绝路径均不丢 provenance”。

## 8. 无 marker 的语义冲突

### 8.1 `/home/xp/src/ghc-api-proxy-py/.claude/settings.json`

新鲜对象级自动 merge 会生成重复 `worktree` key：本地 `6c6504d` 与远端 `2e1f3c8` 都加入 `bgIsolation=none`，Git 按文本位置把两份都保留。远端最终文件已经包含该设置，正确结果应采用远端单份 `worktree` section，并保留远端简化后的 permissions；不要让本地提交制造第二份 key。

这是一处 clean textual merge，但 JSON duplicate key 的解释依赖 parser，不能视作无冲突。

### 8.2 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembling.py`

自动 merge 会把本地 `ClientActionRequirement` 与 `ClientAction` 加进远端扩展后的 `Terminal`。与此同时，远端已经在 `response_action.py` 定义另一份同名 enum。两个 `StrEnum` 即使 value 相同也不是同一个 identity，`is` 比较和类型检查会分裂。

建议统一 enum／classifier ownership 到 `response_action.py`，其余模块只导入或做轻量 projection，不复制 taxonomy。

### 8.3 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py`

自动 merge 会把远端 `Dialect.requires_client_action: Callable[..., bool]` 改成本地 `client_action_requirement: Callable[..., ClientActionRequirement]`。远端 `response_action.py` 则有 `ClientActionObservation(requirement, basis, delivery_required)`，本来用于分开“可观察事实”与“delivery policy”。机械自动 merge 会把这层分离重新压扁。

建议保留一个 canonical classifier，并提供两个 projection：事实读 `.requirement`，buffering 读 `.delivery_required`。按当前 Spec，`delivery_required` 应等于 requirement 不是 `NOT_REQUIRED`。

### 8.4 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log_file.py`

自动 merge 会让本地 legacy terminal fields 与远端 v2 finalized observation 同时进入测试。两者可以共存，但只能是同一 observer 的派生 projection，不能由 Terminal 与 ResponsesObserver 分别计算后恰好相似。尤其 replacement attempt 时，旧字段必须随远端 legacy projection 一并清空。

### 8.5 规格与远端 non-stream observation 的漂移

当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §10 与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 仍明确把 terminal status／typed client-action 展示限定为 direct Responses streaming，并把 non-stream whole-body reader 记为 deferred。远端 `6200600` 已实现 buffered direct Responses observation，并用 `test_a_direct_buffered_responses_reply_is_observed_before_translation` 固定。

这不是本报告可通过选 hunk 代替的决策。根据项目“Spec 先于可观察行为”的规则，应在 merge 完成前把远端行为纳入当前 Spec，或回退未获合同承接的行为。现有代码本身不能反向授权改写 Spec，但若该行为是经过评审的 agent-derived 扩展，Spec 可按自身修订权限即时更新；不能把纠正停在本报告里。

## 9. 被否决方案及原因

1. **整文件选 ours。** 否决。会丢失远端 provider-side `ResponseObservation`、attempt replacement 清理、token admission、body timing、tool choice、reasoning bridge、hosted search、atomic delivery 和新 fixture API。
2. **整文件选 theirs。** 否决。会丢失 `4b7d74f` 的现行 effort 合同，并直接违反 direct-passthrough／TUI Spec 对 unknown projection、completed 着色、unclassified 与逐项 action 输出的规定。
3. **逐 hunk 机械取并集。** 否决。会产生两个不相等的 `ClientActionRequirement` enum、两份 taxonomy、旧 `resolve` 的悬空 import、`request.reasoning` 与 `thinking_effort` 双模型、provider 二次查 catalog，以及同一 reply 的两套展示事实。
4. **只处理 marker 文件。** 否决。`assembling.py`、`passthrough.py`、`test_request_log_file.py` 与 `.claude/settings.json` 已证明存在不会报冲突的语义碰撞。
5. **保留远端相邻 function-call grouping。** 否决。现行 TUI Spec 的 exact oracle 明确要求重复 action 逐项输出；“重复计数仍在”不能代替精确展示合同。
6. **按远端现状把 unknown tool-search 扣住。** 否决。现行 direct-passthrough Spec §7.1 明文规定只有 `not_required` 映射为 `false`，`unknown` 必须映射为 `true`。
7. **继续使用 `translation_target(provider, model_id, profiles)`。** 否决。它会在 routing 后再查询 provider，破坏远端 route-bound descriptor 的 catalog generation 一致性。
8. **保留旧 `ReasoningIntent` 与 `request.reasoning`。** 否决。它与本地 `reasoning.py` 新 API 不兼容，也违反 bridge Spec 对 request-level `ThinkingEffortIntent` 与 response-level reasoning state 分离的规定。
9. **删除本地 terminal/action 回归场景，声称远端测试已完全替代。** 否决。远端当前 tests 正在固定与现行 Spec 相反的颜色、unknown projection、unknown 拼写和 action grouping；它们不能作为这些本地 assertions 的替代 oracle。

## 10. 推荐解决顺序

1. 先统一 `response_action.py` 的 canonical enum／classifier，并按现行 Spec 修正 unknown projection。
2. 修正 `ResponsesObserver` 的 terminal-output authority、集合完备与 malformed item 行为。
3. 决定并实现 observer → `RequestTrace` → `RequestLine` 的单向 projection，避免 Terminal 与 observer 各自产生不同答案。
4. 再解决 `request_log.py`、`request_trace.py`、Responses passthrough 三个生产冲突及其三组测试。
5. 解决 `semantic.py` 的 `ThinkingEffortIntent + ToolChoiceIntent` union。
6. 解决两个 translator 的 effort＋tool-choice／reasoning-bridge union。
7. 解决 `routing.py` 的 descriptor＋profile target，再解决 `driver.py` 的 send/count 共用接线。
8. 最后按上述生产 API 解决五个 marker test files；不要先让测试适配旧 API 再倒逼生产结构。
9. 复核无 marker 的四个 clean-auto-merge 接缝，尤其 `.claude/settings.json` duplicate key。
10. 同步 direct-passthrough Spec 与远端 non-stream observation 的状态，再运行 targeted tests 和项目全套验证。

## 11. 合并候选产生后的验证建议

以下命令只是建议，当前报告没有把它们写成已运行证据：

```bash
uv run pytest tests/int/test_pipeline_app.py tests/unit/config/test_config_loading.py tests/unit/observability/test_request_log.py tests/unit/observability/test_request_log_file.py tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/test_response_observation.py tests/unit/pipeline/translation_driver/test_translation_driver.py tests/unit/pipeline/translation_driver/test_reasoning.py
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

测试运行必须发生在冲突全部解决、clean-auto-merge 接缝也修正后的候选树上。单侧测试结果不能外推到最终组合。

## 12. 我最没把握的三个判断

1. **当前 index 是 12 还是 13 个 unmerged path。** 对象级 merge、`MERGE_MSG` 和 marker-bearing path 都给出 13；隔离护栏下没有在协调者调整后重读主 checkout index。调用方应以当下 `git diff --name-only --diff-filter=U` 为现状权威，本报告的 13 是初始／对象级冲突分母。
2. **最终内部 projection 应保留哪些 legacy fields。** 规范要求 status、typed actions、completeness 持久化，远端 v2 finalized record 已能保存更丰富 observation；最佳内部落点需要结合最终 record schema 决定。本报告能确认的是不能保留两个独立 classifier／collector，不能丢规范事实。
3. **远端 non-stream observation 的最终处置。** 当前代码与测试已实现，当前 Spec 仍写 deferred。项目规则决定必须先同步 Spec 或回退行为，但“采用哪一边”不应由本次只读冲突调查擅自裁定。

## 13. 执行本契约时遇到的摩擦

- 本 subagent 被隔离 worktree 护栏禁止对主 checkout 执行 `git -C /home/xp/src/ghc-api-proxy-py ...`，即使命令只读。协调者随后把任务调整为按固定 SHA 在隔离 worktree 中调查，并提供两个重点测试的 stage blob。
- 这一限制不影响 Git 历史、对象内容、merge-base、4／50 计数和三方 hunk 重建；它影响的是“当前主 checkout index 此刻仍有多少 unmerged path”这一项现状事实，因此报告已收窄该结论。
- 无其他阻塞。

## 14. 交付声明

- delivery_complete: true
- completed_at: 2026-09-05
- finding_total: 8
- conflicts_object_level: 13
- production_conflict_files: 8
- test_conflict_files: 5
- conflict_hunks_total: 28
- hidden_clean_merge_surfaces: 4
- rejected_approaches: 9
- tests_run: 0
- source_or_index_changes: 0
- handoff: 调用方需在主 checkout 重新读取当前 `diff-filter=U`，按本报告解决生产语义后同步测试，并处置 non-stream Spec 漂移；本报告本身未对 resolved candidate 做运行验证。
