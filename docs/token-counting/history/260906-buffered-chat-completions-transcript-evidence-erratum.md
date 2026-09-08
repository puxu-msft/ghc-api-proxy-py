---
report_id: buffered-chat-completions-transcript-evidence-erratum
corrects: /home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-buffered-chat-completions-transcript-evidence.md
corrected_report_sha256: 3680fc7a612755274a786a2d992891363d9cde3180e4c300c93dcba267b1782c
status: complete
reviewed_at: 2026-09-06
---

# “buffered chat completions” transcript 取证勘误

## 勘误对象

原报告 §9 第 4 项写道：把 788 个 `reasoning` item 的 `encrypted_content` 替换为空串、同时保留 item、id 与其它结构后，local estimate 应减少 3729865。这个 mutation oracle 错了。3729865 是**删除全部 788 个 reasoning item**时移除的完整 item contribution，不是只清空 ciphertext 时减少的量。

原报告 §5 的分项表把 `reasoning` 的完整 contribution 记为 3729865，算术本身正确；需要收窄的是解释：其中只有 3715681 可由“非空 `encrypted_content` 相对空串控制”归因给 ciphertext，剩余 14184 来自仍被保留的 reasoning item JSON 结构与 estimator 的逐 item 固定开销。原报告结论中“3729865 tokens 来自把 788 个 `reasoning.encrypted_content` item 当普通 JSON 文本编码”也应按这一限定读取，不能把完整 item contribution 全部称为 ciphertext contribution。

## 独立复算

输入仍是原报告的 candidate payload：bytes 8662058、SHA-256 `724decad3e5b3cac64b8439c9aeec2621dc1b0e579fbf0c123494fe5881ed910`。用事故时同一 production `estimate_responses_input()` 与 `tiktoken==0.14.0` 复算得到：

| 控制 | Local estimate | 相对原值 4539201 的减少量 |
|---|---:|---:|
| 原 candidate | 4539201 | 0 |
| 788 个 reasoning item 全保留，仅把各自 `encrypted_content` 设为空串 | 823520 | 3715681 |
| 删除全部 788 个 reasoning item | 809336 | 3729865 |

空 ciphertext 状态下，788 个 reasoning item仍贡献 14184 tokens；其中 empty-item JSON自身编码贡献 11032，estimator的固定 `+4` 贡献 3152，也就是 `788 × 4`。因此 `823520 - 809336 = 14184`，并且 `3729865 - 14184 = 3715681`。

## 正确 mutation oracle

最小单变量 mutation必须是：保持 788 个 reasoning item、id及其它字段不变，只把存在的 `encrypted_content` 设为 `""`。正确预言是：

- mutated local estimate：823520。
- 相对原 candidate 的 decrease：3715681。
- decrease占原 local estimate的 81.857600%。

“删除全部 reasoning item”可以作为第二个、更宽的结构控制；其预言才是 local estimate降至809336、decrease为3729865。它不能冒充 ciphertext-only mutation，因为它同时删除type／id／status等JSON结构和每item固定开销。

## 主结论是否变化

**不变化。** Candidate local estimate 4539201、upstream-reported input 921248、比值4.927230与相对高估392.723%的计算都不受本勘误影响。Local estimator的主要失真仍由 reasoning history主导：完整reasoning item contribution占82.170078%，其中非空ciphertext的可归因边际占81.857600%。本次会话终止并非local count endpoint直接造成、而是922k prompt cap触发后compaction没有产生可读摘要，这一因果分离也不变化。

## 触发与处置

本勘误由coordinator独立复算发现，并由本调查员按同一candidate、同一production estimator重新复现。按要求没有修改源码、transcript、配置、Git状态或原报告；本文件是不覆盖原件的更正记录。

## 交付声明

delivery_complete: true
completed_at: 2026-09-06
corrections_total: 1
main_verdict_changed: false
