# Reasoning carrier v2 实施进度账本

> **Imported orphaned-source snapshot，not an active implementation tracker.** 本文件从 `origin/dotdev` 导入。原记录所指 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2` 与 branch `worktree/reasoning-carrier-v2` 在当前主仓均不存在，远端 dotdev 只保存文档，没有保存可恢复 source commit；因此以下 done／PASS 只描述另一份 source clone 的点时状态，不能据此继续实施、集成或声明 current main 已包含候选。

状态：source-unreachable；规格与评审记录已持久化，reviewed source history 尚未装位。

目标规范：[`spec.md`](spec.md)。

原实施位置（仅历史记录）：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2`，branch `worktree/reasoning-carrier-v2`。该位置与 ref 当前均不可达，且原报告刻意没有保存 commit token；在找回对应 source ref／bundle 之前不存在可执行的“重新定位”命令。恢复后必须重新核对 source、archive、主仓基线与本账，不得用文档评审 PASS 代替源码可达性。

## 任务列表

| ID | 状态 | 语义边界 |
|---|---|---|
| P1 | done | 统一typed reasoning IR、v2 envelope codec／classifier和独立静态vectors；提交主题`feat: add typed reasoning carrier v2 core`。 |
| P2 | done | buffered request／response双向投影与native opaque回送；提交主题`feat: preserve reasoning through buffered translations`。 |
| P3 | done | streaming summary_index state、authority precedence和双向carrier；提交主题`feat: preserve structured reasoning in streams`。 |
| P4 | done | Anthropic last-mile destack、两套namespace guard和blank-text顺序；提交主题`fix: keep reasoning carriers out of provider wire`。 |
| P5 | done | 旧helper薄委托统一core、测试迁移和actual-wire capture；提交主题`refactor: delegate legacy reasoning bridges to v2 core`。 |
| P6 | done | 独立实现评审全部findings已处置；最终Ruff、Pyright与全量pytest通过。 |

## 验证

在feature worktree运行：

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

最终运行结果：Ruff通过；Pyright 0 errors／0 warnings；pytest 2244 passed／2 skipped，coverage 91.46%。数量是本次运行快照，后续以命令输出为准。默认suite按项目配置排除`tests/tui`，本次diff未触及TUI。

## 评审

- Spec两条评审线最终PASS，处置 authority为`spec-review-disposition.md`。
- 实现两条评审线最终PASS；原findings及处置见`implementation-review-disposition.md`与`reports/`原始报告。
- 最终纯测试类型注解另经原codec reviewer确认，不改变runtime JSON bytes或既有PASS。
- 首轮closeout review发现Spec缺exact dotted record grammar与Responses-slot legacy-v1 classification；两项已进入Spec v5，等待限定复评。

## 原 source clone 的终态与当前恢复状态

原记录的点时终态是：feature branch／worktree 保留，main 未集成，production 未部署，docs 等待 durable sync。当前 checkout 只能确认文档已从 `origin/dotdev` 导入；原 branch／worktree 与 source commit 不可达，所以此前“keep”不再是一项可执行终态，不能继续走 squash／merge。

- source：unreachable；须先找回原 ref、bundle 或另一 clone，之后才能验证候选身份。
- main：当前 checkout 未集成 reasoning carrier v2。
- production：本文不提供当前部署证据。
- docs：Spec、tracking、处置与报告已持久化；它们是恢复输入，不是 source 的替代物。
- next action：只有在 source history 可达后，才重建 feature／archive 身份、复跑相关验证并重新评审集成候选。
