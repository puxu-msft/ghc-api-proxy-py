# Responses Client-Action Display Grouping Implementation Plan

状态：fully implemented on 2026-09-06。Production、unit 与 integration 转录由 `fix: coalesce adjacent response actions in logs` 同步；执行差异与验证结果见文末“实施结果”。

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复 TUI completion line 未合并相邻 `function_call` 的回归，并用 typed display segments、显式相邻归约与共享 renderer 消除双 accumulator 的结构性失效面。

**Architecture:** `ResponseObservation` 和 legacy `ClientAction` 保持逐项事实不变。`request_log.py` 先把 rich items 或 legacy actions 投影成 immutable typed display segments，再用一个 pure pairwise reducer 合并相邻同 raw type 的 named actions与相邻同 kind reasoning，最后统一编码和渲染；contextual `completed` 继续直接读取完整 observation，不从 display segments 反推。

**Tech Stack:** Python 3.14、frozen slotted dataclasses、pytest、Ruff check、Pyright。

**Spec:** [行为 Spec](spec.md)；[内部设计](design.md)；[结构评审与方案比较](history/260906-function-call-grouping-structure-review.md)；[设计复评](history/260906-function-call-grouping-design-review-2.md)；[Spec 复评](history/260906-function-call-grouping-spec-review.md)。

## Global Constraints

- `spec.md` 是可观察行为的唯一权威；不得按当前错误实现或修订前 tests 反向修改 Spec。
- Durable `ResponseObservation.output_items` 逐项保留 index、raw type、raw name、重复和顺序；display grouping 不得回写或去重 facts。
- 只合并 visible segment sequence 中连续、同 raw type、具名且 `REQUIRED` 的 actions；visible reasoning、different raw type、`UNKNOWN` 与 anonymous actions 是 barrier；不可见 `NOT_REQUIRED` item 不制造 barrier。
- Rich observation 与 legacy fallback 复用 action segment selection、adjacent reduction 和 rendering；legacy 不合成 reasoning facts。
- Contextual `completed` 继续读取完整 output facts 与 snapshot completeness，不从 display segments 反推。
- 不修改 `ResponseObservation`、`OutputItemSummary`、`ClientAction` 或 classification schema；不改 Chat Completions、Anthropic stop reason、pending tools、footer 或 delivery policy。
- Production behavior 先实现，再同步关键路径测试；不采用 TDD，不运行 `ruff format`，不建立 mutation framework 或机械 gate。
- 共享主树中只编辑本计划列出的源码和测试范围；提交前重新检查这些路径是否出现同伴改动，提交使用精确 pathspec 与 `-F` message file。

---

## File Map

- Modify: `src/app/observability/request_log.py`——定义 private typed segments、atomic projection、adjacent reducer、renderer，并让 rich／legacy paths 复用它们。
- Modify: `tests/unit/observability/test_request_log.py`——按 projection、reducer、renderer、public rich formatter 与 legacy fallback 五个责任层同步 oracle。
- Modify: `tests/int/test_pipeline_app.py`——更新既有 production-entry terminal-output exact tail，从两个独立 `function_call(Bash)` 改为一个 `function_call(Bash,Bash)`。
- Already revised: `.dev/docs/tui/spec.md`——行为合同与验收 oracle。
- Already created: `.dev/docs/tui/design.md`——内部结构与未采用方案。
- Update during closeout: `.dev/docs/tui/history/260906-function-call-grouping-structure-review-disposition.md`——记录实现、评审与验证终态。

### Task 1: Implement the typed display projection

**Files:**
- Modify: `src/app/observability/request_log.py:231-247`
- Modify: `src/app/observability/request_log.py:279-409`

**Interfaces:**
- Consumes: `OutputItemSummary`, `ClientAction`, `ClientActionRequirement`, `inert_token()`, `_painted_tools()`, `REASONING_WORD`。
- Produces: `_NamedAction`, `_Reasoning`, `_UnknownAction`, `_AnonymousAction`, `_ResponseDisplaySegment`, `_action_display_segment()`, `_response_display_segment()`, `_coalesce_response_display_segments()`, `_render_response_display_segment()`。
- Preserves: `format_client_actions()`, `format_terminal_status()`, `format_response_observation()` 的 public signatures 与 `format_completion_line()` 的 ending precedence。

- [x] **Step 1: Re-run the known-bad reproduction before editing**

Bind the repository root in the same Bash call:

