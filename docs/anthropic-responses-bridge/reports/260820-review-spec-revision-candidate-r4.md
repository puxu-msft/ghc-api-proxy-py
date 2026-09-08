# `spec.md`／`acceptance.md` 修订候选 r4 复评

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-spec-revision-candidate-r4.md`。本轮只复核 r3 的两条 major，并对照 frozen matrix、详细识别顺序与独立反例检查能力表。结论强度：`[p0,bare,p2]` 算法已由代码与人工推导双重确认不误报；但 r4 的十行脚本没有覆盖 bare-only corruption，新增反例足以推翻「只有尾部不可检」的全称结论。

## 两条处置复核

| r3 发现 | 复评 | 依据 |
|---|---|---|
| M1 `DEGRADE` 未落进 frozen matrix | **有新问题** | r4 `:127-140` 新增 v2 normal 与位置异常两行，`TRANSFORM`＋`DEGRADE` 标签及继续源序输出均符合 `spec.md:142`；但 detailed first-match 顺序仍会先把 v2 判 unknown，且 response matrix 漏改 encrypted-only 行，见新 M1、M2。 |
| M2 bare marker 是否占 `i` 序位未定义 | **有新问题** | r4 `:38-53,169-172` 已冻结「bare 占 ordinal、只比 payload `i`」并消除 `[p0,bare,p2]` false positive；十个已列样本与算法一致，但未覆盖只交换／替换 bare blocks 的 corruption，故「只有尾部不可检」仍过强，见新 M3。 |

## 新引入的 blocker 与 major

### M1 — detailed first-match 顺序仍会把 v2 判成 unknown

- frozen `spec.md:238-242` 先识别 v1，随后把项目 namespace 下所有其他 version 归为 `project_unknown_version`；r4 只在矩阵和摘要写「v2 → v1 → upstream」，未给该详细算法的替换文本。
- `spec.md:246` 也只定义 `project_malformed_v1`，没有 v2 strict key／`i` 类型失败的稳定分类；矩阵新增 v2 行不能自动改写这两个规范段落。
- 明确冻结顺序为 v2 payload／bare → v1 payload／bare → project unknown → upstream v1 → foreign，并补 `project_malformed_v2` 的止血行为与 acceptance case。

### M2 — response matrix 的 encrypted-only 行仍强制 v1 producer

- r4 `:140` 只把 `spec.md:182` 的「summary＋非空 encrypted_content」改成 v2；紧邻的 frozen `spec.md:183` 仍要求 non-empty encrypted-only reasoning 使用本项目主 v1 carrier。
- encrypted-only 是独立冻结的 no-loss 合法形态，不能由 `:182` 的改写隐含覆盖；按 r4 producer 发 v2 会直接违反未改的 `:183`。
- 同步把 `:183` 改为 v2 payload carrier，并保留空 visible thinking、value-exact opaque 与 explicit strip 语义。

### M3 — 「只有尾部不可检」忽略了 bare-only reorder／substitution

- detector 只比较 payload carrier；两个 summary-only blocks 都是 bare 时，交换它们不会改变任何可比 `i`。例如合法 `[bareA,bareB,p2]` 与交换后的 `[bareB,bareA,p2]` 对算法都投影成 `[None,None,2]`，均不触发 fact，虽然 corruption 不在尾部。
- 同理，用一个 bare 重复替换另一个而保持 block 数不变也不可检；我用同一 `detects` 谓词独立运行这两例，结果均为 `detected=False`。r4 脚本十行全绿只证明已枚举的十行，不支撑全称能力边界。
- 能力表应收窄为「payload 的 ordinal mismatch 可检」；明确 bare-only 重排／等长替换及尾部损失不可检，并把至少一个 bare-only 反例加入 acceptance。

## Verdict

**needs-fix。** 两条处置均修正了原缺陷，但各有新问题；新 blocker 0、新 major 3。矩阵标签本身正确，`[p0,bare,p2]` 算法也正确；补齐 detailed classifier、encrypted-only producer 行并收窄 bare-only 能力承诺后，才可交给用户。
