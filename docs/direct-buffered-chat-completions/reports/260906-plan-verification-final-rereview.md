# Direct buffered Chat Completions 计划验证最终复评

## 评审范围

复评对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，冻结 SHA-256 为 `4de5826286c5661a91de89966762f035ea3cf2fe0cc435db4fc288189570766a`，本轮`sha256sum`回执一致。复读上一版final rereview后，只复核RR-01～RR-03及新增handoff／finalizer相邻条款对C1、C3、C4、C6、C7的影响；未重新展开全计划审计，未执行尚未实现的测试。

## 总体 verdict

**pass，可定稿。** RR-01、RR-02保持closed，RR-03已关闭；本轮未发现blocker或major。

**Blocker 数：0。**

## Finding复评

| Finding | 结论 | 证据 |
|---|---|---|
| RR-01 | **closed且未回退** | `plan.md:123,261,371,409-487,501`仍保留统一`BufferedMemoryAccount`、state/projection size接口、raw＋state越界及同chunk cap控制；新增handoff/finalizer不改变collector计量。 |
| RR-02 | **closed且未回退** | `plan.md:383,720-734`仍保留choice丢失、provider重写payload/mode、error-envelope字段丢失、synthetic长度覆盖raw accounting及retry时钟／limiter的具名单变量控制。 |
| RR-03 | **closed** | `plan.md:789-823`以typed三态保留打开成功、replacement失败和本地拒绝；`plan.md:630-636,830-842`把attempt与request finalizer分槽，replacement禁止发布request terminal，outer runner唯一终结request。 |

## 相邻复核

- Initial-only ownership已补全：initial pre-header失败仍由原driver发布一次request failure；只有initial成功streaming handoff创建outer request finalizer，replacement成功不创建第二份（`plan.md:630-636,858-860`）。
- Replacement pre-header失败保留exact error identity、origin与attempt index，同时保留旧candidate body／snapshot；production与runner入口都断言exactly-one request terminal，controls分别压成`None`、创建第二finalizer及让inner driver提前发event（`plan.md:795-806,830-842,858-866`）。
- Success已移到final body的ASGI send-return之后；send raise/cancel走两个finalizer的cancelled分支而不先发布success，修订没有把yield误当delivery完成（`plan.md:834,858`）。
- 新handoff文件与测试继续位于精确pytest／Ruff／Pyright命令中；证据分层、TUI默认排除与禁用`ruff format`条款未被改写（`plan.md:520-538,642-662,956-1040`）。

## 指定claims复评

| Claim | 结论 | 证据 |
|---|---|---|
| C1 | **成立** | RR-03的正确样本与多项单变量控制走相同runner／production入口，并指定error identity、origin、index、fallback、finalizer count及event count断言（`plan.md:858-866`）；RR-01／RR-02控制仍在。 |
| C3 | **成立** | Typed reopen不再丢replacement事实；attempt／request终结owner分开，outer runner唯一花post-header ledger并唯一发布request terminal，send-return后才成功（`plan.md:630-636,819-842`）。 |
| C4 | **成立** | `plan.md:23,1029-1040`继续明确fake、local、cassette与live/P6各层不可冒充项，P6/live未执行不记pass。 |
| C6 | **成立** | `response_handoff.py`、finalizer测试与修改路径均在Task 4及Task 8精确命令中（`plan.md:520-538,642-662,956-1027`）；TUI条件入口和`ruff format`禁令未变。 |
| C7 | **成立** | `plan.md:123,260-261,485,501`仍保证每frame只读一次并由同一state服务decision／aggregation／observation；handoff只传immutable snapshot（`plan.md:583-597,918`）。 |

## 被否决建议及原因

1. **否决继续扩大reopen outcome。** 当前三variant已区分candidate打开、已打开attempt失败与本地拒绝，variant加error/index足以保留RR-03所需事实。
2. **否决要求真实provider、Chat cassette或P6。** RR-03是本代理内部控制流与事件所有权，MockTransport production入口已有鉴别力；真实上游不能替代该oracle。
3. **否决新增proof framework。** 具名单变量控制直接落在现有runner与production测试中，能分别判红信息压缩、第二request finalizer和inner terminal event，无需额外治理层。

