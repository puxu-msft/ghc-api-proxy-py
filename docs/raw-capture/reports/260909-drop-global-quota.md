# 报告：移除 raw capture 全局（目录级）配额 `max_total_bytes`

日期：2026-09-09
执行者：leaf executor
规格依据：`.dev/docs/raw-capture/spec.md`（ACTIVE v21）
- §2：「不存在目录级总量配额，遗留文件不参与任何配额计算。」
- §5：「不存在目录级总量配额：capture 的总量由规则选择与单文件配额约束，不再提供 `max_total_bytes`。」

规格与任务清单无矛盾。

## 逐文件改动

### 1. `src/app/config/schema.py`

删除 `RawCaptureConfig.max_total_bytes: int = Field(default=4 * 1024 * 1024 * 1024, ge=0)` 一行。
其余字段（`enabled: Literal[False]`、`directory`、`rules_database`、`compression_level`、`max_file_bytes`）一字未动。
`git diff` 确认本文件改动仅此一行删除。

### 2. `src/app/config/compat.py`

仿照 `_migrate_key` 的风格新增专用 helper `_drop_key(section, old_key, *, section_name)`：键不存在时静默返回；存在时 `pop` 掉旧键并发出 `DeprecationWarning`（`stacklevel=3`，与 `_migrate_key` 一致），消息为：

```text
{section_name}.{old_key} has been removed; raw capture is constrained by the per-file quota (max_file_bytes) only
```

在 `migrate_compat` 中对 `observability` dict 的 `raw_capture` 子 dict 应用（键不存在时两层 `isinstance` 检查直接跳过）：

```python
    observability = migrated.get("observability")
    if isinstance(observability, dict):
        raw_capture = cast(dict[str, Any], observability).get("raw_capture")
        if isinstance(raw_capture, dict):
            _drop_key(
                cast(dict[str, Any], raw_capture),
                "max_total_bytes",
                section_name="observability.raw_capture",
            )
```

`section_name` 用完整路径 `observability.raw_capture`，使告警消息可定位到用户 YAML 中的实际位置。

### 3. `src/app/server/composition.py`

`RawCaptureStore(...)` 调用中删除 `max_total_bytes=raw_capture_config.max_total_bytes,` 一行，其余参数不变。

### 4. `src/app/observability/raw_capture.py`

- 删除常量 `LEGACY_CAPTURE_FILE_SUFFIX = ".jsonl.zst"`（随最后一处使用消失而删除）。
- `RawCaptureStore.__init__`：删除 `max_total_bytes` 参数、`self._max_total_bytes`，以及 `_reserved_total_bytes` 的初始化（含目录 rglob 扫描与 legacy 后缀判断——该块正是 legacy 文件计入总量配额的唯一来源）。
- `append()`：删除 `total_quota_exceeded` 分支（`_max_total_bytes > 0 and _reserved_total_bytes + reserved > _max_total_bytes`）与 `self._reserved_total_bytes += queued.reserved_bytes`。
- `_complete_write()`：删除 `self._reserved_total_bytes -= released_bytes`。`released_bytes` 与 `_reserved_file_bytes` 的回滚逻辑逐字节保持不变。
- per-file 配额检查、reservation 记账、poison（`path_poisoned`）、path 首次 append 前验证、writer ack（`note_writer_frame_queued` / `note_writer_frame_completed`）逻辑均未触碰。

### 5. `tests/unit/observability/test_raw_capture.py`

- 删除 `test_legacy_jsonl_files_still_count_toward_the_total_quota`，替换为判别性测试 `test_legacy_jsonl_files_do_not_participate_in_any_quota`：
  - 目录先放一个较大的遗留 `.jsonl.zst`（用 `handle.truncate(4 GiB)` 创建 sparse 文件，实际不占磁盘）；
  - store 以 `max_file_bytes=0`（per-file 配额禁用）构造；
  - 断言 store 正常追加成功（生成 `.cborseq.zst` 且可读出 `request.start`），legacy 文件原样保留。
  - 判别性说明：旧实现中该 4 GiB legacy 文件会被 rglob 扫描计入 `_reserved_total_bytes`，恰好顶满默认 `max_total_bytes=4 GiB`，第一次 append 即 `total_quota_exceeded`；新实现没有任何总量配额，必须成功。
- 参数化配额测试删除 `({"max_total_bytes": 512}, "total_quota_exceeded")` 一组，保留 `({"max_file_bytes": 512}, "file_quota_exceeded")`。
- 清理 4 处对已删除属性 `private_store._reserved_total_bytes` 的断言（原行 398、442、507、563；这些是 `cast(Any, ...)` 后的运行时访问，属性已删，保留会导致 `AttributeError`）。各处 `partial_size` 在所在测试中仍有其他用途，未产生未使用变量。
- 全文件 grep `max_total|total_quota|LEGACY_CAPTURE_FILE_SUFFIX|_reserved_total_bytes`：无残留。

