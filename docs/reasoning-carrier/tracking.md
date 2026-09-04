# Reasoning carrier v2 实施进度账本

状态：completed-in-worktree，已评审、已验证，尚未集成main；`.dev` durable sync进行中。

规范权威：`.dev/docs/reasoning-carrier/spec.md`。

实施位置：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2`，branch `worktree/reasoning-carrier-v2`。当前候选可由`git rev-parse HEAD`和`git log -1 --format='%ad %s' --date=short`重新定位。

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

## 当前终态

- feature branch：keep，等待用户决定是否按项目squash流程集成；未推送。
- feature worktree：keep，干净；没有删除或清理动作。
- main：未集成；主树并行WIP未被带入或修改。
- production：未启动、未部署、未操作4141。
- docs：main active copy已同步Spec v5、tracking与处置文档；下一步是精确提交到local`dotdev`并完成closeout限定复评。
