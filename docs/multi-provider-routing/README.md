# 多 provider 路由与模型目录

本主题记录 `model_providers` 多 provider 配置、按模型路由、模型目录公开接口和 `/api/status` 的当前行为。

## 文档入口

- [`spec.md`](spec.md)：当前行为 Spec，拥有路由规则、候选名称、serviceability、模型列表筛选和状态端点的规范性事实。
- [`status.md`](status.md)：当前 checkout 的实现状态、提交落点、验证入口和已知边界。
- [`deferred.md`](deferred.md)：仍未闭合的设计事项；已经实现的模型目录行为不再留在这里。
- [`review-disposition.md`](review-disposition.md)：2026-08-27 路由特性的历史评审处置。
- [`reports/`](reports/)：评审原件。原件保留为证据，不作为当前行为权威。

## 当前对外模型目录

代理提供 `GET /models`、`GET /v1/models` 和 `GET /openai/v1/models`。三个入口共享同一份路由可达集合，默认返回 serviceable 模型；非 default provider 的模型以 `provider/model` 形式发现。

列表接口支持 `format=openai|pi`，也支持可选的 `provider` 查询参数。`provider` 按最终 `owned_by` 精确筛选，不改变路由解析；未知或空值返回空列表。

## 权威边界

本主题只描述当前 Python chain 的多 provider 路由和模型目录。用户控制的 `docs/.human-controlled/` 不由本主题直接修改；需要用户文档变化时，先写入 `.dev/human-controlled-docs-candidates/`。

代码中的 docstring、测试和历史评审报告可以解释实现，但与本主题 Spec 冲突时，以当前 `spec.md` 为准；如果实现改变了行为，先修订 Spec，再更新 status 和测试引用。
