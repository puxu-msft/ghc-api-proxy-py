---
report_id: function-call-grouping-code-review-260906
attempt_id: function-call-grouping-code-review-260906-a1
status: in-review
reviewer_role: independent_code_reviewer
baseline_rev: 5995bbe0ac1885482e4976975c3b74d196cb7b11
candidate_main_head: 5995bbe0ac1885482e4976975c3b74d196cb7b11
reviewed_at_rev: "main-worktree@5995bbe0ac1885482e4976975c3b74d196cb7b11; request_log.py@sha256:1c59625ddabdeb1034acc853baf8cf60d65f75955de32770d536df3e91b02dda; test_request_log.py@sha256:ef435ba6d3ea85d4c064efc7dce04e07274339218a427a24da11885655e6e772; test_pipeline_app.py@sha256:7dfb9d17a3a8baa63cda9442dd8a036108757fb0db171d891e70d93797ede42d"
---

# Responses client-action grouping 独立代码评审

## 评审范围

本次只评审 baseline commit `5995bbe0ac1885482e4976975c3b74d196cb7b11` 与主工作树当前 bytes 之间以下三个文件的差异：

- `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py`
- `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py`

行为判据取自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的“描述回复的用词跟随上游”与验收第 7 条；结构判据取自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md` 的“Responses completion display projection”；逐项核查框架取自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/reports/260906-function-call-grouping-code-review-checklist.md` 的 C1～C8。schema、classification、delivery、Chat、Anthropic stop reason、pending tools 与 footer 的既有实现不在改动范围内，但其边界是否被此次改动越过属于 C7 的评审范围。

## 总体 verdict

`needs-fix`。Production implementation 的 grouping、typed segment、shared grammar 与 contextual status 逻辑均符合当前 Spec，但测试没有对 nonempty `NOT_REQUIRED` terminal output 的绿色 `completed` 建立可判否回归判据；默认 full suite 会接受相邻的错误实现。

## Blocker 数

0。另有 1 条 major finding。

## 候选身份与读取方式

- Baseline：`5995bbe0ac1885482e4976975c3b74d196cb7b11`，已作为 Git commit object 读取。
- 当前主工作树 HEAD：`5995bbe0ac1885482e4976975c3b74d196cb7b11`，由主工作树 `/home/xp/src/ghc-api-proxy-py/.git/HEAD` 指向 `refs/heads/main`，再读取该 loose ref 得到；因此候选改动当前未提交。
- Candidate `request_log.py` SHA-256：`1c59625ddabdeb1034acc853baf8cf60d65f75955de32770d536df3e91b02dda`；baseline blob SHA-256：`0fb27361e815e11bc59f11c953f64641a269297bed53fd5c5bb1296bfa2528df`。
- Candidate `test_request_log.py` SHA-256：`ef435ba6d3ea85d4c064efc7dce04e07274339218a427a24da11885655e6e772`；baseline blob SHA-256：`8740d0c000eb3ecc701cc14785eb7d3c41c32c48b31700e05fe2d5089dbc53b3`。
- Candidate `test_pipeline_app.py` SHA-256：`7dfb9d17a3a8baa63cda9442dd8a036108757fb0db171d891e70d93797ede42d`；baseline blob SHA-256：`24855da1bff6f2e99114b8e6267403acff0d7144f5ba443d7d9b77a02b22323e`。
- 判据快照：checklist SHA-256 `56490a3b467cfba89b3863caecdb4cde7da66c024c67dc68d79c237d6144cb62`；Spec SHA-256 `b3bf791e61d11ea6efd1d5ccf462bf968df31e1df39897b1a0a13f89dc630f2f`；design SHA-256 `30c4bb5c18f63c3363557a5ccc0674f68d973df1fa4ce7c9ada084a2a77a2150`。Typed segment 是 coordinator 在用户委托范围内作出的技术选择，不在本报告中误标为用户亲自裁决。
- 读取方式：先以绝对路径读取 checklist、Spec 与 design；再以绝对路径读取主工作树 production 文件、unit test 全文及 integration test 的实际变更区与所依赖 helper／production-entry 上下文。实际 diff 不是从隔离 worktree 的 working tree 取得：我在隔离 worktree 中以 `git show 5995bbe0ac1885482e4976975c3b74d196cb7b11:<path>` 读取三个 baseline blobs 到 `/tmp/function-call-grouping-code-review-260906-a1/`，随后用 GNU `diff --unified=40` 将这些 commit-object bytes 分别与上述三个主工作树绝对路径比较。