```bash
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
PYTHONPATH=src uv run python - <<'PY'
from app.observability.request_log import RequestLine, format_completion_line
from app.pipeline.response_observation import ResponsesObserver

observer = ResponsesObserver()
observer.observe_response({
    "status": "completed",
    "output": [
        {"type": "reasoning", "summary": [], "encrypted_content": "sealed"},
        {"type": "function_call", "name": "TaskCreate"},
        {"type": "function_call", "name": "Bash"},
    ],
})
print(format_completion_line(
    RequestLine(method="POST", path="/v1/messages", inbound_format="anthropic-messages", model="gpt-5.6-sol", status_code=200),
    status="ok",
    response_observation=observer.snapshot(),
))
PY
```

Expected current output suffix: `completed reason(enc:1) function_call(TaskCreate) function_call(Bash)`。这条 probe 记录修复前行为，不冒充自动化回归测试。

- [x] **Step 2: Add private immutable segment types**

Add the following shapes in `request_log.py`, beside the existing response-display helpers:

```python
type _ReasoningKind = Literal["enc", "txt"]


@dataclass(frozen=True, slots=True)
class _NamedAction:
    raw_type: str | None
    raw_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Reasoning:
    kind: _ReasoningKind
    count: int


@dataclass(frozen=True, slots=True)
class _UnknownAction:
    raw_type: str | None


@dataclass(frozen=True, slots=True)
class _AnonymousAction:
    raw_type: str | None


type _ResponseDisplaySegment = _NamedAction | _Reasoning | _UnknownAction | _AnonymousAction
```

Keep these types private to `request_log.py`. `_NamedAction.raw_names` must be non-empty by construction; no runtime validation layer is needed because both constructors are private.

- [x] **Step 3: Add one shared action projector and one rich-item projector**

Implement a shared requirement-to-variant seam so rich and legacy paths cannot drift in their `UNKNOWN`／anonymous／named branching:

```python
def _action_display_segment(
    requirement: ClientActionRequirement,
    raw_type: str | None,
    raw_name: str | None,
) -> _ResponseDisplaySegment | None:
    if requirement is ClientActionRequirement.NOT_REQUIRED:
        return None
    if requirement is ClientActionRequirement.UNKNOWN:
        return _UnknownAction(raw_type=raw_type)
    if not raw_name:
        return _AnonymousAction(raw_type=raw_type)
    return _NamedAction(raw_type=raw_type, raw_names=(raw_name,))


def _response_display_segment(item: OutputItemSummary) -> _ResponseDisplaySegment | None:
    reasoning_kind = _reasoning_kind(item)
    if reasoning_kind is not None:
        return _Reasoning(kind=reasoning_kind, count=1)
    return _action_display_segment(
        item.client_action.requirement,
        item.type,
        item.name,
    )
```

Narrow `_reasoning_kind()` to `_ReasoningKind | None`. Visible reasoning is selected before `NOT_REQUIRED` filtering; an empty reasoning item returns no segment through `_action_display_segment(...NOT_REQUIRED...)`.

- [x] **Step 4: Add the total adjacent reducer**

Implement a pure fold that accepts already-visible segments and never handles encoding or color:

```python
def _coalesce_response_display_segments(
    segments: tuple[_ResponseDisplaySegment, ...],
) -> tuple[_ResponseDisplaySegment, ...]:
    coalesced: list[_ResponseDisplaySegment] = []
    for segment in segments:
        previous = coalesced[-1] if coalesced else None
        if (
            isinstance(previous, _NamedAction)
            and isinstance(segment, _NamedAction)
            and previous.raw_type == segment.raw_type
        ):
            coalesced[-1] = _NamedAction(
                raw_type=previous.raw_type,
                raw_names=previous.raw_names + segment.raw_names,
            )
        elif (
            isinstance(previous, _Reasoning)
            and isinstance(segment, _Reasoning)
            and previous.kind == segment.kind
        ):
            coalesced[-1] = _Reasoning(
                kind=previous.kind,
                count=previous.count + segment.count,
            )
        else:
            coalesced.append(segment)
    return tuple(coalesced)
```

Do not add callbacks, generic run keys or special-case flush state. Every unlisted segment pairing remains a barrier through the final `else`.

- [x] **Step 5: Add the single segment renderer**

Implement grammar after reduction:

