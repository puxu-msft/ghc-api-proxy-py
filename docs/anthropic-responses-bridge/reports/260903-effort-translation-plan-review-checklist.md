# Effort translation 实施计划独立复核清单

- review_id：effort-translation-plan-260903
- attempt_id：effort-translation-plan-gpt-opus-a1
- review_scope：`.dev/docs/anthropic-responses-bridge/plan-effort-translation.md` current working tree及其绑定的current Spec／Acceptance
- report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan.md`
- r2_attempt_id：effort-translation-plan-gpt-opus-a2
- r2_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r2.md`
- r2_scope：R1 M1～M6、整改diff与直接相邻接口；R1绑定的旧checklist hash保持point-in-time意义
- r3_attempt_id：effort-translation-plan-gpt-opus-a3
- r3_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r3.md`
- r3_scope：R2-M1／R2-M2、pure nested Task 2边界、Task 3旧consumer清单、Task 5 profile producer与异常facts mutation；旧报告hash保持point-in-time意义
- r4_attempt_id：effort-translation-plan-gpt-opus-a4
- r4_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r4.md`
- r4_scope：R3-M1、Task 2 spy-only header证据、Task 3 production consumer→test consumer→definition删除的严格顺序及直接相邻接口
- r5_attempt_id：effort-translation-plan-gpt-opus-a5
- r5_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r5.md`
- r5_scope：R4-M1、七个确切文件上的legacy-symbol scan、pre／post同选择面及直接相邻步骤

## 必须逐条核验的断言

- P1：Spec request-level `ThinkingEffortIntent`、双向矩阵、target profile、ultracode、direct bypass、send／count和facts持久化每项都有明确Task owner与证据。
- P2：每个Task先实现production并运行直接探针，再补关键测试；没有被技能默认TDD覆盖项目implementation-first规则。
- P3：所有计划路径、现有符号和测试文件真实存在；新符号在产生Task中有精确签名，消费者只出现在其后。
- P4：`ThinkingTargetProfileConfig`／runtime profile／CompiledThinkingProfiles／Chain／routing／TranslationTarget的import方向无循环，配置只在startup编译。
- P5：bundled config深合并与dict顺序确实能让新增用户regex成为最后fullmatch；同pattern覆盖和不同pattern覆盖都有可执行测试。
- P6：source header在`shape_request`清空前捕获，send与count共用；header不被重新转发到Responses。
- P7：逐消息effort对同值override、多个pending control、future-only control与original payload有唯一算法；beta／非法shape零upstream。
- P8：Forward enabled排除none、disabled要求none、缺省high、explicit effort优先、budget只记loss的所有终态明确且不调用已删除resolver。
- P9：Reverse none／minimal／五档／null、profile正负域、always-on、extended-only、`[enabled,adaptive]`fallback、manual budget两阶段检查与effort对齐均可按计划实现。
- P10：nested residual同格式重建、跨格式精确loss与writer-owned effort覆盖顺序明确，不重复loss。
- P11：profile selected／rejected facts在成功与`TranslationRefused`两条路径都进入RequestContext、RequestTrace、RequestLine和JSONL；`lossless`不被观察facts改变。
- P12：direct Anthropic／Responses路径不执行translator／profile policy，现有subscriber与legacy converter不被本轮重构。
- P13：每个关键验收机制有静态expected与能打红的单侧控制；mock／catalog／live证据边界没有外推。
- P14：五个Task是可独立评审的语义切片；commit pathspec精确且message使用`-F`；`.dev`只在主工作树更新，不在code worktree复制。
- P15：计划无TBD／TODO／“类似Task”／未定义helper／二选一实现；probe命令可运行，最终验证命令符合项目CLAUDE.md且不含`ruff format`。

## 评审输出要求

本轮只展开blocker与major，最多6条、每条不超过6行；minor／nit只计数。逐条回应P1～P15，引用计划与源码行号；发现不可执行步骤时给出具体输入→错误结果。报告最后必须有整体判定、“我最没把握的三个判断”、“执行本契约时遇到的摩擦”和`## 交付声明`，含delivery_complete、completed_at、finding_total及四档计数。只修改自己的报告，不修改计划／Spec／源码。
