---
report_id: retry-continuation-review-round-seven-disposition
status: applied
disposition_of: reports/260824-review-round-seven.md
followup_disposition_of: reports/260824-review-round-seven-followup.md
applied_in:
  main: bb17558
  parent: b5bc8f9
followup_applied_in:
  main: 63a33a7
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

---

# 复评（第七轮 followup）处置

对 [`260824-review-round-seven-followup.md`](260824-review-round-seven-followup.md) 的处置。裁决 `pass-with-fixes`，0 blocker、0 major、2 minor、1 nit。

**全部采纳，无驳回。** 落在主仓 `63a33a7`。

| 编号 | 级别 | 处置 | 落点 |
|---|---|---|---|
| F01 | minor | 采纳 | helper 先清掉 Python 自己造的那条临时回边，再判环；清完仍可达则记 note 不建链接 |
| F02 | minor | 采纳 | `tore_after_terminal` 独立成字段（trace → line → 完成行一段），`elif` 改 `if`，不再决定状态 |
| F03 | nit | 采纳 | 三处 residue：过期的 `asyncio.shield` 陈述、重复半句、stdlib 全称收窄为「本仓样本」 |

## 这一轮真正的教训只有一个，两处同形

**F01 与 F02 是同一个错误在两个层面上。** 把两个可以同时为真的事实写进一个互斥结构：

- F02 在**渲染层**：`max_tokens` 交接与终结后撕裂同时成立，`if/elif` 让前者吃掉后者。
- F01 在**对象图层**：cleanup 失败与 primary 已有的 context 同时存在，`__context__` 只有一格，写新的就丢旧的。

两处我都是先把「常见情形」当成了「全部情形」。判据不是「读起来像不像两选一」，而是**「有没有一条路径上两件事同时成立」**——这个问题要显式问出来，因为默认答案总是"像两选一"。

## 关于 F01 我自己踩了两次的那个坑

同一个环检查，我先后错在两个方向，且两次都有测试通过：

1. **守卫过宽**（第一次）：`_reaches` 用在每一处写入上，在正常路径上恒真击发，cleanup 失败被整个丢弃，三条既有测试变红——这次是测试救了我。
2. **守卫过窄**（第二次）：只守 carry，于是 carry 在它唯一存在理由的那个形状里从不执行。**这次测试是绿的**——因为我写的 carry 测试连续两次直接调用 helper，第二次进来时没有 active primary，只证明了安静情形。复评走真实形状才测出来。

**判据**：为一个「只在特定上下文成立」的行为写测试时，测试必须复现那个上下文。连续两次直接调用不等于「在 except 块里调用」。

## 被推翻的两条我写的断言

评审逐条核了我的数字与全称，推翻两条，均已就地改正：

1. `note_tear_after_terminal` docstring 说「replayed attempt 不会在自己的 terminal 之后撕裂」——**假的**，评审用两 attempt 探针直接打中。真正不可能的是「记录一次之后再有第二次」，因为那条分支 break 整个循环。
2. 「标准库里没有 falsey 的 `BaseException`」——**没有穷举证据**。改成「本仓跑到的异常都是 truthy」，并说明这是关于样本的陈述。契约是 `BaseException` 给的，代码按契约写，不按样本写。

评审同时确认成立的数字：五处 pairing production callsite、falsey 变异下排除新增判别器后 `1591 passed`、shield 变异按 loop report 打红。至于我说的「三条既有测试变红」，评审明确写了那是未提交的第一版、无法从提交恢复，因此不作为放行依据——这个处理是对的。

## 并行开发下的一处记录

复评期间同伴在同一棵主树上落了 `a7a0e05`（干净 EOF 也交接）与两个 `.dev` 提交，并且有 10 个文件的未提交改动。因此：

- 我在混合树上跑出的 `1677 passed` **不是我这次提交的数字**。只提交自己 8 个文件之后解包 `63a33a7` 重跑，得到 `1655 passed, 2 skipped, 90%`，这才是。
- `deferred.md` 一度是混合的（§20 是同伴的、§22之七 是我的）。等我提交时同伴已自行提交了 §20，所以我那一笔只含自己的部分——我第一版提交信息说它带上了同伴的改动，是错的，已 amend 更正。
- `status.md` 里同伴那一行始终没动，由他们自己提交。

**教训**：共享树上「我的全量绿」和「我的提交的全量绿」是两个数，前者会因为同伴的未提交改动而偏高。
