# RawCapture total admission cap 独立评审

日期：2026-09-15

## 评审范围

仅审查 `src/app/observability/raw_capture.py` 的 `RawCaptureStore` 目录总量 admission cap，以及其直接配置装配 `src/app/server/composition.py`、兼容迁移 `src/app/config/compat.py`、schema/config example、`tests/unit/observability/test_raw_capture.py` 与直接 RawCapture/History 的 Spec、deferred 文档。明确不审 `HistoryArchiveStore`、History writer/archive、export routes、replay、provider 与共享工作树的其他并发 WIP。

## 总体结论

**pass。** 未发现本审查切片中违反 ACTIVE v27 的 blocker、major、minor 或 nit。`max_total_bytes` 已从有效配置接到 production composition；启动盘点、同锁总量 reservation、超限 admission-only 行为与稳定完成诊断均有代码和运行证据。History automatic retention/purge/tombstone/compaction 没有被作为本切片的已实现能力宣称。

## Blocker 数

0。

## 独立判据

- RawCapture Spec ACTIVE v27 §5–§6：有效配置接线、现存 `.cborseq.zst` 启动盘点、已落盘和 queued compressed frame 的同锁 reservation、超额只拒绝新 frame、不删除既有 evidence，以及稳定且安全的 incomplete metadata。
- `raw-capture/deferred.md` D-6：RawCaptureStore 不拥有 History/index/replay 引用关系，所以 total cap 不做 evidence eviction。
- History Spec §7 和 `history/deferred.md` HIS-D-03：public physical delete/purge 不存在；受控 cold artifact purge/deletion receipt 仍属 deferred，自动 retention/purge/tombstone/compaction 不能被本切片宣称已实现。

## 发现

未发现问题。

### 承重要求逐项对照

| 判据 | 代码与测试证据 | 结论 |
| --- | --- | --- |
| 有效配置必须接线 `max_total_bytes` | `RawCaptureConfig.max_total_bytes` 是 `ge=0` 的字段，默认 4 GiB；`migrate_compat()` 已移除旧的 `_drop_key()` 分支；`build_chain()` 将 `config.observability.raw_capture.max_total_bytes` 传入 `RawCaptureStore`。`test_raw_capture_total_quota_survives_compat_and_schema_loading` 覆盖 compat 后 schema 值为 123 的路径。`config.example.yaml` 也给出 4294967296。 | 通过 |
| 启动盘点 current-format evidence | 构造器以 `_existing_capture_bytes(root)` 初始化 `_reserved_total_bytes`，仅递归统计 `*.cborseq.zst` 的实际 `stat().st_size`；旧 `.jsonl.zst` 不匹配 suffix。`test_total_quota_inventories_existing_current_capture_files_without_deleting_them` 先创建真实 capture，再以刚好等于既有文件大小的 cap 重开 store，验证新 request 被拒绝、原字节不变、没有第二文件。 | 通过 |
| queued/compressed reservation 与并发不能超预算 | `append()` 先 CBOR 编码和 zstd 压缩，随后在同一 `_lock` 内检查 file/total budget、`put_nowait()`，并增加 file/total reservation；worker 成功写入保持 reservation，失败或短写仅回滚未实际写入字节。`test_total_quota_reserves_queued_compressed_frames_across_capture_paths` 固定每 frame 为 64 bytes、阻塞第一条写入、总 cap 设为 96；第二个不同 path 的首帧被拒绝且文件不创建。因此没有“首帧正在 worker 中、第二帧绕过 total cap”的窗口。 | 通过 |
| 超额仅拒绝新 frame，不删除证据 | total check 返回 `total_quota_exceeded`，不含 unlink/truncate/rewriting 分支；上述 inventory test 比较既有完整 bytes。独立运行时 probe 也以重启后的 existing cap 验证原文件不变且 capture 文件数仍为 1。 | 通过 |
| 失败 metadata 稳定且不泄漏 payload | prepare warning 和 completion warning 仅写 request id、固定 event、固定 reason、exception type/errno 与完整性布尔值。total quota 走固定 `total_quota_exceeded`；`test_quota_drop_is_reported_safely_at_request_completion` 参数化 file/total 两种 cap，断言首个 dropped event、`writer_error=false`、`response_body_capture_complete=false`，并反向断言 body marker、path 不在日志。Spec §6 的封闭 reason 集合包含该值。 | 通过 |
| History retention 不得冒充已实现 | RawCapture Spec v27 §7 将此次能力限定为 admission cap；`raw-capture/deferred.md` D-6 明确不做 evidence eviction；History Spec §7 不提供 public physical delete/purge，`history/deferred.md` HIS-D-03 仍为 deferred。当前共享工作树虽有其他 agent 对 `history/archive.py`、`history/writer.py` 的 WIP，但它们被调用方排除，未读取或作为本结论的证据。 | 通过（限于宣称与范围） |