```python
def _render_response_display_segment(
    segment: _ResponseDisplaySegment,
    *,
    color: bool,
) -> str:
    if isinstance(segment, _NamedAction):
        item_type = inert_token(segment.raw_type or "") or "client_action"
        names = [inert_token(name) for name in segment.raw_names]
        return f"{item_type}({_painted_tools(names, color=color)})"
    if isinstance(segment, _Reasoning):
        return paint(
            f"{REASONING_WORD[ReplyDialect.RESPONSES]}({segment.kind}:{segment.count})",
            DIM,
            color=color,
        )
    if isinstance(segment, _UnknownAction):
        item_type = inert_token(segment.raw_type or "")
        return f"client_action?({item_type or 'unknown'})"
    item_type = inert_token(segment.raw_type or "")
    return item_type or "client_action"
```

The renderer must encode every raw name separately before `_painted_tools()` inserts its own commas. Do not use encoded labels as reducer identity.

- [x] **Step 6: Route the legacy action formatter through the shared seam**

Replace `format_client_actions()`'s immediate string-building loop with atomic projection, filtering, reduction and rendering:

```python
segments = tuple(
    segment
    for action in actions
    if (
        segment := _action_display_segment(
            action.requirement,
            action.type,
            action.name,
        )
    )
    is not None
)
return " ".join(
    _render_response_display_segment(segment, color=color)
    for segment in _coalesce_response_display_segments(segments)
)
```

Keep `format_terminal_status()` unchanged except for consuming the newly grouped string. `classification_complete` and status coloring remain independent of segment reduction.

- [x] **Step 7: Route the rich observation formatter through the typed pipeline**

Keep the existing source-protocol／availability gate and status/error/incomplete logic. Replace only the mutable `reason_run_kind`／`reason_run_count` loop with:

```python
segments = tuple(
    segment
    for item in items or ()
    if (segment := _response_display_segment(item)) is not None
)
parts.extend(
    _render_response_display_segment(segment, color=color)
    for segment in _coalesce_response_display_segments(segments)
)
```

Do not derive `has_client_action` from `segments`; retain the current scan of complete `items` so display selection cannot alter contextual `completed` coloring.

- [x] **Step 8: Re-run the direct reproduction**

Run the Step 1 command again.

Expected output suffix: `completed reason(enc:1) function_call(TaskCreate,Bash)`。

### Task 2: Synchronize unit and production-entry tests

**Files:**
- Modify: `tests/unit/observability/test_request_log.py:10-31`
- Modify: `tests/unit/observability/test_request_log.py:377-430`
- Modify: `tests/unit/observability/test_request_log.py:772-1264`
- Modify: `tests/int/test_pipeline_app.py:5396-5426`

**Interfaces:**
- Consumes: the private segment types/functions from Task 1 and unchanged public formatters。
- Produces: direct responsibility-level oracles plus the production-entry exact tail required by `spec.md` acceptance criterion 7。

- [x] **Step 1: Import the private seam for responsibility-level tests**

Add the private seam to the existing explicit import from `app.observability.request_log`, using the project’s per-symbol Pyright suppression:

```python
    _AnonymousAction,  # pyright: ignore[reportPrivateUsage]
    _NamedAction,  # pyright: ignore[reportPrivateUsage]
    _Reasoning,  # pyright: ignore[reportPrivateUsage]
    _UnknownAction,  # pyright: ignore[reportPrivateUsage]
    _action_display_segment,  # pyright: ignore[reportPrivateUsage]
    _coalesce_response_display_segments,  # pyright: ignore[reportPrivateUsage]
    _render_response_display_segment,  # pyright: ignore[reportPrivateUsage]
    _response_display_segment,  # pyright: ignore[reportPrivateUsage]
```

These imports intentionally make the new internal seam reviewable. They do not make it public API; the leading underscores remain, and no global Pyright rule is relaxed.

- [x] **Step 2: Add atomic projection tests**

Add one table-driven test that constructs real `OutputItemSummary` instances through `ResponsesObserver` and asserts the resulting segment for:

```python
("reasoning readable", _Reasoning("txt", 1))
("reasoning encrypted", _Reasoning("enc", 1))
("message", None)
("function_call Bash", _NamedAction("function_call", ("Bash",)))
("function_call anonymous", _AnonymousAction("function_call"))
("future_tool_call", _UnknownAction("future_tool_call"))
```

Keep expected segment values hand-written; do not call the production projector to build expected values.

Add one focused test for `_action_display_segment()` using legacy-shaped values to establish that `NOT_REQUIRED` returns `None`, `UNKNOWN + "unknown"` remains `_UnknownAction`, and `REQUIRED + empty name` becomes `_AnonymousAction`.

- [x] **Step 3: Add direct reducer tests**

Add `test_response_display_segments_coalesce_adjacent_named_actions` with hand-written segment tuples and complete tuple equality for these cases:

