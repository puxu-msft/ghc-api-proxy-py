# docs/agents 冻结前并发收口检查

- **检查范围**：只读监控主树 `docs/agents/**` 的物理文件集合、worktree Git blob、index Git blob 与冻结依赖顺序；唯一写入是本报告。
- **基线**：物理仓库 `/home/xp/src/ghc-api-proxy-py`，分支 `main`，HEAD `ed77c9d191df81c451c25161420515cca52ce6a4`。
- **观察时点**：第二次间隔读取完成于本报告写入前；写前复核时间为 `2026-08-07T02:03:10Z`。
- **边界**：本检查不做文档内容评审，不把“内容稳定”解释为技术正确、评审通过、用户裁决完成或可提交。

## 收口结论

Architecture 与 Implementation 本轮返回后，最近两次间隔读取的物理集合、7 个 worktree blob 和 6 个已跟踪 index blob 全部一致；index 文件 SHA-256 两次均为 `2b56de0de74cb7d47de7f20dda9f1739d44acbba492c0990605c116053cdf90c`。在本次只读监控口径下，没有观察到继续写入 `docs/agents/**` 的并发写者。

仍须按依赖顺序等待的文件：

1. `docs/agents/anthropic-responses-bridge/acceptance.md`：等待 `architecture.md` 的最终内容身份固定后再冻结。Acceptance 显式绑定 Architecture 内容身份，因此不能先于 Architecture 冻结；它不需要等待 Implementation。
2. `docs/agents/anthropic-responses-bridge/README.md`：最后冻结。README 汇总 Architecture、Acceptance 与易变的 Implementation 状态，必须等待这三者的最终内容身份均固定；因此顺序是 `Architecture → Acceptance → README`，同时 `Implementation → README`。

在最近两次读取与写前复核中可视为“并发静默下内容稳定”的文件：

- `docs/agents/anthropic-responses-bridge/architecture.md`
- `docs/agents/anthropic-responses-bridge/implementation.md`
- `docs/agents/anthropic-responses-bridge/research.md`
- `docs/agents/anthropic-responses-bridge/spec.md`
- `docs/agents/documentation-restructure/plan.md`

其中 Architecture 与 Implementation 的“稳定”只表示本轮返回后 blob 未继续变化；是否满足评审门或用户裁决不在本检查范围内。README 与 Acceptance 自身在两次读取间也未变化，但因下游依赖尚需按上述顺序收口，不应据静默窗口提前冻结。

## 当前物理文档集合与内容身份

| 文件 | worktree Git blob | index Git blob | 最近两次读取 |
|---|---|---|---|
| `docs/agents/anthropic-responses-bridge/README.md` | `7be902d9a1e0c3bba504372ad1c6ae4634c5edc7` | 未跟踪 | 稳定 |
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `9a37dccc17a28c29a14266da674f118e64fab0ba` | `f87e7509af8d51914e87f71d89651bd2b22e3b09` | 稳定 |
| `docs/agents/anthropic-responses-bridge/architecture.md` | `0c95ca408c448bf33ed7330588c68064e7acf4dd` | `24685e1d63ca239937c5085ab960c898bfd26030` | 稳定 |
| `docs/agents/anthropic-responses-bridge/implementation.md` | `c05b34e5e177d432bcc856b22095f2df5c691395` | `b0146833a1215d75fbee92efc74cc7b8e7d9b9ac` | 稳定 |
| `docs/agents/anthropic-responses-bridge/research.md` | `65bfbe1054e51dbe0e24a1fc6655cebab40d1841` | `aefdd33c8f8065dfd10b4f5f4314e1af69c642d2` | 稳定 |
| `docs/agents/anthropic-responses-bridge/spec.md` | `717a3107bda7f0599b4a45a50313a3c3ad090144` | `32dbb8644a1504f20e9ef8eff219951521bdff41` | 稳定 |
| `docs/agents/documentation-restructure/plan.md` | `30391c940a065d6afc5806f7233de7ece706685b` | `c451c74f646976c76fb156d0a3e3ba30ca260f25` | 稳定 |

## index 不变性

本轮未执行任何修改 index 的命令。报告写入前的 index 文件 SHA-256 为 `2b56de0de74cb7d47de7f20dda9f1739d44acbba492c0990605c116053cdf90c`；写入后必须保持相同，且本报告只应以未跟踪文件出现在工作树中。
