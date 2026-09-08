# 待办台账整理报告

整理日期：2026-08-27。范围：`/home/xp/src/ghc-api-proxy-py/.dev/docs/` 下清点报告覆盖的八份台账，以及承接迁出内容的常规文档。全程未执行任何 git 命令，也未写入 `src/` 或 `tests/`；源码只作只读核实。

证据权重：下面标为「已确认」的当前实现事实均在本次整理时对照工作区源码重新核实，强度足以据以迁出台账；它们只说明本次读取时的工作区现状，不替代提交历史。并行源码工作仍在进行；2026-08-27 最后一次快照复核重新检查了承重的已修项、零命中项与两条争议项，结果见各节。

## 各份台账的处置

| 台账 | 迁出与去向 | 当前保留的未闭合项 |
|---|---|---|
| `auto-mode-classifier/deferred.md` | 迁出 0 条；清点报告第二节没有点名该台账的闭合项，本次不扩大范围。 | 5 个编号项：D6、D1、D2、D3、D4。 |
| `client-leg-formats/deferred.md` | 原「已在本轮修掉的」20 条里，18 条经当前源码或对应测试复核后迁入 `README.md`「已完成的清理记录」。另 2 条没有迁出，原因见下文专节。 | 4 条记录：2 个产品项 U-1、n-1，加 2 个待核清的文档对账项。 |
| `delivery-keepalive/deferred.md` | 迁出 14 个 D 编号项（D-1、D-2、D-3a～D-3f、D-5～D-10）与 1 条已经作废的用户文档交还项，共 15 条逻辑记录；原有完成记录、用户裁决、未采纳方案与方法教训逐字迁入新建的 `decisions.md`，未压缩。`status.md` 与 `spec.md` 的活引用同步改指新载体。 | 2 条产品项：D-4 与「错误帧的交付时机要不要做成守卫」；另保留 1 条交还用户的文档问题，即人写配置仍把 `http2_ping_interval` 写得像已生效。 |
| `error-envelope/deferred.md` | E-8、E-6、E-11 共 3 条迁入新建的 `status.md`；E-8 对 retry §4 的旧交办更新为 2026-08-27 已完成，E-6 与 E-11 则在并行源码切片报告到达后同步闭合。E-1 的注释半条另由 2026-08-27 的 `inference.py` 注释修正闭合。 | 9 个 E 编号项：E-1～E-5、E-7、E-9、E-10、E-12；E-1 只剩用户已裁决推迟的主体。 |
| `server-layout/deferred.md` | 迁出 0 条；清点报告第二节没有点名该台账的闭合项，本次不扩大范围。 | 3 个登记项：D-A、D-B、D-C。 |
| `tui/deferred.md` | §2 共 1 条逐字迁入新建的 `decisions.md`；`README.md` 已加入该文件入口。§0.5 的过期成本论证已更正。 | 5 条：§0、§0.5、§1、§3、§4。 |
| `upstream/h2-goaway/deferred.md` | 处置 2 处：§3 的完整历史层收成一行移交墓碑，现状改指 retry 主题；§5 中 `HistoryConsumer` 是否有意不接活链路这一半迁入 `findings.md` 并闭合。 | 4 条产品或调查项：§1、§2、§4、§5；另保留 §3 的编号墓碑。 |
| `upstream/retry-and-continuation/deferred.md` | 迁出 11 个完整条目或表格项：§4、8a、§9、§12、§18、§19、§22、22 之二、22 之三、22 之六、22 之四；其中当前实现状态进 `status.md`，用户裁决进 `decisions.md`，读史提示与方法教训进 `README.md`。§9 在并行源码切片报告到达后同步闭合。另从 §5 迁出 1 个刚裁决的排空子项，并从 §7 的当前成员清单移出 3 个已删除名字。需要被生产源码按编号引用的条目均留下墓碑。 | 18 个未闭合标识：§1、§5、§5 之三、§7、8b～8g、§10、§15、§16、§17、§20、§21、§22 之五、§22 之七；其它已闭合编号只作为墓碑或混合条目的闭合部分保留。 |

## 报告说该关但我核实后没关的

### `client-leg-formats` D-5

