# 第二轮复评：H2 GOAWAY 故障诊断报告

日期：2026-08-20
评审对象：`docs/tmp/260820-h2-goaway-inflight-wipeout.md`（修订版）、`260820-h2-goaway-poc.md`、`260820-h2-goaway-review.md`、`exp/260820-h2-goaway-poc/`
评审基线 HEAD：`820f299`
评审者：与第一轮同一 agent（经 SendMessage 唤醒，带第一轮上下文）
结论：**needs-fix**，major=1、moderate=5、minor=1，共 7 条

> 落盘说明：评审 agent 的 harness 禁止其创建 Markdown 文件，本文件由主会话代为落盘。**下方为其返回文本的压缩转写，不是原文**——保留全部结论与「正确表述」，省略部分命令输出。末尾「处置」一节由主会话添加。

---

## 第一轮 F1–F8 复评判定

| 上轮发现 | 判定 | 复评结论 |
|---|---|---|
| F1 RFC 语义和「上游无过」说强 | **部分修复** | 第二节、状态行、证据表已准确改成 `might`、删除「上游无过」、写明生产对端后续行为未观测；但第三节新写成「服务端明确承诺已受理」，仍强于 RFC → R2-1 |
| F2 同秒不能证明共用单连接 | **已修复** | 已列出四种竞争解释；单连接明确降为未决 |
| F3 593B 不能证明下游零 body | **已修复** | 已准确解释 `block` 是完整 block 即释放；降为未决；建议 B 改条件式 |
| F4 pre-header 重试不等于幂等 | **已修复** | 已区分「对下游可隐藏」与「上游可能已处理」，写明 at-least-once 与重复计费 |
| F5 hyper-h2 同样进入 CLOSED | **已修复** | 已归因于集成栈，建议 E 要求上报两层事实 |
| F6「全部在飞流必死」全称过强 | **已修复** | 已限定为「还需再次网络读取」的流，并补上 pool 只在 Response 返回前捕获 `ConnectionNotAvailable` |
| F7 traceback 错位不能唯一证明旧进程 | **已修复** | 已区分确凿事实与非唯一强解释 |
| F8 孤儿 helper 能力被夸大 | **已修复** | 已列明真实能力与缺失构件 |

**F2 指定核查项**：错误论证「`↓593B` 说明远未触及流数上限」**没有以别的形式复活**。修订版保留该句但明确记为初稿错误并当场说明其错在哪，不再承担任何现行结论——属对未采纳论证的必要留档。

**过度修正检查**：除 R2-7 外，未发现把原本确凿的结论不当压成未决。核心诊断（httpcore 确定性触发机制、hyper-h2 CLOSED 转换、重试判据缺口）都保留了应有强度。

## 新发现

### R2-1｜major｜「`stream_id <= last_stream_id` 等于服务端明确承诺已受理」仍强于 RFC

主报告三处、PoC 报告结论文字、`check_retry_branch.py` 的 label（`the stream server DID accept`）都用了这个说法。

RFC 9113 §6.8 原文：

```text
The last stream identifier in the GOAWAY frame contains the highest-
numbered stream identifier for which the sender of the GOAWAY frame
might have taken some action on or might yet take action on. All
streams up to and including the identified stream might have been
processed in some way.
```

`stream_id <= last_stream_id` 表示该流属于「对端**可能**已经采取过动作、或**仍可能**采取动作」的范围。它既不能被客户端当作确定未处理并无条件重试，**也不是对端「明确承诺已受理并会继续完成」**。

白盒实验只是直接设置 `_connection_terminated.last_stream_id` 后观察 httpcore 分支，**实验中根本没有服务端执行「受理」动作**，因此更不能证明「明确承诺已受理」。

正确表述：

> 对 `stream_id <= last_stream_id` 的流，对端可能已经处理或仍可能处理，客户端不能把它视为确定未处理；RFC 也允许它继续成功。当前栈没有继续读取这类流的路径，而是立即抛错。

分支实验结果本身不受影响，被更正的是对它的解读。

### R2-2｜moderate｜把 PoC 的「分开到达变体」升级成了生产 wire 时序

