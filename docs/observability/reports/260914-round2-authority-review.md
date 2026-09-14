# Round 2 authority review

## 评审范围与代码基线

评审时间：2026-09-14。范围是当前 `.dev` living docs：四个 topic 的 `README.md/spec.md/status.md/deferred.md`、observability `implementation-ledger.md` 与 `review-disposition.md`，以及 `.dev/README.md`。`history/archive/reports` 只作为 provenance，不作为 current authority。

代码事实只按 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 核对：`git cat-file -e` 对 `src/app/history/archive.py`、`src/app/observability/request_journal.py`、`src/app/replay/process.py` 均返回 present；不以共享主树状态或物理缺失路径作证据。上一轮已接受的实现欠口，本轮只检查是否被 current Spec/入口如实表达。

## 总体 verdict

**pass**。未发现 blocker 或 major；已接受的 History restart hardening、RequestJournal taxonomy、Replay result boundary、per-attempt capability 与 user-controlled observability source 均有 current owner、状态和 deferred/disposition 导航，可以进入下一轮。

## C1：authority 唯一性与 ledger 边界

- `.dev/docs/observability/README.md:3,5-14,16-23` 明确四个 topic 各自拥有独立行为 Spec，本页只导航；并明确实现限制只进 `status.md/deferred.md`。
- `implementation-ledger.md:5,11-17,21-23` 只记录状态、提交、验证证据和 owner 链接，明确“不复制合同、字段语义或安全边界”。
- `review-disposition.md:5,7-17` 只映射 finding family 到 current owner，并明确不把 review 结论升级成行为合同。
- 结论：**C1 通过**；未发现第二份 current behavior authority。

## C2：实现切片、状态、边界与 disposition 对账

- History：`history/status.md:6-24` 与 `history/deferred.md:3-7` 明确主体 slice 已落地、restart recovery/per-attempt capability/purge 是限制；`implementation-ledger.md:12-14` 使用 `done-with-deferred-hardening`，未再写成完整 hardening。
- RequestJournal：`observability/status.md:8-14,24-31`、`observability/deferred.md:5-10`、ledger `:15` 明确 bounded subset/JSONL boundary 与 taxonomy deferred；这与 committed HEAD 的 `RequestJournal` 存在及其有限 event kinds 一致。
- Replay：`replay/status.md:6-24`、`replay/deferred.md:3-8`、ledger `:16,29` 明确 process skeleton 已落地，而 CLI mode/result boundary/History persistence deferred；`replay/spec.md:5,97,107-109` 已分层表述。
- Raw capture：`raw-capture/status.md:6-20`、`raw-capture/review-disposition.md:7-13` 明确 full-header closed、aggregate capability 当前、per-attempt matrix deferred；未把旧 v23 evidence 当 current gate。
- 结论：**C2 通过**；没有把已接受的实现欠口伪装成 done，也没有因这些已导航限制重复形成 major。

## C3：过期说法、旧路径与当前未实现

- 各 Spec 都链接当前状态/候选：`observability/spec.md:5,6,118-130`、`history/spec.md:5,168`、`replay/spec.md:5,97,107`；未把实现限制写回为合同变更。
- v23、design-only、`src/.archived/` 等仍只出现在 revision/provenance 或明确的旧实现说明中；`raw-capture/status.md:20` 还明确候选材料不能反推 v24。
- 缺少的 `docs/.human-controlled/observability.md` 被 `observability/README.md:18`、`status.md:31`、`review-disposition.md:17` 明确标为 candidate-only/user-controlled flow，不被 current Spec 静默替代。
- 结论：**C3 通过**；该缺失源是已公开的治理限制，不是 current authority 冲突。

## C4：接手入口、README/status/deferred/disposition

- `.dev/README.md:54,57,59,61,75,77-82` 已把 History、Observability、Raw capture、Replay 纳入 inventory，并要求从 topic README 进入 status/spec。
- 四个 topic README 都给出 Spec/status/deferred/disposition 导航：observability `:5-14`、history `:3-8`、raw-capture `:3-6`、replay `:3-6`。
- accepted limitations 均能从入口落到 owner：History `status/deferred`、Observability `status/deferred`、Replay `status/deferred`、Raw capture `status/deferred`；review disposition 还提供 finding family 到 owner 的汇总。
- 定向 Markdown link probe 对 reviewed entry/README/disposition 返回无 missing output（exit 0）。
- 结论：**C4 通过**；新接手者可以找到 current contract、当前实现边界和已接受限制。

## Major findings

未发现 blocker/major。

## 可记录不修

无。上一轮的 History restart、RequestJournal taxonomy、Replay result boundary、per-attempt capability、topic inventory 与 missing user-controlled source 已分别落入 current status/deferred/disposition；按本轮规则不重复列为 major。

## 搜索面与停止条件

已读取本轮范围内的 current living docs，核对 committed HEAD 的存在与关键实现锚点，并执行 reviewed entry/README/disposition 的定向 Markdown link probe。未扩大到无直接关联 topic，未把历史报告当 current authority，未执行写入性仓库命令、未操作 4141。
