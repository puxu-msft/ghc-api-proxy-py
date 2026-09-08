# Task 3A Implementation Report

## 1．执行身份、权威与基线

Physical worktree：

`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd`

Branch：

`worktree-agent-a2cd3b8776da8ebfd`

Initial HEAD：

`e4edc6ebebb91427654c8ce86f88b6c9b57bbd08`

Exact integration base：

`a2779b644844dcf6cc36454c12b85f4e9f09c2e8`

Final implementation commit：

`56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`

Commit subject：

`feat: preserve token prediction candidates`

第一条复合 Bash 调用在执行前被 managed-worktree isolation guard 拒绝，因为 guard 无法验证带变量和 `git -C` 的复合命令是否仍位于本 worktree。该调用没有执行任何 shell 命令，也没有改变 repository。随后第一条实际执行的工作命令为：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
```

输出：

```text
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd
worktree-agent-a2cd3b8776da8ebfd
e4edc6ebebb91427654c8ce86f88b6c9b57bbd08
```

Initial HEAD ancestry 检查命令：

```bash
git merge-base --is-ancestor e4edc6ebebb91427654c8ce86f88b6c9b57bbd08 a2779b644844dcf6cc36454c12b85f4e9f09c2e8
```

结果：exit 0，无输出，证明 initial HEAD 是 exact base 的祖先。

建立 exact base 的唯一历史操作：

```bash
git merge --ff-only a2779b644844dcf6cc36454c12b85f4e9f09c2e8
```

结果：

```text
Updating e4edc6e..a2779b6
Fast-forward
```

随后执行：

```bash
git rev-parse HEAD
```

输出：

```text
a2779b644844dcf6cc36454c12b85f4e9f09c2e8
```

没有执行 `rebase`、`cherry-pick`、`reset`、shared-main 修改、merge-back 或 push。

## 2．Authority SHA-256 核验

执行：

```bash
sha256sum /home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md
```

输出：

```text
6f98acb6138451fdb4c08031075f274d0d2921244998dc446e81bad2e63dfed2  /home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md
2644ad9a44a9b0b06f072513dfb82834f8512f5b3fc6272a435b45a8a8445834  /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md
```

执行：

```bash
sha256sum /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md
```

输出：

```text
ab7da5a2f0c5c292824ec14f52fbc5657c91fabf5f264428a493042821e3ab68  /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md
```

三项均逐字匹配 dispatch 中给定的 expected SHA-256，因此没有触发 moving-authority stop。

补充：brief 正文第 9～10 行仍转录了较早的 Spec／plan SHA，但本次 dispatch 明确给出了新的 expected hashes，且实际文件与 dispatch 给定值一致。实现以本次用户 dispatch 指定的 current authority 为准，没有把 brief 内旧转录误判为 moving authority。

## 3．Exact changed paths

Final commit 恰好包含以下十个 owned tracked paths：

```text
src/app/tokenization/estimators.py
src/app/tokenization/features.py
src/app/tokenization/learning_schema.py
src/app/tokenization/learning_store.py
src/app/tokenization/types.py
src/app/tokenization/worker.py
tests/unit/tokenization/test_features.py
tests/unit/tokenization/test_learning_store.py
tests/unit/tokenization/test_local_token_worker.py
tests/unit/tokenization/test_responses_estimator.py
```

未修改：

```text
.dev/
.superpowers/
docs/.human-controlled/
uv.lock
src/app/tokenization/prediction.py
pipeline／driver／learning service
shared main
```

Worktree 中有一个 untracked `.dev` symlink：

```text
.dev -> /home/xp/src/ghc-api-proxy-py/.dev
```

它由 managed worktree 环境提供，本任务没有创建、改写、暂存或提交该路径。

## 4．实现逐项 mapping

### 4.1 Candidate identity 与 represented-method cardinality

`src/app/tokenization/types.py`：

- 保持 `PredictionMethod` 恰有原四成员及既有顺序：`history-exact`、`history-prefix`、`profile-calibrated`、`cold-start`。
- 新增 closed `PredictionCandidateVariant`，恰有 `median`、`deterministic`、`additive`、`multiplicative`。
- 新增 frozen／slotted `PredictionCandidateKey(method, variant)`，constructor 只接受七种 V1 legal pair。
- 新增 frozen／slotted `MethodChampion(candidate_key, eligible_for_selection)`；method 由 `candidate_key.method` 派生，没有第二个可矛盾 method 字段。
- `MethodChampion` constructor 拒绝非 closed candidate key、非 bool eligibility，以及 exact／cold-start false eligibility。
- `TokenPrediction` 保留兼容 `method` 字段，新增 required `candidate_key`，constructor 验证 `method is candidate_key.method`。
- `PredictionRecord` 改为保存 `sample_key`、`selected_key`、`candidates`、`method_champions`；`selected` 改为由 `selected_key` 唯一查找的 property。
- `PredictionRecord` 验证 candidate-key unique、cold-start candidate 必存、所有 candidate 共用 identity／profile／generation／schema revision／epoch／history revision。
- represented methods 由 candidates 实际存在的方法集合决定；champions 必须恰好覆盖 represented methods，拒绝 represented missing champion、duplicate champion、absent-method extra champion。
- champion key 必须存在于 candidates；global selected key 必须等于按 `PredictionMethod` 顺序遇到的第一个 eligible represented champion。
- Cold-only record 合法；prefix／profile champion false 合法；exact／cold false 非法。
- `PredictionEvaluation` 新增完整 `candidate_key` 并交叉验证兼容 `method`。
- `LearningSnapshot` evaluation uniqueness 从 `(sample_key, method)` 改为 `(sample_key, candidate_key)`。
- `LearningUpdate` 对账从 method-keyed mapping 改为 candidate-keyed mapping，same-method variants 不再互相覆盖。
- `TokenLearningObservation` 沿用 evaluation tuple，但其 evaluation DTO 现在完整携带 candidate key。

对应 tests：

- 七种合法 pair 全部逐项构造成功，所有非法 method／variant 笛卡尔组合逐项拒绝。
- same-method prefix deterministic／additive 同时存在并保持不同 key。
- duplicate candidate key、missing／duplicate／extra champion、missing champion candidate、selected 非首 eligible、selected noneligible、exact false、cold false 均有直接负控。
- Cold-only record 与 demoted prefix＋eligible cold record 均有正控。

### 4.2 Ephemeral `PredictionDecision`

`src/app/tokenization/types.py`：

- 新增 frozen／slotted `PredictionDecision(prediction, anchor_use_intent)`。
- `history-exact` decision 强制 `AnchorKind.EXACT` intent。
- `history-prefix` decision 强制 `AnchorKind.PREFIX` intent。
- `profile-calibrated` 与 `cold-start` 强制 intent 缺席。
- intent identity 与 epoch 必须匹配 prediction；intent 自身继续拥有 fingerprint、source keys、identity 与 epoch 的既有验证。
- `PredictionDecision` 没有加入 `PredictionRecord`、candidate codec、event codec、SQLite DDL 或 learning observation。

对应 tests：

- exact／prefix 正例。
- missing intent、wrong kind、wrong identity、wrong epoch identity、profile unexpected intent、cold unexpected intent 负例。
- candidate JSON、event evaluation JSON 与 SQLite DDL exact-field oracle 均断言没有 intent 字段。
- `record_anchor_use(intent)` 的既有 store 测试保持通过。

### 4.3 Presence-aware visual capability seam

`src/app/tokenization/types.py`：

- `EstimateFeatures` 新增 required `capability_visual_tokens: int | None`。
- Constructor 区分 `None` 与真实 0，并拒绝 bool、negative、float／其它非 int。
- 新增 closed `VisualTokenFormulaKind.SYNTHETIC_UNRESIZED_PATCH_GRID_V1`。
- 新增 frozen／slotted `SyntheticUnresizedPatchGridFormula`，携带 positive `revision`、`patch_width`、`patch_height`。
- 新增 frozen／slotted `TokenizationCapabilities`，只接受当前 closed synthetic formula union。
- Capability DTO 与 formula 经 pickle round-trip 保持对象相等。

`src/app/tokenization/features.py`：

- `ESTIMATOR_GENERATION` 从 1 增加到 2。
- `PROFILE_SCHEMA_REVISION` 保持 1。
- `analyze_responses_input(payload, *, capabilities=None, timings=None)` 接受 capability snapshot。
- Analyzer 在 classification 时保留逐 media item 对象，不从 aggregate pixels 回推 visual。
- 无 media 时 `capability_visual_tokens == 0`。
- 有 media 且 capability／formula 缺席时为 `None`。
- 任一 media 不是首版支持的 image，或任一 width／height 缺席时为 `None`。
- 全部 image metadata 完整时逐项计算 `ceil(width / patch_width) * ceil(height / patch_height)` 后求和。
- 成功应用 formula 时只移除 `zero-prior:media-without-capability-formula`；opaque／unknown reasons 保留。
- Visual 不进入 `known_tokens`、components 或 `FeatureVector`。
- A18 stub arithmetic 得到 known 29、visual 6、future cold input 35。
- 56×84 与 42×112 均为 4,704 aggregate pixels，但 visual 分别为 6 与 8。

`src/app/tokenization/estimators.py`：

- Legacy `estimate_responses_input()` 可接收 optional capabilities，但仍只返回 `max(known_tokens, 1)`；没有提前消费 visual slot改变公开 integer contract。

`src/app/tokenization/worker.py`：

- Structured `analyze_responses()` 可传 pickle-safe capabilities 到 process worker。
- 旧 caller 不传 capabilities 时仍走原两 positional arguments 形态，兼容既有 monkeypatched worker fixtures。
- Worker structured result 保留 visual 6 并通过 pickle round-trip。

没有把 synthetic formula 接到 production model catalog，没有猜测 resize limit、PDF formula 或 provider-specific values。

### 4.4 V1 persistence 与 graph

`src/app/tokenization/learning_schema.py`：

- `samples` 新增 nullable `capability_visual_tokens INTEGER CHECK (capability_visual_tokens IS NULL OR capability_visual_tokens >= 0)`。
- `prediction_records` 新增 `selected_variant` 与 `method_champions_json`。
- `candidates_json` 每项新增 required `variant`。
- `evaluations` 新增 required `candidate_variant`。
- Evaluation PK 改为 sample owner＋method＋candidate variant。
- Evaluation `CHECK` 只允许 Spec §6.0 的七种 method／variant pair。
- `evaluations_window` index 加入 `candidate_variant`。
- 更新 table manifests、column／PK／CHECK／index literals、三个受影响 table 的 fixed normalized DDL digests及 overall manifest digest。
- Schema version 仍为 V1；没有新增 migration version。

`src/app/tokenization/learning_store.py`：

- Sample insert／select／decode 严格保持 visual `NULL`、0、6。
- Candidate encoder／decoder要求 exact keys，并 encode／decode method＋variant。
- Champion encoder按 `PredictionMethod` 顺序 canonical encode；decoder要求 exact keys、closed method／variant、canonical method order，并复用 DTO cardinality／eligibility invariants。
- Prediction record insert／read保存 selected method＋variant、history revision、champions JSON 与 candidates JSON。
- Evaluation insert／read／delete使用完整 candidate key。
- Event evaluation JSON加入 variant；decoder exact-key 校验完整 candidate key。
- Derived graph reconstruction、persisted-row matching、event matching、mandatory newest diagnostic windows全部由 candidate key 标识。
- Diagnostic retention window key改为 identity／epoch／profile hash／candidate key；same-method variants各自拥有独立 budget。
- Prune plan 与 evaluation delete 使用 method＋variant，不再按 method 一次删除全部 variants。
- Public snapshot evaluation uniqueness及 projection保持 candidate-key facts。
- `PredictionDecision`／intent没有进入 durable codec 或 schema。
- Existing cancellation、migration、revision-before-delete、prune ties、thread provenance、active snapshot contracts均未改。
- `_ACTION_BASE_SHAPES` 未增删；实测保持 108 semantic bases、204 expanded IDs。
- 没有新增或绕过 raw `aiosqlite` call site。

### 4.5 Independent persistence tests

`tests/unit/tokenization/test_learning_store.py`：

- 独立 schema literals加入 visual column／CHECK、selected variant、champions JSON、candidate variant、evaluation PK／pair CHECK／index。
- Fixed expected table DDL digests与 overall manifest digest为 test-owned literals。
- Visual `None`／0／6 分别执行 SQLite round-trip并断言 `typeof` 为 `null`／`integer`。
- Independent SQL corruption验证 negative visual 与 blob storage type被拒。
- Multi-variant transition同时持久化 prefix deterministic、prefix additive 与 cold deterministic，并为每个 candidate key保存 evaluation。
- Round-trip逐项核 selected key、candidate keys、method champions、event evaluation keys。
- Raw corruption覆盖 selected key、cold false champion、illegal candidate key、illegal persisted evaluation key与illegal event evaluation key；startup均为 `INVALID_STATE` 且原 DB bytes不变。
- 用 diagnostic limit 2 的正控证明三个 candidate keys各保留 2 rows；两个 same-method prefix variants不是共享 method-level budget。
- 既有 A32-P／A32-S／A35／A37／A38／A39、fresh migration、bounds、prune、event、action-ID、thread provenance tests全部继续通过。

等待确认后续 PART 2/3：完整 verification commands、环境绑定、counts 与结果。

# 5．Verification environment 与命令绑定

所有承重 pytest／Ruff／Pyright 命令均从 physical worktree：

`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd`

执行，并在同一次 Bash 调用中重新打印：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
```

