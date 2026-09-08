# `app.server` 布局：延后项

**这份是活文档**，只放**未闭合**的条目。查清、决定或做掉的条目从这里移出，并入常规文档（`status.md`、`decisions.md` 或代码注释），移出时带上出处。编号是标识不是序列，移走后不补号。

设计与提案时点分析在 [README.md](README.md)，用户裁决在 [decisions.md](decisions.md)，当前实现状态在 [status.md](status.md)。

## D-A. Gemini 实现时必须先看的四件事

**登记时间**：2026-08-23，随 Azure/Gemini 路由入口切片。
**为什么在这里**：用户裁定「实际处理尚未实现，可以留空」，所以 501 本身不是缺口。但旧链在这件事上已有的东西**无处可查**——这份台账就是那个指路。2026-08-23 用户另行指示把旧实现整体归档，第 1 条因此从「有一半还在活树」改写为「全部在哪、哪一件不是整文件搬迁」。
**来源**：[reports/260823-azure-gemini-route-entry-review-regression.md](reports/260823-azure-gemini-route-entry-review-regression.md) §4.2、§5.4，路径与引用关系我逐条复核过。

1. **旧 Gemini 实现现在全部在 `src/.archived/` 里**，2026-08-23 由用户指示归档。归档前它有一半活在 `src/app/` 且无任何生产调用方——这才是登记它的理由：搬进归档树是为了让「它在哪」有一个确定答案，不是为了让它消失。

   | 现在的位置 | 归档前 | 备注 |
   |---|---|---|
   | `src/.archived/app/protocols/gemini.py` | `src/app/protocols/gemini.py` | `GEMINI_METHODS`、`parse_model_with_method`、`gemini_to_openai`、`openai_to_gemini`；整文件搬迁，`git log --follow` 可追 |
   | `src/.archived/app/models/gemini.py` | `src/app/models/gemini.py` | 请求/响应 Pydantic 模型；整文件搬迁 |
   | `src/.archived/app/tokenization/gemini_estimator.py` | `src/app/tokenization/estimators.py` 中的三段 | **不是整文件搬迁**：`estimate_gemini_input` 与两个私有辅助函数、以及只有它用的 `app.models.gemini` import 被从一个仍在服役的共享文件里切出来；该文件的 Anthropic 与 Responses 估算器还在活树。`git` 不会把它识别为重命名 |
   | `tests/.archived/unit/protocols/test_gemini_protocol.py` | `tests/unit/protocols/test_gemini_protocol.py` | 整文件搬迁 |

   同时清掉的两处出口：`src/app/protocols/__init__.py` 原本全部内容就是 `parse_model_with_method` 的再导出，现在只剩一段说明；`src/app/tokenization/__init__.py` 不再导出 `estimate_gemini_input`。

   `tests/unit/test_module_boundaries.py` 的 `_ARCHIVED` 加了 `app.protocols.gemini` 与 `app.models.gemini`——**这两条是该元组里第一次出现的子模块名**，因为 `app.protocols` 和 `app.models` 本身都是活包，只有它们底下的 Gemini 模块走了。已实测该守卫有鉴别力：把归档件复制回活树立刻打红，还原后转绿。

   实现时**优先复用而不是重写**。特别是 `parse_model_with_method`，它的 `rpartition(":")` 语义与本次路由模板的贪婪段一致（含冒号的模型名如 `vendor:family` 仍是一个模型），三方（旧链、`copilot-api-js` 的 `lastIndexOf`、Starlette 的 `[^/]+` 回溯）已交叉印证。

2. **方法白名单现在有两份独立表达**：`src/app/server/routes/table.py` 里三条模板字面量，与 `src/.archived/app/protocols/gemini.py:6` 的 `GEMINI_METHODS`。内容相同、来源无关。实现时择一为准，另一份改为派生或引用。

3. **`countTokens` 旧链走本地估算**（`estimate_gemini_input`，不打上游），与新链 `/v1/messages/count_tokens` 的 `provider(local)` 那一档是同一类事。当前 501 是对的，但「它该走本地估算而不是上游」这条知识只存在于归档代码里。

4. **错误信封形状待裁**，见 D-B。

## D-B. 未实现端点的错误信封是否要按 inbound 方言分化 —— 待用户裁决

**登记时间**：2026-08-23。
**现状**：Gemini 路径的 501 用的是本代理的通用信封 `{"error": {"message": ...}}`（`src/app/server/routes/inference.py`）。
**旧链与参考实现都不是这个形状**：`src/.archived/app/routes/gemini.py:112-124`、`:162-174` 答的是 Gemini 信封 `{"error": {"code", "message", "status"}}`，`copilot-api-js` 的 `src/routes/gemini/route.ts:34-43` 同。Gemini 客户端 SDK 解析的是 `error.code` / `error.status`。
**为什么不在本切片决定**：这是对外契约，且不限于 501——一旦分化，Gemini 路径上**所有**错误都要跟着分化，波及面远大于「留空」这一步。
**已经顺手做掉的那半**：501 的 message 原本吐的是路由表模板 `/v1beta/models/{model}:generateContent`，客户端拿到花括号什么也做不了；已改为 `request.url.path`。

## D-C. 升级 FastAPI 时要重跑的判据

**登记时间**：2026-08-23。
**事实**：`_dispatch` 从 `request.scope["route"].path` 取路由模板。这个键**完全由 FastAPI 提供**，Starlette 自己从不写它（`fastapi/routing.py:1258` 的 `APIRoute.matches`，与 `:1799` 的 `_IncludedRouter.handle`；版本 FastAPI 0.141.1 / Starlette 1.6.0，评审实测）。
**它消失了会怎样**：退路 `request.url.path` 永远不含 `{}`，所以对 6 条含参数的模板路由只可能命中不到（→ 我们自己的 404 `unknown endpoint`，会写一条 completion 日志，与 FastAPI 的 `{"detail":"Not Found"}` 形状可区分），对字面路径路由则给出与模板相同的正确答案。**失效形态是「Azure 与 Gemini 全线 404、其余照常」的局部退化，不是错路由。**
**处置**：不为退路加防护（那是给一个不可达状态加代码）。但升级 FastAPI 时，含参数的那 6 条路由是要实测的判据。
**来源**：同上评审报告 §2.2，机制与三种挂载形态均为实测。
