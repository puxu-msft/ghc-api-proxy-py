# R-20/R-21 与顶层 `tmp/` 原件迁入报告

- 日期：2026-09-08
- 执行清单：`.dev/docs/dotdev-repository-repair/subtopics/260908-retirement-reference-map.md` 的 R-20、R-21 与第 4 节所列本主题 5 项
- 修改范围：`upstream/retry-and-continuation/`、`upstream/h2-goaway/` 与清单明确授权的 5 份顶层 `tmp/` 原件

## 精确动作与 canonical 位置

以下原件以移动（非复制、非删除）从顶层 `tmp/` 进入本主题的 [`../history/README.md`](../history/README.md) 索引；索引同时声明它们是点时材料，当前状态和未闭合项仍分别以 `status.md`、`deferred.md` 为准。

| 原件文件名 | 原 canonical 位置 | 新 canonical 位置 | SHA-256（移动前后相同） |
|---|---|---|---|
| `260822-deferred-md-inventory.md` | 顶层 `tmp/` | [`../history/260822-deferred-md-inventory.md`](../history/260822-deferred-md-inventory.md) | `00a15be4c9ef3c65e41e6d3497ed48fa73f2f421848cbf0078c663146c5e3d24` |
| `260822-review-session-closeout.md` | 顶层 `tmp/` | [`../history/260822-review-session-closeout.md`](../history/260822-review-session-closeout.md) | `9365da15060f863c7662c5c4dd9001d1feb8436d6e6e0a6c359ff90e510d74e2` |
| `260822-review-never-silent-failure-events.md` | 顶层 `tmp/` | [`../history/260822-review-never-silent-failure-events.md`](../history/260822-review-never-silent-failure-events.md) | `a4d5596245b471687545dee72885fc1f21f0554a364912d27fa3a34e0e996f52` |
| `260822-h2-streamreset-cancel-diagnosis.md` | 顶层 `tmp/` | [`../history/260822-h2-streamreset-cancel-diagnosis.md`](../history/260822-h2-streamreset-cancel-diagnosis.md) | `1c145e566395e2e7e1b940646d445c554ca25159f1ab87789cb1fb20ebafdfad` |
| `260821-plan-g1-upstream-error-events.md` | 顶层 `tmp/` | [`../history/260821-plan-g1-upstream-error-events.md`](../history/260821-plan-g1-upstream-error-events.md) | `d6dc7465704ac5d36d5c6ce78b51fba3de39775c83406a6466ff53facff5096a` |

同时原子改写所有清单列出的 living consumer：

1. `retry-and-continuation/deferred.md` 的两处清点引用、§20 的 closeout review 引用、§21 的 never-silent review 引用均改为本主题 `history/` Markdown links。
2. `retry-and-continuation/status.md` 的 RST_STREAM(CANCEL) 诊断和 G1 G4 引用均改为本主题 `history/` Markdown links。
3. R-20：`h2-goaway/deferred.md` 不再把新的取证能力归属给已计划退役的 docs history 主题，改为同主题 `findings.md` 已说明的 current structured request log／JSONL implementation。
4. R-21：`h2-goaway/findings.md` 直接写明 current owner 是 `src/app/observability/request_log_file.py` 的 structured request log／JSONL implementation，并链接 `../retry-and-continuation/status.md` 的实现状态。
5. `retry-and-continuation/deferred.md` §24／§25 的迁入前来源保留为文字 provenance（“已计划退役的 history 主题之 `decisions.md` §6.1／§6.2”），不再留下可解析的 `.dev/docs/history/decisions.md` 死路径。

## 扫描与验证结果

1. 已在操作前读取 reference map 的 R-20、R-21 与第 4 节相应五行，并重新扫描四份 living consumer 的精确文件名和旧 history path。
2. 移动后，5 个旧顶层 `tmp/` 源路径均不存在；5 个新 `history/` 路径均存在。
3. 移动前后的 SHA-256 如上表逐项一致，确认原件内容未改写。
4. 对 `retry-and-continuation/deferred.md` 与 `status.md` 的五个旧 `../../tmp/...` target 复扫为零；相应 6 个 living 引用均为 `history/` 相对 Markdown links，且目标文件存在。
5. 对 `retry-and-continuation/deferred.md`、`h2-goaway/deferred.md`、`h2-goaway/findings.md` 的 `.dev/docs/history/` 与 `history/decisions.md` 复扫为零；R-20/R-21 的新 owner 叙述已落在 current structured request log／JSONL implementation。
6. 本报告写入后复跑 `git -C .dev diff --check -- docs/upstream/retry-and-continuation docs/upstream/h2-goaway`，通过；同时逐行检查本轮写入和五份移动原件，trailing whitespace 为零。
7. 对 10 对 moved-report `(origin, target)` Markdown link 逐一解析相对 target，全部存在；其中 living consumer 有 6 个实际 link occurrence（`deferred.md` 对清点报告有两处相同 target），history 索引另有 5 处，合计 11 个 occurrence。

## 未做事项

- 未修改任何不在授权范围内的 `tmp/` 文件或其他主题。
- 未删除任何文件；五份授权原件只做 canonical move。
- 未修改已迁入历史原件的内部历史链接；reference map 已明确 archive/history 的自包含化不属于本轮 living dependency 迁移。
- 未修改源码、测试、配置或人写 Spec；未执行 git add、commit、push。
- 未处理 reference map 中其余 R-01～R-19 或其余顶层 `tmp/` 条目。
