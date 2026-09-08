# 顶层 `tmp/` upstream 证据归档

- 日期：2026-09-08
- 依据：`.dev/docs/dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md`
- 范围：ledger 判为 `upstream/retry-and-continuation/history/` canonical history 的精确 12 份原件，以及唯一承重 basename 引用的原子改写

## 精确动作与 canonical 位置

下表每项都从顶层 `tmp/` **移动**到同名的本主题 `history/` 路径；不是复制或删除。原件内容未改写，SHA-256 是移动前后逐项核对的值。

| 文件 | canonical 位置 | SHA-256 |
|---|---|---|
| `260821-probe-history-error-frames.md` | [`../history/260821-probe-history-error-frames.md`](../history/260821-probe-history-error-frames.md) | `6331e98693bd2f719170daa5140a00dd5fb861f4a572773b61ecbaec1006f752` |
| `260821-review-g1-candidate.md` | [`../history/260821-review-g1-candidate.md`](../history/260821-review-g1-candidate.md) | `3c90af81fe20b8f9c64c7fe1bc4c7abda06252f614d18ab3df610a66f0c9f9cf` |
| `260821-truncated-anthropic-stream-diagnosis.md` | [`../history/260821-truncated-anthropic-stream-diagnosis.md`](../history/260821-truncated-anthropic-stream-diagnosis.md) | `e58fbf1a32b23d2ec32076de442d2cc48e14f3bdf2025f19bddee08fdc4c84a4` |
| `260822-p2-complete-fix-handover.md` | [`../history/260822-p2-complete-fix-handover.md`](../history/260822-p2-complete-fix-handover.md) | `e4a7e54008a5a4be185b40b485deaad2fc8bd3a31974c8e4ba148fa234dad5df` |
| `260822-pyright-errors-in-stream-cap-slice.md` | [`../history/260822-pyright-errors-in-stream-cap-slice.md`](../history/260822-pyright-errors-in-stream-cap-slice.md) | `24c7fe67d19d4137412fca40ee4137d16c53f99d3d95192c6d8b528f3742f8f1` |
| `260822-review-complete-fix-gpt.md` | [`../history/260822-review-complete-fix-gpt.md`](../history/260822-review-complete-fix-gpt.md) | `fb17455e9cff1670de65efd553e185440132761dca0415ed1975c50b851d7653` |
| `260822-review-complete-fix-opus.md` | [`../history/260822-review-complete-fix-opus.md`](../history/260822-review-complete-fix-opus.md) | `a8a10c0ab010fbf39871c2ddb5cbfea65d5ed8a2f9913e56488749eecf133aab` |
| `260822-review-streamreset-diagnosis-gpt.md` | [`../history/260822-review-streamreset-diagnosis-gpt.md`](../history/260822-review-streamreset-diagnosis-gpt.md) | `4f508d46372b0077a38b26699ad3568d5e87635389ff3ba86f67f956cd08ab9a` |
| `260822-review-streamreset-diagnosis-opus.md` | [`../history/260822-review-streamreset-diagnosis-opus.md`](../history/260822-review-streamreset-diagnosis-opus.md) | `29f1e4eea43fe7b031dd5064d8dba8ec8dc758e84eaa6e10ebeb9c47d093ae64` |
| `260824-cc-stop-reason-incomplete.md` | [`../history/260824-cc-stop-reason-incomplete.md`](../history/260824-cc-stop-reason-incomplete.md) | `e70d2395e13325336bc137696b3c7136ee666afb8c8c847ee41ba0764b55a970` |
| `260827-fix-silent-drop.md` | [`../history/260827-fix-silent-drop.md`](../history/260827-fix-silent-drop.md) | `d8628655d9b53db8db35b65a056eb8a1b00b7d896406736848bdd3f49ab6ec81` |
| `260908-review-upstream-failure-backoff.md` | [`../history/260908-review-upstream-failure-backoff.md`](../history/260908-review-upstream-failure-backoff.md) | `a55fecf143a5eb1155011ab8e30a0cf935050d76a75c00cc9390b87bf11943b3` |

`history/README.md` 已为所有十二份补充来源、承接内容与时点边界。特别是 backoff review 的原件完整保留其 `_failures` overflow blocker、并发 `_next_allowed` major、delivery replay 固定 base 边界、修复／测试处置，以及 `.dev/human-controlled-docs-candidates/260908-upstream-retry-backoff.md` 尚待用户追认的 provenance；它们没有被本次归档改写成 current behavior 或已采纳 Spec。

## Living basename 引用

ledger 识别的唯一承重 basename consumer 是 `deferred.md` §11：原文错误指向不存在的 `reports/260822-review-complete-fix-opus.md`。该引用已在同一变更改为 [`history/260822-review-complete-fix-opus.md`](../history/260822-review-complete-fix-opus.md) 的 canonical relative link；其“deadline/terminal 次序及受控变异”的证据含义不变。

## 验证

1. 对 12 个精确源路径逐项确认 source absent，并确认同名 canonical destination present。
2. 对 12 个 destination 的 SHA-256 与移动前采样逐项对账，12/12 一致。
3. 解析 `deferred.md` 的新 canonical link，目标存在；复扫确认错误的 `reports/260822-review-complete-fix-opus.md` target 不再出现。
4. 本报告写入后复跑 `git -C .dev diff --check -- docs/upstream/retry-and-continuation`，通过；报告中的 13 个 canonical history link 亦全部解析到存在文件。

## 未做事项

- 未改动或移动任何未在授权清单中的 `tmp/` 文件。
- 未改写移动原件内部的历史路径；它们是 point-in-time evidence，不是本轮要求修复的 living links。
- 未修改源码、配置、人写 Spec、其他主题或 `.dev/docs/history/`。
- 未执行删除、git add、commit 或 push。
