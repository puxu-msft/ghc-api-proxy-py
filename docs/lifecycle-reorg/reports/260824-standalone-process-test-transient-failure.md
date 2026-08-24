---
report_id: standalone-process-test-transient-failure
status: open
observed_at: 2026-08-24
observed_by: 第七轮独立评审（gpt-opus），在评审主仓 `0f2e7f1` 的提交树时顺带撞到
severity: 未定级（观测一次，未复现）
---

# `test_a_run_on_another_port_leaves_the_incumbent_its_record` 观测到一次瞬时失败

## 这份文档为什么在这里

它不属于 upstream/retry-and-continuation 主题。评审是在跑那个主题的全量回归时撞到的，如果只留在那份评审报告里，就会随着主题归档一起沉下去。放在 `lifecycle-reorg/reports/` 是因为被测对象是独立进程与 pidfile 的生命周期。

## 观测

`/home/xp/.claude/jobs/06dcd6c1/tmp/tree-0f2e7f1/`（主仓 `0f2e7f1` 的解包提交树）上第一次全量：

```
FAILED tests/int/test_standalone_process.py::test_a_run_on_another_port_leaves_the_incumbent_its_record
```

评审记录的现象是：**一次性 pidfile 在 child 退出之后依然存在**。

立刻单独重跑该条：`1 passed in 1.88s`。随后在同一棵提交树上重跑全量：`1643 passed, 2 skipped`。

## 这条观测能支持什么、不能支持什么

**能支持**：它不能归因于被评审的 diff。该测试文件在 `0f2e7f1` 与其父提交里都没有改动，两次全量之间那棵树一个字节都没变。

**不能支持**：不能反过来说「这个测试没有 flake」。一次观测到的失败 + 一次重跑绿 = 一个跨进程时序不稳定的样本，不是一份免检证明。评审自己在报告的排除项 10 里明确写了这一点，没有拿第二次的绿抹掉第一次的红。

**结论权重**：弱到只够立案，不够据以改代码。要动它得先能稳定复现。

## 下一步（未做）

- 循环重跑该条若干次，看能不能复现。评审没做，我也没做——它不在当时任何一个人的任务范围内，而**猜一个原因写进文档比留一条诚实的空白更糟**。
- 如果能复现：查 child 退出与 pidfile 清理之间的顺序，以及测试对「child 已退出」的判据是什么（等进程对象，还是等某个副作用）。
- 如果反复跑不出来：也把跑了多少次写下来，因为「跑了 N 次没复现」本身是有用的，而「没提」读起来和「没跑」一样。

## 出处

- 评审原件：`.dev/docs/upstream/retry-and-continuation/reports/260824-review-round-seven.md` 排除项 10 与「执行本契约时遇到的摩擦」一节。
