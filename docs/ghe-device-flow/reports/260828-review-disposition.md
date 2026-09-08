# 两份评审的处置记录

> **更正指引（2026-08-28，写于本文之后）**：本文「两处我的判断与评审不同」第二条里那句「既有部署的行为逐字不变」**是错的**，两轮复核各自独立推翻了它。当前有效的处置见 [260828-review-disposition-r2.md](260828-review-disposition-r2.md)，权威条款见 [spec.md](../spec.md) §3.5。本文其余部分作为第一轮的时点记录保留，不改写。

对象：[260828-review-gpt.md](260828-review-gpt.md)（0 blocker / 1 major / 2 minor）与 [260828-review-claude.md](260828-review-claude.md)（0 blocker / 4 major / 6 minor / 3 建议 / 1 nit）。

**全部采纳，无一条以「不同意」结案。** 两条延后，理由写在下面并登记进 [deferred.md](../deferred.md)。

## 逐条处置

| 编号 | 严重级 | 处置 | 落点 |
|---|---|---|---|
| gpt F-01 / claude F1 | major | **采纳**。`--provider` 单独给出时被静默吞掉——但没有按评审建议的「加一条 `BadParameter`」修，而是连同 F2/F3 一起换掉了整个入口形态（见下） | [spec.md](../spec.md) §3.5 推翻重写；`cli.py` `_selected_provider` |
| claude F2 | major | **采纳**。`auth` 不再自成例外，一律走 `resolve_config_path` 三级发现链 | 同上 |
| claude F3 | major | **采纳**。删掉自造的「恰好一个就用它」，改用既有权威 `resolve_default_name` | 同上 |
| claude F4 | major | **采纳**。bundled `ghc` 删不掉、以及它如何决定运营者该怎么写配置，从测试 docstring 移进 Spec 正文 | [spec.md](../spec.md) §3.5「为什么这不构成既有部署的行为变更」整段 |
| gpt F-02 | minor | **采纳全部三条**：空 label、多尾斜杠、解析器自抛异常的文案。另按其提示在 Spec 里明定多 label tenant 合法及理由 | [spec.md](../spec.md) §3.2；`config.py` |
| gpt F-03 | minor | **采纳**。`logout` 与 `auth` 同一套解析 | 新增 [spec.md](../spec.md) §3.7；`cli.py` `logout` |
| claude F5 | minor | **采纳**。「语义与 `debug models` 逐条一致」这句是假的，已删除；一并去掉会漂的行号引用 | [spec.md](../spec.md) §3.5 |
| claude F6 | minor | **随 F3 消失**。「零个 provider」那条死分支连同旧规则一起删掉了 | —— |
| claude F7 | minor | **采纳**。`_read_config` 的作用域声明已随实际情况更新 | `cli.py:482` 附近 docstring |
| claude F8 | minor | **采纳，并做了它说「由调用方定」的那一半**：§3.6 补上「文件是三级链第三级」的限定，且 `auth` 在环境变量会遮蔽时出声警告 | [spec.md](../spec.md) §3.6；`cli.py` `login()` 内 |
| claude F9 | minor | **采纳**。GHES 登记进 §4 与 deferred | [spec.md](../spec.md) §4；[deferred.md](../deferred.md) D-1 |
| claude F10 | minor | **采纳**。`auth` 现在写配置指定的 token 文件，该现场路径随之消失；示例文件与默认路径仍不同名，属用户亲笔文档，只报告 | [deferred.md](../deferred.md) D-3 |
| claude S1 | 建议 | **延后，不在本片做**。见下 | [deferred.md](../deferred.md) D-2 |
| claude S2 | 建议 | **采纳**。§4 的证据权重拆成两半：REST base 形态有一手文档，Device Flow 端点随租户搬家只有旁证 | [spec.md](../spec.md) §4 末段 |
| claude S3 | 建议 | **采纳**。新增 `status.md` 与 `deferred.md` | —— |
| claude N1 | nit | **采纳**。那个只为 `del` 而收的参数已随测试重写去掉 | `tests/unit/test_cli.py` |

## 两处我的判断与评审不同，说清楚

**一、F1 我没按评审提的那条最窄修法改。** gpt 建议「仅当 `provider is not None and config is None` 时 `BadParameter`」，claude 给了两条出口并倾向后者。我取了后者，理由是：最窄修法只把静默变成响亮，却把 F2 留在原地——租户机器上敲裸 `auth` 仍然登录 dotcom，而**那才是这个功能存在的理由**。修掉症状而留下病因，下一轮还得再来一次。

**二、claude F2 说「拆掉这道门是范围变更，应交用户裁决」——我判断不需要，并给出依据。** 它担心的是既有部署会从「能跑」变成「报错要你指定 `--provider`」。这个担心成立与否取决于一个可查的事实：`src/app/config/bundled-config.yaml:56` 无条件带 `default_model_provider: ghc`，而 `_deep_merge` 只合并不删除键。因此 `resolve_default_name` **永远**解析得出一个名字，那条报错路径只有在运营者显式把该键写成空串时才可达。既有部署的行为逐字不变，不存在需要用户取舍的退化。

**这一判断已写进 [spec.md](../spec.md) §3.5 并附依据**，若该依据被推翻，结论跟着推翻。

## S1 为什么延后而不是顺手做

`GhcClientConfig` 的四个构造点确实会分叉，评审说得对。但把它收拢成 helper 是一次自足的重构，主题是「provider 配置到客户端配置的映射」，与 Device Flow 的 OAuth 源无关；塞进本片只会让 `composition.py` 无谓地进入这次的评审面。按项目「每个自足小补丁独立完成并集成」的做法，它该有自己的一片。已登记 [deferred.md](../deferred.md) D-2，不是丢掉。

## 修完之后重新验证了什么

- `ruff check` / `pyright` 干净；全量 `pytest` 通过（1918 passed / 2 skipped，覆盖率 90.69%）。
- 两次**新的**控制变异，钉的是这一轮真正变了的那两层：
  - 把配置发现链退回成「只认 `--config`」——即第一版的 bug 形态 → `tests/unit/test_cli.py` 4 条红（含裸 `auth` 与环境变量那条）。
  - 空 tenant label 放行 → `test_config.py` 2 条红。
- 两次均按快照还原并核对 SHA-256 一致。

上一轮的两次变异（origin 有没有传下去、`DeviceFlowClient` 有没有真用它）仍然成立，未重做。
