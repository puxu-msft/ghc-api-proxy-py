# Interaction context

本主题保留客户端逻辑会话如何从 inbound request 进入 provider interaction binding 的当前合同。

## 文档入口

- [`spec.md`](spec.md)：唯一的 current/living contract；区分 current implementation、仍待实现或验证的覆盖，以及非目标。
- [`history/README.md`](history/README.md)：point-in-time 设计、比较与 WIP 证据索引；历史材料不是 current authority。
- [`reports/260908-spec-extraction.md`](reports/260908-spec-extraction.md)：2026-09-08 从旧设计稿提炼本文并重新核对 current `src/` 的证据与迁移检查。

## 权威边界

本主题只拥有 interaction identity 的抽取、请求上下文载体、provider send seam，以及 GitHub Copilot interaction binding 的边界。header credential floor、path header policy 的一般规则、body translation、retry policy、token counting 算法和 provider routing 各由其原主题拥有；这里只描述 interaction identity 穿过这些路径时的合同。

[`spec.md`](spec.md) 是当前实现合同。历史设计稿与提炼报告说明条款来源和变化，但不把 2026-09-07 的 dirty WIP、设计建议或 agent 判断升级为用户裁决。