### 6. `docs/.human-controlled/config.example.yaml`（用户控制文件，仅两处最小修改）

- 删除 `max_total_bytes: 4294967296` 一行。
- 节上方英文注释第 416 行由

  `# max_file_bytes / max_total_bytes count actual compressed bytes. 0 disables that limit. …`

  改为仅描述单文件配额：

  `# max_file_bytes counts actual compressed bytes of each capture file. 0 disables that limit. Quota loss is reported at request completion using safe metadata only; raw bodies and credentials never enter ordinary logs.`

未触碰该文件其他任何内容。

## 验证命令与结果

### compat 端到端行为（旧配置仍可加载 + 告警 + 键被删）

```text
$ uv run python -W error::DeprecationWarning -c "...migrate_compat + ProxyConfig.model_validate..."
compat OK: observability.raw_capture.max_total_bytes has been removed; raw capture is constrained by the per-file quota (max_file_bytes) only
key dropped: True
```

`migrate_compat` 在加载链路上被调用（`src/app/config/loader.py:96`、`src/app/config/loading.py:210`），兼容路径真实生效。

### pytest

```text
$ uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/config --no-cov -q
...
FAILED tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses
1 failed, 152 passed in 3.28s
```

**该失败为预存基线失败，与本次改动无关**，证据：

1. ValidationError 报出的 4 个错误全部位于 `model_providers.ghc.github_copilot.exposed_models`、`model_providers.sub2api_a.sub2api.*`、`hook_fix_responses_request.reasoning_encrypted_content`——没有一个涉及 `observability.raw_capture`；pydantic 会报出全部错误，故 raw_capture 节解析通过。
2. `git diff src/app/config/schema.py` 中我的改动只有删除 `max_total_bytes` 一行，未触碰上述出错区域的 schema 定义。
3. 该失败源于同伴在飞改动（schema.py 与 config.example.yaml 均处于 modified 状态）之间的矛盾：example 中已提交的 `exposed_models` / `sub2api.token_file` / `reasoning_encrypted_content` 等键在当前 schema（`extra="forbid"`）下变成 extra_forbidden。
4. 补充只读验证——单独验证 example 的 `observability` 节在新 schema 下解析通过：

```text
$ uv run python -c "...ObservabilityConfig.model_validate(raw['observability'])..."
raw_capture section parses OK; max_file_bytes = 536870912
```

raw capture 相关测试（`test_raw_capture.py`、`test_debug_capture.py`）全部通过。

### ruff

```text
$ uv run ruff check src/app/config/schema.py src/app/config/compat.py src/app/server/composition.py src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py
All checks passed!
```

（未运行 `ruff format`，遵守仓库硬规则。）

### pyright

```text
$ uv run pyright src/app/config/compat.py src/app/observability/raw_capture.py src/app/server/composition.py
0 errors, 0 warnings, 0 informations
```

## 残留检查

6 个改动文件内 grep `max_total|total_quota|LEGACY_CAPTURE_FILE_SUFFIX|_reserved_total_bytes`，仅剩：

- `compat.py:87`：`_drop_key` 调用中的旧键名字符串 `"max_total_bytes"`——删除废弃键本身所需，必须保留。
- `schema.py:74` / `schema.py:365` / `config.example.yaml:317`：`upstream_request_retry.max_total`——无关配置节（重试总数），非 raw capture。

## 边界遵守情况

- 只修改了白名单内 6 个文件；未触碰 `src/app/protocols/*`、`src/app/model_provider/*`、`pipeline/*` 等在飞改动。
- 未执行任何 `git commit` / `git add` / `git stash`。
- 未修改 `.dev/docs/raw-capture/spec.md`。
- 未新增日志；新增代码/注释不含 raw identity、body 或凭据内容。
- 测试新增使用 `handle.truncate` 创建 sparse legacy 文件，不产生 4 GiB 实际磁盘占用。

## 需协调者知悉的事项

1. **预存失败**：`tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` 在本次改动前即失败（同伴在飞改动中 example 的 `model_providers` / `hooks` 键与当前 schema `extra="forbid"` 冲突，4 个 ValidationError，与 raw capture 无关）。需要该文件的作者收敛。
2. `docs/.human-controlled/config.example.yaml` 中 `observability.raw_capture` 节本身也是本次在飞改动新增的（相对 HEAD 整节为新增行），本报告的两处最小修改作用在该新增节上。