```python
(
    _NamedAction("function_call", ("Read",)),
    _NamedAction("function_call", ("Read",)),
    _NamedAction("function_call", ("Bash",)),
)
# => (_NamedAction("function_call", ("Read", "Read", "Bash")),)
```

```python
(
    _NamedAction("function_call", ("Read",)),
    _Reasoning("enc", 1),
    _NamedAction("function_call", ("Bash",)),
    _UnknownAction("future_tool_call"),
    _NamedAction("function_call", ("Read",)),
    _AnonymousAction("function_call"),
    _NamedAction("function_call", ("Bash",)),
)
```

The second tuple must remain unchanged except that adjacent same-kind `_Reasoning` inputs, when included, combine their counts. Add two distinct 121-character raw types that truncate to the same display label and assert they remain separate `_NamedAction` segments.

- [x] **Step 4: Restore grouped public rich-path oracles without changing durable identity assertions**

Rename and update the current regression tests:

- `test_observed_completed_is_green_only_for_a_known_action_free_output` covers both `output=[]` and nonempty `output=[{"type": "message"}]`; both must contain green `completed`, while the nonempty `NOT_REQUIRED` case contains no `client_action?`.
- `test_reasoning_before_repeated_tools_keeps_its_output_position` expects `completed reason(enc:1) function_call(Read,Read,Read,Read)`.
- `test_reasoning_and_tools_preserve_interleaved_visible_order` expects `completed reason(enc:1) function_call(Read,Bash) reason(txt:1) function_call(Read)`; the visible reasoning barrier case remains `function_call(Read) reason(enc:1) function_call(Bash)`.
- `test_responses_observation_preserves_adjacent_calls_without_deduplicating` becomes `test_responses_observation_groups_adjacent_calls_without_deduplicating` and expects `function_call(Read,Read,Read,Read)`.
- `test_responses_observation_preserves_actual_type_order_without_grouping` becomes `test_responses_observation_groups_only_adjacent_same_type_actions`; same-type run expects `custom_tool_call(exec) function_call(Read,Bash,Read)`, while interleaved different types stay separate.
- `test_invisible_non_client_items_do_not_remove_or_reorder_actions` expects `function_call(Read,Bash)` and keeps the full per-item fact assertion unchanged.
- `test_action_names_are_made_inert_before_rendering` expects `completed function_call(Read\\u002cnow,Bash\\u0029\\u001b)` and continues asserting raw delimiter／ANSI absence.
- `test_bounded_display_encoding_does_not_merge_distinct_raw_types` keeps its two-field expectation unchanged.
- Unknown／anonymous tests keep every barrier visible and separate.

Do not weaken `_assert_output_item_identity()` or `_assert_output_item_facts()`; those assertions prove display grouping did not mutate durable facts.

- [x] **Step 5: Add the user-reported names as a public regression example**

Add `test_user_reported_adjacent_function_calls_share_one_display_segment` with adjacent `function_call(TaskCreate)` and `function_call(Bash)` after visible encrypted reasoning. Assert the exact suffix:

```python
"completed reason(enc:1) function_call(TaskCreate,Bash)"
```

This test preserves the production incident's discriminating names without depending on the rest of the copied log line.

- [x] **Step 6: Synchronize legacy fallback tests**

Extend `test_completed_with_client_actions_keeps_status_and_types_uncoloured` to use two adjacent `function_call` actions followed by `custom_tool_call` and assert:

```python
f"completed function_call({DIM}Bash,Bash{RESET}) custom_tool_call({DIM}run_shell{RESET})"
```

Add a legacy barrier test containing named function action, unknown action, named function action, anonymous function action and named function action; assert unknown and anonymous stay visible and prevent cross-boundary grouping. Keep `completed` uncoloured whenever actions exist.

- [x] **Step 7: Update the existing production-entry integration oracle**

Change only `test_terminal_output_drives_both_action_list_and_completed_colour`'s exact suffix to:

```python
assert line.endswith(
    f"completed function_call({DIM}Bash,Bash{RESET}) custom_tool_call"
)
```

Keep terminal authority, reversed `done_order`, exact action multiplicity and non-green `completed` assertions intact. Do not add a new mock framework or a live upstream call.

- [x] **Step 8: Run targeted tests**

Run:

```bash
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
uv run pytest tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour
```

Expected: all selected tests pass; no assertion retains the old adjacent `function_call(X) function_call(Y)` oracle for same raw type.

### Task 3: Verify the implementation candidate

