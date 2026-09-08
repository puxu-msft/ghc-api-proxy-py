# Effort translation final fix wave 报告

> 本文件由coordinator基于implementer `a5185013ca013ad2d`在job tmp中的报告做内容转录，并归一化中英文间距与标点排版；它不是byte-verbatim original。末尾另行追加controller squash integration事实；原始报告保留在`$CLAUDE_JOB_DIR/tmp/final-fix-report-agent.md`等待harness自然过期。

## Identity

- Session：`a5185013ca013ad2d`
- Physical worktree：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/effort-translation`
- Branch：`agent/final-effort-fix-a518`
- Required base：`505d62fd2622c4ecb35e701fad33e1ca12300fb6`
- Verified starting HEAD：`505d62fd2622c4ecb35e701fad33e1ca12300fb6`
- Final HEAD：`99e3642bb3f0b370229358ef651e8572a39b528b`
- Commit range：`505d62fd2622c4ecb35e701fad33e1ca12300fb6..99e3642bb3f0b370229358ef651e8572a39b528b`
- Branch fact：恢复期间harness将本会话落在唯一controller physical worktree；coordinator裁定保留当前branch继续，完成后不切回，由coordinator后续切回`worktree-effort-translation`并squash集成。

## 任务列表

| 阶段 | 范围 | 状态 | 结果 |
|---|---|---|---|
| 1 | 核验review finding与当前实现 | done | brief identity与starting HEAD精确匹配 |
| 2 | Production：持久化request-lifetime source headers | done | `RequestContext`持有一次初始化、跨replay稳定的snapshot；send与count共用 |
| 3 | Production：修正Anthropic-compatible alignment diagnostics | done | filtered candidate domain被明确命名，generic Responses wording不变 |
| 4 | Production：同步public type docstrings | done | `TranslationRefused.facts` snapshot与`Conversion`双载荷合同已说明 |
| 5 | Tests：补replay、precedence、provenance、retention与two-stage alignment oracles | done | 新旧行为均按brief判别 |
| 6 | Focused verification、Ruff、Pyright | done | 全部通过；旧bug控制变异按预期判红 |
| 7 | 精确pathspec语义提交与clean-tree核验 | done | commit `99e3642bb3f0b370229358ef651e8572a39b528b`；工作树clean |

## 修改文件

- `src/app/pipeline/request.py`
- `src/app/pipeline/driver.py`
- `src/app/server/inbound.py`
- `src/app/pipeline/translation_driver/reasoning.py`
- `src/app/pipeline/translation_driver/semantic.py`
- `tests/int/test_pipeline_app.py`
- `tests/unit/pipeline/translation_driver/test_reasoning.py`
- `tests/unit/pipeline/translation_driver/test_translation_driver.py`

## 语义 commit

- `99e3642bb3f0b370229358ef651e8572a39b528b` — `fix: close effort translation review findings`
- Commit使用上述八个文件的精确pathspec；commit message先写入`/tmp/a518-final-fix-commit-message.txt`，再通过`git commit -F`提交；未amend。

## Finding closure

### F-MAJ-1 — closed

`RequestContext.source_headers`使用`Mapping[str, str] | None`区分尚未初始化与合法空mapping。`build_context()`从`forwarded_client_headers()`的过滤结果同时初始化attempt-facing`client_headers`与独立source snapshot；直接构造的context则由`source_headers_for_translation()`在首次调用时从当时的`client_headers`精确初始化一次。`handle()`与`handle_count_tokens()`都在`shape_request()`前取得同一request-lifetime snapshot；target-path policy仍只改写`context.client_headers`，因此source-only`anthropic-beta`不会转发上游。

新增真实pipeline／delivery integration test：translated`/v1/messages`携带合法`mid-conversation-output-config-2026-07-01`、top-level`medium`与生效的effort-only`high`控制；首个Responses attempt在完整block前torn，第二次成功。测试断言两个upstream attempt都发送`reasoning.effort=high`、两个Responses`input`都只有user message、两个upstream request都没有`anthropic-beta`，且客户端收到单一Anthropic message lifecycle并以`message_stop`成功结束。

### F-MIN-1 — closed

`align_anthropic_effort()`仍先过滤到五个Anthropic wire efforts，但现在调用共享`_align_effort()`时显式传入`Anthropic-compatible` candidate domain。Missing／empty intersection、downward与floor diagnostics都描述filtered domain；generic`align_effort()`仍产生原有unfiltered Responses wording。完整loss oracle覆盖raw catalog`("none", "minimal", "future-level")`的incompatible intersection，以及`("minimal", "medium")`的`medium` floor；额外exact unit oracle固定downward wording。

### F-MIN-2 — closed

Responses same-format nested residual现在包含stale`reasoning.effort="low"`，owned intent为`high`，完整结果严格断言为`{"reasoning":{"effort":"high","summary":"auto"}}`对应的reasoning object，因而residual／owned写入顺序反转会判红。

### F-MIN-3 — closed

新增reader-level same-value控制：top-level`high`与有效per-message`high`相同，仍严格断言`effort_source is EffortSource.ANTHROPIC_PER_MESSAGE`。现有future-only public-pipeline test通过`build_context` spy同时观察outbound wire与`RequestContext.original_payload`：控制message不进入Responses input，但完整原始payload保留不变。

### F-MIN-4 — closed

新增两条静态完整wire＋ordered loss oracle。`minimal`＋`medium` only得到adaptive thinking、`output_config.effort="medium"`，loss顺序为`minimal→low`后`low→medium` floor approximation；`minimal`＋catalog absent得到adaptive thinking、无`output_config`，loss顺序为`minimal→low`后`low` not-carried。

### F-NIT-1 — closed

`TranslationRefused` docstring说明`facts`是拒绝点可用non-loss observations的immutable snapshot；`Conversion` docstring说明同时拥有losses与facts，并明确facts不影响只由losses决定的`lossless`。

## Verification

- `uv run pytest tests/unit/pipeline/translation_driver/test_reasoning.py tests/unit/pipeline/translation_driver/test_translation_driver.py`：`187 passed`。
- `uv run pytest tests/int/test_pipeline_app.py`：`179 passed`。
- 精确replay／source-header／future-retention focused selection：`7 passed`。
- 修复态单独replay test：`1 passed`。
- 对八个changed source／test files运行`uv run ruff check`：`All checks passed!`。
- 对八个changed source／test files运行`uv run pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 最终`git status --short`：无输出，工作树clean。

