# Project principles backlog review — 处置账

状态：closed。
日期：2026-09-03。
原报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md`。
独立复审：`/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-general-sonnet.md`。

## 接收回执

- 原报告最新声明：finding_total=3，major=1，minor=2，open=3，contract_blocker=0，contract_open=0；人工反算一致。
- 复审声明：finding_total=3，major=2，minor=1，open=3；人工反算一致。
- 原报告 C1～C9 合同补核：pass。

## 原报告三条 finding 的处置

| finding | statement_kind | 成立度／判断 | 处置 | 级别 | 理由 |
|---|---|---|---|---|---|
| PPR-260903-01 | fact + judgment | confirmed／concurred | adopted | C | 当前 producer/consumer 数据流与我方独立 cassette 探针共同复现。两份 cassette 实证 reasoning parity；tools 缺口由源码控制流证明。列为 D-5 后的同主题高优先项，不降格成日志补丁。 |
| PPR-260903-02 | fact + judgment | confirmed／concurred | adopted | C | count-tokens 当前仍直接写 `trace.usage`；即时渲染无错误，结构漂移风险成立。排在 D-5 与 F-01 后。 |
| PPR-260903-03 | fact + judgment | confirmed／concurred | adopted | C | 三处越权承诺面当前仍存在，正确动作是撤回 surface 上的外部结局断言、保留邻近 rationale。低风险清理，不改变首选。 |

## 独立复审三条 finding 的处置

| finding | statement_kind | 成立度／判断 | 处置 | 级别 | 理由与修改 |
|---|---|---|---|---|---|
| PPRR-260903-01 | fact + judgment | confirmed／concurred | adopted | C | Spec §2.7 已裁定 selector 启用时保留当前 `signature_delta` 默认；长期 D-4 仍待用户。将 reshape preservation 加入 D-5 对外完成／selector 前置。 |
| PPRR-260903-02 | fact + judgment | confirmed／concurred | adopted | C | 原报告漏比 hosted web search D6 与 `empty_result`，且无 route traffic。两项补入排序；D-5 改为在没有已记录近期 hosted-search rollout 的现状下中等置信首选，不再声称无条件全序。 |
| PPRR-260903-03 | fact + judgment | confirmed／concurred | adopted | C | 两份 cassette 只含 reasoning/message；实证仅覆盖 reasoning，tools 由源码证明。修订证据措辞，不新增证明系统。 |

## 被否决的建议

无。所有发现均采纳；没有暂定驳回。

## 复评结论

独立 reviewer 已于 2026-09-03 完成窄复评：`PPRR-260903-01`～`03` 全部 `closed`，无 remaining blocker／major／minor，原报告可交付。原报告自己的三条产品 finding 仍为 `open` 且均已采纳；报告通过不表示产品已修复。
