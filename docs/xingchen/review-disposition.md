# Xingchen provider 评审处置

> **Imported source-clone disposition，not current integration status.** 本账从 `origin/dotdev` 导入；closed 与下列 PASS 只适用于另一份 source clone 的 reviewed candidate。当前 checkout 不含文中 source/archive/squash commits，也没有 Xingchen 实现；报告与处置作为点时证据保留，不能据此声称 current main 已集成。

状态：imported-external-clone-snapshot

目标行为规格：[`spec.md`](spec.md)；当前 checkout 尚未实现

原始报告：

- [`reports/260904-protocol-review.md`](reports/260904-protocol-review.md)
- [`reports/260904-code-review.md`](reports/260904-code-review.md)

## Round 1

协议评审为 PASS。代码正确性评审提出 3 个 major，均为 C 级“落进产物但可逆”的裁定，全部采纳；没有驳回或暂定项。

| ID | 原发现 | 处置 | 首次确证 | 修复与验收 |
|---|---|---|---|---|
| M1 | Provider graph reload 移除新增 provider 后留下 default/fallback/count selectors | 采纳（C） | 在冻结 HEAD 运行探针得到 `providers=['ghc']`、`default='x'`、`restart_required=('model_providers.x',)`；显式 count leg 会在最终 revalidation 失败 | Spec §3.3 已补 provider selector 原子恢复。代码将让 graph pin 返回变化信号，并在 graph 变化时恢复启动时的 `default_model_provider`、`fallback_model_provider` 和 `inbound.anthropic_count_tokens.providers`；补 default/fallback/count 三种回归测试 |
| M2 | Pydantic validation input 把 gateway credential 写入错误字符串 | 采纳（C） | 无效 Xingchen 配置遗漏 `install_id` 时，`'LEAK-CREDENTIAL' in str(ValidationError)` 为 `True` | Spec §3.1 已规定 validation error 不含输入值。采用 Pydantic `hide_input_in_errors`，补 `ProxyConfig.model_validate` 与 CLI 两层负控，保留字段路径和错误原因 |
| M3 | Canonical-equivalent 静态模型跨 hash seed 选择不同上游 ID | 采纳（C） | `canonical('m-1.0') == canonical('m-1-0')`；由 frozenset 建 dict 时，`PYTHONHASHSEED=1/2` 选择 `m-1.0`，`3/4` 选择 `m-1-0` | Spec §3.1 已规定按 trim/lower/`.`→`-` 的模型名规则拒绝碰撞。配置 validator 将拒绝 canonical collision，并以 pipeline `canonical` 的测试断言校准转录 |

## Round 2

原代码 reviewer 对修复提交 `2ed92c5ee15aa28726673343a2df290537da494f` 复评为 PASS，可合并，M1–M3 全部关闭，0 blocker/major。完整转录见 [`reports/260904-code-rereview.md`](reports/260904-code-rereview.md)。协议 reviewer 的 C1–C5 范围未被本轮 config-only 修复触及，保留 Round 1 PASS。

最终 feature candidate 验证：

- `uv run --frozen ruff check src tests`：通过。
- `uv run --frozen pyright src tests`：0 errors、0 warnings、0 informations。
- `uv run --frozen pytest tests --cov=app --cov-report=term --cov-fail-under=80`：2251 passed、2 skipped、coverage 91.66%。

## 收口条件

- 三项修复均有能在旧实现上失败的回归测试。已满足。
- 原代码 reviewer 复评 M1–M3 的修复 diff 与相邻契约，达到 0 blocker/0 major。已满足。
- 协议 reviewer 只在修复触及其 C1–C5 范围时复评；本轮只修改 config validation/reload，因此保留 Round 1 PASS。已满足。
- Targeted suite、全仓 Ruff、全仓 Pyright 与项目全量 pytest/coverage 在最终 candidate HEAD 通过。已满足。

## 集成结果

- Reviewed source：`2ed92c5ee15aa28726673343a2df290537da494f`。
- Source archive：`archive/260904-xingchen-provider`，精确指向 reviewed source。
- Squash commit：`0cd1641aae90b4758a6ec4fc0fa053d24bf5906c`，基于当时 `main` 的 `33cf3870afee562351b49141efc8d5901f850c16`。
- Main-side gate：Ruff 通过；Pyright 0 errors、0 warnings、0 informations；pytest 2263 passed、2 skipped；coverage 91.69%。
- `main` 通过 `git merge --ff-only integration/xingchen-provider` 前进到 squash commit；共享索引仍为空，集成前已有的 translation-driver、其测试、`uv.lock` 和实验 WIP 保留。
