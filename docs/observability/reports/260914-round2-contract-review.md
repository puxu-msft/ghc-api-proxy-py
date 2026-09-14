# Observability / History / Raw Capture / Replay 第二轮对抗性契约复审

## 评审范围与证据边界

本轮只复核当前 `.dev/docs` 中 raw capture、History、Replay、Observability/Journal 的：

- `spec.md`
- `status.md`
- `deferred.md`
- `review-disposition.md`
- `implementation-ledger.md` 与各 topic README 的 authority/navigation boundary

代码事实按 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 核对；不使用共享主树 status、stale working copy 或物理文件缺失作为证据。本轮不扩展扫描到无关 topic，也不重复报告已被 status/deferred/disposition 明确接受的实现限制。

## 总体结论

**VERDICT: pass**

**blocker 数：0。major 数：0。**

**可以进入下一轮。**

本轮确认：上一轮识别的限制已被正确分流为 current status/deferred/disposition，而不是继续在 ledger 中伪装成 `done`：

- `OBS-D-01/02/03`：Journal taxonomy、JSONL owner、per-attempt capability 明确 deferred；
- `HIS-D-01/02`：History restart recovery、per-attempt capability 明确 deferred；
- `RPL-D-01/02/03/04`：Replay CLI/result boundary、History provenance、per-attempt gate 明确 deferred；
- History identity projection 已在 History v2 与 raw-capture v25 中明确区分 History-owned metadata 与 raw transport fields。

这些限制仍然存在于 committed HEAD，但当前文档没有把它们写成已完成能力，因此不构成新的 major。

## 复核结果

### Observability / RequestJournal

`observability/spec.md` v2 保持 normative contract，同时在 §6 明确 bounded Journal 只是实现子集；`status.md`、`deferred.md` 和 ledger #5 使用 `partial-accepted`/deferred 记录当前状态。JSONL owner 与完整 taxonomy 没有被 ledger 重新宣称为完成。无 major。

### History

History Spec v2 仍定义目标行为；`history/status.md` 明确 segment restart recovery 未达完整 durable contract，`history/deferred.md` 以 HIS-D-01/HIS-D-02 承接，ledger #2–#4 使用 `done-with-deferred-hardening`。`review-disposition.md` 也把 History restart recovery 标为 accepted/deferred。无 major。

History-owned session/agent metadata 已从 raw transport headers/credentials 中分离；raw-capture Spec v25 的修订记录、History Spec v2 和 History status 使用同一边界。无 major。

### Raw capture

Raw capture v24 的 full-header、credential-sensitive evidence、History attachment 与 aggregate capability 已由 status/disposition 标为已落地；per-attempt durable matrix 在 status/deferred/disposition 中一致地标为 deferred。无 major。

### Replay

Replay Spec v3 不再把完整 result boundary 或 CLI mode exposure 写成当前已完成能力，而是链接 `replay/status.md`；status、deferred、ledger #6 同步说明 CLI 以 wire diagnostic 为主，semantic/live 依赖注入 executor，delivery/cancel/History reference 仍 deferred。无 major。

## Minor / nit

### DOC-GOV-R2-01 — Raw-capture disposition 的版本指针落后一个修订

- **severity:** minor
- **location:** `.dev/docs/raw-capture/review-disposition.md:3`
- **evidence:** 该页仍写“当前状态由 v24 Spec、`status.md` 和本表共同导航”，而当前行为权威已是 `.dev/docs/raw-capture/spec.md` ACTIVE v25；v25 新增了 History-owned identity metadata 与 raw transport identity 的边界澄清。
- **影响:** 复审者若只沿 disposition 的版本文字回看，可能漏读 v25 的安全边界修订；topic README/status 的直接链接仍能把读者带到当前 Spec，因此不升级为 major。

## C1–C5 覆盖

| 清单 | 结论 |
|---|---|
| C1 | full-header、History-owned metadata、transport export、Replay current-auth boundary 已有一致的 current contract；aggregate/per-attempt 限制已 deferred |
| C2 | semantic/transport/full export、capture_ref、archive/pin/retention 合同与当前状态/ deferred 分层一致；restart hardening 已明确 deferred |
| C3 | Replay capture-required、selector、mode、target、deadline/cancel、client-action、provenance 的未完成部分均已在 status/deferred 公开，不再被写成 done |
| C4 | RequestJournal 与 History 不持久化完整 journal 的边界清楚；taxonomy/JSONL owner 的实现限制已 deferred |
| C5 | 未发现仍会让合理读者得出互斥产品行为的 major 文档读法 |

## 搜索面与验证

- 已读取四个 topic 的当前 README、Spec、status/deferred，以及可用的 review disposition、Observability implementation ledger。
- 已按需对照 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 中 Replay、RequestJournal、History archive/writer、History routes、raw capture capability 的既有证据。
- 未读取无关 topic，未操作 4141，未执行 `git add` 或 `git commit`。
