# next-root-fix-analysis 评审处置

状态：closed。
日期：2026-09-03。
评审报告：`/home/xp/.claude/jobs/f5849771/tmp/260903-next-root-fix-analysis-review-general-opus.md`。
评审对象：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md`。

## 接收回执

- received_at：2026-09-03。
- counts_declared：finding_total=7，blocker=0，major=4，minor=3。
- counts_verified：yes。尾部哨兵完整，F-01～F-04 与 M-01～M-03 共 7 条，逐项回应 C1～C9。

## 发现处置

| finding | statement_kind | 成立度／判断 | 处置 | 级别 | 理由与实际修改 |
|---|---|---|---|---|---|
| NRF-01 | fact + judgment | confirmed／concurred | adopted | C | 当前 non-stream 入口在 `inference.py:524-573` 独立走 whole-body，现有 continuation 只认 Anthropic `stop_reason/content`；用户合同明确非流式也支持。草稿补 non-stream intent 投影、两种 direct body 的真实入口判据与验收。 |
| NRF-02 | fact + judgment | confirmed／concurred | adopted | C | native failure 分支在 `stream.py:398-405` 直接发 failure 并 return，不咨询 replay／continuation；没有 D-6 taxonomy 就无法区分可继续与不可继续。草稿改为 D-6 可独立提交，但属于 D-5 完成与 selector 启用前置。 |
| NRF-03 | fact + judgment | confirmed／concurred | adopted | C | Anthropic `signature_delta` 默认 reshape 当前只在 parsed `CompletedBlock` 路径生效，passthrough production 没有对应 reshape。草稿把保持当前默认值列为 selector 前置，同时明确长期 D-4 仍待裁。 |
| NRF-04 | fact + judgment | confirmed／concurred | adopted | C | 项目 `CLAUDE.md` 把主产品路径定义为 Anthropic inbound → Responses upstream；Anthropic direct 只是 Claude 模型的重要可达 route。删除“主路径”论据，以后续用户裁决、当前 direct 主线 blocker 与确定性组合故障排序，并重述 hosted search 的真实主路径优势。 |
| NRF-M01 | judgment | concurred | adopted | C | D-7 属于 D-5 完成边界，但允许先做独立语义提交；草稿区分完成边界与 commit 边界。 |
| NRF-M02 | fact + judgment | confirmed／concurred | adopted | C | hosted-search 候选漏列已裁未实现的 `empty_result`。补入近邻项，不改变当前首选。 |
| NRF-M03 | judgment | concurred | adopted | C | 优先扩展现有 `AnthropicFramer`／`ResponsesFramer` 或复用其 module-level builders，不建立第三套方言 writer；保留 typed intent 与显式 ending outcome。 |

## 被否决的建议

无。所有发现均采纳；没有暂定驳回。

## 复评结论

原 reviewer 已于 2026-09-03 完成窄复评：7 条 finding 全部 `closed`，`open=0`，`blocker=0`，`major=0`，`minor=0`，判定修订稿可交付。复评追加在原报告 `## 复评：七条处置闭合核验`；其逐条状态与本处置账一致，无需 reopen。
