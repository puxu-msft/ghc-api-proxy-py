---
report_id: retry-continuation-review-round-seven-disposition
status: applied
disposition_of: reports/260824-review-round-seven.md
applied_in:
  main: bb17558
  parent: b5bc8f9
written_at: 2026-08-24
---

# 第七轮评审处置

对 [`260824-review-round-seven.md`](260824-review-round-seven.md) 的逐条处置。原件是时间点记录，不改；本文是处置账。

**结论：7 条发现 + 2 条未计级建议，全部采纳，无一驳回。** 落在主仓 `bb17558`。

## 处置表

| 编号 | 级别 | 处置 | 落点 |
|---|---|---|---|
| R7-01 | minor | 采纳 | `sse.py`、`keepalive.py` 两处改用 helper；`test_session_liveness_keeps_upstream_error_primary_when_close_fails` 的 pull 带上 root cause，断言改成「root 仍在 `__cause__`、close 失败在 `__context__`」 |
| R7-02 | minor | 采纳 | helper 契约重写：同对象直接 raise；已有 `__context__` 挂到新 cleanup_error 之下而非覆盖；`_reaches` 守护新链接 |
| R7-03 | minor | 采纳 | 四处 `or` → `is None`；另补 `_counted_upstream` 的活路径测试 |
| R7-04 | minor | 采纳 | `asyncio.shield` → `asyncio.wait({cleanup_task})`；补装 loop exception handler 的回归 |
| R7-05 | minor | 采纳 | `stream.py` 归因注释改写为当前事实，并区分 §22之六（已闭合）与 §22之七 |
| R7-06 | nit | 采纳 | 测试改名并收窄措辞到 `begin_attempt`；写清本测试不区分两种读法 |
| R7-07 | nit | 采纳 | `:1477` 改成逐个列名的五个对象 |
| 建议 1 | 未计级 | 采纳 | second-cancel 测试改 Event 同步 |
| 建议 2 | 未计级 | 采纳 | pyright helper 改 `getattr` + `isinstance` |

## 落实过程中自己犯的两个错，值得单独记

这两条都不是评审说的，是我按评审动手时新造出来又自己抓回来的。记下来是因为它们各自代表一类。

### 一、守卫在正常路径上恒真击发，把它要保护的东西整个丢掉

修 R7-02 时我把 `_reaches` 环检查**同时**用在了 `primary.__cause__ = cleanup_error` 与 `primary.__context__ = cleanup_error` 两处写入上。结果三条既有 `session_liveness` 测试全红，症状是 `ValueError('pull failed').__cause__ is None`——close 失败**根本没被记录**。

原因：close 在 primary 正被处理时失败，Python 已经把 primary 设成 `close_error` 的隐式 `__context__`。于是 `cleanup_error` 到 `primary` 恒可达，`raise primary from cleanup_error` **每一次**都构成环。那个环是 Python 自己造的常态，`traceback` 用 seen-set 走它，从来不是缺陷。

**判据：一个在正常路径上每次都击发的守卫不是守卫。** 最终只守护 carry 那一条——因为只有它是一条此前不存在的新链接。

同族已记在案：`.dev` 的 `deferred.md` §21 与项目记忆里「护栏拦的是整次调用」。这一条的形态是新的：守卫本身写对了，但**适用面**取的是全集而不是差集。

### 二、测试是绿的，而变异证明它什么都没测到

修 R7-04 写的第一版 `test_cleanup_that_fails_after_a_cancellation_leaves_no_unconsumed_future` 一次就绿。变异回 `asyncio.shield` **仍然绿**——它压根没复现评审说的那个组合（我把 `pending` 与 stream 的角色搭错了，取消也没落在 close 里）。

改法是先写探针把现象钉死（`shield` 得到 `['RuntimeError exception in shielded future']`，`asyncio.wait` 得到 `[]`），再照探针的形状重写测试。

**判据：新写的回归测试第一次就绿，必须变异；「它绿了所以修好了」在这里恰好是反的。** 见技能 `my-skills:trusting-a-green-result`。

### 附带：R7-03 那处本来就没有任何东西看着

`inference.py` 的 `_counted_upstream` 那处 `or`，变异回去之后 `tests/unit` + `tests/int` 共 1591 条全绿。四个同形站点里，被测到的是另外三个。**同一机制有多个实例时，「有测试」是按实例算的，不是按机制算的。**

## 评审自己标注的三条低把握，我的看法

原报告「我最没把握的三个判断」列了三条。逐条回应：

1. **R7-02 定 minor 而非 major**——同意 minor。我没有找到「同一 primary 在一次真实请求里连续遭遇两个独立 cleanup failure」的可达组合，评审也没有。改都改了，级别之争不影响处置。
2. **second-cancel 测试不列 flake**——同意，且已按建议改成 Event 同步，这条问题不再存在。评审 25 次未复现只支持「当前未观测到 flake」，不支持「绝对稳定」，改成 Event 之后连这个问题都不必回答。
3. **R7-01 定 minor**——同意。两处残留调用点当前无 production caller 是事实，但正如评审所说，那不是把已知会丢 root cause 的行为留在受测实现里的理由。已统一。

## 未闭合

- **§22之七 的族级映射取舍**：要不要为消除误归因放弃 h2 族级映射，仍是产品裁决，需用户决定。见 [`deferred.md`](../deferred.md) §22之七。
- **`test_a_run_on_another_port_leaves_the_incumbent_its_record`**：评审第一次全量跑到一次随后无法复现的失败（pidfile 跨进程时序），单独重跑绿。评审明确写了这只能排除对本次 diff 的归因，不能反过来宣称该测试没有 flake。**这条仍开着，且不属本主题**——登记在此以免丢，归属应是 lifecycle 主题。
