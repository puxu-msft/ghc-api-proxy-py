# tmp history migration — `project-review-principles` skill

- **执行日期**：2026-09-08
- **性质**：归档迁移验证记录；不是 current plan、current rule 或模型实际加载的 skill 指令。
- **范围**：只迁移下表六份指定 `.dev/docs/tmp/` 历史原件至 `history/`；原件内容未改写。

## 验证结果

迁移前逐一计算 source SHA-256；迁移后逐一计算 destination SHA-256。每一对完全一致，且迁移后全部 source 路径不存在。

| Source（迁移前） | Destination（迁移后） | SHA-256 | Source 已不存在 |
| --- | --- | --- | --- |
| `.dev/docs/tmp/260822-review-gate2-ownership.md` | `.dev/docs/project-review-principles-skill/history/260822-review-gate2-ownership.md` | `99ac83e794439571cfe9f0c4a2ef198fa740ad298be39d46f7f7e28689a1da22` | 是 |
| `.dev/docs/tmp/260822-review-skill-carrier-tradeoff.md` | `.dev/docs/project-review-principles-skill/history/260822-review-skill-carrier-tradeoff.md` | `2c21b685972423fb22d6dff3fd23739d1f0eea8f41cdd3412fd06fe0e8b3b437` | 是 |
| `.dev/docs/tmp/260823-nonfile-candidates-review-A.md` | `.dev/docs/project-review-principles-skill/history/260823-nonfile-candidates-review-A.md` | `de787f031b05cd38021583b49c23e1259bc9a574e9dc5515cccfbb0848f8eea3` | 是 |
| `.dev/docs/tmp/260823-nonfile-candidates-review-B.md` | `.dev/docs/project-review-principles-skill/history/260823-nonfile-candidates-review-B.md` | `a4dd9e08905f9e5f1c8a1cad7d07778628d72863cafcfdfb4263c09cdcda2d95` | 是 |
| `.dev/docs/tmp/260823-nonfile-candidates-review-C-subagents.md` | `.dev/docs/project-review-principles-skill/history/260823-nonfile-candidates-review-C-subagents.md` | `599b23bb49738e00614595b53800a95888753d08a914503b8b8936e650bc5975` | 是 |
| `.dev/docs/tmp/260823-session-closeout-nonfile-candidates.md` | `.dev/docs/project-review-principles-skill/history/260823-session-closeout-nonfile-candidates.md` | `5948ed162248154538e5d3ee3b382c2d7230141908b765c1ee5267cd4e5854a9` | 是 |

`history/README.md` 已明确这些是点时 checkpoint／评审／skill 演化证据，绝不能成为 current plan 或 rule；并将 A、B、C 与 closeout 列为一个必须成组阅读的索引。

## 可复现检查

在仓库根目录执行：

```bash
sha256sum .dev/docs/project-review-principles-skill/history/*.md
for f in \
  260822-review-gate2-ownership.md \
  260822-review-skill-carrier-tradeoff.md \
  260823-nonfile-candidates-review-A.md \
  260823-nonfile-candidates-review-B.md \
  260823-nonfile-candidates-review-C-subagents.md \
  260823-session-closeout-nonfile-candidates.md
do
  test ! -e ".dev/docs/tmp/$f"
done
```