每次均执行 ancestry assertion：

```bash
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
```

每次 Python／pytest／Pyright 命令均设置：

```bash
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src
```

Python、pytest、Ruff、Pyright 均直接取自 brief 指定的已验证 Task 3 venv：

```text
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv
```

环境版本由 pytest／brief记录为：

```text
Python 3.14.2
Ruff 0.16.6
Pyright 1.1.411
```

没有运行 `uv sync`、`uv lock` 或任何会生成／修改 `uv.lock` 的命令。没有运行 `ruff format`。

承重命令在 commit 前输出 exact base：

```text
a2779b644844dcf6cc36454c12b85f4e9f09c2e8
```

Post-commit store verification 输出 final commit：

```text
56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
```

因此 import path、physical cwd、Git top-level与被测 source tree均指向本 isolated worktree，没有从 shared main import。

# 6．Development compile 与 schema probes

## 6.1 Production module compile

执行：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m py_compile src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py
```

结果：exit 0，无输出。

## 6.2 Revised normalized table-DDL digest probe

执行：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
import hashlib
from app.tokenization.learning_schema import CREATE_TABLE_STATEMENTS
from app.tokenization.learning_store import _normalize_ddl_v1
for statement in CREATE_TABLE_STATEMENTS:
    normalized = _normalize_ddl_v1(statement)
    name = normalized.split('create table ', 1)[1].split(' ', 1)[0]
    print(name, hashlib.sha256(normalized.encode('utf-8')).hexdigest())
PY
```

