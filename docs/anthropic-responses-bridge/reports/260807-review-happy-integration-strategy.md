# Anthropic Responses happy-path 四切片集成策略只读预审

- **评审范围**：只读预审共同 base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 上的四个 reviewed source HEAD：reasoning carrier v2 `8301ee938601ad86c7f72d313abc6c976a74b2a9`、non-stream response `7ddf17364d97349638d44352bbd9a9b025723ccc`、stream parser `73a6aa114647440262691651cd17e9127785c75a`、route policy `84a22c07db3923768db44a1314e5ae6d5aed2e98`。范围包括每片完整 commit range、精确 path 集、潜在文本／语义冲突、固定集成顺序与组合 gate；不修改任何代码，不把 checkpoint 集成解释为完整 bridge 产品符合性。
- **总体 verdict**：**可进入集成实现。** 唯一顺序固定为 `base → carrier v2 → nonstream → stream parser → route policy`。四片任意两片的 source range path 交集均为空，临时组合快照按全部七个 source commits 顺序三方回放无文本冲突；但 carrier 与 nonstream 存在真实的共享 producer 语义依赖，因此不能仅凭“path 无交集”任意换序。每片必须消费完整 range并形成内容等价的单片 integration commit，不得只取 tip commit。
- **blocker 数**：0。
- **major 数**：0。
- **产品状态边界**：完整 bridge 仍为 **`UNVERIFIED`**。Usage reasoning detail、完整 stream grammar／framing／strict lifecycle／sequencer、route handler／transport／retry／History 等后续边界均未因本次 checkpoint 集成关闭。
- **双视角覆盖证据——机械核对**：验证五个完整 commit object、四个 source HEAD 对 base 的 ancestry、每个完整 range 的 commit 列表与 `diff --name-status`；两两比较四片 path 集，六组交集均为空；逐行读取 carrier codec／forward／reverse／direct Messages strip、nonstream converter、stream parser、route policy 及其定向测试；扫描 nonstream 对共享 reasoning helper 的调用，扫描 stream parser 中 carrier／signature 编码引用为空，扫描 route policy 的网络 import／send／connect 调用为空；读取四份最新代码评审和 nonstream／carrier 仲裁。另在一次性临时 Git 快照中按七个 source commits回放四片，定向 checkpoint tests、独立跨片 carrier oracle与Ruff通过；全量 pytest与全量Ruff也通过。组合 Pyright 首次被共享终端外部 `SIGINT`中断，后续临时绝对路径运行又产生不可信的跨树stub解析，第三次输出被共享终端串线污染，因此本文**不把组合 Pyright写成绿色证据**，而将其保留为最终组合必跑 gate。
- **双视角覆盖证据——第一人称执行**：模拟集成者从 base 逐片做等价 squash，分别走“只取tip”“先nonstream后carrier”“用测试内共享helper生成expected”“整文件ours／theirs”“把stream parser当carrier encoder”“让route policy自行触网”六条失败路径；再沿 Responses reasoning item → nonstream shared producer → 项目主v1 signature → client echo → Responses consumer，以及同一 echo 进入direct Messages final preparation的双腿路径执行。独立组合探针确认一item一block、source order、encrypted-only、项目主v1 exact vector、consumer value-exact恢复、producer不输出upstream v1、direct Messages synthetic strip与真实Anthropic signature保留可以同时成立。

## 冻结的集成顺序与身份规则

1. **Carrier v2 先落。** 它建立项目主v1 producer／双格式consumer和direct Messages strip，是nonstream reasoning wire的共享依赖。
2. **Nonstream 第二。** 它只消费共享 `responses_reasoning_to_anthropic()`；只有在carrier已落的组合态，项目主v1 wire gate才有意义。
3. **Stream parser 第三。** 它与前两片无文本重叠，只发布semantic facts；当前切片不编码carrier，也不接renderer／sequencer。
4. **Route policy 最后。** 它与前三片无文本重叠且只作pure decision；当前切片不打开网络，不接handler／transport。

每片允许在integration分支形成一个内容等价的squash commit，但“内容等价”必须同时满足以下机械门：source root／branch／完整HEAD／base ancestry正确；`base..source HEAD`的完整commit range已列出；该range的精确path集与待提交path集相等；每个待提交path的integration blob与source HEAD blob相等；integration commit父提交等于上一片已验收commit；提交后工作树和index clean。只摘取每片tip会漏掉其第一笔`feat`提交，属于确定性错误。

## 四片完整 range、精确 paths 与潜在冲突

### 1. Reasoning carrier v2

