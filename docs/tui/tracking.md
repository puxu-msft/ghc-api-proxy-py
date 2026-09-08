# TUI Responses function-call 聚合进度账本

权威行为：[`spec.md`](spec.md)“描述回复的用词跟随上游”与验收第 7 条。内部机制：[`design.md`](design.md)“Responses completion display projection”。执行细节：[`function-call-grouping-plan.md`](function-call-grouping-plan.md)。

## 任务列表

| ID | 状态 | 所有者 | 最近更新 | 内容 |
|---|---|---|---|---|
| G1 | done | session `21e1d9` | 2026-09-06 | 根因调查：确认 `f97d243` merge resolution 删除 action grouping 并反转 tests oracle |
| G2 | done | session `21e1d9` | 2026-09-06 | Spec 与 typed-segment design 修订；design、Spec 和 implementation plan 均经独立评审收口至 0 blocker／0 major |
| G3 | done | session `21e1d9` | 2026-09-06 | `request_log.py` 已实现 typed visible segments、adjacent reducer、shared rich／legacy renderer；direct probe 产出 `function_call(TaskCreate,Bash)` |
| G4 | done | session `21e1d9` | 2026-09-06 | Unit 分层 oracle 与既有 production-entry integration oracle 已同步；targeted run 为 85 passed |
| G5 | done | session `21e1d9` | 2026-09-06 | Ruff clean、Pyright 0 errors；最终 full run 为 2854 passed／2 skipped、coverage 91.77%；code review 1 个 major 已补测并复评通过 |
| G6 | done | session `21e1d9` | 2026-09-06 | `abdfd54` 已按精确三路径提交；job-private archive negative control 精确得到 3 failed；living docs 与处置账已同步，所有实现相关评审 findings closed |
| G7 | done | session `21e1d9` | 2026-09-06 | 最终独立评审逐项核验 F1～F10，结论 pass、0 blocker／0 major；工作单元结束 |

## 当前边界

- 只合并 visible segment sequence 中连续、同 raw type、具名且 `REQUIRED` 的 actions；visible reasoning、different raw type、`UNKNOWN` 与 anonymous actions 是 barrier；不可见 `NOT_REQUIRED` item 不制造 barrier。
- Durable observation 逐项保留事实；display projection 不回写、不去重。
- Rich observation 与 legacy fallback 复用 action selection、adjacent reduction 与 rendering；contextual `completed` 独立读取完整 observation。
- 不修改 provider schema、classification、delivery policy、Chat Completions、Anthropic stop reason、pending tools 或 footer。

## 共享工作树协调

本轮拥有的源码／测试范围只有：`src/app/observability/request_log.py`、`tests/unit/observability/test_request_log.py`、`tests/int/test_pipeline_app.py` 的 grouping 相关段。并行 Chat 文档和其它工作保持原样；任一目标路径出现新的同伴改动时重新核对 hunk ownership。