**Files:**
- Verify: `src/app/observability/request_log.py`
- Verify: `tests/unit/observability/test_request_log.py`
- Verify: `tests/int/test_pipeline_app.py`

**Interfaces:**
- Consumes: the implementation and tests from Tasks 1–2。
- Produces: targeted, static and full-suite evidence bound to the shared main worktree candidate before independent review。

- [x] **Step 1: Run focused static checks in the target root**

```bash
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
uv run ruff check src/app/observability/request_log.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py &&
uv run pyright src/app/observability/request_log.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py
```

Expected: Ruff clean; Pyright reports 0 errors for the selected files.

- [x] **Step 2: Run the project verification commands in the target root**

```bash
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
uv run ruff check src tests &&
uv run pyright src tests &&
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

Expected: all commands succeed. Do not run `ruff format`.

### Task 4: Review, commit, verify the failure mechanism, and synchronize living state

**Files:**
- Review: `src/app/observability/request_log.py`
- Review: `tests/unit/observability/test_request_log.py`
- Review: `tests/int/test_pipeline_app.py`
- Update: `.dev/docs/tui/spec.md`
- Update: `.dev/docs/tui/design.md`
- Update: `.dev/docs/tui/history/260906-function-call-grouping-structure-review-disposition.md`

**Interfaces:**
- Consumes: verified implementation candidate and all prior reports。
- Produces: independent review consensus, fresh verification for the final bytes, one semantic source/test commit, an isolated negative control, and living docs that state the implementation is synchronized。

- [x] **Step 1: Record candidate hashes and dispatch an independent code review**

Create a pre-review hash manifest in the current job’s own temp directory, with the target root bound in the same call:

```bash
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
: "${CLAUDE_JOB_DIR:?CLAUDE_JOB_DIR must be set}" &&
JOB_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR")" &&
TMP_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR/tmp")" &&
case "$TMP_ROOT/" in "$JOB_ROOT/"*) ;; *) printf '%s\n' 'job tmp escaped job root' >&2; exit 2 ;; esac &&
sha256sum \
  src/app/observability/request_log.py \
  tests/unit/observability/test_request_log.py \
  tests/int/test_pipeline_app.py \
  > "$TMP_ROOT/function-call-grouping.pre-review.sha256"
```

Review against `spec.md` acceptance criterion 7 and `design.md`. Require the reviewer to inspect the actual diff, typed segment invariants, rich／legacy adapters, contextual status independence and exact tests; report to a new file under `.dev/docs/tui/history/` and record every adopted or rejected finding in the disposition ledger.

- [x] **Step 2: Resolve findings and re-review only changed semantics**

Apply confirmed findings, record rejected suggestions with concrete reasons, and resume the same reviewer for a limited re-review. Stop when active blocker and major counts are both zero; do not repeat a full review over unchanged bytes.

- [x] **Step 3: Refresh verification when review changes source or tests**

Compare the three current files to the pre-review manifest. If all hashes still match, Task 3 evidence covers the final candidate and must not be rerun. If any source／test byte changed, rerun the affected targeted tests, focused Ruff and Pyright, then rerun the full project verification because the final candidate differs from the one Task 3 verified:

```bash
set -euo pipefail
cd /home/xp/src/ghc-api-proxy-py &&
test "$(pwd -P)" = "/home/xp/src/ghc-api-proxy-py" &&
: "${CLAUDE_JOB_DIR:?CLAUDE_JOB_DIR must be set}" &&
JOB_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR")" &&
TMP_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR/tmp")" &&
case "$TMP_ROOT/" in "$JOB_ROOT/"*) ;; *) printf '%s\n' 'job tmp escaped job root' >&2; exit 2 ;; esac
if sha256sum --check --status "$TMP_ROOT/function-call-grouping.pre-review.sha256"; then
    printf '%s\n' 'source and test bytes unchanged; reusing Task 3 verification'
else
    uv run pytest tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour &&
    uv run ruff check src/app/observability/request_log.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py &&
    uv run pyright src/app/observability/request_log.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py &&
    uv run ruff check src tests &&
    uv run pyright src tests &&
    uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
