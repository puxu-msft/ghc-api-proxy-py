# `tests/unit` 与 `tests/smoke` 合并跑会挂住

日期：2026-08-20。性质：**既有缺陷，先于本日的取证记录工作存在**。可信度：**可据以行动**（三重复现，见下）。

## 现象

```
uv run pytest tests/unit tests/smoke -q -p no:randomly
```

不终止。观测到 9 分 20 秒仍未结束，其中 **8 分 43 秒是用户态 CPU** ——是空转，不是阻塞在 I/O 或网络上。

## 复现边界

| 组合 | 结果 |
|---|---|
| `tests/unit` 单跑 | 1044 passed, 28s |
| `tests/smoke` 单跑 | 113 passed + 2 skipped, 7.8s |
| `tests/http` 单跑 | 98 passed, 10.3s |
| `tests/integration` 单跑 | 62 passed, 17.4s |
| `tests/http` + `tests/unit` | 1150 passed, 37.3s |
| `tests/http` + `tests/smoke` | 213 passed + 2 skipped, 33.6s |
| **`tests/unit` + `tests/smoke`** | **挂住** |
| 四组合并 | 挂住（即 unit+smoke 这一对所致） |

## 与本日改动无关的证明

当日提交了 `9110518 test: stop the suite writing to the developer's own data directory`，给四个测试组各加了一份带 autouse fixture 的 `conftest.py`。为排除它是成因，做了三次独立复现：

1. **把四份 conftest 移开**（改用 `XDG_DATA_HOME` 环境变量维持隔离，避免重新污染真实数据目录），跑 `tests/unit tests/smoke` → 仍然挂（rc=124）。
2. 用 `git archive` 导出 **干净 HEAD**（`7ebb405`，不含任何未提交改动）到临时目录后跑 → 仍然挂。
3. 用 `git archive` 导出 **`db91dcf`**，即上述提交之前的那一个 → 仍然挂。

结论：成因位于 `db91dcf` 及更早的已提交代码中。

## 为什么这件事要紧

项目纪律要求「squash 候选合入前跑一次完整回归」。按目前形态，那一跑会挂住而不是失败——**挂住比失败更坏**，因为它不给出任何指向成因的信息，且容易被误读为「机器慢」或「测试量大」。当日第一次尝试合并跑四组时，正是被 900 秒的 `timeout` 杀掉后才注意到异常。

## 尚未做的排查

以下都没做，留给接手者，按预计信息量排序：

1. 用 `-p no:cacheprovider`、`--collect-only` 区分是**收集期**还是**执行期**挂住。
2. 二分定位：`tests/unit` 与 `tests/smoke` 各自逐文件缩小，找出那一对具体文件。
3. 挂住时对进程取一次栈（`py-spy dump` 或 `faulthandler.dump_traceback_later`），直接看空转在哪。用户态 CPU 占满意味着栈会很有指向性。
4. 检查两组之间是否共享了某个模块级或进程级状态：事件循环策略、`logging` 的 root handler、全局注册表、`asyncio` 的默认执行器。`tests/smoke` 与 `tests/unit` 都会构造 app，而 `tests/tui` 之所以被排除在默认清扫之外，本身就说明这个仓库里存在过组间环境互相影响的先例。

第 3 项预计一步到位，建议先做。