- **完整 range**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79..8301ee938601ad86c7f72d313abc6c976a74b2a9`。
- **必须消费的 source commits**：
  1. `f19dc32b83f744f088191cf67c21c10b5aeb329c`——`feat: add versioned reasoning carrier codec`。
  2. `8301ee938601ad86c7f72d313abc6c976a74b2a9`——`fix: strip synthetic thinking from Messages wire`。
- **精确 paths**：
  - `src/app/anthropic/request_preparation.py`
  - `src/app/anthropic/thinking/reasoning_carrier.py`
  - `src/app/anthropic/thinking/responses_reasoning.py`
  - `src/app/protocols/anthropic_responses.py`
  - `tests/unit/test_anthropic_client.py`
  - `tests/unit/test_anthropic_preparation.py`
  - `tests/unit/test_anthropic_responses_request.py`
  - `tests/unit/test_reasoning_carrier.py`
  - `tests/unit/test_responses_reasoning.py`
- **共享 reasoning 文件重点**：`reasoning_carrier.py`拥有项目主v1 encode／双格式decode／direct Messages synthetic分类；`responses_reasoning.py`拥有一item一thinking block的forward producer和逐block reverse consumer；`anthropic_responses.py`的request converter消费同一decode结果。三者是一套共享基座，不能只搬codec而漏forward／reverse／request consumer。
- **Direct Messages strip重点**：`request_preparation.py`在final wire preparation删除整个项目synthetic namespace、upstream v1 prefix form及legacy sentinel对应的thinking block，并保留真正Anthropic signature。该strip只属于Messages leg；Responses converter仍须在strip之前／另一协议腿消费合法carrier。
- **潜在冲突**：与其他三片的path交集为零，预期无Git文本冲突；风险是漏掉第二个fix commit后synthetic carrier会泄漏到Messages wire，或把strip错误前移到共享入站状态导致Responses leg也失去carrier。
- **片内 gate**：精确path／blob门；carrier定向tests；项目主v1固定`opaque-😀`向量；项目bare、upstream合法payload／bare／legacy、unknown／malformed／foreign分类；一item一block与encrypted-only roundtrip；Messages synthetic全剥离＋`CAIS`保留；Responses consumer仍恢复项目及upstream合法形态。

### 2. Responses → Anthropic non-stream response

- **完整 range**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79..7ddf17364d97349638d44352bbd9a9b025723ccc`。
- **必须消费的 source commits**：
  1. `b5b82f87f17ce229e8ec85f29071f7ff6280fecf`——`feat: convert Responses JSON to Anthropic messages`。
  2. `7ddf17364d97349638d44352bbd9a9b025723ccc`——`fix: separate Anthropic response identity`。
- **精确 paths**：
  - `src/app/protocols/responses_anthropic.py`
  - `tests/unit/test_responses_anthropic_nonstream.py`
- **项目主carrier依赖**：converter没有也不应复制carrier codec；它调用共享 `responses_reasoning_to_anthropic([item])`。因此path虽不重叠，reasoning wire correctness依赖前一片已将共享producer替换为项目主v1。固定顺序不是Git需要，而是oracle需要。
- **测试假绿风险**：现有nonstream reasoning用例调用同一个共享helper生成expected。它能证明converter消费helper和block顺序，却不能独立证明helper输出项目主v1。组合gate必须使用Spec内嵌的硬编码项目exact vector，不能调用产品helper生成expected。
- **潜在冲突**：与其他三片path交集为零；语义风险是一旦先验收nonstream单树，会观察到base上的旧upstream v1 producer并得到已知假失败，或因共享helper同源expected得到假绿。
- **片内 gate**：精确path／blob门；nonstream定向tests；public `msg_` id不泄漏`resp_*`、原upstream id／model与conversion facts仍value-exact可用；text／tool／reasoning source order；unknown／server-tool／failed显式失败；基础cache usage算式。
- **组合carrier gate**：在已含carrier片的integration commit上，以硬编码项目主v1 exact bytes断言nonstream output；两个reasoning items保持两个有序thinking blocks；encrypted-only保留；client echo后逐item恢复；producer不得输出`copilot-api:`；同一echo进入Responses leg可恢复，进入direct Messages leg被strip，真实Anthropic signature仍保留。
- **后补但不阻断checkpoint**：`output_tokens_details.reasoning_tokens`当前未进入public usage／诊断facts。按既有仲裁这是完整Spec的真实required gap，但不追溯成为本happy-path checkpoint blocker。不得要求full-Spec verifier整体全绿才落本片，也不得把组合carrier gate通过写成usage已完成。

### 3. Responses stream parser

