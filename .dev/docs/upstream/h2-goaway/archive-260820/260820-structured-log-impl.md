# 结构化请求日志：实现记录

日期：2026-08-20
提交：`10e4811 feat: keep a durable record of every completed request`
规格：`docs/tmp/260820-structured-log-survey.md` §3–§4（定稿设计）
实现：由异源 agent 按定稿规格落地，主会话评审并提交

> 本文由主会话代写：落地 agent 的 harness 禁止其创建报告文件。下述内容基于主会话对 diff 的逐处评审，不是 agent 的自述转录。

---

## 改了什么

| 文件 | 做什么 |
|---|---|
| `src/app/observability/request_log_file.py`（新） | 追加一行 JSON 到 `<user_data>/requests/requests-YYYYMMDD.jsonl`，按名字剪枝保留 14 天。与 `rejection_capture` 同形：派生路径、never raises、按名字（非 mtime）剪枝 |
| `src/app/observability/request_log.py` | `RequestLine` 补 `request_id` / `message_id` / `started_at` / `first_upstream_byte_s` / `terminal_seen` / `blocks` / `upstream_conn`；完成行顺带显示 `request_id` |
| `src/app/pipeline/delivery/assembler.py` | `Terminal.record()` 加 `self.blocks += 1`。选这里是因为它是三个生产者唯一共用的记录点 |
| `src/app/server/pipeline_app.py` | 响应头到手时快照连接事实；`_counted_upstream` 记首字节时刻；`_log_completion` 写一行 |
| `tests/unit/test_request_log_file.py`（新） | 本切片的定向测试 |

## 两处设计要点

**连接标识零私有 API。** httpcore 把连接自己的 `network_stream` 放进 `Response.extensions`，HTTP/2 另给 `stream_id`；`network_stream.get_extra_info("client_addr")` 得到本端 `(ip, port)`——这是该 TCP 连接在本机的唯一名字，且能直接与 `ss -tnp` / tcpdump 对上，自造序号做不到。连接池与 `AsyncOpenAI.post(cast_to=httpx.Response)` 都原样透传（调研用 MockTransport 塞哨兵对象验过 `is` 相同）。

**时序坑已处理。** 连接关闭后 `get_extra_info("client_addr")` 抛 `OSError: [Errno 9] Bad file descriptor`（底下是 `getsockname()`），而 `_log_completion` 有意跑在上游 response 释放**之后**。所以地址在响应头到手那一刻就被读成字符串存进 trace，`network_stream` 对象不被留存。读取本身全程防御，拿不到就留空。

## 不重复抽取

结构化行是既有聚合记录 `RequestLine` 的序列化，**没有第二条抽取路径**——没有另写 `_build_json_record(trace)`。JSON 里的 `status` 与控制台 `[FAIL]` 前缀共用同一次 `status_for(...)` 调用，两条交付路径不会各说各话。这是规格 §4.3 点名的最要紧一条，实现遵守了。

顺带白赚：`RequestLine` 有了 `request_id` 之后，控制台完成行终于能和别的东西关联——此前它完全没有 id。

## 验证

- 本切片相关测试 97 passed（`test_request_log_file` + `test_pipeline_app` + `test_stream_delivery`）。
- 落地 agent 自报「全量 1484 passed / ruff / pyright 均通过」。**其中「pyright 通过」不予采信**：主会话实测 pyright 在本仓库连 `pydantic` 与 `orjson` 都解析不了（`Import "pydantic" could not be resolved`），全仓报 2672 个错，它当前不是有效判据。ruff 与 pytest 主会话独立复跑确认。

## 提交时的归属处理（值得记下）

提交时工作树里混着并行会话的在飞改动。逐文件核对后：

- **同伴的**：`schema.py` / `subscribers/__init__.py` / `bundled-config.yaml` / `test_builtin_subscribers.py` / 新文件 `hosted_web_search.py`（hosted web search 一摊），以及 `handler.py` 里正在进行的 idle-timeout 重构。
- **`tests/http/test_pipeline_app.py` 的三个 hunk 全是同伴的**——落地 agent 自报的「改了 5 个文件」把它算了进去，实际它一行没动。
- **唯一真正混合的是 `pipeline_app.py`**，混进去的是同伴重构的连带结果：一行 `stream_idle_seconds(chain)`（去掉了按模型覆盖的参数）。

处理方式：不碰工作树，构造索引内容——读工作树文件、把那一行还原成 HEAD 形态、`hash-object -w` 写 blob、`update-index --cacheinfo` 只改索引。前置断言两侧各出现恰好一次；事后核验暂存内容中 `web_search|stream_idle|models_support|model_mappings` 命中数为 0。同伴的改动一条不少地留在树里。

## 已知的小事，记下不改

`_prune()` 在**每条请求**上做一次 `glob` + 排序。目录里只有 ≤15 个文件，代价可忽略；按日切换时才剪会更干净，但不值得为它单开一次改动。

## 后续（非本切片）

字段设计的目的是回答事故当时答不出的问题。`upstream_conn.local` 四行相同即同一条连接，不同则是节点级回收——**这把待裁项里「收益取决于回收的是单条还是整节点」从不可判变成可判**。`terminal_seen` / `blocks` / `bytes_out` / `first_upstream_byte_s` 一起回答「失败时已经拿到什么、停在哪个语义位置」，那正是 `decide_stream_ending()`（`5c1afbe`）要读的对象。

并行会话已在此基础上扩建：加了 `count_tokens` / `counter` 字段，并把 `request_id` 的显示收窄为只在失败行出现（理由是成功的请求没有可 join 的对象，而该 id 比数个真实字段加起来还宽）。该收窄优于本切片原来的写法。
