# `spec.md`／`acceptance.md` 修订候选 r5 复评

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-spec-revision-candidate-r5.md`。本轮只复核 r4 的三条 major；frozen `spec.md` 是矩阵、识别顺序与 malformed 行为的权威。

## 三条处置复核

| r4 发现 | 复评 | 依据 |
|---|---|---|
| M1 detailed first-match 仍把 v2 判 unknown | **生效** | r5 `:121,162-179,206-207` 给出完整六步顺序，把 v2 payload／bare 放在 v1 与 project unknown 之前；`project_malformed_v2` 与跨 block 位置异常分开分类、分开止血，且 acceptance 分别钉住。v2、v1、project unknown、upstream v1、legacy bare、foreign 之间没有 prefix 重叠或 fallback 矛盾。 |
| M2 encrypted-only response matrix 仍强制 v1 | **生效** | r5 `:160` 单独改写 `spec.md:183` 为 v2 payload carrier，并保留空 visible thinking、value-exact opaque、no-loss 与 explicit strip；不再依赖 `:182` 隐含覆盖。 |
| M3 「只有尾部不可检」过强 | **生效** | r5 `:65-72,143,197,209-212` 把能力边界改为 detector 只看 payload carrier，明确尾部损失与 bare-only corruption 两类不可检；bare-only swap 反例进入 acceptance，脚本也只被描述为证伪已列断言，不再承担全称证明。 |

## 新引入的 blocker 与 major

无。

## Verdict

**pass，可以交给用户。** 三条处置全部生效，新 blocker 0、新 major 0。剩余「是否切 producer」「准入等待上界」「是否覆盖 `spec.md:8`」均已明确呈现为用户裁决项，不是本轮技术缺口。