主报告第五节写「分开到达（**本次生产故障的形态**）」。但生产 traceback 只证明我方栈收到 GOAWAY 后、在后续一次 `_receive_events` 入口抛了 `RemoteProtocolError`；它**不能证明生产对端后来还发送过 DATA**，更不能证明「GOAWAY 与后续 DATA 分开到达」。

这与主报告第二节已正确写明的「对端随后本来会继续传输，还是也会关闭连接，这一半未观测」直接冲突。

正确表述：

> PoC 的分开到达变体复现了与生产相同的异常类型和 httpcore 抛出点；生产 traceback 不足以证明对端在 GOAWAY 后还发送了 DATA，也不足以还原 GOAWAY 后的具体 wire 时序。

「是否落在同一次 `receive_data()` 会改变该 PoC 场景中的异常类型」可保留，但不要写成适用于所有 GOAWAY 场景的无条件二分。

### R2-3｜moderate｜「在判据里多加一个裸 h2 类型」既不会生效，也再次过度扩大重试类型

现有捕获接线（`src/app/ghc_client/client.py`）：

```python
except (httpx.TransportError, OpenAIAPIConnectionError) as error:
    if is_responses_headers_pending_transport_error(error):
        raise ResponsesHeadersPendingTransportError(error) from error
    raise
```

裸 `h2.exceptions.ProtocolError` 不是这两个 except 类型之一，**只改 `transport.py` 的元组不会让 classifier 被调用**。要归一化它，首先必须改变捕获边界。

其次，`h2.exceptions.ProtocolError` 是**宽类型**，也表示其它协议状态机错误。整类纳入可重试集合会重演 F4 的问题。

正确表述：

> 若要处理，需要先在适当的 transport boundary 归一化，并以具体 GOAWAY 状态／异常内容和请求阶段作窄匹配；不能只在现有 classifier 中增加整个 `h2.exceptions.ProtocolError` 类型。

「机制确凿、生产频率未测」的强度分级本身正确。

### R2-4｜moderate｜把上一轮评审的源码核对写成了「独立实测」

主报告写「评审与 PoC 各自独立测到同一件事」、证据表写「PoC 与评审独立各测一次」。

上一轮评审实际做的是**读取并打印 hyper-h2 状态机源码**，确认 `RECV_GOAWAY → CLOSED` 以及 closed 状态缺少 `RECV_DATA` transition；**没有执行 post-GOAWAY DATA 实验**。运行时验证来自 PoC。

实际证据组合是：独立评审做源码级核对 + PoC 做运行时实测 + 原始输出里的裸 `ProtocolError` traceback。这已足以把机制列为确凿，**不需要虚增第二次实测**。

### R2-5｜moderate｜上一轮评审文件的 provenance 不忠实

结论语义基本忠实、未弱化，但三处不实：

1. 元数据把评审者写成「异源模型（gpt-opus）」，**实际评审模型不是 Opus**。
2. 称「findings 正文为评审者原文」，但当前文件是**明显的压缩转写**，省略了逐项列出的实际命令、源码输出和部分限定文字。保留了结论，但不是原文。
3. 处置一节称 F4 是评审者误读、「不算事实错误」。原文句法是「`httpx.RemoteProtocolError`（MRO：…）不在其中。该类的 docstring 写的是……」，**就近语法先行词是 `httpx.RemoteProtocolError`**。上一轮指出该句会被读作错误归属**并非误读**；修订版写全类名是正确处置，但处置记录不应反过来撤销已采纳的 finding。

### R2-6｜moderate｜「行号基线」使用了不存在的线性历史，且行号并未全部保持

主报告写「并行会话推进了 `main`（`8870385` → `7fa71f3`）」。实际核对：

```text
git merge-base --is-ancestor 8870385 7fa71f3  → 否
merge-base = 9110518...
git branch --all --contains 8870385           → 空
```

`8870385` 与 `7fa71f3` 是从共同祖先分出的**不同历史**，不是线性推进。当前 main 包含的是同主题 squash commit `b822b45`，**没有任何 ref 包含 `8870385`**。

行号也不是「在 `7fa71f3` 下仍然成立」。`_tracked_delivery`：

```text
8870385:  435 except Exception / 438 accounting.failure / 439 raise
7fa71f3:  436 except Exception / 439 accounting.failure / 440 raise
```

