# Anthropic Responses bridge 文档 merged-state 独立评审

## 评审结论

- **评审范围**：current `main` `ed77c9d191df81c451c25161420515cca52ce6a4` 工作树中的 `docs/agents/anthropic-responses-bridge/{spec,architecture,acceptance,research,implementation}.md` 与 `docs/agents/documentation-restructure/plan.md`。六份文件均按最终工作树内容评审，不重复各文件全文首轮评审；重点对账状态／裁决／HEAD／下一步、reasoning wire 与 cardinality、server-tool、buffering、低概率策略、squash／archive 规则和目录治理。
- **总体 verdict**：**修复 major 后可进入下一阶段**。当前 merged state 不能作为本轮正式开发文档提交。
- **blocker 数**：0。
- **major 数**：5。
- **机械核对覆盖证据**：每次有效 shell 取证均在同一调用中验证物理根目录、`main` 与 `HEAD == refs/heads/main`；计算六份 current 工作树内容 SHA-256；核验 bridge 候选 commits、archive ref、相关 branches／worktrees 与九份评审报告；逐项扫描状态、verdict、HEAD、next step、route policy、reasoning carrier／cardinality、server-tool no-revive、buffering、低概率扩展、报告治理和 squash／archive 条款。另直接读取 cardinality 候选 `b876e626…` 的实现与测试，核对 empty／encrypted-only／multiple reasoning item 边界。
- **第一人称执行覆盖证据**：分别模拟了四条执行路径：按 `acceptance.md` manifest 启动 required gates；按六文档决定哪个文件可产生行为 expected；按 research 的 route 结论实现 native Responses 与 Anthropic bridge；按 documentation-restructure 阶段 0／1 生成新的 buffering truth。另模拟按 `implementation.md` 的 cardinality → liveness → request 顺序组合、squash、创建 immutable archive refs 和清理 worktrees；该收敛顺序本轮未发现 blocker／major。

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:7-8` — Required gate 绑定的 Spec／Architecture 内容身份已经失效

`acceptance.md` 声明 Spec SHA-256 为 `6c36c7fbab001b776787d17845d5deee9a97da6e3de8dac635c33b0e52d0a04a`、Architecture SHA-256 为 `74fef4675ebc61c89dbc31648acce6c21c8554649b8473ed20236c8a4e7e683c`，并明确规定 Spec hash 改变后必须先重做逐项 policy 对账，不能沿用旧 verdict。current 工作树实测分别为 `7e4389947998de7b0028d04eb23b6c4c053d4a35afbda9def67b967a76451699` 与 `ea6a3eca21c653096b17914d56497a5c6bbb6a8d1c237ebf2a055db24e31dc86`。因此执行者严格照文档运行时，所有 policy-dependent expected 都必须判为 `UNVERIFIED`；当前 `READY_FOR_FINAL_REVIEW` 不能支撑正式验收 oracle。

**修复建议**：以 current Spec／Architecture 内容重新做逐项 policy 对账，更新两处 hash 与 manifest 绑定，再对修订后的 Acceptance 做独立最终复评。不能只替换数字而保留未经重对账的 verdict。

### 2. [major] `docs/agents/anthropic-responses-bridge/implementation.md:7` — 行为 oracle 的权威边界与 Acceptance、Architecture 自述冲突

`implementation.md` 把 Spec 与 Architecture 并列放在“行为 oracle”下，只补充“规格继续优先于架构”；但 `acceptance.md:7-8` 明确只有 Spec 是行为 oracle，Architecture 只是用于细化观测点的参考，其待确认内容不得产生 expected；`architecture.md:3` 又明确自述为“待主会话确认的架构提案，不是已接受 ADR”。执行者遇到 Spec 未明确覆盖而 Architecture 给出推荐时，当前文本无法机械判断该推荐是 required behavior、实现建议还是尚待裁决事项。

**修复建议**：把 `implementation.md` 改为“Spec 是唯一行为 oracle；Acceptance 是验收 oracle；Architecture 是非规范实现参考”，并为 Architecture 中已获用户裁决／仍待确认的条目建立明确清单。若 Architecture 要升级为 accepted architecture，应另有用户接受记录或 ADR，不能仅凭 0／0 文档评审完成升格。

### 3. [major] `docs/agents/anthropic-responses-bridge/research.md:17` — “两个对外端点都默认走 Messages”错误扩大了 bridge route 裁决的作用域

Research 把用户裁决写成“对外 Anthropic Messages 与 OpenAI Responses 两个端点的默认 upstream leg 均为 Messages”。Spec 的冻结算法实际只描述 `/v1/messages` bridge：无 override 时双能力模型选 Messages、Responses-only 模型选 Responses；同时 `spec.md:30` 明确保留已有 OpenAI／Responses routes 的公共入口，`architecture.md:27` 也记录原生 Responses facade 调用 `send_responses()`。按 Research 执行会把 native OpenAI Responses 公共入口错误改道到 Messages，与 Spec 的 bridge scope 和当前生产事实冲突。

**修复建议**：把 Research 的裁决限定为“Anthropic `/v1/messages` bridge 对双能力 resolved model 默认选择 Messages；Responses-only 仍选 Responses”。原生 OpenAI Responses 公共入口是否允许改走 Messages 必须作为独立产品裁决，不能从 bridge route precedence 推导。

### 4. [major] `docs/agents/documentation-restructure/plan.md:50,553-565` — 文档重组计划会把 bridge 已冻结合同重新生成成未决问题

Plan 先写“block 的逐协议定义、失败／重取、History 时点、资源预算、背压、取消和 envelope 尚未决定”，随后在 buffering 门控问题中再次把 block 定义、retry 选择、History／usage 时点、单 block 上限、spill、取消所有权和 SSE envelope 全列为未决。对本 bridge，这些轴已由 `spec.md:294-330,515-518` 与 Acceptance 冻结：semantic block 是 Anthropic content block；pre-commit 可透明 retry、post-commit 默认 partial failure；memory-only、无 spill、无 16 MiB 专属阈值；SSE envelope、delayed response start、cancel／cleanup 与 History 时点均有合同。阶段 1 若照 Plan 从旧 streaming 文档生成新的 `docs/agents/buffering/spec.md`，会制造第二份把既决事项重新开放的开发真相源。

**修复建议**：把门控表按协议／主题分栏。Anthropic Responses bridge 一栏引用当前 Spec／Acceptance 并标为已决；只有未被该规格覆盖的其他协议或跨协议共用机制保留“未决”。阶段 1 的派生产物 ownership／provenance manifest 必须把 bridge Spec 作为该主题的规范输入之一，禁止从旧 `docs/2604-rewrite` 文档反向降级既有裁决。

### 5. [major] `docs/agents/anthropic-responses-bridge/spec.md:7,548` 与 `implementation.md:7,113-118` — 正式规格自身仍要求复评，但状态文档同时宣称它已定稿且无需下一轮

Spec 首屏 verdict 仍是 `READY_FOR_TARGETED_REREVIEW`，结论又写“现进入独立收口复评，复评放行后继续实施”；Implementation 则记录 Spec R3 已是 0 blocker／0 major、可定稿，并在文档复评表中写“无；内容再变更才触发新一轮”。从正式规格进入实施的执行者只读 Spec 会停在待复评，读 Implementation 则会跳过复评；两者不能同时作为当前状态。Architecture 仍自述“待主会话确认”，也进一步说明“评审通过”与“已接受”尚未被统一表达。

**修复建议**：在本轮 major 修复并完成 merged-state 复评后，同步更新各文件自己的状态头。Spec 应记录其最终复评报告与终态；Architecture 应明确“评审通过但待接受”或“已接受”的唯一状态；Implementation 只汇总这些源文档状态，不替源文档宣布定稿。

## 已核验但未形成 blocker／major 的重点

- **Reasoning wire 与 cardinality**：Spec、Architecture、Acceptance、Research 和 Implementation 均区分固定 upstream v1 carrier wire 与目标一-item一-block语义；候选 `b876e626…` 对 summary-only、non-empty encrypted-only、multiple reasoning items 和逐 block reverse 的实现／测试与该边界一致。空 summary＋空／absent payload 不生成无意义 block，Acceptance 已给出明确 oracle。
- **Server-tool**：六文档的有效产品合同均保持 no-revive／显式 reject；Implementation 已正确撤销外部验收 F1，不把 hosted server tool 偷渡为 bridge 能力。
- **Buffering 与低概率策略**：bridge 五文档一致保持完整 Anthropic content block 才提交、无 token／event live forwarding、memory-only、普通 request/global reservation、无 16 MiB 专属阈值；malformed repair、multimodal tool result、foreign thinking forwarding和公开 suffix 均有冻结基础行为，不阻塞基础合同。
- **Squash／archive**：cardinality → liveness → request 的组合顺序、共享 `responses_reasoning.py` 禁止整文件覆盖、main-side 复验、reviewed pre-squash HEAD 的 immutable archive ref、先 archive 再清理 worktree／branch 等规则可执行；相关 commits、refs 与 worktrees 均已机械核验存在。
- **目录与临时报告治理**：`docs/tmp` 被明确限制为待归纳证据，正式状态归入 `docs/agents/<topic>/`；新报告使用实际创建日与轮次，历史报告不复制改名。该规则与本轮用户指定的唯一报告路径不冲突。

## 主观建议

未列。本轮只报告会影响正式提交或后续执行正确性的 blocker／major。

## 最终判定

**0 blocker，5 major。** 修复上述五项并对 current merged state 复评到 0 major 后，方可把这组六份文件作为本轮正式开发文档提交。
