# Direct buffered Chat Completions 计划验证最终复评

## 评审范围

复评对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，冻结 SHA-256 为 `7a8ff1230aab624bdca8a79acd7afc64ddab74d2a663743941ae4b6e07c67a27`，本轮`sha256sum`回执一致。复读上一轮final rereview后，只复核RR-01、RR-02及新增handoff／finalizer相邻条款对C1、C3、C4、C6、C7的影响；未重新展开全计划审计，未执行尚未实现的测试。

## 总体 verdict

**needs-fix，不可定稿。** RR-01、RR-02仍为closed；新增handoff／finalizer接缝留下1条major，0 blocker。

**Blocker 数：0。**

## 原finding逐条复评

| 原finding | 结论 | 证据 |
|---|---|---|
| RR-01 | **closed且未回退** | `plan.md:252,371`保留state/projection size接口；`plan.md:427-477`保留统一`BufferedMemoryAccount`；`plan.md:485-501`仍在raw/state mutation前预留总量，并保留raw＋state越界、同chunk`[DONE]`／tail及zero-state-size控制。 |
| RR-02 | **closed且未回退** | `plan.md:383`保留choice-0控制；`plan.md:720-730`保留provider重写payload/mode、error-envelope字段丢失、synthetic长度覆盖raw accounting及两类retry时钟／limiter控制，且均指定同入口目标断言。 |

## Major findings

### RR-03：reopen结果把replacement failure与本地拒绝压成`None`，finalizer无法保留正确失败或保证request事件一次

- **位置：** `plan.md:791-804`；权威三分法为`direct-passthrough/spec.md:254-266`，最终candidate还必须另记replacement failure（`design.md:120-124`）。
- **问题：** `reopen`只返回`BufferedCandidate | None`；`None`既不携带replacement的exception／origin，也不表明replacement attempt是否真正打开，但Step 2仍要求“record replacement failure separately”并对旧candidate调用`request_failed(error)`，此处可用的`error`只有旧body failure。
- **现有接缝证据：** `driver.py:221-246,279-296`的`replay_prepared()`返回含`outcome.error`的`HandledRequest`；`direct_driver/base.py:438-460`还会在replacement pre-header终局失败时自行发布request-failed。压成`None`会丢replacement事实，并可能再由旧finalizer发布第二次request-failed。
- **测试缺口／影响：** `plan.md:824-834`虽测fallback和一般finalizer计数，却未要求“replacement已开且headers前失败”同时断言replacement error identity／origin、旧snapshot与全request仅一次terminal event；C1、C3被该邻接修订破坏。
- **要求：** 让reopen返回可区分`OpenedCandidate`／`AttemptFailed(error, attempt_opened)`／`ReopenRefused`的typed outcome，并明确唯一request-finalization owner；用同一production入口注入pre-header replacement failure，分别判红错误归因和双request-failed。

## 指定claims复评

| Claim | 结论 | 证据 |
|---|---|---|
| C1 | **不成立** | RR-01／RR-02的具名控制仍在，但RR-03所述replacement-pre-header failure没有同入口的错误归因与exactly-once terminal-event控制。 |
| C3 | **不成立** | Memory／deadline／limiter／ledger等原断言仍在；然而`plan.md:791-804`无法表示replacement failure来源并留下request-finalization双owner，fallback/candidate lifecycle仍可错误。 |
| C4 | **成立** | `plan.md:23,997-1008`仍明确fake/local/cassette/live各层不可冒充项，Chat cassette与P6/live仍为未执行而非pass。 |
| C6 | **成立** | 架构新增`response_handoff.py`及其测试已进入文件地图、Task 4和Task 8的pytest／Ruff／Pyright命令（`plan.md:41,50,520-534,638-656,956-995`）；TUI与`ruff format`边界未变。 |
| C7 | **成立** | `plan.md:123,260-261,485,501`仍保证collector只调用一次reader并让同一state服务decision／aggregation／observation；Task 7只消费显式snapshot（`plan.md:884-886`）。 |

## 被否决建议及原因

1. **否决重开RR-01／RR-02。** 统一内存账户和四类具名控制均仍存在；RR-03是新增handoff/finalizer接缝问题，不应把已关闭问题整体否定。
2. **否决要求真实provider、Chat cassette或P6来验证RR-03。** 失败分类与事件所有权是本代理内部控制流，可由MockTransport production入口确定性构造；真实上游证据不能替代该oracle。
3. **否决建立新的proof framework。** 一个typed reopen outcome和一组现有入口测试足以关闭问题，不需要manifest、hash gate或状态机式验收系统。

## 搜索面与限制

- 核对冻结hash，读取计划的shared contracts、Task 2～8相关修订，并对照当前`replay_prepared()`与`DirectDriver._handle_failure()`源码以及既有Spec三分法。
- 只执行`sha256sum`、`rg`和文件读取；未运行pytest／Ruff／Pyright，未修改计划、源码、tests或其它living docs。

## 结论

**不可定稿。** RR-01、RR-02仍closed；需关闭RR-03后再定向复评C1／C3。C4、C6、C7未被本次架构修订破坏。