fi
```

Any verification failure keeps the task open. Do not commit until the exact post-review bytes pass the required branch above.

- [x] **Step 4: Freeze and inspect the candidate bytes**

In one standalone call, freeze the current parent and three worktree blob ids, produce diffs against that frozen parent without touching the shared index, then recheck the blobs after printing. The manifest created here is the candidate the human reviews; later steps may only verify it, never redefine it:

```bash
set -euo pipefail
ROOT="/home/xp/src/ghc-api-proxy-py"
: "${CLAUDE_JOB_DIR:?CLAUDE_JOB_DIR must be set}"
JOB_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR")"
TMP_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR/tmp")"
case "$TMP_ROOT/" in "$JOB_ROOT/"*) ;; *) printf '%s\n' 'job tmp escaped job root' >&2; exit 2 ;; esac
MESSAGE_FILE="$TMP_ROOT/function-call-grouping-commit-message.txt"
APPROVED_PARENT_FILE="$TMP_ROOT/function-call-grouping.approved-parent"
APPROVED_BLOBS_FILE="$TMP_ROOT/function-call-grouping.approved-blobs"
EXPECTED_PATHS_FILE="$TMP_ROOT/function-call-grouping.expected-paths"
BASELINE_ROOT="$(mktemp --directory "$TMP_ROOT/function-call-grouping-baseline.XXXXXX")"
printf '%s\n' 'fix: coalesce adjacent response actions in logs' > "$MESSAGE_FILE"
git -C "$ROOT" rev-parse HEAD > "$APPROVED_PARENT_FILE"
printf '%s\n' \
  'src/app/observability/request_log.py' \
  'tests/int/test_pipeline_app.py' \
  'tests/unit/observability/test_request_log.py' \
  > "$EXPECTED_PATHS_FILE"
: > "$APPROVED_BLOBS_FILE"
APPROVED_PARENT="$(<"$APPROVED_PARENT_FILE")"
while IFS= read -r PATHNAME
do
    printf '%s %s\n' \
      "$(git -C "$ROOT" hash-object "$ROOT/$PATHNAME")" \
      "$PATHNAME" \
      >> "$APPROVED_BLOBS_FILE"
    mkdir -p "$BASELINE_ROOT/$(dirname "$PATHNAME")"
    git -C "$ROOT" show "$APPROVED_PARENT:$PATHNAME" > "$BASELINE_ROOT/$PATHNAME"
    set +e
    git diff --no-index -- "$BASELINE_ROOT/$PATHNAME" "$ROOT/$PATHNAME"
    DIFF_RC=$?
    set -e
    if [ "$DIFF_RC" -gt 1 ]; then
        exit "$DIFF_RC"
    fi
done < "$EXPECTED_PATHS_FILE"
test "$(git -C "$ROOT" rev-parse HEAD)" = "$APPROVED_PARENT"
while read -r APPROVED_OID PATHNAME
do
    test "$(git -C "$ROOT" hash-object "$ROOT/$PATHNAME")" = "$APPROVED_OID"
    printf '%s %s\n' "$APPROVED_OID" "$PATHNAME"
done < "$APPROVED_BLOBS_FILE"
printf '%s\n' '=== shared staged paths ==='
git -C "$ROOT" diff --cached --name-status
```

Read the three diffs, approved blob lines and shared staged-name output before the next step. If another session owns an overlapping hunk or has staged unexpected content in the same target paths, stop and re-evaluate ownership. Unrelated staged entries may remain because the next step uses an exact pathspec commit. The baseline archive remains under the current job directory; no cleanup is needed.

- [x] **Step 5: Recheck and commit only the approved bytes**

After the standalone inspection has been accepted, reuse the parent, path set, message and blob manifest created by Step 4; this step must not regenerate or redefine any approved input. Recheck the frozen parent and every approved blob immediately before committing. After the pathspec commit, verify the actual candidate’s parent, subject, changed path set and three blob ids before writing the candidate pointer:

```bash
set -euo pipefail
ROOT="/home/xp/src/ghc-api-proxy-py"
: "${CLAUDE_JOB_DIR:?CLAUDE_JOB_DIR must be set}"
JOB_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR")"
TMP_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR/tmp")"
case "$TMP_ROOT/" in "$JOB_ROOT/"*) ;; *) printf '%s\n' 'job tmp escaped job root' >&2; exit 2 ;; esac
MESSAGE_FILE="$TMP_ROOT/function-call-grouping-commit-message.txt"
APPROVED_PARENT_FILE="$TMP_ROOT/function-call-grouping.approved-parent"
APPROVED_BLOBS_FILE="$TMP_ROOT/function-call-grouping.approved-blobs"
EXPECTED_PATHS_FILE="$TMP_ROOT/function-call-grouping.expected-paths"
ACTUAL_PATHS_FILE="$TMP_ROOT/function-call-grouping.actual-paths"
CANDIDATE_FILE="$TMP_ROOT/function-call-grouping.commit"
test -f "$MESSAGE_FILE"
test -f "$APPROVED_PARENT_FILE"
test -f "$APPROVED_BLOBS_FILE"
test -f "$EXPECTED_PATHS_FILE"
APPROVED_PARENT="$(<"$APPROVED_PARENT_FILE")"
test "$(git -C "$ROOT" rev-parse HEAD)" = "$APPROVED_PARENT"
while read -r APPROVED_OID PATHNAME
do
    test "$(git -C "$ROOT" hash-object "$ROOT/$PATHNAME")" = "$APPROVED_OID"
