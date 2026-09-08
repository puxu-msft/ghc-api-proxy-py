# Hosted web search 历史证据

本目录存放支持 Hosted web search 演进脉络的历史设计快照。它们记录迁移前的设计边界、兼容矩阵与 hooks 阶段，**不是 current authority**，也不把其中的 agent-authored 设计表述升级为一手用户裁决。当前用户可观察行为以 [`../status.md`](../status.md) 为本主题状态入口；跨协议 Hosted web search 的规范性合同以 [`../../anthropic-responses-bridge/hosted-web-search-spec.md`](../../anthropic-responses-bridge/hosted-web-search-spec.md) 为准。

| 文件 | 原位置 | 性质与适用边界 |
|---|---|---|
| [`2604-tool-use.md`](2604-tool-use.md) | `../../archived-2604-rewrite/tool-use.md` | 旧的 tool-use 设计快照，保留“不在收到 400 后剥离并重试”等当时设计边界的背景；不证明该边界是用户逐字裁决，也不覆盖现行 Spec。 |
| [`2604-anthropic-compat.md`](2604-anthropic-compat.md) | `../../archived-2604-rewrite/anthropic-compat.md` | 旧的 Anthropic 兼容矩阵与请求整形快照，仅作 Hosted web search 相关兼容性历史背景；不描述当前实现或 current compatibility contract。 |
| [`2604-hooks-system.md`](2604-hooks-system.md) | `../../archived-2604-rewrite/hooks-system.md` | 旧的 hooks 生命周期、阶段与订阅者设计快照，仅作历史背景；不治理当前 pipeline、hook 或 server-tool 行为。 |

三份文件于 2026-09-08 逐字移动，未在迁移中改写。其正文中的相对链接反映快照当时的文档布局，不保证在新位置仍可解析，不能据此建立新的 current dependency；需要使用当前资料时应从上列 current carrier 出发。
