# Direct buffered Chat Completions：状态

状态日期：2026-09-06。

## 当前状态

设计已定稿并取得两条评审线0 blocker／0 major共识。Task 1已实现并squash集成到main `5995bbe0ac1885482e4976975c3b74d196cb7b11`，reviewed source保存在`archive/260906-direct-chat-capability`（`38979123336a622a02424645ffbcad3822136c2f`）；main-side targeted gate为147 passed、Ruff clean、Pyright 0 errors。Task 2经四轮fix完成并squash集成到main `92ac5643985d0b28fb1d94bbce3d5eb24abcfc44`，reviewed source保存在`archive/260906-direct-chat-facts`（`bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3`）；独立评审的14项finding全部关闭且没有新Critical／Important，main-side gate为128 passed、Ruff clean、Pyright 0 errors。Task 3准备开始。实施计划在Task 2评审与Task 2→3接口复核后修订为SHA-256 `b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`；此前`7ed5221a…`版本曾取得架构与验证判据两条评审线0 blocker／0 major，当前修订增加Task 3 single-frame proposal/cursor、逐frame state-aware cap与两阶段materialization，正做定向plan复评。设计处置见 [`reports/260906-review-disposition.md`](reports/260906-review-disposition.md)，计划处置见 [`reports/260906-plan-review-disposition.md`](reports/260906-plan-review-disposition.md)。

## 已确认的现状缺口

1. direct `stream:true /chat/completions` 在 response headers后走 `one_shot_delivery()`，整轮缓冲但不 replay；tear时会把失败 attempt的 partial bytes交给客户端。
2. 原 CodeBuddy `stream:false` 路径在 provider内部强制 upstream streaming并聚合；body tear没有经过现有 normalizer，clean EOF无 `[DONE]` 被合成为成功。
3. CodeBuddy与Xingchen在 provider层修改 Chat model-protocol payload；这与用户 2026-09-05～06 确认的 provider能力声明／pipeline执行边界不符。
4. direct buffered Chat 没有 provider response observation，完成行与 durable schema缺少 native finish reason、reasoning、ordered tool calls和 usage。
5. 当前关于 CodeBuddy upstream不支持 `stream:false` 的材料只有参考实现行为、代码注释与同源测试；P6真实负控未运行。用户决定本次不实测，保守把该 compatibility上移 pipeline并标明证据等级。

## 下一步

1. 按 [`plan.md`](plan.md) Task 2实现bounded raw SSE frame、strict Chat facts与standard multi-choice state。
2. 完成Task 2独立评审后再接single-attempt collector；后续任务顺序不变。
3. 每个任务在独立评审后按语义提交；不以绿灯本身划commit边界。

## 当前阻塞

无。Task 2 gate已关闭，可以进入Task 3。
