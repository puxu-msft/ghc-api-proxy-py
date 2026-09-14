# Observability / History / Raw Capture / Replay 第三轮最终对抗性契约复审

## 评审范围与证据边界

本轮只复核当前 `.dev/docs` 中 raw capture、History、Replay、Observability/Journal 的 `spec.md`、`status.md`、`deferred.md`、`review-disposition.md`、`implementation-ledger.md` 与 topic README authority/navigation boundary。

代码事实按 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 核对；不使用共享主树 status、stale working copy 或物理文件缺失作为证据。不扩展扫描无关 topic，也不重复报告已明确 accepted/deferred 的实现限制。

## 总体结论

**VERDICT: pass**

**blocker 数：0。major 数：0。**

**可以进入下一轮。**

当前文档已把 committed HEAD 的已落地能力、实现子集和 deferred hardening 分开表达。上一轮识别的限制均有对应 owner：

- RequestJournal taxonomy、History receipt event、JSONL owner：`OBS-D-01/02`；
- per-attempt capability：`OBS-D-03`、`HIS-D-02`、`RPL-D-04`；
- History restart recovery：`HIS-D-01`；
- Replay CLI/result/History provenance：`RPL-D-01/02/03`；
- History identity 与 raw transport fields：History v2 / raw-capture v25 已明确区分。

这些限制仍存在于 committed HEAD，但当前 `status.md`、`deferred.md`、`review-disposition.md` 和 ledger 没有把它们写成已完成能力，因此不构成 major。

## 复核结果

### Observability / Journal

`observability/spec.md` v2 保持 normative contract，并在实现边界节明确 bounded Journal 是子集；`status.md`、`deferred.md`、ledger #5 和 shared disposition 都使用 `partial-accepted`/deferred 表达 taxonomy、handoff receipt 与 JSONL owner 的当前限制。未发现仍会让调用方误以为完整 Journal 已接线的合同冲突。

### History

History Spec v2 仍定义跨重启、archive、query/export、pin/retention 和 capability 的目标合同；`history/status.md`、`history/deferred.md`、shared disposition 与 ledger #2–#4 明确标出 restart/tail hardening 和 per-attempt capability 尚未完成。History-owned identity metadata 与 raw transport headers/credentials 的边界已在 Spec 修订记录中对齐。未发现 major。

### Raw capture

Raw-capture v25 的 full-header、credential-sensitive transport、History-owned normalized metadata、aggregate capability 和 explicit evidence projection 与 `status.md`/`deferred.md`/review disposition 一致。D-3/D-4 的失败 attempt、cleanup boundary 和 warning hardening 被标为 accepted-deferred，没有被 ledger 写成 v25 全部闭合。未发现 major。

### Replay

Replay Spec v3 明确把 source gate、wire diagnostic、注入式 executor、target/deadline skeleton 与当前 result boundary 分层；`replay/status.md`、`deferred.md` 和 ledger #6 同步说明 CLI 以 wire diagnostic 为主，semantic/live、delivery/cancel facts、History reference 仍 deferred。未发现 major。

## Minor / nit

### DOC-GOV-R3-01 — Raw-capture review disposition 仍有 v24/v25 版本指针冲突

- **severity:** minor
- **location:** `.dev/docs/raw-capture/review-disposition.md:3-5`
- **evidence:** 页首已写当前 Spec 为 ACTIVE v25，但下一句仍写“当前状态由 v24 Spec、`status.md` 和本表共同导航”；当前 `raw-capture/deferred.md` 也已明确以 ACTIVE v25 为依据。
- **影响:** 点时 disposition 的 authority pointer 不精确，可能让复审者漏读 v25 的 identity-boundary amendment；README/status 的直接链接仍指向当前 `spec.md`，因此不构成 major。

## C1–C5 覆盖

| 清单 | 结论 |
|---|---|
| C1 | full-header、History-owned metadata、transport export、Replay current-auth boundary 已有一致 current contract；per-attempt 限制已明确 deferred |
| C2 | semantic/transport/full export、capture_ref、archive/pin/retention 与当前状态分层一致；restart hardening 已明确 deferred |
| C3 | Replay selector/mode/target/deadline/cancel/client-action/provenance 的未完成部分均在 status/deferred 公开，不再写成 done |
| C4 | RequestJournal 与 History 不持久化完整 journal 的边界清楚；taxonomy/JSONL owner 已 deferred |
| C5 | 未发现仍会让合理读者得出互斥产品行为的 major 文档读法 |

## 搜索面与验证

- 已读取四个 topic 的当前 README、Spec、status/deferred、可用 review disposition 与 Observability implementation ledger。
- 已按需对照 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 中 Replay、RequestJournal、History archive/writer/routes 和 raw-capture capability 的既有证据。
- 未读取无关 topic，未操作 4141，未执行 `git add` 或 `git commit`。
