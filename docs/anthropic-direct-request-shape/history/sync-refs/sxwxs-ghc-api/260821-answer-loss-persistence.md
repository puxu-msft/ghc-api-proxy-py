# 翻译损失要不要单开一个 SQLite 存储

- 日期：2026-08-21
- 提问：「为翻译损失清单增加持久指标存储，用 sqlite 合适吗？」
- 结论：**不合适——但不是因为 SQLite 不好，而是因为翻译损失不该有自己的存储。** 它已经落地为 `RequestLine` 的一个字段，随既有的每请求 JSONL 落盘；跨请求的频率走 Prometheus。两者都不需要新建任何东西。
- 落地提交：`a07f74a`

## 1. 「持久指标存储」其实是两个需求

把它们分开之后，答案就明显了：

| 需求 | 问题形态 | 该用什么 | 现状 |
|---|---|---|---|
| **明细** | 「昨天那条 400 的请求，翻译丢了什么？」 | 每请求一条的结构化记录 | 已落地：`RequestLine.losses` → `requests-YYYYMMDD.jsonl` |
| **计数** | 「`extensions-not-carried` 一天出现多少次？是不是每个请求都在丢？」 | 计数器 | 已落地：`ghc_proxy_translation_losses_total{direction,code}` → `/metrics` |

两个都不需要 SQLite。**明细**天然属于「该次请求的完成记录」，而那份记录已经存在、已经持久、已经保留 14 天；**计数**是 Prometheus Counter 的本职，而 `/metrics` 端点在活链路上早就挂着，只是此前一个业务指标都没有。

## 2. 为什么不该单开存储

本项目明确反对「同一事实在两条交付路径上各推导一遍」。翻译损失是**一次请求的伴随事实**，不是独立实体——它没有自己的生命周期、没有自己的查询维度、也不会脱离某次请求单独存在。给它单开一张表意味着：

- 多一个写入路径，多一处可能与 `RequestLine` 不一致的地方；
- 而它唯一有意义的查询（「哪些请求丢了东西」）本来就要 join 回请求记录。

`.dev/docs/history/spec.md` §1.4 已经把这条纪律写成规范，措辞比我这里更硬：

> 它们共享 `RequestLine` 这一份聚合记录，**这是有意的单写源**：同一事实不得在两条交付路径上各推导一遍。……**任何新字段都加在 `RequestLine` 上，绝不在 L1 的写入路径里就地从 `_Trace` 再推一次。**

本次实现照此办理：`_Trace.absorb_losses` 从 `context.extras` 全量重算一次，写进 `RequestLine.losses`，之后终端行、JSONL、以及未来的取证库 L1 都读同一份。

## 3. SQLite 什么时候才真的需要

当问题从「这一条请求丢了什么」变成「**过去一周所有 `reasoning-intent-not-carried` 的请求，按模型分组**」时，JSONL 就不够了——那需要索引和过滤。

而这恰好是并行会话正在设计的取证库 L1 `ForensicRequest` 的职责范围（`.dev/docs/history/spec.md` §2.1）。它的字段来源是 `RequestLine`，所以：

**`losses` 作为 `RequestLine` 的字段，在 L1 落地的那一天会自动成为一个可查询的列，不需要为它单独做任何事。** 这是不单开存储的第二个理由——单开的那张表，到时候要么废弃，要么与 L1 重复。

如果届时需要按 loss code 过滤，L1 那边只要给这一列加个索引即可；这属于取证库的实施细节，不构成现在就要做的事。

## 4. 一处需要用户知晓的张力

`.dev/docs/history/spec.md` §9.6 的建议是「L1 与 JSONL **并存，但 JSONL 不再扩字段**」。

本次改动给 `RequestLine` 加了 `losses`，而 `write_request_record` 的写法是 `{"at": …, "status": …, **asdict(line)}`——所以 **JSONL 自动多了一个字段**。

这与那条建议是否冲突，取决于它的读法：

- 若「不再扩字段」指的是「不为 JSONL 单独设计字段」，则不冲突：这里扩的是单写源 `RequestLine`，JSONL 只是跟着走，正是同一份 spec §2.1.1 描述的机制（「`RequestLine` 加一个字段，JSONL 自动就有」）。
- 若指的是「JSONL 的字段集从此冻结」，则本次改动违反了它。

我按前一种读法实施。**§9.6 本身是待用户裁决项**，所以这里只是把张力点摆出来，不代替裁决。

## 5. 本次实际落地的东西

- `src/app/observability/metrics.py`（新）：`ghc_proxy_translation_losses_total{direction,code}` 与 `ghc_proxy_attribution_lines_stripped_total`。定义即导出，因为 `/metrics` 序列化的就是 `prometheus_client` 的默认 REGISTRY。
- `RequestLine.losses: tuple[dict[str, str], ...]`，每项 `{"direction": "request"|"response", "code": …, "detail": …}`。方向是损失的属性而非第二个字段——「这次请求丢了什么」是一个问题，从两个列表里拼答案是它们开始漂移的方式。
- `_Trace.absorb_losses` 在 `_dispatch` 的四个「翻译刚结束」的点各调一次，全量重算而非追加。为什么是四处而不是一处，写在方法的 docstring 里。
- 计数在 `_log_completion` 里从 `line.losses` 这同一个 tuple 产生，所以 `/metrics` 与 JSONL 不可能对不上。

尚未做、也不建议现在做的：把损失显示在终端日志行上。`extensions-not-carried` 在跨格式路径上很可能是常态，一个几乎每行都亮的字段不携带信息——要不要显示应当先看真实频率，而频率正是刚接上的那个计数器要回答的。