## C1～C8 核验

### C1：通过

`_response_display_segment()` 先把每个 item 投影成 typed atomic segment 或 `None`，`_coalesce_response_display_segments()` 只合并相邻、同 raw type 的 `_NamedAction`，并以 tuple concat 保留原始名称顺序与重复。不同 raw type、`_Reasoning`、`_UnknownAction` 与 `_AnonymousAction` 均落入 append 分支而形成 barrier；`NOT_REQUIRED` 且没有可见 reasoning 的 item 在 reducer 前被过滤，因此不制造 barrier。实现与 Spec 的可见性和相邻归约规则一致。

### C2：通过

Legacy `format_client_actions()` 与 rich `format_response_observation()` 均调用同一个 `_action_display_segment()`、`_coalesce_response_display_segments()` 与 `_render_response_display_segment()`；requirement→variant 映射没有复制。Legacy carrier 不具有 reasoning facts，候选没有伪造这类 segment，符合 design 明示边界。

### C3：通过

Reducer 的输入与输出均为 `_ResponseDisplaySegment` tuple；merge identity 比较 `previous.raw_type == segment.raw_type`，发生在 `inert_token()` 之前。Renderer 对 `raw_type` 和每个 `raw_name` 分别编码，再由 `_painted_tools()` 添加逗号和颜色。四个 presentation dataclass 均为 frozen／slots，归约只构造新 tuple，不回写 `ResponseObservation.output_items`；相关 public formatter tests 也分别核对 durable item identity／facts。

### C4：通过，但其一项正向测试义务计入 C6 的 major finding

Rich path 的 `clean_completed` 直接由 `items is not None` 与完整 items 上的 `REQUIRED`／`UNKNOWN` 存在性决定，未读取 segments、合并结果或渲染文本。`format_completion_line()` 的 `count_provider → rich observation → legacy terminal → stop reason → pending tools` precedence 不在 diff 中，候选未改变它。当前 production 谓词符合合同；缺的是 nonempty `NOT_REQUIRED` 正向颜色回归判据，见 `function-call-grouping-code-review-260906-01`。

### C5：通过

Reducer 只为 `_NamedAction + same raw_type` 与 `_Reasoning + same kind` 写了两个 merge arm，其余 variant 统一 append；因此当前 unknown／anonymous 与今后新增但未显式加入 merge arm 的 typed variant 默认是 barrier。新结构消除了旧的 reasoning accumulator／manual flush loop，没有重新引入第二个 pending accumulator。

### C6：不通过

Atomic projection、shared legacy projection、named-action reducer、各类 barrier、same-kind reasoning、raw-type collision、renderer encoding、`TaskCreate,Bash`、legacy grouping、durable facts 与 production-entry `function_call(Bash,Bash)`／non-green completed 均有相应断言；禁用 named-action merge arm 的 `/tmp` 单变量控制使所选 5 个 grouping／legacy／production assertions 全部目标变红。可是 nonempty `NOT_REQUIRED` 的 clean-completed 正向格没有颜色断言，且错误收窄谓词的变异令默认 full suite 保持全绿，故 C6 的整体声明不成立，详见 finding 01。

### C7：通过

Baseline 与 candidate 的实际三文件 diff 只在 `request_log.py` 增加 private presentation types／projection／reducer／renderer 并令两个既有 formatter 复用它，另两文件只调整或增加相关 tests。没有 schema、classification、delivery、Chat、Anthropic stop reason、pending tools 或 footer 改动；未发现吞错、未处理异常、不可达分支或新增 public API。Supporting producer 阅读确认 legacy `ClientAction` 仍只承载 required／unknown actions，candidate 没有改写其语义。