清点报告把「一次性交付的前提写成断言（路由被翻译过就 raise）」计入 20 条完成记录。当前 `src/app/server/routes/inference.py` 的 `if framer is None:` 分支没有该断言；全 `src/` 搜索 `translation_required` 与 `raise` 或 `assert` 的组合也没有相符实现。证据权重：当前源码直接反证，足以拒绝把这句作为完成事实迁入 `README.md`；但它不能独自判断守卫是被重构遗漏，还是前提已由其它构造性约束承接。因此原记录已改成待文档对账项，没有替用户重新裁定行为。

### `client-leg-formats` 启动期探测

清点报告把「启动期探测失败一律阻止启动」计入完成记录。当前源码明确不是「一律阻止」：`resolve_provider_base_urls()` 只对 401/403 继续上抛，对其它 HTTP 状态与 `httpx2.TransportError` 记 warning 后继续；`pipeline_app.py` 还会捕获 `refresh_catalogs()` 的异常并以 not-ready 状态启动。现行 `client-leg-formats/README.md` 第五节也记录了这一较窄行为。证据权重：当前控制流是直接反证，强度足以拒绝迁出；它不回答哪次后续裁决或改动取代了原记录。该句留作待文档对账项。

## 其它清点报告误差

清点报告把 `streamReplay.max_retries` 列为 retry §7 里当前仍存在的成员；本次对 `src/`、`tests/` 与人写文档复核，未找到该名字，只有一般性的 `upstream_replay_refused_while_draining` 日志词。证据权重：对该标识当前是否存在，文本检索的否定结果配有相邻正样本，足以据以从当前成员清单移除；不据此推断它历史上何时删除。原 §7 的完整沿革已迁入 `decisions.md`，当前台账只列仍存在的 `RetryBudget`、`buffered_retry.py`、`delayed_commit.py` 与 `hedge`，并继续保留 `decide_stream_ending()` 的 `COMPLETE` 形状问题。

## 2026-08-27 新裁决：排空拒绝重开后不为零提交交接

retry §5 中这一格已从待裁决改为闭合，并迁入 `decisions.md` 第六节。裁决是维持现状、整批丢弃、不为交接开口；`committed_count == 0` 表示客户端一个字节都没收到，没有「已经收到一半」的部分状态可由 `turn_interrupted` 协调，客户端重发的语义更干净。文档同时明确保留被接受的代价：上游 token 已经计费，重发会再付一次；`buffering_policy: full` 时可能丢掉并重付一整份完整回复。该格当前无需改代码，§5 的其它格未被一并结案。

## 并行源码切片在整理期间闭合的三条

实施报告 `/home/xp/.claude/jobs/0e3de57b/tmp/fix-inference-accounting.md` 在整理末段到达。除任务点名的 E-1 注释半条外，它还闭合了 error-envelope E-6、E-11 与 retry §9；本次重新对照当前源码后，将这三条分别迁入两个主题的 `status.md`，没有让已知完成项继续停在台账。证据权重：报告含定向测试与受控变异，本次又直接核对了 `stream.py` 的 `raise torn`、`inference.py` 共用 `ErrorInfo.message`、以及无 assembler 的 one-shot 结局分支，强度足以据以闭合。

## E-1 注释半条的闭合载体

原来的 J 片与 F 片均已完成且未带上这半条，台账已取消这两个失效载体，改由 2026-08-27 的 `inference.py` 注释修正闭合。实施报告 `/home/xp/.claude/jobs/0e3de57b/tmp/fix-inference-accounting.md` 已生成；当前注释明确写出 `one_shot_delivery` 会先送出已经到达的上游字节，而客户端没有 error frame，报告第 4 条与「主会话复核」还记录了有分辨力的源码断言。台账因此直接标记这半条于 2026-08-27 闭合；E-1 主体仍按用户裁决推迟。

## 我否决了什么

1. 否决不读当前源码就把 `client-leg-formats` 的 20 条整批迁出；其中 D-5 与「启动期探测失败一律阻止启动」两句被当前源码反证，故只迁出 18 条。
2. 否决继续把 `streamReplay.max_retries` 写成 retry §7 的当前成员；当前检索不支持该断言，完整历史被保留到 `decisions.md`，没有静默删除教训。
3. 否决删除按编号被生产源码引用的墓碑；已迁出的 §4、8a、§12、§19、§22 之六等只缩成闭合指针，编号不回收。
4. 否决替用户修改 `docs/.human-controlled/` 中的 `http2_ping_interval` 表述；该问题仍以交还用户事项留在 delivery 台账。
