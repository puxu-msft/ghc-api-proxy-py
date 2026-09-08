# Interaction-context Spec 提炼与迁移报告

日期：2026-09-08

## 1. 范围与判据

本次只创建 `.dev/docs/interaction-context/` 并把精确源 `.dev/docs/tmp/260907-interaction-context-design.md` 移入 topic-local history。没有修改 `src/`、tests 或其他文档路径；没有删除材料，也没有执行 `git add`、commit 或 push。

先读材料：

- [`../../dotdev-repository-repair/README.md`](../../dotdev-repository-repair/README.md)：point-in-time 材料不得升级为 current authority，迁移必须先建立 retained owner；
- [`../../dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md`](../../dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md)：唯一“需活主题”的材料是本设计稿，要求先按 current source 提炼 living Spec，再保真归档；
- [原设计稿](../history/260907-interaction-context-design.md)：完整读取 450 行。其长期承重内容是 identity 三分、六候选顺序、显式 provider/GHC seam，以及 direct/translated/retry/count_tokens/anonymous 边界；当日 HEAD/dirty WIP 和方案比较不直接进入 current authority。

核对基线：主仓 `HEAD` `3097c5cb0142d3e066f16921bf7c606780a7f3f3` 的 current working tree。核对时工作树已有与本任务无关的 `src/` 修改；下列结论以磁盘上的 current source 为准，不把它们冒充该 HEAD 的纯提交态。

## 2. 提炼结果

新建：

- [`../spec.md`](../spec.md)：current/living contract；
- [`../README.md`](../README.md)：主题入口与权威边界；
- [`../history/README.md`](../history/README.md)：将 2026-09-07 原稿标为 dirty-WIP / 设计比较；
- 本报告。

Spec 对每一组边界分别标记 **current implementation**、**仍待实现或验证**、**非目标**。没有把原稿建议、WIP 或 agent 判断改写成用户裁决。

## 3. Current source 证据

| 合同 | 代码证据 | 当前测试证据 |
|---|---|---|
| 六候选的有序、case-insensitive、blank-skip 抽取 | `src/app/pipeline/session_identity.py:5-12,22-31` | `tests/unit/server/test_server_inbound.py:53-67` 只覆盖 Claude 候选压过 generic；完整表驱动覆盖仍缺 |
| 抽取后从 forwarding bags 删除 | `src/app/server/inbound.py:64-76`；`src/app/pipeline/session_identity.py:34-41` | `tests/unit/server/test_server_inbound.py:53-67` |
| `id` / `interaction_id` / memoized provider resolution | `src/app/pipeline/request.py:77-82,119-122` | `tests/unit/pipeline/test_direct_driver.py:736-776` |
| provider send 显式 seam | `src/app/model_provider/base.py:80-97`；`src/app/pipeline/direct_driver/base.py:496-506` | driver tests 观察 declared、frozen retry 和 anonymous fallback |
| GHC inference 必须有显式 id，并写 owned header | `src/app/model_provider/github_copilot.py:189-227`；`src/app/model_provider/ghc_client/client.py:40-68,138-216`；`src/app/model_provider/ghc_client/headers.py:19-55` | `tests/unit/model_provider/test_model_provider.py:412-429`；`tests/component/model_provider/ghc_client/test_client.py:205-227` |
| 非 GHC provider 接受并忽略该字段 | `src/app/model_provider/codebuddy.py:180-191`；`src/app/model_provider/xingchen/provider.py:108-119`；`src/app/model_provider/openai_compatible/provider.py:177-188` | protocol/fake call sites随 suite 类型面覆盖 |
| direct/translated 共用 send seam，translated whitelist 为空 | `src/app/pipeline/driver.py:112-151,188-299`；`src/app/pipeline/request_headers.py:45-77` | `tests/int/test_pipeline_app.py:616-633` 钉住 translated session binding |
| retry 与 delivery reopen 复用 context | `src/app/pipeline/direct_driver/base.py:356-410`；`src/app/pipeline/driver.py:241-299`；`src/app/server/routes/inference.py:938-978` | pre-header retry freeze 已测；delivery reopen identity 专项仍缺 |
| GHC count 不走 client interaction seam | `src/app/model_provider/base.py:100-116`；`src/app/model_provider/github_copilot.py:229-242`；`src/app/model_provider/ghc_client/client.py:174-184` | component endpoint test 观察 count 使用 provider instance id；inbound-session negative test 仍缺 |
| provider-instance fallback 的构造 | `src/app/server/composition.py:457-489` | current tests以固定 `interaction_id=\"interaction\"` 构造 fixture |

定向回归：

```text
uv run pytest -q \
  tests/unit/server/test_server_inbound.py \
  tests/unit/pipeline/test_direct_driver.py \
  tests/component/model_provider/ghc_client/test_headers.py \
  tests/component/model_provider/ghc_client/test_client.py \
  tests/int/test_pipeline_app.py \
  -k 'interaction or session_identity or session_id or no_client_headers_sends_none'

6 passed, 341 deselected, 1 warning in 3.60s
```

该命令只证明被选择的六项现有测试通过；它不证明未被现有测试命名的六候选矩阵、direct e2e、delivery reopen、anonymous cross-request 或 inbound-session count negative boundary。

## 4. 未采纳的旧状态

下列内容保留在 history 原稿，但没有写入 current contract：

- “HEAD 没有 `RequestContext.interaction_id` / provider 只有 `extra_headers`”是 2026-09-07 的旧对照面，current source 已不成立；
- “driver 直接传 `context.interaction_id`，匿名 inference 落到 GHC 进程 UUID”是旧 WIP，current source 已改为 `interaction_id_for_provider()`；
- 原稿建议直接计算 `context.interaction_id or context.id`，current source 又增加 `provider_interaction_id` memoization，以防 mutable subscriber 在 retry/reopen 间拆分 binding；
- 原稿建议 GHC inference method 可选参数并保留 method-level fallback；current GHC inference methods要求显式 `interaction_id`，fallback 只留给 provider-owned catalog/count 路径；
- 原稿测试矩阵是建议，不是“已经验证”。Spec 只把实际存在的测试列为已验证，其余保留为待验证；
- “count_tokens 默认不绑定”作为 current interface fact保留，但没有升级为永久产品裁决。

## 5. Link 与 source/target 检查

移动完成后的实际结果：

- **source absent**：`.dev/docs/tmp/260907-interaction-context-design.md` 不存在；
- **destination present**：`.dev/docs/interaction-context/history/260907-interaction-context-design.md` 存在；
- moved original SHA-256 为 `a5e13fb123580439736256f38660ecb6bdf65f431bd2dcda27eb0ac39099bf4b`，与移动前记录一致；
- 扫描本 topic 五份 Markdown 的相对 links：`links-checked=14`、`missing=0`；
- `.dev` repo 的精确 scoped status 为 `?? docs/interaction-context/`；原 tmp 文件没有 tracked deletion 条目，因此 Git 不能在这一工作树中把该 filesystem move显示成 rename。source/target 与 hash 检查承担移动完整性证明；
- 本任务的写操作仅为创建 `.dev/docs/interaction-context/` 下四份新文档，以及把精确源移动为该目录下第五份文档；未对其他路径执行写操作。