主报告仍写 `pipeline_app.py:435-439`，该区间只对 `8870385` 完整成立，在 `7fa71f3` 下漏掉了第 440 行的 `raise`。

正确做法不是建更多版本矩阵，而是把基线写准，并把易漂移处改为引用符号名与关键语句。

### R2-7｜minor｜「GOAWAY 由 HTTP/2 peer 发来」被压得略低

`_connection_terminated` 只在 `_read_incoming_data()` 返回的事件中遇到 `h2.events.ConnectionTerminated` 时设置，该事件由 hyper-h2 解析入站 GOAWAY 产生；项目生产代码没有人工构造该事件。这已是源码级确定的产生点。

应为「**确凿**（前提：该 traceback 来自真实生产 transport 而非人工注入事件）」。需要继续保持未决的是 **peer 的身份**（源站／边缘／中间 TLS 终止节点），而不是 GOAWAY 是否来自当前 peer。

## PoC 转述忠实度

核心结论转述基本忠实：哨兵值路径、`last_stream_id=0` 真值短路、`last_stream_id=1/stream_id=3` 进入 `ConnectionNotAvailable`、hyper-h2 拒绝 post-GOAWAY DATA、same-write 变体只是 best-effort 且生产频率未知——均忠实。

需修正的四处即 R2-1、R2-2、R2-3、R2-4。

## 复修后可接受的结论

> 生产请求共同收到了同形状的入站 GOAWAY。单连接还是多连接同步事件未观测。httpcore 1.0.9 对任何还需再次网络读取的相关流会立即抛错；hyper-h2 4.3.0 同时把连接状态转为 CLOSED，无法继续处理 post-GOAWAY DATA。该栈行为足以造成所见失败。RFC 只表示 `stream_id <= last_stream_id` 的流可能已处理并可能继续成功，不保证完成；生产 peer 在 GOAWAY 后实际做了什么仍未观测。

---

## 处置（主会话）

**7 条全部采纳。**

| 发现 | 处置 | 落点 |
|---|---|---|
| R2-1 「已受理」强于 RFC | 采纳 | 主报告第三节表格 + 三处表述已改为「落在『可能已处理或仍可能处理』的范围」，并加了一段措辞更正说明。**PoC 报告与 `check_retry_branch.py` 的同类标签待改**——PoC 评审 agent 正在读这两个路径，避免评审中途改文件，待其交付后一并处理 |
| R2-2 生产 wire 时序 | 采纳 | 五.5 重写，删除「本次生产故障的形态」，加明确限定；证据表新增一行「GOAWAY 之后的具体 wire 时序｜未决」 |
| R2-3 裸 h2 类型 | 采纳 | 五.5 补入 `client.py` 的捕获边界代码与「只改元组不会生效」；建议 A 改为「不要简单加类型」并给出两条理由 |
| R2-4 虚增实测 | 采纳 | 正文与证据表均改为「独立评审读源码核对 + PoC 运行时实测」 |
| R2-5 provenance 不忠实 | 采纳 | 评审报告元数据改为 agent type `gpt-opus`（GPT 系列，非 Claude Opus）；「原文」改为「压缩转写」并说明省略了什么；**F4 那条辩解已撤回**——就近先行词确实是 `httpx.RemoteProtocolError`，是原文歧义而非评审者误读 |
| R2-6 历史与行号 | 采纳 | 基线说明重写：写明 `8870385` 不在 main 历史上、二者从 `9110518` 分叉、同主题以 `b822b45` squash 入 main；易漂移处改引用符号名 |
| R2-7 强度压低 | 采纳 | 证据表该行升为「确凿」并注明前提；「peer 身份未决」单列一行 |

未采纳：无。

**一条关于我自己的观察，记在这里而不是藏起来**：连续两轮评审，每轮都在我的文字里查出「把未观测说成已确认」。第一轮是四处，第二轮我在**修第一轮问题的过程中**又引入了同型的 R2-1。这不是偶发笔误，是一个稳定倾向——写诊断时倾向于把机制讲得比证据允许的更干脆。后续同类文档应默认多做一轮针对「强度虚标」的定向复查。
