# 干净 EOF 接管改动的评审探针（2026-08-24）

## 它回答的问题

主仓 `a7a0e05`（*hand a severed stream back to the client, however it was severed*）让「上游流无终结事件、且本来要发 SSE error」的结局先咨询合成续写。第二轮异源评审要判定的是：**这个改动的触发面到底有多宽，以及它有没有碰到不该碰的格子。**

单元测试只能钉住交付层。这个探针走的是**真实 app 入口**（`tests/int/test_pipeline_app.py` 的 `make_client` / `_delivered` / `_handed_back`），一次覆盖六格。

## 结论（探针跑通时逐条 assert 成立）

| 场景 | 观察 |
|---|---|
| `UpstreamStreamUnterminated` 的分类 | `normalize_upstream_error` → `None`，`replay_reason` → `None`，且**不是** `DeliveryError` |
| Anthropic 上游腿：交付一个完整块后被切穿 | 交接触发，`category=upstream`，`message` 含 `UpstreamStreamUnterminated`；无 `incomplete_responses_stream`；完整块保留、未合拢的草稿丢弃 |
| 块边界 + `unterminated_stream_stop_reason` 默认值 | **不交接**，发合成 `stop_reason:"incomplete"`，无 error 帧 —— 2026-08-22 那条裁决未被本次改动碰到 |
| 块边界 + `unterminated_stream_stop_reason: ""` | **交接取代了本来会发的 SSE error**，`category=upstream` |
| 一个完整块都没交付过 | 下游 body 为**空字节**，既不交接也不发 error —— 既有行为，本次改动未触及 |
| Responses 上游 → Anthropic 客户端 | 交接触发，`category=upstream`，完整 item 保留、草稿丢弃 |
| Responses 客户端（`/responses`） | 续写被 wire format 拒绝，仍得 `incomplete_responses_stream`，无 `response.completed` |

第四格值得单独指出：**本仓测试套件里没有它的对照。** 上一轮评审曾建议补一个「`unterminated_stream_stop_reason` 清空且 continuation 已配置」的用例，当时判为与既有两个用例重复而未补；这个探针就是那一格的实际证据。谁要动 `unterminated_stream_stop_reason` 的语义，先看这里。

## 它**不能**证明什么

- **不是回归测试，也没有接进任何 gate。** 它是一次点时取证，跑一次、读输出、写进报告。
- **源码钉死在 `a7a0e05`，依赖环境不是**：第 11 行 `assert` 会拒绝在任何别的提交上运行，但下面的重跑配方用的是**当前项目的依赖环境**（`uv run --project`），不是 `a7a0e05` 当时那套。所以它证明的是「`a7a0e05` 的源码在今天的依赖下如此表现」，**不是历史运行环境的完全复刻**。依赖若发生过不兼容变更，重跑失败要先怀疑这一层。
- **上游全是手写字节**，不是 cassette。它证明的是「给定这样的 SSE 序列，本侧如此反应」，**不证明 Copilot 真的会发出这样的序列**。真实上游行为要看 `tests/int/cassettes/`。
- **每格只有一条路径**。例如「零完整块」只试了 Anthropic 腿一种缓冲策略，没有遍历 `buffering_policy` 的其他取值。
- 断言的是**结果字段**，不是全字段等价。

## 怎么重跑

它依赖一棵位于 `a7a0e05` 的树，且树根要有写着该 SHA 的 `.review-commit`：

```bash
PROBE_DIR=/home/xp/src/ghc-api-proxy-py/.dev/exp/260824-handover-clean-eof-review-probe
REPO=/home/xp/src/ghc-api-proxy-py

# 1. 造一棵一次性的树（别在共享工作树里跑——它会 import 生产代码）
T=$(mktemp -d)
git -C "$REPO" archive a7a0e058fc1940c188626e8d3f4aa38e0393ea9c | tar -x -C "$T"
printf 'a7a0e058fc1940c188626e8d3f4aa38e0393ea9c\n' > "$T/.review-commit"

# 2. 放进探针
cp "$PROBE_DIR/review_probe.py" "$T/review_probe.py"

# 3. 跑（需要 httpx2 与 orjson，取自当前项目环境——见上文的限定）
cd "$T" && uv run --project "$REPO" python review_probe.py
```

预期是七行 `print`，任何一条 assert 失败即为行为已变。**assert 失败不等于回归**——先确认 `a7a0e05` 之后的裁决有没有故意改掉那一格，再确认不是依赖环境漂移。

第三轮评审于 2026-08-24 在一次性 tmpfs（`bwrap`）中按本配方实跑过一次：七项输出全部出现、全部 assert 通过、宿主无残留。

## 来源

由第二轮异源评审 agent 在其自建的隔离副本 `/tmp/ghc-api-proxy-review-a7a0e05-d3e11298` 中写就并运行，用于避免在共享工作树上做变异。评审结论见 `../../docs/upstream/retry-and-continuation/reports/260824-review-handover-on-clean-eof.md`。

**它差点被丢掉**：收尾时我核验那棵副本「是否持有独有内容」，`git status` 只限定了 `src tests exp` 三个路径，**没看树根**，于是这个文件从未进入清单。第三轮评审（清单评审）把它判为 blocker 并拦下了删除。教训记在记忆 `prove-the-probe-ran-before-reading-its-number` 一族里：**核验范围写窄了，得到的「无独有内容」与真的没有同形。**
