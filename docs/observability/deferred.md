# Observability 长期改进

本页只记录已识别、当前接受不做的长期形状改进。它不是行为合同；一旦采用，先修改对应 Spec，再修改实现。

| ID | 候选 | 当前处置 | 说明 |
|---|---|---|---|
| OBS-D-01 | 完整 RequestJournal taxonomy | deferred | 补齐 route/attempt/block/terminal/history receipt，并让 freeze 顺序覆盖最终 handoff |
| OBS-D-02 | JSONL writer owner 收敛 | deferred | 明确为 shadow/export 或移除独立 durable truth，避免与 History 形成第二事实源 |
| OBS-D-03 | per-attempt capture capability | deferred | 让 RawCaptureObservation、History attachment 和 Replay selector 共享 attempt matrix |
| OBS-D-04 | full regression baseline failures | accepted baseline | 4 个失败已在 `54bc1b5c` 重现；不归因于本轮 slice，待所属 pipeline/config/catalog 主题处理 |
