# `spec.md`／`acceptance.md` 修订候选 r3 复评

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-spec-revision-candidate-r3.md`。本轮只复核 r2 的 4 条新发现与遗留 r1-B1，并独立重算 carrier vectors、对账 frozen 字段处置矩阵。证据强度：vectors 由未 import `app.*` 的独立 stdlib 计算重新得到，足以冻结；其余结论由 r3 与 frozen spec 逐句对账，足以据此要求修订。

## 五条处置复核

| 待复核项 | 复评 | 依据 |
|---|---|---|
| r2 新 B1：`n` 在块提交时不可知 | **生效** | r3 `:19-48,86-99` 完全删除 `n`，没有用另一字段绕回 whole-response buffering；不完备能力被提升为头号用户裁决，尾部丢失／合并与 bare-marker 边界均明确列出。 |
| r2 新 B2：summary-only 覆盖 bare-marker 裁决 | **生效** | r3 `:95,99,119,126,135` 恢复 v2 bare marker，并明确保持 `spec.md:221,325`、`acceptance.md:141-144` 与独立空 reasoning 裁决不变。 |
| r2 新 M1：rollback 顺序写反 | **生效** | r3 `:137-143` 改为仅回退 producer、永久保留 v2 consumer；无法保留 consumer 的整 build 回滚被准确标成不支持无损回滚的部署限制。 |
| r2 新 M2：异常 `(i,n)` 的 wire 行为未冻结 | **有新问题** | r3 `:101-107` 选择继续源序输出＋conversion fact，行为本身符合 `DEGRADE` 的「可继续但记录损失」语义；然而未同步 frozen 字段处置矩阵，且 bare marker 如何参与 `i` 序列校验未定义，见新 M1、M2。 |
| 遗留 r1-B1：acceptance vectors 未生效 | **生效** | 我用独立 Python stdlib 按字段顺序 `tag,encrypted_content,i`、`ensure_ascii=False`、紧凑 JSON 与 unpadded base64url 重算；四条 payload signature 与 r3 `:115-118` 逐字节一致，decode→encode canonical check 四条均为 true，`:119` bare marker 也准确。 |

## 新引入的 blocker 与 major

### M1 — `DEGRADE` 语义选得对，但 frozen 矩阵没有相应落点

- `spec.md:141` 明定只有矩阵显式列为 `DEGRADE` 的项目才可 permissive 继续；当前 request 矩阵 `:161-164` 只有项目 v1 normal／bare／malformed，response 矩阵 `:182` 仍要求 v1 producer。
- 合法 v2 carrier 的跨 block `i` 异常既不是单 payload malformed，也不命中现有任何 `DEGRADE` 行；r3 `:121-126` 的「必须一并修订」清单却没有这些矩阵行。
- 补入「v2 normal＝TRANSFORM」「v2 位置异常＝DEGRADE，源序输出＋fact」并把 response producer 行改为 v2；否则正文允许继续、矩阵却禁止该 permissive 行为。

### M2 — bare marker 是否占据 `i` 序列位置未定义，会产生 false positive 或与能力表冲突

- r3 `:97` 把 `i` 定义为所有 reasoning items 中的 ordinal，但 `:95,99` 的 summary-only item 是无 `i` 的 bare marker。
- 对合法序列 `[payload i=0, bare, payload i=2]`，若只检查恢复出的 `i` 列表就会把 `[0,2]` 误报为空洞；若按所有 block 的源序位置校验则合法通过，而且丢掉中间 bare 后 `i=2` 会暴露错位，与 `:38`「丢 summary-only 不能发现」的全称表述冲突。
- 冻结一种算法并加 normal／drop vectors；可准确写成只有 trailing bare loss 必然不可检，而不能既让 bare 占 ordinal 又从验证序列中无定义地消失。

## Verdict

**needs-fix。** 五条处置中 4 条生效，1 条有新问题；新 blocker 0、新 major 2。四条 payload vector bytes 已独立确认正确，`DEGRADE` 归属本身也合乎现有语义；修齐矩阵与 bare-marker 序列算法后即可再判是否交给用户。