- **完整 range**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79..73a6aa114647440262691651cd17e9127785c75a`。
- **必须消费的 source commits**：
  1. `af5956be47ecf222ecd25c044436a36656206bce`——`feat: assemble Responses stream events`。
  2. `73a6aa114647440262691651cd17e9127785c75a`——`fix: preserve Responses stream source order`。
- **精确 paths**：
  - `src/app/openai/responses_stream_parser.py`
  - `tests/unit/test_responses_stream_parser.py`
- **职责边界重点**：本片只从Responses lifecycle events产出immutable semantic facts：`SourceOpened`、`CompletedBlock`、`ReasoningBlock(summary, encrypted_content)`、typed terminal与unsupported observation。源码和测试中没有`reasoning_carrier`、`encode_reasoning_carrier`、synthetic signature或Anthropic wire编码引用。
- **不能做的事**：不要为了“复用carrier”把encoder导入parser。Carrier应由后续共享renderer／semantic normalizer在`ReasoningBlock`完成后消费；parser继续只负责authoritative `.done`、identity、source／completion order与attempt-local lifecycle。
- **潜在冲突**：与其他三片path交集为零，预期无Git文本冲突；语义风险是consumer误把`SourceOpened(content_index=None)`当可渲染block，或按completion order而非source order提交。当前还没有production sequencer，不能把parser checkpoint误写为stream bridge完成。
- **片内 gate**：精确path／blob门；parser定向tests；message／tool／reasoning交错时较早open source保持commit barrier；reasoning采用item done中的authoritative summary与ciphertext；unknown item lifecycle保持typed failure；terminal不把open／unsupported item伪装为成功；静态负门确认parser没有carrier／signature编码依赖。
- **后补边界**：完整SSE framing、CRLF／multi-line data／fragmentation、clean EOF／`[DONE]`、refusal、严格事件先后、完整grammar、continuous-prefix sequencer、renderer与delivery owner均继续开放。

### 4. Typed protocol route policy

- **完整 range**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79..84a22c07db3923768db44a1314e5ae6d5aed2e98`。
- **必须消费的 source commits**：
  1. `84a22c07db3923768db44a1314e5ae6d5aed2e98`——`feat: add typed protocol route policy`。
- **精确 paths**：
  - `src/app/pipeline/route_policy.py`
  - `tests/smoke/test_route_policy.py`
- **职责边界重点**：本片仅把resolved model facts、endpoint capability、override和已知transport availability转换为typed `RouteDecision`或`RouteDecisionError`。它可以读取“transport是否可用”的事实，但不import upstream client，不send／connect，不打开HTTP／WebSocket，也不拥有fallback／retry。
- **零网络含义**：unknown／missing／conflict、unsupported override或selected leg transport unavailable时，pure policy在任何handler／transport调用之前返回错误。当前切片未接production handler，因此“零网络”由纯模块无网络入口＋后续接线时的spy call-count gate共同保证，不能仅凭smoke标题宣称真实route已验收。
- **潜在冲突**：与其他三片path交集为零；语义风险是下游handler重新推导precedence、override失败后fall through、或把HTTP／WS availability反向改写protocol leg。
- **片内 gate**：精确path／blob门；双支持默认Messages、single capability、显式override优先、override不fall through、unknown／missing／conflict fail closed、Chat非候选、`/responses`与`ws:/responses`仅证明Responses protocol capability、physical transport正交；静态负门确认模块无网络依赖。
- **后续接线 gate**：用transport spy证明任何policy error下调用数严格为零；成功decision只由driver消费一次；handler／transport不得再次推导leg或静默fallback；每个真实exchange形成可见attempt。该gate不属于当前pure-policy squash的阻断条件，但属于route启用前硬门。

## 组合 gate

### A. 集成前 provenance与范围门

- integration worktree物理root、branch与当前parent必须现场打印并验证；初始parent必须是共同base或上一片已验收integration commit。
- 四个source worktree分别验证物理root、branch、完整HEAD、clean状态及base ancestry。
- 对每片冻结`base..source HEAD`完整commit列表和精确path集合；tip-only、遗漏首commit、额外path、缺path均立即停止。
- 每片提交前逐path比较source HEAD blob与integration index blob；提交后再比较integration commit blob。比较失败不得以测试绿色覆盖。

### B. 每片增量门

- Carrier提交后：carrier／reasoning／request conversion／direct Messages preparation定向tests＋Ruff＋Pyright；硬编码项目exact vector；Messages strip与Responses consume双腿黑盒。
- Nonstream提交后：nonstream定向tests＋前述独立carrier→nonstream→echo→consumer组合oracle；保留usage reasoning detail为已知后补，不把full-Spec verifier整体作为checkpoint veto。
- Stream parser提交后：parser定向tests；source-order/open-barrier／authoritative done oracle；确认无carrier encoder引用；不得新增renderer或delivery行为。
- Route policy提交后：route smoke；frozen precedence与transport正交探针；确认无网络import／调用；不得把pure decision的绿色外推为真实route接线。

### C. 最终merged-state门