输出：

```text
schema_meta 7f9e205943982384c03ec5ed3ca70b5120dc14868ea101d4803380380ec7adc0
identity_state acddf5655f3fb5784515ef57e6744f42853178b00e680d2c720840b0a8bc523c
epoch_state 6a69ca401c1a815fdcdbccf3840fd4feaff2929989823f9f1caacb18370f47ce
samples af25963a93043ead8476c730bc77070d0f3375afb91c73242f9167bcbea1202c
prediction_records b4ab4b923a7958a6cd089bcef5401e792f7e7b25ccc5b62a994eefd8be717d00
evaluations bfb7fda5d6b2d25c800f10224445d66b6ddec4203903a8db83c14dfb54093beb
exact_anchors 0f54940dc321b3b004c8195b8123fa0554d8dbdfc0be6364dbbe604b4cd24608
prefix_anchors b30d1052145729f0253cee767869b4ae45e08042c86336acf05ea173328527d1
learning_events 32da83245973a5659d767ac94056d28ececb4783fc6bda8cba13fe732c5868ef
```

这一步用于固定受影响的 `samples`、`prediction_records`、`evaluations` 三个 DDL digest literals；其它表 digest保持不变。Test-side expected digests随后作为独立 literals转录，没有由 actual DB introspection反向生成。

## 6.3 Revised overall manifest digest probe

执行：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from app.tokenization.learning_schema import SCHEMA_MANIFEST_DIGEST
print(SCHEMA_MANIFEST_DIGEST)
PY
```

输出：

```text
e6dc46757fc9d729ca3cabcec43e4de2eb9c251ce3bee7a2635aebe5ea47ca1b
```

## 6.4 Confirmed-action cardinality probe

执行：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from app.tokenization.learning_store import CONFIRMED_ACTION_IDS, _ACTION_BASE_SHAPES
print(f'action_bases={len(_ACTION_BASE_SHAPES)} action_ids={len(CONFIRMED_ACTION_IDS)}')
PY
```

输出：

```text
action_bases=108 action_ids=204
```

# 7．Pytest verification commands、counts 与 results

以下包含开发过程中暴露转录缺口的红跑，以及修正后的最终绿跑。红跑没有被计作通过证据。

## 7.1 Initial DTO／feature compatibility run

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py --maxfail=20
```

结果：

```text
collected 44 items
44 passed in 0.92s
```

这是 production DTO 初步改造后、Task 3A新增完整 discrimination tests之前的兼容性检查，不冒充最终 focused count。

## 7.2 Initial complete store run，暴露三处旧 raw fixture transcription

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py --maxfail=20
```

结果：

```text
collected 357 items
354 passed
3 failed
```

三个失败：

```text
test_complete_derived_graph_rejects_each_single_corruption[evaluation-extra-1]
test_newest_128_diagnostics_and_160_record_reconstruction_are_independent
test_composite_relations_reject_cross_identity_epoch_and_partial_event_links
```

