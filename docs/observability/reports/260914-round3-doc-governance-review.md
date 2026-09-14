# 第三轮最终治理复审

## 评审范围

本轮只复审：

- `.dev/README.md` 与 `docs/dotdev-repository-repair/README.md` 对目标结构、当前 re-root/worktree 状态和唯一 current owner 的区分；
- `raw-capture/spec.md` ACTIVE v25、`raw-capture/review-disposition.md`、其 `reports/` 原件与 `deferred.md` 的逐报告/逐 finding 处置；
- `observability`、`history`、`raw-capture`、`replay` 四主题入口及其 current links。

代码事实若需使用，只以 clean committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a`（短 SHA `30384269`）为准；不读取共享主树 working-copy 作为代码证据。不扩大到其他主题、实现或部署面。

## 总体 verdict

**needs-fix**

## blocker 数

0

## Major findings

### DOC-GOV-R3-01 — raw-capture adversarial report 的 major finding 未被 current disposition 逐 finding 收敛

- **finding_id:** `DOC-GOV-R3-01`
- **severity:** major
- **primary_location:** `.dev/docs/raw-capture/review-disposition.md:8-20`
- **related_locations:** `.dev/docs/raw-capture/reports/raw-capture-review-2026-09-09-adversarial-verifier.md:120-157`；`.dev/docs/raw-capture/deferred.md:11-17`
- **涉及清单:** C3、C5

**证据**

`raw-capture/review-disposition.md` 已经逐项列出了 implementation-audit 的 A1-01 至 A1-05、final re-review 的 RC-FINAL-01 至 04，以及 merged-state review 的 M-1/M-2/S-1；但对 adversarial verifier 只写成 `AC-08/09/27 deviations`，并附带 `AC-28 remains unverified`。

该报告实际的 finding 是：

- `F-01`（**major**），覆盖 AC-08、AC-09、**AC-23**；
- `F-02`（minor），覆盖 AC-23；
- `F-03`（minor），覆盖 AC-27；
- AC-28、AC-29 均明确为未验证。

因此当前 disposition 没有给 `F-01` 一个唯一的 `closed / accepted-deferred / rejected / superseded` 处置，也没有说明它是否与 implementation-audit 的 A1-01 重复、由 A1-01 代替，或独立接受延期；`F-02` 和 AC-29 也没有对应条目。`deferred.md#D-3` 虽复述了 AC-08/09/27 的主题，但不能替代报告 finding ID 的处置映射。

**影响**

该报告仍保留 `needs-fix` 与一条 major。接手者既可以把 F-01 当作未决 current gate，也可以凭 D-3 的概括把它当作已接受延期；两种结论都无法从 current disposition 复现。报告生命周期因此仍不可执行，且会丢失同一 finding 在多份报告之间的去重/继承关系。

**闭合要求**

在 current disposition 中为 adversarial verifier 至少补齐 `F-01`、`F-02`、`F-03`、AC-28、AC-29 的明确处置，并在 F-01 与 A1-01 的情况下写清 `duplicate/superseded` 关系、current owner、适用 v25 Spec 锚和替代证据。完成后，`reports/` 中每份报告及其每个 blocker/major/minor 或 unverified 条目都必须能沿一条唯一路径得到 current 结论。

## Minor / 牛角尖

### DOC-GOV-R3-M01 — raw-capture disposition 的版本指针仍写 v24

`raw-capture/review-disposition.md:4` 已写明当前 Spec 为 ACTIVE v25，但第 6 行仍说当前状态由 “v24 Spec” 导航。`spec.md` 顶部与 `deferred.md` 已统一为 v25，故 authority 没有丢失；这是 current pointer 的 minor 漂移，不另升 major。

## 结论矩阵

| 检查面 | 结论 | 依据 |
|---|---|---|
| 目标结构 / 当前 re-root 状态 | **通过** | `.dev/README.md:5,7-20` 明确把目标根树与“当前 re-root/worktree 尚未闭合”分开；repair README:3,23-29,48 给出同一 current owner 与剩余顺序。 |
| raw-capture v25 Spec / disposition | **不通过** | v25 header、deferred anchors 和大部分报告映射已到位，但 `DOC-GOV-R3-01` 仍遗漏 adversarial verifier 的 F-01/F-02/F-03/AC-29 逐项处置。 |
| 四主题入口 | **通过** | root inventory 中 `history`、`observability`、`raw-capture`、`replay` 各出现一次；observability group README 提供四主题唯一导航表；各主题 README 的 Spec/status/deferred 链路均可继续解析。 |
| current links | **通过** | 对 21 份 scoped current Markdown 检查 157 个本地链接，missing=0；四主题 README、Spec、status、deferred 均存在，未发现 competing current target。 |

## 搜索面与验证

- 只读取 `.dev/README.md`、`dotdev-repository-repair/README.md`、四主题入口/status、raw-capture v25 `spec.md`/`deferred.md`/`review-disposition.md`，以及 raw-capture `reports/` 的报告头、finding 与 verdict；未扩大到其他主题。
- raw-capture 报告核对覆盖 implementation-audit A1-01..05、final re-review RC-FINAL-01..04、merged-state M-1/M-2/S-1、adversarial verifier F-01..F-03/AC-28/AC-29、coordinator checklist。
- 代码未参与本轮 finding 判定；若需代码事实，基准明确为 clean HEAD `30384269`，未读取共享 working-copy 作为代码证据。
- 已执行只读入口/link probe：四个 root inventory 行各一次；21 个 current scoped 文件、157 个本地链接、missing=0。未运行测试；除本报告外未创建、修改或删除文件；未执行 `git add` 或 `git commit`。