done < "$APPROVED_BLOBS_FILE"
git -C "$ROOT" commit -F "$MESSAGE_FILE" -- \
  src/app/observability/request_log.py \
  tests/unit/observability/test_request_log.py \
  tests/int/test_pipeline_app.py
CANDIDATE="$(git -C "$ROOT" rev-parse HEAD)"
test "$(git -C "$ROOT" rev-parse "$CANDIDATE^")" = "$APPROVED_PARENT"
test "$(git -C "$ROOT" show --no-patch --format=%s "$CANDIDATE")" = 'fix: coalesce adjacent response actions in logs'
git -C "$ROOT" diff-tree --no-commit-id --name-only -r "$CANDIDATE" | sort > "$ACTUAL_PATHS_FILE"
cmp --silent "$EXPECTED_PATHS_FILE" "$ACTUAL_PATHS_FILE"
while read -r APPROVED_OID PATHNAME
do
    test "$(git -C "$ROOT" rev-parse "$CANDIDATE:$PATHNAME")" = "$APPROVED_OID"
done < "$APPROVED_BLOBS_FILE"
printf '%s\n' "$CANDIDATE" > "$CANDIDATE_FILE"
git -C "$ROOT" show --stat --oneline --summary "$CANDIDATE"
```

The exact pathspec commit reads the three paths from the working tree and preserves unrelated staged entries. A peer write between the pre-check and commit is detected by the post-commit blob comparison; a peer commit between commit and `rev-parse` is detected by the parent／subject／path checks. On any mismatch, do not write or reuse the candidate pointer and do not proceed to mutation; preserve the commit and coordinate the attribution instead of rewriting history. Do not use `git add -A`, bare `git commit`, `--amend`, `restore`, `reset` or stash.

- [x] **Step 6: Run the named-action negative control in an isolated archive of the committed candidate**

Never mutate or restore the shared main worktree. Export the exact committed candidate into this job’s private temp directory, mutate only that copy, and run the three discriminating tests against the copied source:

```bash
set -euo pipefail
ROOT="/home/xp/src/ghc-api-proxy-py"
cd "$ROOT" &&
test "$(pwd -P)" = "$ROOT" &&
: "${CLAUDE_JOB_DIR:?CLAUDE_JOB_DIR must be set}"
JOB_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR")"
TMP_ROOT="$(realpath --canonicalize-missing -- "$CLAUDE_JOB_DIR/tmp")"
case "$TMP_ROOT/" in "$JOB_ROOT/"*) ;; *) printf '%s\n' 'job tmp escaped job root' >&2; exit 2 ;; esac
CANDIDATE_FILE="$TMP_ROOT/function-call-grouping.commit"
test -f "$CANDIDATE_FILE"
CANDIDATE="$(<"$CANDIDATE_FILE")"
git -C "$ROOT" cat-file -e "$CANDIDATE^{commit}"
MUTATION_ROOT="$(mktemp --directory "$TMP_ROOT/function-call-grouping-mutation.XXXXXX")"
MUTATION_OUTPUT="$MUTATION_ROOT/pytest-output.txt"
MAIN_SOURCE="$ROOT/src/app/observability/request_log.py"
MAIN_HASH_BEFORE="$(sha256sum "$MAIN_SOURCE")"
git -C "$ROOT" archive "$CANDIDATE" | tar --extract --directory="$MUTATION_ROOT"
test -x "$ROOT/.venv/bin/python"
python - "$MUTATION_ROOT/src/app/observability/request_log.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
needle = "            and previous.raw_type == segment.raw_type\n"
replacement = "            and False\n            and previous.raw_type == segment.raw_type\n"
if text.count(needle) != 1:
    raise SystemExit(f"expected exactly one merge condition, found {text.count(needle)}")
