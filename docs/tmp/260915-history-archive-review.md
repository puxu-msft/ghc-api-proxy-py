# History archive restart fix 独立评审

## 评审范围

- **被评实现：** `src/app/history/archive.py`、`tests/unit/history/test_archive.py` 的当前工作树版本。
- **判据来源：** `.dev/docs/tmp/260915-history-archive-fix.md`，以及调用方指定的已复现真实缺陷：`HistoryArchiveStore` 重建后 `_segments` 为空，后续 append 会从 offset `0` 覆盖既有 frame。
- **明确排除：** 所有其他 capture、history route、replay、retention 改动；并发工作树中的其他文件不作为本次评审对象。

## 总体 verdict

**pass**。在限定范围内，未发现高置信 blocker、major 或 minor。此前的重启后 offset 归零缺陷已闭合；本轮独立检查也未发现该修复引入的高置信系统问题。

## Blocker 数

0

## 独立判据

1. 重建后的首个 append 必须恢复对应 identity 的现有 segment number 和可信 byte size，不能覆盖既有 frame。
2. 既有 reference 的 digest 与 offset 必须继续可读；恢复后新 reference 的 offset 必须接在完整 frame 边界之后。
3. 最新 segment 已满或容不下新 frame 时，恢复路径必须按既有规则 rotation 到下一个编号。
4. 既有 archive 的损坏或截断尾部必须安全处理，不能静默在不可信边界续写，也不能破坏既有可读 frame。
5. 结论必须以本次执行证据为准，不能仅采信修复报告的自述。

## 评审进度

- 已取得独立判据与修复报告，随后读取当前实现、完整目标测试与限定 diff。
- 已执行目标测试以及独立的重启、rotation、截断尾和畸形尾 probe。

## 上一轮已知问题闭合度

| 上轮问题 | 状态 | 独立证据 |
| --- | --- | --- |
| 重建后的 `HistoryArchiveStore` 因 `_segments` 为空而把已有 segment 的新 reference offset 记为 `0`，导致旧/新 frame reference 不能同时正确读取。 | **closed** | `_segment_for()` 在没有内存 segment 时调用 `_restore_current_segment()`；后者扫描该 identity 的严格命名 segment、验证每个 frame 并将最高编号 segment 的实际验证后 size 恢复到内存状态。`test_history_archive_restores_existing_segment_before_appending` 与本次独立 restart probe 均确认新 reference 的 offset 位于已存 frame 之后，且旧、新 reference 均可读。 |

## 当前系统的新问题

未发现高置信的新问题。

### 承重判据逐项比对

| 判据 | 结论 | 代码与执行证据 |
| --- | --- | --- |
| 重启后恢复正确 segment number 和可信 size，不能从 offset `0` 继续。 | 满足 | `src/app/history/archive.py` 的 `_restore_current_segment()` 枚举目标 identity 目录，并由 `_validated_segment_size()` 逐 frame 验证后使用流的实际末尾位置；`_segment_for()` 以恢复结果计算 offset。目标测试通过。 |
| 既有 reference 的 digest/offset 保持可读，新增 reference 从完整 frame 边界开始。 | 满足 | `read()` 仍先检查 length 和 SHA-256 digest，再解码 frame。目标重启测试读取旧、新 reference；独立 probe 对三条跨重启及 rotation 的 reference 均读取成功。 |
| 恢复到已满的最新 segment 时，按既有规则 rotation 到下一个编号。 | 满足 | `_segment_for()` 保留 `current.size + frame_length <= max_segment_bytes` 的沿用条件，不满足时以恢复的最高编号加一创建 segment。目标 rotation 测试和独立 probe 均确认 `000002` 被创建、三个 reference 可读。 |
| 截断或畸形尾部不能被当成可信边界续写，既有完整 frame 不被破坏。 | 满足 | `_validated_segment_size()` 通过 `_read_zstd_frame()` 与 `_decode_history_frame()` 验证至 EOF；不可信尾会使 append 失败而不是返回 size。目标截断尾测试、独立截断尾 probe、附加畸形 `junk` 尾 probe 均确认 append 失败、文件字节未变、原 reference 仍可读。 |

## 执行证据

| 命令/探针 | 结果 |
| --- | --- |
| `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/history/test_archive.py` | **7 passed**（3.04s）。 |
| 同一隔离临时目录内的 restart + rotation probe | **pass**：先构造 `000000` 和 `000001`，重建 store 后产生 `000002`，三条 reference 都可读取。 |
| 同一隔离临时目录内的截断尾 probe | **pass**：append 以 `ValueError` 失败；归档字节不变，既有 reference 可读取。 |
| 同一隔离临时目录内的畸形尾 (`junk`) probe | **pass**：append 以 `ValueError` 失败；归档字节不变，既有 reference 可读取。 |
| `git -C /home/xp/src/ghc-api-proxy-py diff --check -- src/app/history/archive.py tests/unit/history/test_archive.py` | 通过（无输出且后续命令继续执行）。 |

## 搜索面与限制

- 读取的判据来源仅为 `.dev/docs/tmp/260915-history-archive-fix.md` 和调用方给定的真实缺陷/验收条件；没有把实现者的「已修复」自述当作结论。
- 检查了当前完整的 `src/app/history/archive.py` 与 `tests/unit/history/test_archive.py`，并检查二者的限定 diff。
- 明确未评审并发工作树中其他 capture、history route、replay、retention 或其他不在范围内的改动；也没有修改被评实现或测试。唯一写入是本评审报告。
