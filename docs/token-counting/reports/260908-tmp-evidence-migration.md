# Token-counting tmp 历史证据迁移

**日期**：2026-09-08。**依据**：`dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md` 的逐份 final disposition。**范围**：仅将本表 9 份顶层 `tmp/` 原件移入 `token-counting/history/`，并新增该 history 的索引；没有删除、改写或升级任一原件的事实、版本范围、`in-review` 元数据、已推翻假设或历史性质。

## 移动清单与 SHA-256 对账

| 原位置 | canonical 位置 | SHA-256 | 分组 / 保留边界 |
|---|---|---|---|
| `../tmp/260824-autocompact-window-is-one-million.md` | `../history/260824-autocompact-window-is-one-million.md` | `3bc276b7e9e605cd5fd8fa48539c29f484ef99dbcc7122ab316818627392b503` | auto-compact 证据链；保留 Claude Code 2.1.241、1M window 和 967k threshold 的环境限定。 |
| `../tmp/260824-cc-autocompact-same-version-divergence.md` | `../history/260824-cc-autocompact-same-version-divergence.md` | `097639673ab916186b6321e08f6721dbf0145a2717e5fb92591ff515b25a06d1` | auto-compact 证据链；保留同版本环境/模型名/熔断分歧及其 2.1.241 代码锚。 |
| `../tmp/260824-cc-autocompact-trigger-forensics.md` | `../history/260824-cc-autocompact-trigger-forensics.md` | `510dc74471d5073e3338e90a6a5a36472ee92846b100ca611b68b35e85964af8` | auto-compact 证据链；保留静态版本对照、判定路径和已纠正的 `Vyl` 入口假设。 |
| `../tmp/260824-why-autocompact-did-not-fire.md` | `../history/260824-why-autocompact-did-not-fire.md` | `eb20dcabf3bb5e24dc4ebe3e3fd4d8006cca454b94ab307751409418ebb43bde` | auto-compact 证据链；保留顶部更正、被推翻的版本/环境主线及其仅适用于无该 env 的历史边界。 |
| `../tmp/260824-count-tokens-heterogeneous-review-gpt.md` | `../history/260824-count-tokens-heterogeneous-review-gpt.md` | `4f6bfd4470bbc09946b43a3115cd82e9fdb9af975f94ad2e2277aa0a39869262` | count endpoint 独立评审；保留 Claude Code 2.1.241 的兼容性限定。 |
| `../tmp/260824-count-tokens-prior-art-survey.md` | `../history/260824-count-tokens-prior-art-survey.md` | `b135f622396ae24d4925f0201e7ec7463c58bacc56a1b73bdc3e93382d8c3911` | count endpoint 的 prior-art 清点；保留固定基线与时点性质。 |
| `../tmp/260906-buffered-chat-local-tokenizer-analysis-review.md` | `../history/260906-buffered-chat-local-tokenizer-analysis-review.md` | `fb00de13d18ed439f0b1d7105d29da9f8b94feca3a34afd5443f4d1253d5a4e0` | local-tokenizer R1/R2/R3 评审链；保留 `in-review` 元数据和 R1 的 two-minor verdict。 |
| `../tmp/260906-buffered-chat-local-tokenizer-analysis-review-r2.md` | `../history/260906-buffered-chat-local-tokenizer-analysis-review-r2.md` | `2d68643cbd428f9f16d5418a6ca61439de9e2a21eb71768dc641402b41a92f06` | 同一评审链；保留 `in-review` 元数据及 LT-09 residual minor。 |
| `../tmp/260906-buffered-chat-local-tokenizer-analysis-review-r3.md` | `../history/260906-buffered-chat-local-tokenizer-analysis-review-r3.md` | `6f53dbdf7708adcaa5a79872bf58579757cfb7581de388903f1ff798ae1a4032` | 同一评审链；保留 `in-review` 元数据和其仅覆盖 LT-09 closure 的 narrow scope。 |

## 原子分组

- **Auto-compact 组（4）**：`trigger-forensics` 与 `why-autocompact` 保存初始判据和被收窄的旧主线；`same-version-divergence` 与 `window-is-one-million` 保存对该主线的环境/阈值修正。四份必须共址阅读，不能取其中一份替代其余三份。
- **Local-tokenizer review 组（R1/R2/R3，3）**：三轮限定评审依次记录 finding、残余和 closure，且都保留 `in-review` 这一原始时点元数据。它们与已在本 history 的 analysis、transcript evidence、erratum 和 code audit 共同组成完整证据链。

## 验证要求

迁移完成后应确认：9 个原 source 均不存在；9 个 destination 均存在且 SHA-256 与本表相同；两组组员完整共址；`history/README.md` 能导航至全部原件。本批 ledger 未列 current/living inbound link，故本次没有改写 parent README、Spec、status 或其他主题路径。
