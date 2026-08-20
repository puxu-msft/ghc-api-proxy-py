# 上游 HTTP/2 GOAWAY 打掉在飞流式请求

**读这个目录从 [`findings.md`](findings.md) 开始。** 那是唯一的活文档；本目录其余部分是它的证据。

一起看的还有主仓的 `exp/260820-h2-goaway-poc/` 与 `exp/260820-h2-stream-cap/`——PoC 代码与原样输出留在主仓，因为它们是可复跑的产物，不是记录。

## 这个主题回答了什么

2026-08-20 15:01:59，四条流式请求在同一秒集体失败于一帧上游 GOAWAY（`NO_ERROR`，`last_stream_id=2^31-1`，即 RFC 9113 §6.8 的优雅关闭首帧）。

**结论**：httpcore 1.0.9 与 hyper-h2 4.3.0 组成的栈，在收到任意 GOAWAY 后不会为已受理的流发起新的网络读取——本该「可能继续成功」的在飞流被一次性判死。HTTP/2 把并发请求复用到一条连接上，于是一次连接级事件就是一次全员伤亡。

**它不回答什么**：谁发的 GOAWAY、为什么发、我方停止读取之后对端做了什么。这三项在客户端一侧**原理上不可判定**，已裁决不再作为待查项（见 `findings.md`）。

## 目录

| 路径 | 是什么 |
|---|---|
| `findings.md` | **活文档**。现象、机理、确凿与未决、已落地的五处修复、待裁决项 |
| `archive-260820/` | 当日的过程产物，内容已冻结，只作证据 |
| `evidence/` | 取证查询脚本，见下 |

### `archive-260820/` 里的九份

| 文件 | 角色 |
|---|---|
| `260820-h2-goaway-inflight-wipeout.md` | 主诊断报告全文（`findings.md` 是它的蒸馏） |
| `260820-h2-goaway-review.md` | 主诊断第一轮独立评审，8 条 |
| `260820-h2-goaway-review-round2.md` | 复评，7 条；末尾记着一条关于作者倾向的观察 |
| `260820-h2-goaway-poc.md` | GOAWAY 行为的端到端 PoC，含更正头 |
| `260820-h2-goaway-poc-review.md` | PoC 独立评审，8 条，**其中一条推翻了主诊断的一个结论** |
| `260820-h2-stream-cap-poc.md` | 每连接流数上限的可行性 PoC 与维护性风险 |
| `260820-goaway-frequency-forensics.md` | 频率与模式取证，93125 条请求 |
| `260820-structured-log-survey.md` | 结构化日志落点调研，含连接标识可行性实测 |
| `260820-structured-log-impl.md` | 结构化日志实现记录 |

三轮独立评审共 23 条发现，全部采纳。**每一轮都查出「把未观测的说成已确认」**，其中第二轮那条是在修第一轮问题的过程中新引入的，第三轮推翻的那条是纯文本评审三轮都没查出、只有实测才推翻的。这个模式记在 `260820-h2-goaway-review-round2.md` 末尾。

### `evidence/` 里的三个脚本

`history-frequency-analyze-{1,2,3}.py`——`260820-goaway-frequency-forensics.md` 全部数字的**唯一产出者**。报告里引了它们的原样输出，但脚本本身留下来，因为数据源还在原地、随时可以重跑：

```
~/.local/share/copilot-api/history-v3*.db        （现网 copilot-api-js 的 history，只读打开）
/home/xp/src/ghc-api-proxy-py/.venv/bin/python history-frequency-analyze-1.py
```

**它们不证明什么**：脚本数的是「同 pid 同秒成批失败」这个**代理指标**，不是 GOAWAY 帧本身——`copilot-api-js` 的 GOAWAY ledger 在 manifest 的压缩 blob 里，未解码。而且覆盖的是**现网 Bun 服务**的流量，不是本项目：本项目当时零生产数据（History 未接活链路、日志不落盘、不在 systemd 下），这正是结构化日志要解决的。

## 本次会话产出的代码（都在主仓 `main`）

| 提交 | 做了什么 |
|---|---|
| `16dd68c` | STR-04 的 SSE 信封一半：无终止事件的 EOF 改发 Anthropic SSE `error`，不再伪装成干净结束 |
| `5a366a8` | `upstream_transport.http2` 开关，可选 HTTP/1.1 上游 |
| `10e4811` | 结构化请求日志：每条完成请求一行 JSON，带上游连接标识 |
| `5c1afbe` | `decide_stream_ending()`：读已收内容裁决 COMPLETE / REPLAY / CONTINUE / ABANDON |
| `09ef3cc` | headers 之前撕裂的连接纳入重试判据，并让裸 `h2.ProtocolError` 进得了捕获边界 |
| `42738c9` | `upstream_transport.max_streams_per_connection`：每连接流数上限 |

## 变异检验记录

两处新逻辑做过变异检验（结论已在此，`.orig` 备份不保留）：

| 被变异的符号 | 变异 | 应转红的测试 | 实际 |
|---|---|---|---|
| `decide_stream_ending` 的 `not downstream_opened` | 反向 | `test_stream_ending.py` 全组 | 8 条红 |
| `decide_stream_ending` 的 `committed_blocks == 0` 分支 | 删除 | `test_an_opened_but_empty_response_can_do_neither` | 1 条红 |
| `decide_stream_ending` 的 `ledger.take` | 改为 `consider` | `test_deciding_spends_the_budget_it_grants` | 1 条红 |
| `StreamCappedConnection.is_available` 的 cap 条件 | 恒真 | `test_the_real_pool_opens_another_connection_once_one_is_full` | 4 条红 |
| `StreamCappedConnection.assigned_request_count` | 恒返回 0（**私有 API 静默失效的形态**） | 同上 | 4 条红 |
| `StreamCappedConnection.max_concurrent_requests` | 不转发 | `test_max_concurrent_requests_answers_rather_than_going_missing` | 1 条红 |

倒数第二行是这套守卫存在的理由：`pool._requests` / `.connection` 改名时 cap 会**退化成什么都不做的装饰而不报错**，那一行证明了测试抓得住它。