根因均为测试中独立 raw SQL fixtures仍按旧 V1 schema构造，分别缺失 `candidate_variant`、`selected_variant`／`method_champions_json`，或按旧 column count执行 `INSERT ... VALUES`。Production store 主路径在同一轮已有大量用例通过；这些 failures被归为本 Task DTO／schema变更造成的 contract transcription failures，并仅修改 owned `test_learning_store.py`。

## 7.3 Corrected raw fixture selector run，暴露最后一个 extra-evaluation旧转录

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k 'complete_derived_graph or newest_128 or composite_relations' --maxfail=10
```

结果：

```text
collected 357 items / 345 deselected / 12 selected
11 passed
1 failed
```

剩余失败：

```text
test_newest_128_diagnostics_and_160_record_reconstruction_are_independent
sqlite3.IntegrityError: NOT NULL constraint failed: evaluations.candidate_variant
```

原因是该用例后段的 independent extra-evaluation corruption fixture还有一处旧 `INSERT` 缺少 candidate variant。补齐为合法但 record 中不存在的 `history-exact/median` extra row后，该用例继续验证 graph validator，而不是被基础 NOT NULL constraint提前截断。

## 7.4 Task 3A focused DTO／feature／worker／store selectors

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py -k 'prediction_candidate or prediction_record_preserves or prediction_decision or a18_visual or capability_visual or candidate_keys_champions or diagnostic_retention_budget or legacy_integer_wrapper or pickle_safe_structured' --maxfail=20
```

结果：

```text
collected 436 items / 425 deselected / 11 selected
11 passed in 8.03s
```

Selectors覆盖：

```text
closed candidate pairs
same-method variants
represented-method champions
PredictionDecision
A18 known／visual arithmetic
visual presence
worker capability pickle path
legacy wrapper non-consumption
candidate-key persistence
per-candidate diagnostic budget
```

## 7.5 Expanded feature／DTO file

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py --maxfail=10
```

结果：

```text
collected 48 items
48 passed in 0.94s
```

## 7.6 Task 3A store selectors after raw fixture corrections

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k 'capability_visual or candidate_keys_champions or diagnostic_retention_budget or newest_128' --maxfail=10
```

结果：

```text
collected 362 items / 356 deselected / 6 selected
6 passed in 3.51s
```

## 7.7 Complete store run before最后一组 corruption／encoder exact-key tests

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py --maxfail=20
```

结果：

```text
collected 367 items
367 passed in 94.74s
```

此后新增 direct candidate encoder exact-key test及五个 raw candidate-key graph corruption参数实例，因此本次结果不是最终 store count；最终 count见 §7.9。

## 7.8 Complete tokenization unit group

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/ --maxfail=20
```

结果：

```text
collected 533 items
533 passed in 173.31s
```

该命令覆盖最终 source bytes与当时完整 `tests/unit/tokenization/test_learning_store.py`，不含独立 TUI group。它在 commit 前执行；commit只记录同一份已经验证的 index／working-tree bytes，没有在 commit 后修改 source。

## 7.9 Post-commit complete learning-store verification

Commit完成后执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py
```

身份输出：

```text
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd
worktree-agent-a2cd3b8776da8ebfd
56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
```

结果：

```text
collected 368 items
368 passed in 85.20s
```

这是 final commit上完整、最终的 store count。

# 8．Ruff commands 与 results

## 8.1 First changed-path Ruff run

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
```

结果：exit 1，发现 3 个 `I001`，均为新增 type imports的顺序：

```text
src/app/tokenization/learning_store.py:1:1 I001
tests/unit/tokenization/test_features.py:1:1 I001
tests/unit/tokenization/test_learning_store.py:1:1 I001
Found 3 errors.
```

没有其它 Ruff finding。Import order以手工 exact edits修正，没有运行 `ruff check --fix`，更没有运行 `ruff format`。

## 8.2 Concise Ruff diagnosis

执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check --output-format concise src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
```

结果：exit 1，仍恰为上述 3 个 `I001`。

随后为读取单文件建议执行：

```bash
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check tests/unit/tokenization/test_features.py
```

结果：exit 1，恰有 1 个 `I001`；建议把 `TokenizationCapabilities` 排到 `TokenLearningObservation`之前。按建议手工调整后重新执行 concise Ruff：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check --output-format concise src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
```

结果：

```text
All checks passed!
```

## 8.3 Final load-bearing changed-path Ruff run

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
```

结果：

```text
All checks passed!
```

# 9．Pyright commands 与 results

## 9.1 First full `src tests` Pyright run

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/pyright src tests --pythonpath /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python
```

结果：exit 1，`4 errors, 0 warnings, 0 informations`。

四项：

```text
src/app/tokenization/features.py:243:5
media_items default factory type partially unknown

src/app/tokenization/worker.py:71:24
variadic tuple arguments could not be assigned to run_sync positional signature

tests/unit/tokenization/test_features.py:1133:51
monkeypatch lambda argument type partially unknown

tests/unit/tokenization/test_features.py:1133:58
lambda parameter _name type unknown
```

处置：

- 新增 typed `_empty_media_items()` factory。
- Worker把 capabilities absent／present分成两个显式 `run_sync` branches，保留旧双参数测试 seam并让三参数路径静态可判。
- 把 monkeypatch lambda改成具名、带 `str` 参数与 exact return type的 `stub_encoding()`。

## 9.2 Second full `src tests` Pyright run

执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/pyright src tests --pythonpath /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## 9.3 Final full `src tests` Pyright run

在所有 mutation恢复、最终 tests与手工 import ordering完成后再次执行：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/pyright src tests --pythonpath /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

# 10．Verification summary

最终承重绿证据：

```text
Task 3A focused selectors：11 passed
Expanded test_features.py：48 passed
Final committed test_learning_store.py：368 passed
Complete tests/unit/tokenization/：533 passed
Ruff changed paths：All checks passed
Pyright src tests：0 errors, 0 warnings, 0 informations
Confirmed action registry：108 bases／204 IDs
```

