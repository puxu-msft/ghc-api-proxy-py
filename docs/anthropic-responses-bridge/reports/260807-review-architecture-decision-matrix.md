# Architecture 用户裁决矩阵独立终审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/architecture.md`。本轮仅逐条复核 `docs/tmp/260806-architecture-decision-reading-check.md` 的两项 major，并检查对应修订是否引入新的 blocker／major；为核对 Spec 已决边界与用户阅读入口，交叉读取 current `spec.md` 与 `README.md`，未重做技术 R3。
- **总体 verdict**：**可进入下一阶段。** 两项原 major 均已关闭，未发现修订引入的新 blocker／major。Architecture 已达到用户裁决就绪状态。
- **blocker 数**：0。
- **major 数**：0。
- **用户阅读就绪结论**：**用户可以从 `README.md` 开始，按其阅读顺序完整阅读五份文档，尤其完整阅读 `architecture.md` 后，分别裁决 `D-ARCH` 与 `D-MIGRATION`。** 独立终审通过不替代用户接受。
- **证据基线**：每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。终态复核时 current `architecture.md` SHA-256 为 `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327`。

## 双视角覆盖证据

### 机械核对

- 完整读取 current `architecture.md`、上一轮阅读核对报告和 `README.md`，并读取 current `spec.md` 中与完整 block／首 block 前零 success headers／`message_start`、post-commit partial failure 和 continuation 边界有关的正式条款。
- 扫描 Architecture 全文的“待用户裁决／接受／另行裁决／独立 ADR／重开 Spec／用户门控”措辞，确认 current 文本明确声明全文唯一待决项为 `D-ARCH` 与 `D-MIGRATION`，旧 `ADR-BRIDGE-02`～`06` 只作为已决 Spec 输入或历史承载记录。
- 核对唯一裁决矩阵恰有 `D-ARCH`、`D-MIGRATION` 两行；核对方案 B 的不可拆分核心逐项列出五项，并另列可局部调整边界；核对迁移表同时列出 M1／M2 的优点、风险、兼容代价与退出条件。
- 核对正式 bridge route 启用前置门覆盖 single owner、per-attempt semantic conversion、protocol／transport、delivery、lifecycle／History 与真实入口验收，并确认 M2 另有受约束 adapter 边界及过渡退出条件。
- 对 `architecture.md` 执行 `git diff --check`，未发现 whitespace error。

### 第一人称执行模拟

- 模拟用户选择 `D-ARCH=B`：可以明确知道接受的是 typed facts、single driver、protocol／transport 正交、完整 delivery chain、History projection ownership 五项共同核心；删除或替换任一项必须记录为对 B 的修改，具体类型名、函数签名、模块拆分、sink 内部调用粒度等列明为可局部调整。
- 模拟用户选择 `D-ARCH=B` 后独立选择 M1：实施者必须一次建立完整 B 核心，并在全部 route 前置门通过后才能启用生产 Responses leg。
- 模拟用户选择 `D-ARCH=B` 后独立选择 M2：实施者可用受约束 A 形 adapter 渐进迁移，但 adapter 不能形成第二 owner／converter，生产 route 仍受同一组合门约束，并在列明条件满足后退出。
- 模拟用户选择 A 或 C，或尚未选择 B：`D-MIGRATION` 的 M2 推荐不会自动生效，文档要求按所选目标重新制定迁移决策，因此迁移节奏没有反向绑定或偷渡目标 B。
- 模拟用户拒绝任一 current 待决项：不能借此推翻完整 block／Anthropic SSE／首 block 前零 success headers／body，或无 resume contract 时 post-commit partial failure 等 Spec 已决行为。

## 原 major 逐条复核

### 阅读核对-M1：ADR-BRIDGE-02／05 混合已决行为与待决内部结构

**结论：已关闭。**

- `architecture.md:532-567` 已将 `ADR-BRIDGE-02` 与 `ADR-BRIDGE-05` 放入“已决 Spec 输入与历史 ADR 承载记录（非待裁决）”。
- 完整 block、SSE、delayed response start 和无 resume contract 时的 partial failure 均明确写为已决行为或架构承载，不再要求用户投票。
- 原先可能混入的内部选择已正确降为非分叉建议或未来独立 ADR：单个逻辑 block batch 的 sink API 调用粒度属于 B 的可局部调整边界；首版不预留 dedicated continuation port，未来 continuation 必须另行形成 ADR 与 PoC。
- `architecture.md:569-607` 的唯一裁决矩阵与 B 可调整边界共同保证，拒绝 current `D-ARCH` 或 `D-MIGRATION` 不会重开 Spec。

### 阅读核对-M2：待决集合缺迁移节奏，且方案 B 接受范围不可追踪

**结论：已关闭。**

- `architecture.md:569-576` 建立全文唯一裁决矩阵，将目标架构 `D-ARCH` 与迁移节奏 `D-MIGRATION` 分成可独立记录的两项决策，并明确一项的接受不自动接受另一项。
- `architecture.md:578-607` 比较 A／B／C，明确推荐 B，并把 B 的五项不可拆分核心与六类可局部调整边界分开陈述；用户能知道接受 B 的完整范围，也能知道哪些实现细节不需重开 `D-ARCH`。
- `architecture.md:609-640` 直接比较 M1／M2 的风险、兼容代价和退出条件；M2 的 adapter 边界、共同 route 前置门及过渡退出条件均已列明。
- 文档明确规定：没有选择 B 时，M2 推荐不自动生效；选择 M1 或 M2 都不能绕过正式 route 的组合前置门。迁移节奏因此可独立裁决，同时不会改变目标架构或 Spec 行为。

## 事实性发现

未发现 blocker 或 major。

## 主观建议

未提出。本轮范围是对两项既有 major 的关闭复核及新 blocker／major 检查；current 文本已经提供足够且可执行的用户裁决材料。

## 最终结论

两项原 major 均已实质关闭，修订没有引入新的 blocker／major。用户现在可以从 `README.md` 开始完整阅读规定的五份文档，并在完整读完 `architecture.md` 后分别裁决：

1. `D-ARCH`：长期目标选择 A、B 或 C；本文推荐 B，其中五项核心整体构成方案 B。
2. `D-MIGRATION`：在目标 B 下选择 M1 或 M2；本文推荐 M2，但其受 adapter 边界、route 前置门和退出条件共同约束。

本报告只判定 Architecture 已具备裁决条件，不记录或代替用户对这两项决策的接受。