## Replay test discrimination

对`src/app/pipeline/driver.py`做了受控旧行为变异，把`handle()`与`handle_count_tokens()`的source snapshot读取临时恢复为旧代码`dict(context.client_headers)`；先以`/tmp/a518-driver-before-old-bug-mutation.py`保存修复态快照，变异测试同步运行且未放后台，随后从快照恢复并以`cmp --silent`核对。该变异下新增replay test精确失败，抛出`TranslationRefused: per-message effort requires its beta header`，栈上对应`code="beta-required"`；日志显示首attempt后stream failure。原因是第一次`shape_request()`已按translated path清空`context.client_headers`，replay的第二次`handle()`因而读到空mapping，在`begin_attempt()`前拒绝control message，所以无法产生第二个upstream attempt。恢复修复态后同一测试`1 passed`。

## Concerns

- 按用户对唯一fix-wave implementer的约束，本轮禁止派subagent，因此没有实施后的独立reviewer verdict；本报告与commit交由coordinator复核并squash集成，当前状态不冒充已集成终态。
- 受控变异快照`/tmp/a518-driver-before-old-bug-mutation.py`与commit message文件`/tmp/a518-final-fix-commit-message.txt`未删除；没有独立manifest review时不执行不可逆清理。
- 本轮没有已知的code／test／docstring未闭合项。
- `F-MAJ-2`的Spec／Acceptance修订不在本轮范围，未编辑`.dev`，由coordinator处理。
- 未触碰cassette，未进行真实网络调用，未启动、停止、signal或替换`4141`服务。
- 未运行全仓库full Ruff／Pyright／pytest；brief明确由coordinator在应用`.dev`修订后运行最终combined checks。本轮已覆盖全部changed tests、完整effort translation unit neighborhood与完整`tests/int/test_pipeline_app.py`。

## Controller squash integration

- `worktree-effort-translation`在精确base`505d62f`且clean时接收`agent/final-effort-fix-a518@99e3642`的squash diff。
- Staged set逐文件核对为上述八个路径，无其它文件。
- Squash commit：`ed6addd017f461c15abc494584e727f1badec633` — `fix: preserve effort translation across replay`。
- 集成后`worktree-effort-translation` clean；临时agent branch未删除。