证据边界：

- Synthetic DTO／feature／SQLite tests证明本项目的 candidate cardinality、visual presence／arithmetic、codec、schema与graph行为。
- 它们不证明 real provider vision formula、real upstream billing accuracy或 production pipeline wiring。
- 本 slice没有实现 Task 4A predictor，也没有把 synthetic visual formula接到 production catalog。

等待确认后续 PART 3/3：六个 mutation 的精确注入命令、目标失败、snapshot恢复、超时 background停止与无残留证据、commit命令、最终 tree、未执行项、concerns及被否路线。

# 11．Mutation controls

六轮 mutation 均以 production／test source当前正确版本作 snapshot，mutation test前台启动，目标不变量变红后从 snapshot恢复。恢复命令均包含 `cmp` 与 `git diff --check`；`git diff --stat` 输出的是本 Task相对 exact base的预期工作 diff，不是 mutation残留。

## 11.1 Mutation 1：按 method collapse same-method candidates

### Snapshot 与注入命令

```bash
cp src/app/tokenization/types.py /tmp/task3a-mutation1-types.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/types.py')
text = path.read_text()
old = 'candidate_keys = tuple(candidate.candidate_key for candidate in self.candidates)'
new = 'candidate_keys = tuple(candidate.method for candidate in self.candidates)'
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
```

Mutation精确改变：

```python
candidate_keys = tuple(candidate.candidate_key for candidate in self.candidates)
```

变为：

```python
candidate_keys = tuple(candidate.method for candidate in self.candidates)
```

因此同一 `history-prefix` method的 deterministic与additive candidates被错误折叠。

### 承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py -k prediction_record_preserves
```

结果：

```text
collected 48 items / 47 deselected / 1 selected
1 failed
```

目标失败：

```text
test_prediction_record_preserves_variants_champions_and_selection_cardinality
ValueError: prediction candidates must have unique candidate keys
```

失败发生在构造原本合法的 prefix deterministic＋prefix additive＋cold record时，证明该 test能判否 method-level collapse，不是因 fixture parsing或旁路断言而红。

### 恢复命令与证据

```bash
cp /tmp/task3a-mutation1-types.py src/app/tokenization/types.py
cmp /tmp/task3a-mutation1-types.py src/app/tokenization/types.py
git diff --check -- src/app/tokenization/types.py
git diff --stat -- src/app/tokenization/types.py
```

结果：

- `cmp` exit 0，无输出。
- `git diff --check` exit 0，无输出。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/types.py | 200 +++++++++++++++++++++++++++++++++++++-----
1 file changed, 177 insertions(+), 23 deletions(-)
```

## 11.2 Mutation 2：删除 exact／cold unconditional eligibility validator

### Snapshot 与注入命令

```bash
cp src/app/tokenization/types.py /tmp/task3a-mutation2-types.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/types.py')
text = path.read_text()
old = '''        if (
            self.candidate_key.method in {PredictionMethod.HISTORY_EXACT, PredictionMethod.COLD_START}
            and not self.eligible_for_selection
        ):
            raise ValueError("represented exact and cold-start champions must be eligible")
'''
assert text.count(old) == 1
path.write_text(text.replace(old, ''))
PY
```

Mutation删除 `MethodChampion.__post_init__()` 中 exact／cold false的无条件拒绝。

### 承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py -k prediction_record_preserves
```

结果：

```text
collected 48 items / 47 deselected / 1 selected
1 failed
```

目标失败：

```text
test_prediction_record_preserves_variants_champions_and_selection_cardinality
Failed: DID NOT RAISE ValueError
```

具体在：

```python
with pytest.raises(ValueError, match="must be eligible"):
    MethodChampion(cold.candidate_key, False)
```

处未抛异常。该用例在此前所有 cardinality与selection checks仍通过后，精确失败于 cold false guard；同一 test紧邻还有 exact false guard，因此 mutation击中了 brief要求的 unconditional eligibility invariant。

### 恢复命令与证据

```bash
cp /tmp/task3a-mutation2-types.py src/app/tokenization/types.py
cmp /tmp/task3a-mutation2-types.py src/app/tokenization/types.py
git diff --check -- src/app/tokenization/types.py
git diff --stat -- src/app/tokenization/types.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/types.py | 200 +++++++++++++++++++++++++++++++++++++-----
1 file changed, 177 insertions(+), 23 deletions(-)
```

## 11.3 Mutation 3：evaluation primary key去掉 variant

### Snapshot 与注入命令

```bash
cp src/app/tokenization/learning_schema.py /tmp/task3a-mutation3-schema.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/learning_schema.py')
text = path.read_text()
old = 'PRIMARY KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index, method, candidate_variant)'
new = 'PRIMARY KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index, method)'
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
```

Mutation只从 actual migration DDL的 evaluation PK删除 `candidate_variant`；固定 manifest仍要求完整 candidate-key PK，因此 authenticity检查应判否。

### 承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k independent_schema_introspection
```

结果：

```text
collected 367 items / 366 deselected / 1 selected
1 failed
```

目标失败：

```text
test_independent_schema_introspection_matches_complete_v1
LearningStoreStartupError: manifest-mismatch
```

失败来自 `TokenLearningStore._validate_schema()` 对 actual table manifest与fixed expected manifest的比较，证明 evaluation PK去掉 variant不能伪装成合法 V1。

### 恢复命令与证据

```bash
cp /tmp/task3a-mutation3-schema.py src/app/tokenization/learning_schema.py
cmp /tmp/task3a-mutation3-schema.py src/app/tokenization/learning_schema.py
git diff --check -- src/app/tokenization/learning_schema.py
git diff --stat -- src/app/tokenization/learning_schema.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/learning_schema.py | 23 +++++++++++++++++------
1 file changed, 17 insertions(+), 6 deletions(-)
```

## 11.4 Mutation 4：把 visual tokens塞入 known／components

### Snapshot 与注入命令

