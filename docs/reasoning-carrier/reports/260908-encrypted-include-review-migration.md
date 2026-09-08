# FRR-01：encrypted-include review 迁移报告

## 评审范围

本次只判定 `.dev/docs/tmp/260908-reasoning-encrypted-include-review.md` 是否应由 `reasoning-carrier` 保存为历史原件，并在获准范围内移动该唯一源文件、建立/更新本主题 history index 和记录迁移证据。判据先读取 `.dev/docs/reasoning-carrier/spec.md`、`tracking.md`、既有 history snapshot、三份 review disposition，以及 `.dev/docs/dotdev-repository-repair/README.md`；随后完整读取候选评审，并对照它所涉及的当前 `src/`、配置、subscriber 注册/composition 与测试。未修改产品源码、测试、配置、Spec 或其它主题文档。

## 总体 verdict

**归入 history：通过。** 该文件是明确绑定 2026-09-08 非单一 commit 工作树的独立评审，而非产品 Spec、当前实施账或用户裁决。它保留一个当时的 `should-fix`、两个 `nit`、测试搜索面，以及对候选人控配置材料的 provenance 限制，具备后续追溯价值；将其留在 `tmp/` 会使暂存目录仍承载未归口证据。

## Blocker 数

0。

## 归档与权威边界

- 原件已原样从 `tmp/` 移至 [`../history/260908-reasoning-encrypted-include-review.md`](../history/260908-reasoning-encrypted-include-review.md)，没有编辑其正文。
- 新建的 [`../history/README.md`](../history/README.md) 将该原件标为：绑定当时工作树的独立评审、含 `should-fix` 与候选人控材料 provenance、非 current authority；并将 current contract 和 current implementation state 分别指回 `spec.md` 与 `tracking.md`。
- 当前工作树的 integration test 已有该评审 `include-01` 所建议的默认 `["reasoning.encrypted_content"]` 透传控制，并单独断言 `ProxyConfig().reasoning_encrypted_include == "passthrough"`。这是迁移时的 current-source 观察，不倒写进历史原件，也不把它表述为该原评审的后续独立复评结论。
- 评审所涉的配置默认、Responses-target gate、attempt-prepare wiring 和 `to_openai_responses()` 不自行生成 `include` 的事实，与 current source 一致。该 review 没有指出任何产品行为与 current reasoning-carrier Spec 的 contract 冲突；Spec 不因本次归档而改写。

## 后续项处置

不在 `tracking.md` 或 deferred 新增事项。原件的 `should-fix` 已是有界的工作树评审事实，而不是 current Spec 的待裁决项；迁移时看到的 current integration-test control 也不构成足以关闭原评审的独立验收。候选人控文档继续只是候选，不能由本报告变成产品 authority。

## 验证

- 移动前 SHA-256：`e290f8107afbdccdb2bafbf1c81a8b1ab3f0eb5f6034000194e1cc2d3e629c79`。
- 移动后 destination SHA-256 相同；source 已不存在，destination 存在。
- `history/README.md` 的四个 Markdown targets（current Spec、tracking、两份 history original）均在本工作树中解析。
- 候选原件未含需要随移动改写的 Markdown 入站链接；修复主题的 readiness report 对旧路径的提及是历史 location 说明而非 Markdown target。

## FRR-01 记录层闭合（2026-09-08）

本节取代“后续项处置”中“不在 `tracking.md` 或 deferred 新增事项”的初始迁移判断。`include-01` 现由 [`../tracking.md`](../tracking.md) 的 `RC-TF-01` 作为 current test follow-up 持有，并 canonical 链接唯一 history 原件 [`../history/260908-reasoning-encrypted-include-review.md`](../history/260908-reasoning-encrypted-include-review.md)。

因此 FRR-01 的**记录层**已闭合：唯一历史原件有确定去处，仍需独立复验的 test concern 也有当前 owner。该 owner 明确保留三条边界：finding 来自点时独立 review；当前源码只见部分 integration cover、尚未独立复验；登记不构成用户裁决，也不改写产品 contract 或 Spec。