### C8：执行证据本身通过，但不能抵消 C6 的分辨力缺口

Checklist 中的 pre-review 数字没有冒充为本报告的运行结果。我在 candidate 三文件 hash 不变的主工作树独立复跑：targeted 为 `85 passed`；Ruff 为 `All checks passed!`；Pyright 为 `0 errors, 0 warnings, 0 informations`；default full suite 为 `2854 passed, 2 skipped`，coverage `91.77%`。这些数值与 checklist 一致。随后受控变异证明同一 full suite 仍会接受一项违反 contextual status 合同的实现，所以原始绿灯只能证明当前断言集合通过，不能证明 C6 声称的正反辨识面完整。

## Findings

### function-call-grouping-code-review-260906-01：非空但全为 `NOT_REQUIRED` 的 terminal output 缺少绿色 `completed` 回归判据

- `finding_id`：`function-call-grouping-code-review-260906-01`
- `severity`：major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py:696-718`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:5345-5359`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:437-470`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:131,146,218`
- 证据：现有 production 逻辑正确地用完整 `output_items` 中是否存在 `REQUIRED`／`UNKNOWN` 来决定 `completed` 是否着绿，但测试只对空数组断言绿色，对 nonempty `NOT_REQUIRED` 的 `message` integration case 以 `color=False` 运行。于是我在 `/tmp` overlay 中只把 `clean_completed = items is not None and not has_client_action` 变异为 `clean_completed = items is not None and not items`；该变异会把 `output=[{"type":"message"}]` 错误地保持为不着色，却仍使候选 targeted 集合的全部 85 tests 通过，另加的 overlay identity 正控也通过，总计 `86 passed`。默认 full suite 在同一变异下同样得到 `2855 passed, 2 skipped`，其中一项是 overlay identity 正控，因此项目自身仍为 `2854 passed, 2 skipped`。反向控制把同一表达式变异为 `clean_completed = items is not None`，targeted 命令得到 `2 failed, 84 passed`，失败恰落在 required／unknown 单元与 production-entry integration 的绿色断言，证明 overlay 确实被加载且测试能观察颜色，只是没有覆盖 nonempty `NOT_REQUIRED` 这一格。无需更宽的 mutation framework；这一对单变量控制已裁决目标命题。
- 影响：Spec 要求 `completed` 直接按完整集合中没有 required／unknown action 判绿，而不是按 output 是否为空判绿；当前测试集无法区分这两个相邻实现。一次把正确谓词收窄为“只有空 output 才 clean”的回归会让正常的 terminal `message`／server-side item 看起来仍需关注，同时 targeted suite 全绿；因此 C6 所称的 `complete not-required` 分辨力未成立。
- 建议：增加一个局部、启用 `color=True` 的断言，输入 nonempty 且分类为 `NOT_REQUIRED` 的完整 terminal output，例如单个 `message`，精确要求绿色 `completed` 且没有 `client_action?`；无需增加 mutation framework 或改动 schema。该断言可放在现有 rich observation formatter 单元，若要同时固定 production wiring，也可把既有 terminal-message integration case 改为着色并断言绿色 span。
- 证据强度：足以据此行动。受控变异只改变目标谓词，candidate 与 mutant 都从主工作树同一份 tests 运行；overlay identity test 排除了误载主树模块，反向控制排除了测试命令空转。它证明默认 full suite 对该回归失明；`tests/tui/` 按项目约定不在默认 sweep 中，本结论不外推到该手动测试组。

## 未采用建议