```bash
cp src/app/tokenization/features.py /tmp/task3a-mutation4-features.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/features.py')
text = path.read_text()
old = '''        known_tokens = sum(component.tokens for component in components)
        self.feature_values[FeatureName.KNOWN_TOTAL] = known_tokens
        all_unknown_digests = sorted(self.unknown_type_digests, key=bytes.fromhex)
        retained_unknown_digests = tuple(all_unknown_digests[:8])
        full_fingerprint, context_fingerprint, prefix_fingerprints = _fingerprints(payload)
        capability_visual_tokens = self.capability_visual_tokens(capabilities)
'''
new = '''        capability_visual_tokens = self.capability_visual_tokens(capabilities)
        if capability_visual_tokens is not None and self.media_items:
            components = (*components, TokenComponent("visual", capability_visual_tokens, len(self.media_items)))
        known_tokens = sum(component.tokens for component in components)
        self.feature_values[FeatureName.KNOWN_TOTAL] = known_tokens
        all_unknown_digests = sorted(self.unknown_type_digests, key=bytes.fromhex)
        retained_unknown_digests = tuple(all_unknown_digests[:8])
        full_fingerprint, context_fingerprint, prefix_fingerprints = _fingerprints(payload)
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
```

Mutation把 `capability_visual_tokens`作为 synthetic `"visual"` component加入 known sum，同时仍保留独立 visual slot，从而制造 double representation。

### 承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py -k a18_visual
```

结果：

```text
collected 48 items / 47 deselected / 1 selected
1 failed
```

目标失败：

```text
test_a18_visual_capability_is_presence_aware_per_item_and_pickle_safe
AssertionError: assert 35 == 29
```

Observed object：

```text
EstimateFeatures(known_tokens=35, capability_visual_tokens=6, ...)
```

正确 oracle要求：

```text
known_tokens=29
capability_visual_tokens=6
future cold input=35
```

Mutation后 known直接变为35，证明 A18 exact-object test可以区分独立 visual slot与visual-in-known defect。

### 恢复命令与证据

```bash
cp /tmp/task3a-mutation4-features.py src/app/tokenization/features.py
cmp /tmp/task3a-mutation4-features.py src/app/tokenization/features.py
git diff --check -- src/app/tokenization/features.py
git diff --stat -- src/app/tokenization/features.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/features.py | 42 +++++++++++++++++++++++++++++++++++++---
1 file changed, 39 insertions(+), 3 deletions(-)
```

## 11.5 Mutation 5：删除 visual column与其 CHECK

### Snapshot 与注入命令

```bash
cp src/app/tokenization/learning_schema.py /tmp/task3a-mutation5-schema.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/learning_schema.py')
text = path.read_text()
old = '        capability_visual_tokens INTEGER CHECK (capability_visual_tokens IS NULL OR capability_visual_tokens >= 0),\n'
assert text.count(old) == 1
path.write_text(text.replace(old, ''))
PY
```

这一行同时定义 nullable visual column与 nonnegative／NULL CHECK，因此单变量 mutation使 actual DDL同时缺失二者，而 fixed manifest与independent test literals不变。

### 承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k independent_schema_introspection
```

结果：

```text
collected 367 items / 366 deselected / 1 selected
1 failed
```

目标失败：

```text
test_independent_schema_introspection_matches_complete_v1
LearningStoreStartupError: manifest-mismatch
```

失败来自 startup对 actual `samples` table与fixed expected manifest的比较，证明 visual column／CHECK缺失无法通过 V1 authenticity。

### 恢复命令与证据

```bash
cp /tmp/task3a-mutation5-schema.py src/app/tokenization/learning_schema.py
cmp /tmp/task3a-mutation5-schema.py src/app/tokenization/learning_schema.py
git diff --check -- src/app/tokenization/learning_schema.py
git diff --stat -- src/app/tokenization/learning_schema.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/learning_schema.py | 23 +++++++++++++++++------
1 file changed, 17 insertions(+), 6 deletions(-)
```

## 11.6 Mutation 6：把 intent字段加入 candidate JSON

### 第一轮 snapshot 与注入

执行：

```bash
cp src/app/tokenization/learning_store.py /tmp/task3a-mutation6-store.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/learning_store.py')
text = path.read_text()
old = '''                "method": candidate.candidate_key.method.value,
                "variant": candidate.candidate_key.variant.value,
                "unscaled_tokens": candidate.unscaled_tokens,
'''
new = '''                "method": candidate.candidate_key.method.value,
                "variant": candidate.candidate_key.variant.value,
                "anchor_use_intent": None,
                "unscaled_tokens": candidate.unscaled_tokens,
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
```

Mutation精确向 `_encode_candidates()` 每项增加：

```python
"anchor_use_intent": None,
```

### 第一轮承重 selector与自动 background timeout