- `git diff --name-status base..final`必须精确等于四片path集合的并集，且无额外修改；每个path与其所属source HEAD最终blob相等。
- 完整组合运行全量pytest、全量Ruff、全量Pyright，且import／module-resolution oracle必须指向integration worktree。本文的临时快照已取得全量pytest与Ruff绿色，但组合Pyright没有形成可信绿证，所以最终integration不得沿用本文替代实跑。
- 重跑独立硬编码carrier组合oracle，不能只跑使用共享helper expected的现有nonstream test。
- 验证direct Messages synthetic strip与Responses consumer兼容同时成立；验证stream parser仍仅发布semantic facts；验证route policy仍是无网络pure decision。
- 最终integration commit集合做一次merged-state代码复评，重点核对shared reasoning producer／consumer、nonstream同源expected假绿、parser→未来renderer边界和route policy→未来driver边界。
- 状态文字只能写“happy-path checkpoints已组合并通过其声明范围gate”；不得写“nonstream complete”“stream complete”“route enabled”或“bridge PASS”。

## 为什么禁止 `ours`／`theirs`

1. **当前没有合法的文件级二选一问题。** 六组path交集均为空，按正确base和完整range应用不应产生文本冲突；若出现冲突，首先说明integration parent、source identity、path范围或并发状态已漂移。
2. **`ours`会静默丢掉切片。** 对新增文件使用`ours`可直接保留“不存在”，对carrier修改文件则会恢复旧producer／旧forward／缺direct strip。
3. **`theirs`会掩盖错误parent。** 即使当前source文件本身正确，整文件接受`theirs`也无法证明此前integration语义、邻接修改或测试oracle未被覆盖；它把“为什么会冲突”从证据链中抹掉。
4. **全局`-X ours`／`-X theirs`更不可接受。** 它会把偏好扩散到所有当前与未来冲突，可能无提示丢source代码、tests或共享helper接缝。
5. **正确处置**：意外冲突时立即停止，重新打印root／branch／HEAD／parent／base ancestry与冲突path，比较base、source HEAD和integration parent三方blob；若确认出现真实语义重叠，则逐hunk构造语义并集、补跨片回归并重新评审新bytes。不得用整文件checkout、restore或strategy option跳过裁决。

## 事实性发现

未发现阻止按上述策略进入集成实现的blocker或major。

[minor] `tests/unit/test_responses_anthropic_nonstream.py:5,111-115`——nonstream reasoning expected由与产品相同的共享helper生成，单独测试无法证明项目主v1 producer bytes——如果carrier未落、producer回退到upstream v1，actual与expected可一起变化而测试仍绿——保留现有测试验证converter消费关系，同时把Spec硬编码项目exact vector与producer-only组合oracle设为最终必跑gate。

[minor] 组合预演的Pyright证据未形成可信绿色——首次运行被共享终端外部`SIGINT`中断，随后两次分别受到临时绝对路径stub解析和共享终端串线影响——这不是候选代码失败证据，也不能被记为通过——最终integration必须在已绑定root、import oracle指向该worktree的独立进程中重跑全量Pyright并取得完整退出结果。

## 结构怪味扫描

- `tests/unit/test_responses_anthropic_nonstream.py:5,111-115`——**测试 oracle 与产品共享同一 reasoning helper，属于同源 expected／集成接缝假绿风险**——本轮不改 source test；在最终组合 gate 增加硬编码项目主v1 exact vector和producer-only oracle，后续可将该独立vector固化为专门跨片测试。
- `src/app/openai/responses_stream_parser.py:29-31,496-505`与未来renderer接缝——**semantic fact与wire encoding职责若在parser内合并会形成职责错位**——本轮保持parser只输出`ReasoningBlock`，后续renderer单独消费共享carrier producer并做集成测试。
- `src/app/pipeline/route_policy.py:65-144`与未来driver接缝——**下游若再次推导precedence会形成重复业务规则**——本轮保持policy为唯一pure decision入口；后续handler只消费typed decision，并以error路径transport call-count为零作接线门。

## 主观建议

无。本轮已有唯一顺序与可机械验证的集成策略，不再提供可交换顺序或`ours`／`theirs`快捷方案。

## 最终结论

**可按 `base → carrier v2 → nonstream → stream parser → route policy` 进入四切片happy-path集成。** 每片消费完整source range并形成精确path／blob等价的单片commit；carrier→nonstream是不可交换的验收顺序依赖，stream parser保持semantic-only，route policy保持无网络pure decision。任何意外冲突都先判为身份／基线漂移，禁止`ours`／`theirs`。Usage reasoning detail后补不阻断checkpoint，但完整产品持续为`UNVERIFIED`；最终放行仍需在真实integration worktree通过全量pytest、Ruff、Pyright、独立carrier组合oracle及merged-state复评。