## 搜索面与限制

- 核对冻结hash，读取计划的shared contracts、Task 2～8中memory／control／handoff／finalizer相邻条款；对照当前`replay_prepared()`与`DirectDriver._handle_failure()`的既有行为。
- 只执行`sha256sum`、`rg`和文件读取；未运行pytest／Ruff／Pyright，未修改计划、源码、tests或其它living docs。

## 结论

**可定稿。** RR-01～RR-03均closed；C1、C3、C4、C6、C7未被本次架构修订破坏；本轮范围内为0 blocker、0 major。


---

## SHA-256 `7ed5221a…` 定向复核追加记录

复核对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，完整SHA-256为`7ed5221af6938d861690532ee0554d2809ebe572b82a063e05947c12de31a484`；本轮`sha256sum`回执一致。范围仅为RR-01～RR-03及相邻finalizer文义同步。

**Verdict：pass，可定稿。Blocker 0，major 0。**

- RR-01仍closed：统一`BufferedMemoryAccount`、state／projection size接口、raw＋state越界与同chunk cap控制保留于`plan.md:123,261,371,410-500`。
- RR-02仍closed：choice丢失、provider重写payload/mode、error-envelope字段丢失及synthetic长度覆盖raw accounting的具名控制保留于`plan.md:383,729-733`。
- RR-03仍closed：owner表明确attempt finalizer只管limiter／attempt events，initial request finalizer由outer runner持有且replacement不创建第二份（`plan.md:139-140`）；Task 5把initial pre-header、initial successful handoff与replacement三种finalization路径分开（`plan.md:631-637,697`）；Task 6显式消费initial request finalizer，并保留typed reopen三态、replacement error identity／origin／index、旧fallback与exactly-one request terminal控制（`plan.md:791-843,859-867`）。
- 相邻send-return语义保持正确：final body仅在ASGI send返回后发布attempt／request success；send raise/cancel只走cancelled，不先发布success（`plan.md:835,859`）。因此本次文义同步没有破坏C1或C3；C4、C6、C7相关条款未改且仍成立。

本追加复核只执行`sha256sum`、`rg`与文件读取；未运行尚未实现的pytest／Ruff／Pyright。未发现新的blocker或major。


---

## SHA-256 `d3f272ee…` Task 2／3定向复核追加记录

复核对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，完整SHA-256为`d3f272eed18507a999f969fb926b1878c0e997b5258ae960aafd1b7b729852a0`；本轮`sha256sum`回执一致。范围仅为Task 2／3新增接口、正确样本＋单变量控制、证据边界和命令可执行性。

**Verdict：needs-fix，Task 3暂不ready。Blocker 0，major 2。**

### T23-01：collector步骤仍调用被明令禁止的batch `feed_bounded()`，没有落实逐frame重算cap

- **位置：** `plan.md:448-464,536-540`。
- **问题：** 新接口要求cap-aware collector只用`propose_one_bounded()`并在每个frame的state mutation后重算容量，且明确“must not use”batch API；实际collector步骤仍逐字命令调用`feed_bounded(...)`。
- **影响：** 实施者照Step 3会一次提议多个frame，后一个frame看不到前一个frame增加的state held bytes；同chunk raw＋state越界仍可能被接受，RR-01／C3因此被计划内部矛盾重新打开。
- **要求：** 把Step 3改为循环调用`propose_one_bounded(memoryview_suffix, remaining_capacity=...)`，每次apply并更新MemoryAccount后再推进offset／重算capacity；控制须把实现退回batch proposal并让同chunk raw＋state样本判红。

### T23-02：same-state component test引用已删除的`to_completion_payload()`，验证步骤不可执行

