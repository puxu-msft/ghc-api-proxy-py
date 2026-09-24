# Raw capture total quota：实施报告

日期：2026-09-15  
结论：**pass（本次授权的 RawCapture admission-cap slice）**

## 实施内容

- `RawCaptureStore` 新增 `max_total_bytes`（默认 `4 * 1024 * 1024 * 1024`；`0` 禁用 total limit）。
- store 构造时仅盘点现有 current-format `*.cborseq.zst` 的真实磁盘字节；遗留 `*.jsonl.zst` 不计入。
- 每个新 frame 在同一 accounting lock 内，以 compressed 实际字节同时预留 per-file 与 directory-total 预算；因此已入队、尚未写盘的 frame 也会阻止并发超额。
- worker 成功完成时 reservation 保持；写入失败/短写时，未写入的部分同时从 file 与 total reservation 回滚，部分已写字节继续计入实际成本。
- total budget 已满或启动盘点已超过预算时，写入返回稳定 `total_quota_exceeded`，停止该 request 后续 capture；**不删除、截断、迁移或重写任何已有 evidence**。
- `RawCaptureConfig.max_total_bytes`、`config.example.yaml`、compat loading 与 production composition 已接线；配置不再被 `migrate_compat()` 静默删除。

## 新增覆盖

`tests/unit/observability/test_raw_capture.py` 新增或扩展：

1. `max_total_bytes` 经 compat migration 和 schema validation 后仍保留；
2. 新 store 启动盘点 existing `.cborseq.zst` 后，在等于当前用量的 cap 下拒绝新 capture，并逐字保留已有 evidence；
3. 人工阻塞 worker 的第一条 64-byte frame，验证第二个 capture path 因 queued reservation 被 total cap 拒绝，且没有创建第二个文件；
4. quota completion diagnostics 同时覆盖 `file_quota_exceeded` 与 `total_quota_exceeded`，维持 body/credential 不进入普通日志的断言；
5. 既有 large legacy `.jsonl.zst` fixture 继续证明 legacy 文件不消耗 current-format total quota。

## 合同同步

- `.dev/docs/raw-capture/spec.md` 升至 **ACTIVE v27**：记录 total cap 的 config 含义、启动盘点、双重 reservation、超额时 admission-only 行为和新增 reason 枚举值。
- `.dev/docs/raw-capture/deferred.md` 新增 D-6：明确 RawCaptureStore 不做 evidence eviction，因为它不拥有 History/index/replay 引用关系。

## 明确 deferred

History automatic retention/purge 没有实施，且没有改动 `src/app/history/archive.py` 或 `src/app/history/writer.py`。这次只选择不会破坏 index-referenced evidence 的 RawCapture admission cap；History 的 automatic purge、tombstone/deletion receipt 与 segment compaction 仍需独立设计和实施。

## 验证

| 命令 | 结果 |
| --- | --- |
| `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/observability/test_raw_capture.py` | **33 passed**，5.06s |
| `cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/observability/raw_capture.py src/app/config/schema.py src/app/config/compat.py src/app/server/composition.py tests/unit/observability/test_raw_capture.py` | **passed** |
| `cd /home/xp/src/ghc-api-proxy-py && uv run pyright` | **0 errors, 0 warnings** |

验证时共享工作树仍有其他 agent 的未暂存 WIP（包括 History archive/writer 相关文件）；本任务没有读取、修改或覆盖这些后到的 WIP。上表的 RawCapture focused suite、scoped Ruff 和全量 Pyright 均在这些并发状态下执行，结论仅覆盖本报告列明的 RawCapture admission-cap slice。