- 未建议改写 `ResponseObservation` schema、action classifier 或整个 TUI。现有 rich facts 已足够兑现本次 display contract，实际缺口只在回归 oracle；扩大生产范围没有事实依据，也违反本次边界。
- 未建议恢复双 accumulator 或引入通用 callback reducer。Typed pairwise reducer 已直接表达 merge 与 barrier 规则，现有受控变异也证明关键 merge arm 被当前 tests 命中。
- 未建议建立 mutation framework 或机械 gate。本次 `/tmp` 单变量 probes 是评审证据；修复只需一条能判否的局部颜色测试。
- 未把 legacy carrier 无法重建其未保存的 reasoning facts 报为缺陷。Design 明确限定该 carrier 不合成 reasoning；共享的是现有 client-action sequence 的 projection grammar，而不是虚构已丢失的 segment。

## 搜索面与验证

### 已读取和比对

- 按指定顺序读取 checklist、Spec、design，再读取主工作树三个 candidate 文件。`request_log.py` 与 unit test 全文已读；integration 文件因全文超过读取工具的 25,000-token 单次上限，读取了完整 86-line 实际 diff、`responses_observability_sse()`、`_logged_direct_responses()`、五组 terminal-output production-entry cases 及相邻 buffered Responses case。Supporting semantics 另读 `response_action.py` 的完整 classifier、`response_observation.py` 的 item schema／terminal authority／summarization 路径，以及 legacy `ClientAction` 定义与 producer。
- 三个 baseline blobs 均从指定 commit object 抽取；三个 candidate 均取自主工作树绝对路径。Diff context 分别为 393、698 与 86 行，没有以本 agent 的 isolation working tree 冒充 candidate。
- 扫描了整个 `tests/` 中对绿色 `completed` 的断言位置；没有发现 nonempty `NOT_REQUIRED` terminal output 的颜色 oracle。范围外的 `tests/tui/` 命中未作为本次三文件评审的验收证据。

### Candidate 运行结果

- `PYTHONDONTWRITEBYTECODE=1 uv run --directory /home/xp/src/ghc-api-proxy-py pytest --no-cov -p no:cacheprovider tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour`：`85 passed`。
- `uv run --directory /home/xp/src/ghc-api-proxy-py ruff check src tests`：`All checks passed!`。
- `uv run --directory /home/xp/src/ghc-api-proxy-py pyright src tests`：`0 errors, 0 warnings, 0 informations`。
- `COVERAGE_FILE=/tmp/function-call-grouping-code-review-260906-a1/.coverage PYTHONDONTWRITEBYTECODE=1 uv run --directory /home/xp/src/ghc-api-proxy-py pytest tests --cov=app --cov-report=term --cov-fail-under=80 -p no:cacheprovider`：`2854 passed, 2 skipped`，coverage `91.77%`，耗时 `273.12s`。唯一 warning 是 Starlette `BlockingPortal` alias deprecation，与本改动无关。

### 分辨力 controls

- 核心 grouping 正控：在独立 `/tmp` overlay 中只禁用 `_NamedAction` merge arm，overlay identity test 通过；reducer、用户报告的 `TaskCreate,Bash`、legacy colored grouping、legacy barrier grouping 与 production-entry exact tail 共 5 项全部按目标失败。
- Contextual-status 反向控制：在另一 `/tmp` overlay 中只把 clean predicate 放宽为任何 available output 都绿色，overlay identity test 通过；required／unknown 单元和 production-entry non-green assertion 共 2 项按目标失败。
- Contextual-status 缺口变异：在第三个 `/tmp` overlay 中只把 clean predicate 错误收窄为 output 必须为空；overlay identity test 通过，而 targeted project tests 仍 `85 passed`，默认 full project suite 仍 `2854 passed, 2 skipped`。该结果直接支撑 finding 01。

### 未覆盖面