### 绿灯分辨力

focused suite 中的 reservation test 不是仅检查正常写入：它以固定 64-byte compressed frame、96-byte total cap 和受控阻塞 worker 制造必须拒绝第二个 path 的反例；若移除 total cap 检查或在 lock 外/写入后才 reserve，第二个 path 会被创建，`assert not second_path.exists()` 会失败。启动盘点 test 也以“cap 恰等于已存在 evidence”这个边界条件检查禁止增长和禁止删除。

## 上轮 blocked 原因闭合情况

**闭合（就可定位的历史阻塞而言）。** ACTIVE Spec v21 曾依用户裁决移除 directory-level `max_total_bytes`，同时旧 `compat.py` 的 `_drop_key()` 会把该配置静默删掉；这使 total quota 无法作为有效配置工作。ACTIVE v27（2026-09-15）明确恢复 current-format total admission cap，且本轮代码已删除删除配置的 compat 分支、加入 schema 与 production composition 接线，并由 focused test 和独立 probe 证实实际生效。

进度账本仍把 2026-09-15T23:42:42Z 的 `raw-capture-quota`/`focused-tests` 标为 WIP，但该账本不是独立 review finding；它不能推翻本次执行结果。History retention 的 deferred 状态没有、也不应在本切片中“闭合”——它是明确保留的未来工作而非 RawCapture quota cap 的未修复缺陷。

## 验证执行

所有命令均在 `/home/xp/src/ghc-api-proxy-py` 显式执行：

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/unit/observability/test_raw_capture.py` | 33 passed，4.56s |
| `uv run ruff check src/app/observability/raw_capture.py src/app/config/compat.py src/app/config/schema.py src/app/server/composition.py tests/unit/observability/test_raw_capture.py` | All checks passed |
| `uv run pyright` | 0 errors、0 warnings、0 informations |
| 静默 Python quota probe（新建临时 directory，先创建 existing capture，再以其实际 size 作为新 store cap） | 退出成功且 stdout/stderr 为空；断言 existing bytes 不变、`.cborseq.zst` 数量为 1 |
| `git diff --check --`（仅本评审范围） | passed |

probe 不传入或输出 request/response body、credential 或其他 sensitive payload；它只验证总量 admission 的可观察不变量。

## 搜索面与限制

已读判据：`.dev/docs/raw-capture/spec.md`（ACTIVE v27，特别是 §5–§7）、`.dev/docs/raw-capture/deferred.md`（D-6）、`.dev/docs/history/spec.md`（§7）和 `.dev/docs/history/deferred.md`（HIS-D-03）、当前 quota 进度账本与实施报告。

已读最终实现/接缝：`raw_capture.py` 的 store、append/reservation/worker/completion 路径；`composition.py` 的 `RawCaptureStore` 装配；`compat.py`；`schema.py` 的 `RawCaptureConfig`；config example；`test_raw_capture.py` 的 quota、writer rollback 与安全 diagnostics 测试；以及上述文件的 scoped diff。

明确未读/未评：`HistoryArchiveStore` 的实现、History archive/writer、history/export routes、replay、provider，以及工作树中其他并发 WIP。本报告也不对这些面的测试或 Pyright 所可能覆盖到的其他文件作质量结论；全量 Pyright 仅记录为当前工作树状态下的辅助验证。
