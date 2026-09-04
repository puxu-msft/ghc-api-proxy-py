# 待办：多 provider 路由

只放**未闭合**的条目。查清的移出本文、并入常规文档并带上出处。编号是标识不是序列，移出后不补空号。

## D-1 · `model_mappings` 的静态卫生只覆盖了一半

**状态**：开着。**来源**：实现评审 nit-2（[reports/260827-impl-review.md](reports/260827-impl-review.md)），2026-08-27。

`inspect_mappings`（Spec §5.1、§5.1.2）检查三类：限定的 provider 名认不出、限定的模型名为空、别名链成环。它**不检查空的键**。

`{"": "A/x"}` 因此在三处同时不可见：`_candidate_names` 的 `if not key` 静默跳过它，所以 `/v1/models` 与 `/api/status` 的 `routes` 都没有这一行；`inspect_mappings` 只看值，所以启动 WARN 也没有。schema 是 `dict[str, str]`，YAML 里写得出空键，它能通过校验。

**为什么没有顺手补**：这一个孔可以两行代码补上，但它属于「mapping 表的静态卫生」这个更大的题目——同族的还有键含 `/`（会被请求侧前缀先剥掉，于是永不命中）、键含 `@format`（同理，已由 MPR-11 在报告侧对齐但配置侧仍无告警）、键是纯空白。只补空键会留下一组形状相同、告警覆盖不一致的孔。

**下一步**：把「哪些键形状永远不可能被命中」列全，一次性加进 `inspect_mappings`，作为第四类 WARN。不阻塞任何事——这些都是配置写错才会遇到的形状，且都 fail-closed。

## D-2 · 连接池隔离与凭据隔离没有运行证据

**状态**：开着，且**是用户裁决的结果**，不是遗漏。**来源**：Spec §10.2，2026-08-27。

Spec §8.1 要求每个 provider 一个 httpx client，理由是连接级故障（GOAWAY）不该跨 provider 传播。已验证的只有结构：两个不同的 `AsyncClient` 对象、各自装了 stream cap、`Chain.aclose()` 后都关闭。

**没有验证的**：真实 GOAWAY 的爆炸半径确实被限制在一个 provider 内；两份凭据各自只出现在对应 provider 的 auth/inference leg 上。前者需要真实 HTTP/2 连接故障注入，后者需要两份真实 Copilot 凭据——用户已裁掉真实双账号 canary（Spec §10.1）。

**下一步**：若将来要验，最小手段写在 Spec §10.2：同账号配成两个 provider 能覆盖除凭据隔离外的一切；凭据隔离只有两份真 token 才能证明。

## D-4 · 计数腿的配置名不真正选择 provider

**状态**：开着。**来源**：Spec §1.3 收尾，2026-08-27。

`inbound.anthropic_count_tokens.providers` 里的 provider 名**不选择**由谁计数：`driver.py` 的 `ask_upstream` 闭包捕获的是 `shape_request` 定下的那个 provider。所以 `providers: [A, local]` 而某请求路由到了 B 时，问的是 B。

配置里那个名字实际只起两个作用：**是不是要问上游**，以及**与 local 的先后顺序**。

单 provider 下两种读法行为完全一致，所以这个偏差一直不可见。多 provider 让它可见了，但它是**既有行为**，不是本次引入的，因此没有顺手改。

**要改的话得先回答一个真问题**：token 计数是模型相关的，只能问服务这个模型的那个 provider。所以「让配置真正选择计数用的 provider」要么退化成「哪些 provider 被允许用于计数」（路由到不在列表里的 provider 就跳过上游、用 local），要么就得接受「用 A 去数 B 才有的模型」这种没有意义的组合。前者语义清晰且单 provider 完全兼容，是我倾向的方向，但它改变行为，需要用户裁。

## D-3 · 四处越出用户原裁决边界的推导待确认

**状态**：开着。**来源**：Spec §12。

不在此重复，读 `spec.md` §12 的表。四条都能被单独推翻，每条都写了推翻之后的退路。

摘要：`/v1/models` 候选集加入 mapping 键（目录会多出十几个别名）；启动 WARN 从一类扩到三类；mapping 值不支持 `@format`（是纠正用户亲笔文档还是实现它）；`provider/model` 前缀只在请求体端点生效。