- **位置：** `plan.md:262,407,554`。
- **问题：** Task 2公共接口与materialization合同只定义`projection_reservation()`＋`to_completion_bytes(reservation)`；Task 3的关键same-state test却仍调用全计划唯一一处`to_completion_payload()`。
- **影响：** 按文档写测试会在方法查找处失败，无法到达reader calls=N、same-state identity或reparse-forbidden目标断言；这种红由setup/API漂移代打，C1与“命令／步骤可执行”要求不成立。
- **要求：** 改为先取reservation、在MemoryAccount预留后调用`to_completion_bytes(reservation)`，再做observation reservation／materialization；明确reader计数与sentinel失败仍落在目标断言。

## 已确认未回退的相邻判据

- Independent literal baseline仍由改动前literal table提供，改后decoder与`read_events()`都对异源literal expected；没有新增同源oracle（`plan.md:265-316`）。
- null／array／malformed、large key／big int／stdlib size、logprobs／usage、unattributed／layer collision、carrier-before-freeze与single raw bytes均有正确样本和具名单变量控制（`plan.md:312,339-419`）。
- 统一logical MemoryAccount、raw＋state、deep／many materialization以及same-state意图仍存在（`plan.md:405-407,479-552`）；T23-01／T23-02是把这些判据接到可执行步骤上的两个残口。
- Choice丢失、provider重写、error field、raw accounting、两条retry入口的event limiter／fixed deadline控制仍在（`plan.md:419,781-793,909-919`）。证据表继续明确无Chat cassette、P6/live未执行且不得记pass（`plan.md:1083-1092`）。
- Task 2与Task 3的pytest／Ruff／Pyright命令所列路径在各自Task完成后存在且命令形状可执行（`plan.md:423-427,558-562`）；问题是T23-02中的测试步骤调用，不是CLI selector。

本追加复核只执行`sha256sum`、`rg`与文件读取；未运行尚未实现的pytest／Ruff／Pyright。未要求真实provider、cassette或新proof framework。


---

## SHA-256 `b2577401…` T23修复定向复核追加记录

复核对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，完整SHA-256为`b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`；本轮`sha256sum`回执一致。范围仅为T23-01、T23-02及其相邻Task 2／3判据。

**Verdict：pass，Task 3 ready。Blocker 0，major 0。**

- T23-01已关闭：collector逐transport chunk持有caller-owned memoryview cursor，每次只调用`propose_one_bounded()`取得至多一frame，先reserve raw＋prospective state、apply并推进cursor，再为同chunk下一frame重算capacity；同时明禁batch`feed_bounded()`（`plan.md:448-464,536-540`）。
- T23-01的正确样本与控制具备鉴别力：同chunk frame A显著增长state、frame B只在旧raw-only预算下可放入；正确路径保留A并拒绝B，batch mutation必须在body／state／reader-count目标断言变红（`plan.md:552`）。
- T23-02已关闭：same-state test按`projection_reservation → BufferedMemoryAccount reserve → to_completion_bytes`及`observation_reservation → reserve → observation_facts`执行；reader calls=N、state generation／identity和reparse sentinel均落在目标断言，不再引用`to_completion_payload()`（`plan.md:554`）。
- Independent literal baseline仍不依赖新decoder（`plan.md:265-316`）；null／array／malformed、large keys／big ints／stdlib size、logprobs／usage、unattributed／layer collision、carrier-before-freeze及single raw bytes均保留正确样本和具名单变量控制（`plan.md:312,339-419`）。未发现新同源oracle。
- 统一logical MemoryAccount、raw＋state、2,000,000-byte/deep/many materialization controls与single-state计数仍在（`plan.md:405-407,479-554`）；choice丢失、provider重写、error field、raw accounting及两条retry入口event limiter／fixed deadline控制仍在（`plan.md:419,781-793,909-919`）。
- Task 2／3的pytest／Ruff／Pyright命令路径与任务产物一致（`plan.md:423-427,439-445,556-564`）；证据表继续明确没有Chat cassette、P6/live未执行且不得记pass（`plan.md:1083-1092`）。未发现不可执行命令或步骤。

本追加复核只执行`sha256sum`、`rg`与文件读取；未运行尚未实现的pytest／Ruff／Pyright。未发现新的blocker或major，可继续Task 3。