未调用真实 Copilot upstream，也未运行默认 sweep 之外的 `tests/tui/`。本次命题是纯 display projection、已有 mock production wiring 与测试辨识力，不依赖真实 provider shape 或 PTY layout；因此这些未覆盖面不阻塞本评审，但本报告不把 mock 结果外推成真实 upstream 实况，也不把 default suite 外推成 TUI 手动组结果。CodeGraph 对主仓返回“未建立 `.codegraph/` index”，故 supporting-call-path 检查改用绝对路径 Read 与 `rg`。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-06T14:27:30+00:00`
- `finding_total: 1`
- `blocker_count: 0`
- `major_count: 1`

### 整体判定

`needs-fix`。当前 production implementation 本身符合本次 action grouping 与 contextual status 合同，且 candidate 的 targeted、full、Ruff、Pyright 均通过；但 C6 明示的 nonempty `NOT_REQUIRED` clean-completed 回归格缺失，单变量错误实现可穿过默认 full suite，因此进入下一阶段前应补上该局部判据。

### 我最没把握的三个判断

1. Finding 01 定为 major 而非 minor。把握度中高：当前 production 行为正确，缺陷只在 tests；但该格由 Spec 验收第 7 条明确要求，历史根因正是错误 oracle 把回归固化为新行为，而且本次实测默认 full suite 对相邻错误实现全绿，所以它属于关键长期维护义务未满足。
2. C5 对未来 typed variant 的默认 barrier 保证足够。把握度中等：现有 reducer 的最后一个 `else` 确实 append 所有未列入 merge arm 的 variant；若未来作者把新语义错误地塞进 `_NamedAction` 而非增加 variant，这项结构保证不会保护那次错误建模，但那不构成当前实现缺陷。
3. 没有通读 80,738-token integration 文件仍足以评审本次 integration 变化。把握度中高：完整 commit-object diff 显示该文件只有一个 86-line context hunk，且已读取该 hunk、fixture builder、production-entry helper、相邻五组控制和 supporting call path；不过本结论只覆盖本次三文件 diff，不声称对整个 integration module 做了普查。

### 执行本契约时遇到的摩擦

- Worktree isolation 拒绝直接对主工作树执行 `git -C` 和直接 `Write` 报告。为避免把 isolation working tree 冒充 candidate，我从共享 object database 的指定 commit 抽取 baseline blobs，再与主工作树绝对路径作 GNU diff；报告先写入 `/tmp/function-call-grouping-code-review-260906-a1/260906-function-call-grouping-code-review.md`，交付时按用户授权精确复制到固定 REPORT_FILE，且使用 no-clobber 语义避免覆盖既有尝试。
- CodeGraph 对 `/home/xp/src/ghc-api-proxy-py` 返回没有 `.codegraph/` index，改用绝对路径 Read 与 `rg`。
- `test_pipeline_app.py` 全文超过 Read 工具单次 25,000-token 上限，因此按完整实际 diff 定位并读取相关 helper 与生产入口窗口；覆盖边界已在“未覆盖面”中明示。

## 限域复评：finding 01

本段只复评 `function-call-grouping-code-review-260906-01` 的处置，不重开 C1～C8 全量评审。此前 `## 交付声明` 保留为首轮快照；以下最新段落与文件末尾的新交付声明取代首轮 verdict 和未关闭计数。

### 复评候选身份

