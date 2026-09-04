# 错误信封：实施状态

本文件承接已闭合的实施记录。2026-08-27 从 [`deferred.md`](deferred.md) 迁入 E-8；当前未闭合项仍以 `deferred.md` 为准，规范行为以 [`spec.md`](spec.md) 当前版本为准。

## E-8　上游流内失败事件的登记定级需要重评 —— **已闭合**

**闭合于**：2026-08-24，R 片落地（主仓 `f12f76d`）。
**当时登记的是什么**：`.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条把这件事描述为「客户端收到的与撕裂产生的帧不可区分」。自 2026-08-22 干净 EOF 改动落地后那句就不成立了——现状是**与成功不可区分**，代价比登记时重。
**现在是什么**：上游的失败事件不再被吞。直连腿原样重放上游自己的事件名与 payload，翻译腿过 IR 后按客户端方言写出，两条腿都不再以正常终结收尾。
**原交办的另一半**：`upstream/retry-and-continuation/deferred.md` 第 4 条曾仍需按新事实改写；2026-08-27 已完成该台账清理，原条目以墓碑保留，闭合记录迁入其 `status.md`。

## 2026-08-27 并行源码切片闭合

以下两条原本不在 2026-08-27 清点报告的「应该关掉」组内，但并行源码切片在本次整理结束前完成并交付了可核实报告。为维持台账只放未闭合项，现一并迁入；实施与变异证据见 `/home/xp/.claude/jobs/0e3de57b/tmp/fix-inference-accounting.md`。

## E-6　可观测性面与线路对同一事件给出两种说法

**状态**：Spec §11 排除（不改可观测性面）。
**事实**（清点 §6.1，实测）：客户端截止时间到期那一例，线路上写的是 `client_deadline_exceeded`，而完成日志行写的是「upstream stream ended without a terminal event」。成因是 `stream.py:364` 是 `return` 而非 `raise`，于是 `_tracked_delivery` 把它记成 `drained`。
**为什么值得留着**：一个读日志的人和一个读线路的人会得出不同结论，而这正是本项目花力气拉开的那类区分。

**闭合核实（2026-08-27）**：`stream.py` 写出 `client_deadline_exceeded` error frame 后现在重新抛出原 `ClientDeadlineError`，`_tracked_delivery` 因此记录 failure，不再把同一事件算作 clean drain。

## E-11　完成日志行与线路对同一次失败给出两种说法

**状态**：新登记，2026-08-24，随 K 片。**未闭合**，需要决定改不改可观测性面。

**事实**：`[FAIL] … 400 POST /v1/messages` 那一行的尾巴取自 `str(UpstreamRejected)`，也就是 `model_provider/ghc_client/errors.py` 里 `f"upstream rejected the request: {error}"` —— `{error}` 是 SDK 的 `__str__`，形如 `Error code: 400 - {'error': {...}}`（Python `dict` 的 repr，单引号、不可解析）。而客户端收到的 `message` 自 J 片起就由本项目自己构造，K 片之后在上下文超限这一格更是**完全不同的句子**（`prompt is too long: …`）。

**为什么值得留着**：Spec §4.5 花了力气把 wire 上的 `message` 从 SDK 的 `__str__` 里拆出来，理由是「本项目没有一处代码知道自己在往里放什么」——那个理由对日志行同样成立，而日志行至今还在用它。**这正是用户 2026-08-24 报来的那条记录的形态**：用户看到的是 SDK repr，客户端拿到的是另一句话，两者都为真却读不出对方。

**与 E-6 的关系**：同一类问题的第二例（E-6 是客户端截止那一格）。若要一并处理，判据应当是「完成行的失败说明取自 `ErrorInfo.message`」，而不是逐格打补丁。

**闭合核实（2026-08-27）**：上游 outcome 没有 response 时，`inference.py` 只调用一次 `describe(...)`，完成行的 `trace.detail` 与 `error_response(...)` 共用同一个 `ErrorInfo.message`；SDK exception 的 `__str__` 不再成为该完成行的另一套说法。