path.write_text(text.replace(needle, replacement))
PY
set +e
(
    cd "$MUTATION_ROOT" &&
    test "$(pwd -P)" = "$MUTATION_ROOT" &&
    PYTHONPATH="$MUTATION_ROOT/src" "$ROOT/.venv/bin/python" -m pytest \
      --quiet \
      --tb=short \
      --color=no \
      tests/unit/observability/test_request_log.py::test_response_display_segments_coalesce_adjacent_named_actions \
      tests/unit/observability/test_request_log.py::test_user_reported_adjacent_function_calls_share_one_display_segment \
      tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour
) > "$MUTATION_OUTPUT" 2>&1
MUTATION_RC=$?
set -e
if [ "$MUTATION_RC" -ne 1 ]; then
    printf 'expected pytest assertion-failure exit 1, got %s; output: %s\n' "$MUTATION_RC" "$MUTATION_OUTPUT" >&2
    exit 3
fi
if rg --fixed-strings --quiet 'ERROR' "$MUTATION_OUTPUT"; then
    printf 'negative control hit setup or collection ERROR; output: %s\n' "$MUTATION_OUTPUT" >&2
    exit 4
fi
if ! rg --regexp '^3 failed(?:,| in )' "$MUTATION_OUTPUT"; then
    printf 'expected exactly three failed tests; output: %s\n' "$MUTATION_OUTPUT" >&2
    exit 5
fi
for TEST_NAME in \
  test_response_display_segments_coalesce_adjacent_named_actions \
  test_user_reported_adjacent_function_calls_share_one_display_segment \
  test_terminal_output_drives_both_action_list_and_completed_colour
do
    if ! rg --fixed-strings --quiet "$TEST_NAME" "$MUTATION_OUTPUT"; then
        printf 'expected assertion failure missing from output: %s\n' "$TEST_NAME" >&2
        exit 6
    fi
done
MAIN_HASH_AFTER="$(sha256sum "$MAIN_SOURCE")"
test "$MAIN_HASH_AFTER" = "$MAIN_HASH_BEFORE"
printf 'negative control produced exactly three test failures at the action-grouping oracles; artifact: %s\n' "$MUTATION_ROOT"
```

Expected: pytest exits 1, reports exactly `3 failed`, contains all three test names and contains no `ERROR`; the shared main source hash is unchanged. Keep the archive under the job directory until session cleanup; no restore, delete or Git mutation is needed. If the negative control unexpectedly passes, reports setup／collection errors or fails at a different count, keep the task open and diagnose before claiming coverage.

- [x] **Step 7: Update living documentation after implementation**

Change `spec.md` and `design.md` status text from “production/tests 待同步” to the actual implemented state. Close the two original structure findings and all design／Spec／plan／code review findings in `260906-function-call-grouping-structure-review-disposition.md`, including the source commit and verification commands. Preserve review reports as point-in-time records; do not rewrite their original findings.

- [x] **Step 8: Persist `.dev` artifacts by the project’s dotdev workflow**

Use the project’s dedicated dotdev worktree and exact pathspecs for this task’s owned files only. If the documented dotdev synchronization procedure remains unavailable, keep the files in the main-root `.dev` working copy, report that persistence limitation explicitly and do not invent a bulk-copy workflow.

## 实施结果

- Production、unit 与 integration 三文件已作为语义单元提交，提交主题为 `fix: coalesce adjacent response actions in logs`。
- 实现采用计划中的 typed segments、shared action projector、pairwise reducer 与 renderer；没有修改 provider schema、classification、delivery policy 或其它 TUI 路径。
- Code review 首轮发现 nonempty `NOT_REQUIRED` output 的绿色 `completed` 判据不足；新增正向断言后，原收窄谓词 mutation 在目标断言判红，复评为 0 blocker／0 major。
- 最终新鲜 sanity check：用户示例输出 `function_call(TaskCreate,Bash)`；targeted 85 passed；Ruff clean；Pyright 0 errors。提交前第二次 full regression 为 2854 passed、2 skipped、coverage 91.77%；第一次 full run 曾在 `tests/unit/streaming/test_streaming_resilience.py` 出现一次失败，该测试立即单独重跑通过。
- 从已提交 candidate 导出的 job-private archive 中，仅禁用 named-action merge arm，三个目标 oracle 精确得到 `3 failed` 且无 setup／collection `ERROR`；共享主树 source hash 未变。
- `.dev` 当前缺少项目指令所称的同步说明文件，且同一文档树有并行 Chat 工作；本次不猜测 bulk-copy 或提交边界，所有文档保留在主根 `.dev` 工作副本并记录该限制，未删除、移动或推送任何材料。
