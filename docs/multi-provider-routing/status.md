# 多 provider 路由状态

更新时间：2026-09-08。

当前 checkout 已完成多 provider 路由与模型目录的两项后续修复：

- `52d57a09 fix: expose secondary provider models`：为非 default provider 的可用模型生成 `provider/model` 候选名，使 secondary provider 能从模型目录被发现。
- `3b223e8e fix: filter model listings by provider`：让三个模型列表入口消费可选的 `provider` 查询参数，按最终路由 owner 筛选。

## 当前实现

`model_providers` 的 provider 名参与 `provider/model` qualifier 解析。`default_model_provider` 同时决定没有 provider 限定时的归属，以及显式写了未知 provider 时的兜底归属。模型名映射仍由 `model_mappings` 承载，路由选择和目录展示共用 `app.pipeline.routing.route_table`。

当前映射解析由 `app.pipeline.model_resolution.resolve_with_catalogs` 执行：裸请求先查裸 mapping 键，再查 default-provider 限定键；带 provider 的请求先查完整键，再查以 default provider 替换前缀的键。某个候选键一旦存在，目标不可用时只沿目标自身的 mapping 链继续，不能切换另一候选键或 passthrough；裸目标按来源 provider、default provider 查目录，全限定目标只查值中的 provider。mapping value 的 `@format` 会成为显式出站格式，最终无可用模型在路由阶段返回 400。

模型目录候选包括所有 provider 的裸可用模型 ID、非 default provider 的 `provider/model` 限定 ID，以及 `model_mappings` 的键。裸 secondary ID 通常会按 default provider 解析而变成不可服务；限定 ID 才是无需额外 mapping 即可到达 secondary provider 的可发现名称。模型列表只返回 `serviceable == "yes"` 的条目，`owned_by` 是实际会处理该条目的 provider 名。

`GET /models`、`GET /v1/models` 和 `GET /openai/v1/models` 共享 `list_models` handler。`format` 控制 OpenAI 或 Pi 投影；`provider` 是可选精确筛选项，过滤基于最终 `owned_by`，未知或空值不会报错而是返回空数据。

`GET /api/status` 返回每个 provider 的目录状态和完整 routes 表；`GET /health/readiness` 只依据 default provider 的可用目录判断就绪。两者共享 readiness 判据，但不是同一个响应。

## 代码与测试落点

- 路由候选生成：`src/app/pipeline/routing.py` 的 `_candidate_names`、`_report_for` 和 `route_table`。
- 模型列表投影与筛选：`src/app/server/routes/ops.py` 的 `_model_entries` 和 `list_models`。
- 入口回归：`tests/int/test_pipeline_ops_routes.py` 中的模型列表、provider owner、secondary provider qualified ID 与 provider filter 测试。
- provider catalog 行为：各 provider 的实现与 `tests/unit/model_provider/` 下对应测试。

## 当前边界

`provider` 查询参数只作用于模型列表端点，不改变 `GET /models/{model}` 的单模型路由，也不为 Gemini 或 Azure 的 URL 路径模型参数增加新的 provider 语法。

`docs/.human-controlled/config.example.yaml` 已由用户更新，明确 `default_model_provider` 同时承担默认与未知 provider 兜底；代码与本状态按该用户文档同步。`review-disposition.md` 与 `reports/` 保留为历史证据，旧的候选集推导只在其历史上下文中有效，不得覆盖当前 Spec。

## 验证入口

模型目录关键回归位于 `tests/int/test_pipeline_ops_routes.py`。代码改动的常规检查仍以项目根 `CLAUDE.md` 和 `.claude/rules/00-development-workflow.md` 中的 Ruff、Pyright、pytest 命令为准。
