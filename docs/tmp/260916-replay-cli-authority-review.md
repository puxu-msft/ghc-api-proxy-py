# Replay CLI source-authority merged-state review

## 评审范围

当前工作树的 merged state：`src/app/replay/__main__.py`、`tests/unit/replay/test_cli.py`、`.dev/docs/replay/status.md`；为核验注入式 authority contract 而直接读取的 `src/app/replay/process.py` 与 `tests/unit/replay/test_process.py`；以及判据来源 `.dev/docs/replay/spec.md`、`.dev/docs/history/spec.md`。未评审主程序的 History route/export 实现、RawCapture/History 的完整持久化实现、其他工作树改动或任何网络/真实 upstream 行为。

## Verdict

**pass**

## Blocker 数

**0**

## 发现

未发现有证据的问题。

## C1–C6 核验

| 断言 | 结论 | 证据 |
|---|---|---|
| C1：CLI 不读取或信任 caller 的 `--capture` path/ref | 通过 | `_parser()` 仅把 `--capture` 解析为惰性的 `Path` 值；`_run()` 在任何 source 处理前 `del args`，不向 Replay process、History 或文件 API 传递该值。CLI 没有 caller-supplied capture ref 参数。 |
| C2：无只读 History-backed source-authority seam 时 fail closed，结构化输出和退出码稳定 | 通过 | CLI 固定返回退出码 `2`，输出固定 JSON envelope：`error.code=replay_cli_unavailable`、`not_started=true`。`test_replay_cli_is_explicitly_disabled_without_history_authority` 对整个反序列化后的 envelope 和返回码做精确断言；动态 probe 得到相同结果。 |
| C3：forged/missing/mismatched/offline source 不触碰文件或绕过 authority | 通过 | 对 `/definitely-not-a-capture` 运行 CLI 时，在模块导入后将 `Path.open/read_bytes/read_text/stat/exists/is_file/iterdir` 全部替换为会失败的探针；CLI 仍按 C2 输出且探针记录为空。由于 disabled CLI 不调用 source authority 或 Replay process，caller 的 forged/missing path、mismatched receipt 或 offline authority 均无可达的文件读取或绕过路径。关联的 process tests 还验证 authority 缺失、receipt entry/ref mismatch、无 capture 都在 reader/executor 前 fail closed。 |
| C4：status 准确说明 CLI disabled 和重新启用前提 | 通过 | `status.md` 明确写出 `app.replay` 返回 `replay_cli_unavailable`，不把 caller `--capture` 当 source receipt 或直接读取路径；重新启用的前提是独立 CLI 可安全组装的只读 History source-authority seam，且不得绕过 History index/capability gate。该表述符合 Replay/History specs 的 capture-required、History capability-authoritative source contract。 |
| C5：禁用 CLI 未误改 process-level injected authority contract | 通过 | `ReplayProcess.__init__` 仍公开 `source_authority: ReplaySourceAuthority | None` 注入点；`_resolve_source_receipt()` 先通过它按 entry/ref 取得 receipt，随后比对 receipt entry/ref 并验证 History capability，才可能读取 receipt 的受控 `capture_path`。`test_process.py` 覆盖 authority 未配置、receipt mismatch、无 capture 和未授权 attempt 的 reader-before-denial 边界。 |
| C6：测试在回退到 caller-path 读取时会变红 | 通过 | 在 `/tmp` 中复制 `src/app`，仅将复制体 CLI 的 `_run()` 变异为先执行 `args.capture.read_bytes()`；以该隔离复制体运行原 `tests/unit/replay/test_cli.py`，测试按预期失败，失败点为 `/forged.capture` 的 `FileNotFoundError`。仓库文件未改。 |

## 已执行证据

- `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/unit/replay/test_cli.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py tests/unit/history/test_archive.py`：**61 passed**。
- `PYTHONDONTWRITEBYTECODE=1 uv run ruff check --no-cache src/app/replay/__main__.py src/app/replay/process.py tests/unit/replay/test_cli.py tests/unit/replay/test_process.py`：**All checks passed**。
- `PYTHONDONTWRITEBYTECODE=1 uv run pyright src/app/replay/__main__.py src/app/replay/process.py tests/unit/replay/test_cli.py tests/unit/replay/test_process.py`：**0 errors, 0 warnings, 0 informations**。
- metadata-only file-isolation probe：对不存在的 caller capture path 返回预期 structured error，且所有导入后安装的 `Path` 文件操作探针均未被调用。
- C6 隔离 mutation probe：变异体运行原 CLI unit test 得到 **1 failed**，退出码 `1`，其余仓库内容未被写入。

## 覆盖与未覆盖面

本次是当前工作树状态的只读评审，而非单一 commit/diff 审查；开始时发现工作树已有大量不在范围内的修改和未跟踪文件，均未评价或改动。未发现可用的只读 History-backed source-authority adapter，因此没有对“重新启用后的 CLI 与实际 History adapter”的集成行为作出验证；这正是当前 disabled boundary 保留的前提。没有运行真实 capture、真实 upstream、网络或 process-level executor。