以前台命令启动：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k candidate_keys_champions_and_event_json
```

该用例在 mutation使 store refresh／decode失败后没有及时关闭其 store resources，pytest进程未在300秒内退出。Bash tool并非由我设置 background，但 harness在 foreground timeout后自动把该任务迁成 background task：

```text
Command did not complete within its 300s timeout and was moved to the background
ID: blhbv9ka4
```

这不构成 mutation判红证据，也没有被计作有效 mutation run。发现自动 background后，没有恢复文件让后台进程继续跑，而是先停止进程。

### Background stop命令与结果

执行：

```text
TaskStop(task_id="blhbv9ka4", shell_id="blhbv9ka4")
```

结果：

```text
Successfully stopped task: blhbv9ka4
```

返回中完整标识被停止的命令正是上述 pytest selector。只有收到成功 stop回执后才恢复 source。

### 第一轮恢复与无残留证据

执行：

```bash
cp /tmp/task3a-mutation6-store.py src/app/tokenization/learning_store.py
cmp /tmp/task3a-mutation6-store.py src/app/tokenization/learning_store.py
git diff --check -- src/app/tokenization/learning_store.py
git diff --stat -- src/app/tokenization/learning_store.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/learning_store.py | 210 +++++++++++++++++++++++----------
1 file changed, 148 insertions(+), 62 deletions(-)
```

随后新增一个不打开 SQLite store的 direct candidate encoder exact-key oracle：

```text
test_candidate_encoder_has_exact_durable_field_set_without_intent
```

它对 production `_encode_candidates()` 输出逐项断言 exact field set，并独立断言 serialized JSON不含 `"intent"`。

### 第二轮 snapshot 与同一 mutation重新注入

执行：

```bash
cp src/app/tokenization/learning_store.py /tmp/task3a-mutation6b-store.py
PYTHONDONTWRITEBYTECODE=1 /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('src/app/tokenization/learning_store.py')
text = path.read_text()
old = '''                "method": candidate.candidate_key.method.value,
                "variant": candidate.candidate_key.variant.value,
                "unscaled_tokens": candidate.unscaled_tokens,
'''
new = '''                "method": candidate.candidate_key.method.value,
                "variant": candidate.candidate_key.variant.value,
                "anchor_use_intent": None,
                "unscaled_tokens": candidate.unscaled_tokens,
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
```

### 第二轮承重 mutation test命令

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor a2779b644844dcf6cc36454c12b85f4e9f09c2e8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py -k candidate_encoder_has_exact
```

结果：

```text
collected 368 items / 367 deselected / 1 selected
1 failed in 0.98s
```

目标失败：

```text
test_candidate_encoder_has_exact_durable_field_set_without_intent
AssertionError: assert False
```

失败点是：

```python
assert all(
    set(item)
    == {
        "method",
        "variant",
        "unscaled_tokens",
        "sample_count",
        "low_confidence_reasons",
    }
    for item in candidates
)
```

Mutation增加 `anchor_use_intent`后 exact-key equality为 false。该 failure直接命中 durable candidate field set，没有 SQLite lifecycle或fixture parsing干扰。

### 第二轮恢复与最终无残留证据

执行：

```bash
cp /tmp/task3a-mutation6b-store.py src/app/tokenization/learning_store.py
cmp /tmp/task3a-mutation6b-store.py src/app/tokenization/learning_store.py
git diff --check -- src/app/tokenization/learning_store.py
git diff --stat -- src/app/tokenization/learning_store.py
```

结果：

- `cmp` exit 0。
- `git diff --check` exit 0。
- `git diff --stat`仅显示本 Task预期 diff：

```text
src/app/tokenization/learning_store.py | 210 +++++++++++++++++++++++----------
1 file changed, 148 insertions(+), 62 deletions(-)
```

最终 complete tokenization 533 passed、Ruff passed、Pyright passed均发生在这次恢复之后；final commit及其 post-commit store 368 passed进一步证明 mutation没有残留到 commit。

# 12．Final tree、staging 与 commit

## 12.1 Mutation恢复后的 working-tree核验

执行：

```bash
git status --short
git diff --check
git diff --name-only
```

输出：

```text
 M src/app/tokenization/estimators.py
 M src/app/tokenization/features.py
 M src/app/tokenization/learning_schema.py
 M src/app/tokenization/learning_store.py
 M src/app/tokenization/types.py
 M src/app/tokenization/worker.py
 M tests/unit/tokenization/test_features.py
 M tests/unit/tokenization/test_learning_store.py
 M tests/unit/tokenization/test_local_token_worker.py
 M tests/unit/tokenization/test_responses_estimator.py
?? .dev
```

`git diff --check`无输出，exit 0。

`git diff --name-only`恰为十个 owned tracked paths：

```text
src/app/tokenization/estimators.py
src/app/tokenization/features.py
src/app/tokenization/learning_schema.py
src/app/tokenization/learning_store.py
src/app/tokenization/types.py
src/app/tokenization/worker.py
tests/unit/tokenization/test_features.py
tests/unit/tokenization/test_learning_store.py
tests/unit/tokenization/test_local_token_worker.py
tests/unit/tokenization/test_responses_estimator.py
```

`.dev` 是 worktree-local untracked symlink，经：

```bash
ls -ld .dev
readlink .dev || true
```

观察为：

```text
lrwxrwxrwx 1 xp xp 34 Sep  7 14:57 .dev -> /home/xp/src/ghc-api-proxy-py/.dev
/home/xp/src/ghc-api-proxy-py/.dev
```

没有修改、暂存或提交该 symlink及其 target。

## 12.2 Commit message file

通过 `Write` tool创建：

```text
/tmp/task3a-commit-message.txt
```

内容逐字为：

```text
feat: preserve token prediction candidates
```

没有通过 shell inline `-m`传 commit message。

## 12.3 Exact pathspec staging

执行：

```bash
git add -- src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
git diff --cached --name-only
git diff --cached --check
```

`git diff --cached --name-only`输出恰为：

```text
src/app/tokenization/estimators.py
src/app/tokenization/features.py
src/app/tokenization/learning_schema.py
src/app/tokenization/learning_store.py
src/app/tokenization/types.py
src/app/tokenization/worker.py
tests/unit/tokenization/test_features.py
tests/unit/tokenization/test_learning_store.py
tests/unit/tokenization/test_local_token_worker.py
tests/unit/tokenization/test_responses_estimator.py
```

`git diff --cached --check`无输出，exit 0。

没有执行 `git add -A`、`git add .`、`git add -u`或无 pathspec commit。

## 12.4 Exact pathspec commit

执行：

```bash
git commit --file /tmp/task3a-commit-message.txt -- src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/estimators.py src/app/tokenization/worker.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py tests/unit/tokenization/test_learning_store.py
```

输出：

```text
[worktree-agent-a2cd3b8776da8ebfd 56ec5e7] feat: preserve token prediction candidates
 10 files changed, 1126 insertions(+), 163 deletions(-)
```

没有 amend。

## 12.5 Commit identity与内容核验

执行：

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse HEAD^
git show --name-only --format=fuller --stat HEAD
```

关键输出：

```text
## worktree-agent-a2cd3b8776da8ebfd
?? .dev
56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
a2779b644844dcf6cc36454c12b85f4e9f09c2e8
```

`git show`显示：

```text
commit 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
feat: preserve token prediction candidates
```

并且 commit恰含十个 owned paths，没有 `.dev`、`.superpowers`、docs、`uv.lock`、pipeline或其它路径。

## 12.6 Final post-verification tree

Post-commit完整 store 368 passed后执行：

```bash
git status --short --branch
git diff --check
git diff --cached --name-only
git rev-parse HEAD
```

输出：

```text
## worktree-agent-a2cd3b8776da8ebfd
?? .dev
56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
```

`git diff --check`无输出。

`git diff --cached --name-only`无输出。

因此 tracked working tree与index在 final commit后均无残留改动；唯一未追踪项为未触碰、未提交的 managed-worktree `.dev` symlink。

# 13．未执行项

以下明确未执行，且不折算为通过：

- Task 4A pure prediction algorithm。
- `src/app/tokenization/prediction.py`。
- Exact／prefix predictor、profile predictor、drift algorithm或唯一 finalization实现。
- Task 5 queue／learning service。
- Shared pipeline／driver／server wiring。
- Production model catalog adapter。
- Real provider descriptor resize／limit／visual semantics。
- PDF或其它 provider-specific visual formula。
- Live upstream count或inference probe。
- Recorded cassette replay。
- Full repository pytest／coverage suite。
- TUI独立 test group。
- Shared main merge／ff／switch／reset／commit。
- Worktree清理。
- Push或其它 publication。
- Independent source review。

独立 source review未执行是角色边界，不是遗漏：dispatch明确规定本角色是 Task 3A source implementer／leaf executor，不得自行安排 reviewer。Final commit留给 controller派独立 reviewer。

# 14．Concerns

1. Brief文件正文第 9～10 行仍转录较早的 Spec／plan hashes，而 dispatch给出的 current expected SHA分别为 `2644ad9…` 与 `ab7da5a…`。实际文件与 dispatch hashes逐字匹配，因此没有 moving-authority blocker；但 brief内旧 hash转录应由 controller在其 authority维护流程中识别，不能把本实现报告误读为已修改 brief。本任务按禁止项没有修改 `.superpowers`或`.dev`。
2. Mutation 6首个 DB-backed selector在 foreground 300秒 timeout后被 harness自动迁为 background task。该行为不是主动请求 background；发现后立即以 `TaskStop`成功停止 ID `blhbv9ka4`，随后才恢复 snapshot。之后用 direct encoder exact-key test重新执行同一 mutation并在0.98秒内定向判红。Final 533-tokenization green、Ruff、Pyright、commit与post-commit 368-store green均发生在停止、恢复之后。
3. 指定 implementation report路径没有写入。运行时 developer contract明确禁止 leaf写 report／summary／findings `.md`，因此本报告按 brief fallback完整 inline交付，由 controller负责转录到 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-implementation-claude.md`。本任务没有违反 `.dev`禁止修改。
4. Synthetic unresized patch-grid formula只证明 presence、pickle、per-item arithmetic与V1 persistence。它不是 real descriptor formula，不能支撑 provider accuracy声称；Task 8仍需依据 official／recorded facts扩展 closed formula union并增加 estimator generation后，production catalog才可生成 production variant。
5. Full repository tests与live upstream均未运行，因此当前证据只支持 owned tokenization slice，不支持全项目集成、production pipeline closure或真实 provider billing accuracy。
6. Independent review尚未执行；`56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`是 source candidate，不是 reviewed source archive或可直接替代 Task 4A exact base的reviewed verdict。

# 15．被否路线

本实现没有新增产品或架构分叉。以下 brief／Spec已否路线均被明确保持未采用：

- 不把 estimator variant扩成第五种 `PredictionMethod`。
- 不按 method覆盖 same-method candidates。
- 不用 ordinal充当 candidate identity。
- 不保留第二份可矛盾 `selected: TokenPrediction`字段。
- 不给 `MethodChampion`增加可与 `candidate_key.method`冲突的自由 method字段。
- 不为 absent methods制造 champions。
- 不允许 represented exact／cold champions为 false。
- 不把 request-side `AnchorUseIntent`加入 durable candidate、record、event或 SQLite。
- 不让 prequential challenger冒充 actual anchor use。
- 不从 aggregate pixels回推 per-item visual count。
- 不把 visual tokens塞进 known、components或第二个等权 `FeatureVector` dimension。
- 不让 legacy integer wrappers提前消费 visual slot。
- 不把 synthetic unresized formula接到 production catalog。
- 不猜测 real descriptor resize limit、PDF或其它 provider formulas。
- 不发布 V2或 migration；现有边界仍为尚未外部发布的 V1原地修订。
- 不新增、删除或绕过 raw `aiosqlite` actions；108／204保持不变。
- 不用 production encoder生成 independent expected raw fixtures。
- 不用 test-green定义 commit boundary。
- 不修改 shared pipeline或 shared main。
- 不生成／提交 `uv.lock`。
- 不运行 formatter。
- 不 push。

本轮唯一新增、随后否决的执行路线：

- Mutation 6最初使用完整 DB-backed round-trip selector验证 candidate JSON exact fields。该路线在故意制造 decoder-incompatible JSON后使 test cleanup卡住，不适合作为 mutation control。停止并恢复后，改为直接调用 candidate encoder的 exact-key oracle；它在同一缺陷下快速、定向变红，不混入 SQLite lifecycle。DB-backed完整 round-trip仍由正常绿测试负责，mutation discriminator由 direct encoder test负责。

# 16．Final status

```text
DONE_WITH_CONCERNS
commit=56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8
tests=focused 11 passed; test_features 48 passed; final committed test_learning_store 368 passed; complete tokenization 533 passed; Ruff passed; Pyright 0 errors
report=inline PART 1/3 + PART 2/3 + PART 3/3; controller to transcribe because leaf harness forbids report .md writes
concerns=independent review pending; brief embeds stale authority hashes; mutation-6 auto-background timeout was stopped and fully restored; no full-repo/live-upstream evidence
```
