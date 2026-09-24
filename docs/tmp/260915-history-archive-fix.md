# HistoryArchiveStore 重启恢复修复报告

## 任务账本

| 任务 | 状态 | 时间（UTC） | 说明 |
| --- | --- | --- | --- |
| 检查实现、测试与工作树 | done | 2026-09-15 | 确认当前实现仅在内存维护 `_segments`，重建后会将相同 identity 的 offset 误认为 0。工作树另有用户 WIP，未触碰。 |
| 实现安全恢复 | done | 2026-09-15 | 首个重启后 append 扫描匹配 identity 的既有 segment，并按实际、经验证的 frame 边界恢复大小。 |
| 增加回归测试 | done | 2026-09-15 | 已加入并执行重启续写、多个既有 segment/满段 rotation、截断尾拒绝追加的确定性覆盖。 |
| 验证 | done | 2026-09-15 | `pytest tests/unit/history/test_archive.py` 为 7 passed；目标文件 ruff 通过；全项目 pyright 为 0 errors、0 warnings、0 informations。 |
| 交付报告 | done | 2026-09-15 | 本文件已补齐实现、安全边界、验证结果和工作树范围说明。 |

## 当前设计判断

恢复路径只接受名称严格符合 `history-000000.history.cborseq.zst` 形式的常规文件。对同一 session/agent 目录内的所有既有 segment，逐 frame 找到 zstd frame 边界并完成 zstd+CBOR map 解码验证；任何截断或不可读 frame 都使该 identity 的 append 失败，而不是把损坏尾部误判为完整数据并继续写入。经验证后选择编号最大的 segment；其大小达到 `max_segment_bytes`，或容纳不了新 frame 时，沿用既有 rotation 规则创建下一个编号。

## 实现变更

- `HistoryArchiveStore._segment_for()` 在内存中没有该 identity 的当前 segment 时，先恢复磁盘状态，再计算 append 位置。
- 恢复仅扫描该 identity 对应的 `session-<hash>/agent-<hash>/` 目录，并只接受严格的六位数字 `history-<number>.history.cborseq.zst` 文件名；不把无关文件当作 archive segment。
- 每个既有 segment 都通过 `_read_zstd_frame()` 按独立 zstd frame 找边界，并用 zstd 解压及 CBOR map 解码验证。扫描后的 `stream.tell()` 是可信的实际末尾，故重建后的首条 reference 从已有 frame 之后开始。
- 因为所有既有 segment 都被验证，编号较高的当前 segment 以外的损坏也不会被悄悄忽略。若存在截断或不可读 frame，append 抛出 `ValueError`，不创建新 segment，也不写入损坏文件。
- 若编号最高的有效 segment 已满（包含 size 恰好等于 `max_segment_bytes`），恢复后的常规 rotation 继续使用下一个编号；frame 仍保持独立的 CBOR+zstd 数据、既有 digest/reference 以及原来的 oversized-first-frame 语义。
- `read()` 与 `iter_records()` 共用 frame 解码辅助函数；对外可观察的校验顺序及错误语义不变。

## 回归覆盖

1. `test_history_archive_restores_existing_segment_before_appending`：store A 写入后构造新的 store B；第二条 reference 与第一条同 segment、offset 等于第一 frame 长度，且两条都可读。
2. `test_history_archive_scans_existing_segments_and_rotates_from_full_latest_segment`：先强制产生 `000000`、`000001` 两个 segment，再以最后一个 frame 长度作为 max 重建；重建扫描多个既有 segment，并在恰好满的 `000001` 后创建 `000002`，三条都可读。
3. `test_history_archive_refuses_to_append_after_truncated_existing_tail`：人为向有效 segment 追加不完整 zstd magic；重建后的 append 安全失败，文件字节不变，原 reference 仍能读取。

## 验证记录

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/unit/history/test_archive.py` | 7 passed，6.67s |
| `uv run ruff check src/app/history/archive.py tests/unit/history/test_archive.py` | All checks passed |
| `uv run pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |

## 范围与工作树说明

实际源代码改动仅为 `src/app/history/archive.py` 与 `tests/unit/history/test_archive.py`。报告位于本文件。验证时工作树还包含调用方/其他 agent 的既有或并发 WIP，其中包括其他 `src/app/history/*` 文件；它们未被本修复读取后改写、未纳入此修复，也未被回退。