- 当前主工作树 HEAD 仍为 `5995bbe0ac1885482e4976975c3b74d196cb7b11`。
- Production `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py` SHA-256 仍为 `1c59625ddabdeb1034acc853baf8cf60d65f75955de32770d536df3e91b02dda`；integration `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py` SHA-256 仍为 `7dfb9d17a3a8baa63cda9442dd8a036108757fb0db171d891e70d93797ede42d`。这两项与首轮完全相同，支持 coordinator 所述“production 未改”。
- 更新后的 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py` SHA-256 为 `1415dcd55586fc32d76be8676674a0c1d5f872a983adac3c3da463373ad2d056`；首轮候选 hash 为 `ef435ba6d3ea85d4c064efc7dce04e07274339218a427a24da11885655e6e772`。

### Finding 01 处置复核

`function-call-grouping-code-review-260906-01`：`closed`。

新增用例在 `test_observed_completed_is_green_only_for_a_known_action_free_output()` 内构造 nonempty terminal `output=[{"type":"message"}]`，经真实 `ResponsesObserver` 分类得到 `NOT_REQUIRED`，以 `color=True` 走 public `format_completion_line()`，并同时断言 `GREEN + completed + RESET` 存在且 `client_action?` 缺席。相邻 empty-output positive、missing-output negative、required／unknown negative 及 rich-over-legacy precedence tests 均保持原义。该补充正好区分“完整集合无 required／unknown”与“output 必须为空”，没有扩展 schema、production 或 TUI 范围。

### 独立复评证据

- 正确 candidate：`pytest` 精确运行 `test_observed_completed_is_green_only_for_a_known_action_free_output`、`test_observed_completed_with_required_or_unknown_actions_is_not_green` 与 `test_response_observation_precedes_legacy_terminal_and_unavailable_falls_back`，结果 `3 passed in 2.13s`。
- 原 finding 的单变量控制：继续使用 production hash 未变的 `/tmp/function-call-grouping-code-review-260906-a1/mutant-nonempty-not-required-not-green/src`，其中唯一语义变异仍为 `clean_completed = items is not None and not items`。同样三个 contextual tests 加 overlay identity test 的结果为 `1 failed, 3 passed`，唯一失败是新增断言所在的 `test_observed_completed_is_green_only_for_a_known_action_free_output` 第 728 行；错误值为 plain `completed`，预期为绿色 `completed`。两个相邻 contextual tests 与 overlay identity 正控均通过，故失败来自目标格而非错误装位或旁路破坏。
- 更新后的 unit test 文件执行 Ruff：`All checks passed!`；执行 Pyright：`0 errors, 0 warnings, 0 informations`。
- Coordinator 提供的 `3 passed` 仅作为待核声称收到；上述 `3 passed` 是本 reviewer 对当前 hash 独立执行所得，不冒充 coordinator 的证据。

### 复评结论

Finding 01 已被精确关闭，未发现新的 blocker／major；若存在仅属 minor 的可读性取舍，不在本次只报 blocker／major 的阈值内。最新 verdict 为 `pass`。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-06T14:32:07+00:00`
- `finding_total: 1`
- `open_finding_total: 0`
- `blocker_count: 0`
- `major_count: 0`
- `closed_major_count: 1`

### 整体判定

`pass`。首轮唯一 major finding 已由新增 nonempty `message`／`NOT_REQUIRED` 颜色断言关闭；正确 candidate 的三项 contextual tests 通过，原单变量错误实现由新增断言在目标处判红，production 与 integration bytes 未改变。

### 我最没把握的三个判断

1. 未重跑 full suite 是否足以给出本次限域 `pass`。把握度高：coordinator 明确要求不重开全量评审；修复只增加一组 unit assertions，production 与 integration hashes 未变，且正确／错误两侧的三项 targeted evidence 已闭合。本 verdict 只覆盖 finding 01 的复评，不替代首轮 full-suite 结果的时点边界。
2. 用一个原生 `message` 代表 nonempty `NOT_REQUIRED` 集合是否足够。把握度高：颜色谓词读取的是封闭三态 requirement，而不是 item type；`message` 经 production classifier 进入 `NOT_REQUIRED`，已经区分目标谓词与 `not items` 错误谓词。再枚举每个 server-side type 不增加该分支的辨识力。
3. `assert GREEN-completed in non_action_line` 而非整行 equality 是否会漏掉本 finding 的回归。把握度中高：该 finding 只要求 clean-completed 的颜色与 action marker 缺席，两条断言分别固定这两个属性；整行还含 HTTP status、subject 等不属本次变更的字段，改成整行 equality 只会扩大耦合。

### 执行本契约时遇到的摩擦

- Isolation 仍不允许直接 Edit 主工作树报告；本次先确认主树报告与 `/tmp` 作者副本逐字节相同，再在作者副本追加复评段，随后精确同步回固定 REPORT_FILE。
- 复用了首轮 `/tmp` mutant，而不是重新复制 production；这是有意的，且由 production SHA-256 在首轮与复评间保持 `1c59625ddabdeb1034acc853baf8cf60d65f75955de32770d536df3e91b02dda` 证明其基底未过期。

