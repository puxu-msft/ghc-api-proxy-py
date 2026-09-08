# Direct buffered Chat Completions 计划验证复评

## 评审范围

复评对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md`，冻结 SHA-256 为 `6f290bcd36bb5922859bbd76b6377645a57d6dfcefa02232e5d7f24ba25c9a7c`，命令回执与协调方给值一致。先复读原报告`260906-plan-verification-review.md`，本轮只复核F-01～F-06的修订及其相邻条款；没有重新展开全计划审计，也没有执行尚未实现的测试。

## 总体 verdict

**needs-fix，不可定稿。** 原F-01～F-06的直接要求均已关闭，但相邻复核发现2条major；0 blocker。

**Blocker 数：0。**

## 原finding逐条复评

| 原finding | 结论 | 证据 |
|---|---|---|
| F-01 | **closed** | `plan.md:255-276`先冻结literal输入与expected，再改production；`plan.md:300-302`明确新decoder和`read_events()`都对literal oracle，而不互相比作oracle，并列LF-only与drop-EOF单变量控制。 |
| F-02 | **closed（原问题）** | `plan.md:251,278-298,396-412`改为bounded feed，在memoryview上逐frame接纳，并加入同一transport chunk内`[DONE]`＋越界tail的正例与pre-reject／append-first控制；原先的同chunk缺口关闭。相邻的总内存计量缺口见RR-01。 |
| F-03 | **closed** | `plan.md:252,414`提供injectable reader、单一state实例、reader calls=N、decision／aggregation／observation同源身份断言，以及synthetic-body reparse sentinel控制；production黑盒仍只承担接线。 |
| F-04 | **closed** | `plan.md:538-542,614-622,701-709`分别在generic seam、pre-success production entry与post-header runner覆盖event limiter、单次budget、HTTP 200 raw status及固定client deadline，并明确重算deadline／绕过event signal的控制。 |
| F-05 | **closed** | 虚构的GitHub测试路径已从文件地图删除（`plan.md:67-87`）；Task 4～7均有完整pytest／Ruff／Pyright命令（`plan.md:544-550,624-634,711-721,785-795`），TUI条件命令也与`pyproject.toml:56-61`一致。 |
| F-06 | **closed** | `plan.md:22,871-882`明确unit/component、MockTransport、historical cassette、live/P6四层的实际集合与不可冒充项；Chat cassette与live均记not used/not executed，Responses cassette只能作无关回归证据。 |

## Major findings

### RR-01：bounded decoder修了同chunk截尾，却仍未把protocol state／observation副本计入cap

- **位置：** `plan.md:298,384-412`；权威合同为`direct-passthrough/spec.md:694-696`，其中明确raw buffer、protocol state及同时保留的预渲染／observation副本都计入当前持有量。
- **问题：** collector只按`cap - len(committed_raw)`给decoder容量并以`peak_held_bytes`断言raw／staging；计划没有state或projection的size接口，也没有把这些副本从remaining capacity扣除。
- **影响：** 大量content／reasoning／unknown JSON可同时保留raw bytes和解析后对象，使真实持有量超过`buffer_cap_bytes`，而新增同chunk测试仍全绿；这是保护合同失效，不是计数精度问题。C1、C3仍不成立。
- **要求：** 明确一个覆盖raw、decoder staging、Chat state及并存projection副本的统一held-size口径；加入raw本身未超cap但raw＋state超cap的正例和“忽略state size”单变量控制。

### RR-02：C1的全称仍由Task 8一句总括代替，若干关键判据没有具名缺陷控制

- **位置：** `plan.md:28,327-341,580-622,827-829,911`。
- **问题：** standard multi-choice client JSON、provider content transparency／四行mode matrix、nested／flat／malformed error carrier的exact status/body/absence、raw-vs-synthetic accounting等只列正确样本；没有逐条写“注入哪个单变量缺陷、同一入口哪条断言变红”。
- **影响：** `plan.md:829`的“each nontrivial criterion”与`plan.md:911`的已勾选全称不可执行，也不能证明失败不会由fixture／旁路代打；例如把aggregation收窄为choice 0或让provider重新强制stream，没有指定控制会判红。C1仍不成立。
- **要求：** 只为这些正确性关键项补具名控制及目标断言，不扩大成mutation campaign；至少覆盖choice丢失、provider重写mode/payload、error-envelope字段丢失和synthetic长度覆盖raw accounting。

## C1～C8复评结论

| Claim | 结论 | 证据 |
|---|---|---|
| C1 | **不成立** | 原六项所点控制已补，但RR-01／RR-02仍给出可绿的单变量缺陷；`plan.md:829,911`的全称强于实际枚举。 |
| C2 | **成立** | literal byte oracle在`plan.md:255-302,337-341,707-709`；完整对象、缺席、排序、重复／exactly-once在`plan.md:777-783,827-829`。 |
| C3 | **不成立** | calls／ledger／prepare／admission／mode／deadline／cleanup／candidate／limiter现已有明确路径与控制，但RR-01所述总held-memory accounting仍不足。 |
| C4 | **成立** | `plan.md:22,871-882`逐层限定fake、local injection、cassette与live；P6明确not executed且不得记pass。 |
| C5 | **成立** | `plan.md:14-16,24-25`保持implementation-first、不追coverage、不建proof framework；新增内容只是直接测试与一次性控制。 |
| C6 | **成立** | `plan.md:213-227,343-349,416-422,544-550,624-634,711-721,785-795,831-869`给出可复制命令；默认TUI排除与条件入口符合`pyproject.toml:56-61`和`tests/tui/conftest.py:0-14`；无`ruff format`。 |
| C7 | **成立** | `plan.md:252,414`提供shared-state component入口与reparse-forbidden控制，`plan.md:781-783`的production test仅证明投影接线。 |
| C8 | **成立（流程结构）** | `plan.md:859-898`含full regression、证据分层、独立review、finding disposition、受影响证据复跑、closeout与no-push；真实upstream／cutover不构成完成门。 |

## 被否决建议及原因

1. **否决要求新增或运行Chat cassette／P6。** `plan.md:22,871-882`已正确把缺席证据记为缺席；用户裁决允许本次不取真实provider证据，修复RR-01／RR-02不需要扩大范围。
2. **否决为RR-02建立mutation manifest或proof framework。** 只需把单变量缺陷与目标断言写进现有Task测试步骤；新增治理装置会违反本计划自己的边界。
3. **否决因RR-01退回整套bounded decoder设计。** 同chunk接纳与截尾已经闭合；剩余缺口只在统一held-size口径及其判别测试，不能把局部未闭合夸成整项作废。

## 搜索面与限制

- 复读原报告全文，并复读冻结计划的Global Constraints、File and Interface Map、Task 2～8及self-review相邻段落；对照原评审已引用的`direct-passthrough/spec.md:694-696`、当前`pyproject.toml:56-61`与`tests/tui/conftest.py:0-14`。
- 运行`sha256sum`确认评审对象未漂移；用只读检索核对cap、命令、证据层与测试路径。未运行pytest／Ruff／Pyright，也未修改计划、源码、tests或其它living docs。

## 结论

**不可定稿。** 原F-01～F-06均已按直接要求关闭；需修复RR-01与RR-02后再做定向复评。其余C2、C4～C8可沿用本轮结论，除非下一次修订触及对应条款。
