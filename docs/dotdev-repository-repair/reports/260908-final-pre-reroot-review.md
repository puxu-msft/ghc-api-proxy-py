# dotdev re-root/worktree 挂载前最终独立复审

## 评审范围

- **目标**：独立复核 `reports/260908-pre-reroot-readiness-review.md` 的 PRR-01～PRR-05 是否实际闭合，并判断 `.dev` checkpoint 与其后的 dotdev re-root/worktree 挂载能否进入下一阶段。
- **被检对象**：当前 `.dev/README.md`、`.dev/docs` 活动树、retained living Markdown 与 evidence assets、`src/`、`tests/`、`pyproject.toml`，以及 repair README、final ledger、上轮 review 和六份本轮修复记录。
- **明确排除**：`reports/`、`history/`、`archive*` 与 repair control-plane 中为 provenance 保留的旧路径表不反算为 current consumer；不验收 `httpx2-migration`、`systemd-runtime`、`reasoning-carrier` 各自尚未完成的产品/运行时工作。
- **只读边界**：除按委托写入本报告外，未修改、移动或删除被检对象，未执行 `git add`、commit、push、checkpoint、re-root 或 worktree 挂载。

## 总体 verdict

**NEEDS-FIX。** 上轮 PRR-02 尚未闭合，且独立系统复扫另发现一处上轮漏报的 current `src/` consumer。当前不应创建作为 re-root 前门的最终 `.dev` checkpoint，也不应执行 re-root/worktree 挂载。

## Blocker 数

**0**

## Findings

### FPRR-01 — current production comments 仍消费已退役目录或已清空的 top-level `tmp` child

- **severity**：major
- **status**：open；阻止最终 checkpoint 与 re-root/worktree 挂载
- **primary_location**：`src/app/pipeline/driver.py:432`
- **related_locations**：
  - `src/app/server/routes/inference.py:864`
  - `.dev/docs/token-counting/history/2604-rewrite/tokenization.md`
  - `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary.md`
  - `.dev/docs/tui/history/260908-pre-reroot-path-relink.md`
  - `reports/260908-pre-reroot-readiness-review.md` 的 PRR-02
- **claim**：上轮明确列入 PRR-02 的 `driver.py` comment 未改链；此外，独立抛开上轮清单复扫当前 `src/`，发现 `inference.py` 仍引用已经清空的 top-level `tmp` child。两处均有已存在的 canonical destination。
- **evidence**：
  - `src/app/pipeline/driver.py:432` 当前仍写 `.dev/docs/archived-2604-rewrite/tokenization.md`；该 retired directory 不存在，canonical 原件存在于 `.dev/docs/token-counting/history/2604-rewrite/tokenization.md`。
  - `src/app/server/routes/inference.py:864` 当前仍写 `.dev/docs/tmp/260822-ghc-api-conformance-summary.md`；top-level `tmp/` 当前 regular files 为 0，该 source 不存在，canonical 原件存在于 `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary.md`。
  - 本轮六份修复记录中，TUI/observability 记录明确说未处理 token-counting；没有一份记录声明或实施 `driver.py` 改链。filesystem 最终状态与这一范围边界一致。
- **impact**：当前 tree 仍不满足 repair README 要求的 retired exact path、legacy alias 与具体 top-level `tmp/<file>` consumer 清零门。现在 checkpoint 会把两个不可解析 provenance 指针冻结到 re-root 后；结构迁移不会自行修复它们。
- **minimal_next_step**：把 `driver.py` 的注释精确改到 `.dev/docs/token-counting/history/2604-rewrite/tokenization.md`，把 `inference.py` 的注释精确改到 `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary.md`；随后对 retained living/evidence、`src/`、`tests/`、`pyproject.toml` 重跑 retired path、legacy alias、top-level `tmp` child 与 basename 扫描。

### FPRR-02 — PRR-01 的 fragment 仍是失效的 same-file link

- **severity**：minor
- **status**：open；不单独阻断结构迁移
- **primary_location**：`.dev/docs/upstream/retry-and-continuation/decisions.md:117`
- **related_locations**：
  - `.dev/docs/upstream/retry-and-continuation/deferred.md:303`
  - `.dev/docs/upstream/retry-and-continuation/reports/260908-pre-reroot-evidence-relink.md`
  - `reports/260908-pre-reroot-readiness-review.md` 的 PRR-01
- **claim**：修复把 fragment 补成了目标 heading 的完整 slug，却没有把 link path 从当前 `decisions.md` 改为实际承载 heading 的 `deferred.md`。修复报告“已指向 `deferred.md`”的自述与最终文件不一致。
- **evidence**：
  - `decisions.md:117` 当前链接仍为 `(#22-之四-一条状态断言在写下时就已经过期--已移入教训文档2026-08-27)`，因此按 Markdown 语义解析到 `decisions.md` 自身。
  - `decisions.md` 没有该 heading；实际 heading 是 `deferred.md:303` 的 `### 22 之四. 一条状态断言在写下时就已经过期 —— 已移入教训文档（2026-08-27）`。
  - 本轮 upstream 修复报告第 3 项宣称链接“已指向 `deferred.md`”，但验证段只核对了 slug，没有核对最终 target file，因而没有发现 path component 仍缺失。
- **impact**：读者仍不能从 current decisions 页跳到所指墓碑；这是 retained living fragment 完整性缺陷。它不依赖 retired topic 或 top-level `tmp`，故不单独阻断 checkpoint/re-root。
- **minimal_next_step**：把 target 改为 `deferred.md#22-之四-一条状态断言在写下时就已经过期--已移入教训文档2026-08-27`，再用同时校验 target file 与 target heading 的 parser 重跑 retained living fragments。

## 上轮 findings 逐条闭合状态

| 上轮 finding | 本轮结论 | 独立复核摘要 |
|---|---|---|
| PRR-01 fragment | **not-closed** | slug 已补完整，但最终 target 仍是 `decisions.md` 的 same-file fragment，不是 `deferred.md#...`；见 FPRR-02。 |
| PRR-02 retired/tmp consumers | **partially-closed** | TUI Spec 两项、`request_log.py`、bridge research、upstream probe/README/report 已改到 canonical path 或移除已删依赖；`driver.py` 未改。系统复扫另发现 `inference.py` 的 top-level `tmp` child，见 FPRR-01。 |
| PRR-03 TUI evidence index | **closed** | repair README 已链接 TUI migration record，并准确写成 9 份 topic reports + 1 份 TUI record、合计 183 项；60 occurrences、59 unique destinations、missing=0。 |
| PRR-04 malformed SHA-256 | **closed** | 报告已是合法 64-hex digest；destination、dotdev `HEAD` old-source blob、index old-source blob 三者均为同一 SHA-256。 |
| PRR-05 future root README | **closed** | `.dev/README.md` 已成为 future direct-root/worktree 入口，retained topic inventory 与 current status 边界正确；旧 nested layout 只作为 pre-reroot provenance 被否定，不再是操作模型。 |

## 独立复核通过项

### 1. 目录退役、`tmp` 与 retained topics

- 下列 15 个 retired top-level topic path 均不存在，且 `-e`/`-L` 组合检查未发现 dangling symlink：`architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、top-level `history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure`。
- `.dev/docs/tmp/` 机制目录存在，top-level regular files=`0`。
- `.dev/docs/interaction-context/spec.md` 与 `history/260907-interaction-context-design.md` 均存在。
- `.dev/docs/httpx2-migration/` 与 `.dev/docs/systemd-runtime/` 均保留；`pyproject.toml:16` 仍指向 `.dev/docs/httpx2-migration/plan.md`。

### 2. PRR-02 已闭合的 consumer 子项

- `.dev/docs/tui/spec.md` 的两个 Markdown links 分别解析到 `tui/history/2604-rewrite/telemetry-observability.md` 与 `tui/history/2604-rewrite/lib-survey/SELECTIONS.md`。
- `src/app/observability/request_log.py:3` 指向 `.dev/docs/tui/history/2604-rewrite/DESIGN.md`。
- `.dev/docs/anthropic-responses-bridge/research.md:63` 指向 `hosted-web-search/history/2604-tool-use.md`，明确其仅为 historical provenance；已删除、无 canonical original 的 `request-pipeline.md` 不再承担证据依赖，current 行为改由本节目标现状与 bridge Spec 支撑。
- upstream probe 的 `EV`、topic README 与 `260821-max-tokens-block-completeness.md` 均改用 topic-local `evidence/max-tokens-block-completeness/`；`scan_hits.txt`、`inc_table.txt` 与 probe 均存在。
- 对 retained living/evidence assets、`src/`、`tests/`、`pyproject.toml` 的旧路径 literal 扫描，实际 current consumer 命中只有 FPRR-01 的两处。`reports/`、`history/`、`archive*`、repair control-plane 与 retained-topic migration mapping 中保留的 old→new 路径表未被误计为 consumer。

### 3. README evidence index 与 TUI 三项

- candidate residual ledger 独立计数为 canonical history=`183`、delete=`36`；其中 TUI canonical rows=`3`。
- repair README 的 residual evidence 段已链接 `.dev/docs/tui/history/260908-residual-history-migration.md`。该 record 逐项列出 `DESIGN.md`、`telemetry-observability.md`、`lib-survey/SELECTIONS.md` 三个 destination。
- 三个 current destination 的 SHA-256 分别为 `0f922929886fb04ef0b6d2ac6cd337a51a443a34418233fc0d0b467002c523e3`、`45a9e3fc9f5cd110e95b89a99810d5ecf1e37e8c4c73804de0777cb12e6e832d`、`23c2b9c78a37317f005c0215eb2b554b43a4beb9f93f33241d2ede83b9ac4d05`，均与 TUI migration record 一致。
- 用 `markdown-it-py 4.0.0` 解析 repair README，得到 local Markdown link occurrences=`60`、unique destinations=`59`、missing=`0`；README 自述准确。

### 4. future root README

- active `.dev/` 已有未来 direct root 所需的 `README.md`、`docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 与 `verification/`；README 把主工作树 `.dev/` 定义为 worktree mount，而不是远端树的永久路径前缀。
- topic inventory 与当前 `.dev/docs/` 的 29 个 top-level retained topic/mechanism directories 对齐；未列入 15 个 retired candidates。
- 未发现“远端只有 `.dev/` prefix”“不得把根树推到 dotdev”、reasoning source unreachable/main 未集成或 timeout 实现尚未装位等旧状态。旧 `.dev/.dev/` 只在明确的 pre-reroot history/provenance 否定语境出现。
- root README 共 7 个 local links，7 个 target 均存在。

### 5. PRR-04 SHA

- `.dev/docs/ghe-device-flow/reports/260908-residual-history-migration.md` 的修正 digest 为 `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b`。
- 对 current destination 直接 `sha256sum`，以及只读读取 dotdev `HEAD` 与 index 的 old-source blob 后计算 SHA-256，三次结果完全相同。迁移内容一致，PRR-04 已实际闭合。

### 6. retained living Markdown links/fragments

- retained living safe superset 为 114 份 Markdown；另单独加入 root `.dev/README.md`。范围排除了任一 `reports/`、`history/`、`archive*` component 与整个 repair control-plane。
- 114 份 living Markdown 共 734 个 Markdown links，其中 724 个为 relative local/same-file links、705 个带 path、19 个带 fragment；root README 另有 7 个 relative local path links。
- path target missing=`0`。fragment unmatched=`1`，即 FPRR-02；未发现第二个真实断链。

## checkpoint / re-root 门判定

- **最终 `.dev` checkpoint：当前不可进行。** FPRR-01 表明结构门所要求的 retired/top-level-tmp current consumer 清零尚未成立。若只想保存一个明确标注 known-broken 的临时保险点，那不是 repair README 所说的 final、可进入 re-root 的 checkpoint，不在本次放行结论内。
- **dotdev re-root/worktree 挂载：当前不可进行。** 必须先修复 FPRR-01，建议同批闭合 FPRR-02，再重跑同范围 final scan；扫描通过后才建立可审查、可恢复的 `.dev` checkpoint，随后才能按 ancestor-chain、direct-root layout、mount 与主仓 `git status` 可见性验收 re-root/worktree。
- **不构成结构迁移 blocker 的 retained work**：
  - `httpx2-migration` step 4 prose/logger 筛噪与验证仍未闭合，只阻止该 topic 退役；
  - `systemd-runtime` S5 仍等待具备独立 user manager 与 delegated cgroup v2 的可销毁环境，只阻止 S5/runtime PASS 与该 topic 退役；
  - `reasoning-carrier` 的 `RC-TF-01` 仍待 test-discriminability 独立复验，只是 retained-topic follow-up。

  三者均应保留并随 direct-root 一起迁移，不应被误当成 checkpoint/re-root 的结构性前置。`timeout-408` 的远端根因/策略边界同理仍是 topic 内 retained work，当前 status 已正确区分审计基线实现与未验证范围。

## Severity 汇总

| severity | count |
|---|---:|
| blocker | 0 |
| major | 1 |
| minor | 1 |

## 搜索面与执行记录

- 必读材料：repair README、上轮 pre-reroot review、final ledger refresh、current `.dev/README.md`，以及本轮六份记录：TUI evidence-index fix、TUI/observability path relink、bridge research relink、GHE SHA correction、root README refresh、upstream evidence/fragment relink。
- 文件树：15 retired paths 的存在/符号链接检查；`tmp/` top-level regular-file count；`interaction-context`、`httpx2-migration`、`systemd-runtime` existence；active `.dev/` direct-root children 与 `.dev/docs/` top-level inventory。
- consumers：逐个读取上轮 PRR-02 指定 consumers；另扫描 retained living/evidence assets、`src/`、`tests/` 与 `pyproject.toml` 的 retired names、2604 legacy aliases 和 `.dev/docs/tmp/<child>` literals。
- Markdown：用 CommonMark token parser 解析 retained living safe superset、repair README 与 root README 的 local targets；按 GitHub heading slug 规则校验 fragment target file 与 heading。
- integrity：独立计数 FRR-02 ledger 的 canonical/delete/TUI rows；对 TUI 三项与 PRR-04 destination/source blob 直接计算 SHA-256。
- Git：只读查看主仓与 dotdev status、dotdev `HEAD`/index blob；没有执行产品 tests、探针、外部请求、checkpoint、re-root 或 worktree 操作。结构审阅不以未运行的 retained-topic产品 tests 冒充放行证据。

## 最小下一步

1. 修复 FPRR-01 的 `driver.py` 与 `inference.py` 两个 comment target。
2. 同批把 FPRR-02 改成 `deferred.md#...`，避免 final scan 继续保留唯一 fragment 断链。
3. 重跑本报告的 15 paths、top-level `tmp`、retained/current consumer、README counts/targets 与 retained Markdown path/fragment 全扫描。
4. 只有扫描得到 current consumer=`0`、path missing=`0`、fragment unmatched=`0` 后，才建立最终 `.dev` checkpoint；checkpoint 经逐路径审查与恢复性确认后，再执行 re-root/worktree 挂载。

---

## 附录：FPRR-01/FPRR-02 限域复审（2026-09-08）

### 范围与结论

本附录只复审 FPRR-01/FPRR-02 的最终修复，不重新验收本报告其它已通过面。读取并核对：

- `src/app/pipeline/driver.py` 的 tokenization provenance comment；
- `src/app/server/routes/inference.py` 的 one-shot delivery comment；
- `.dev/docs/upstream/retry-and-continuation/decisions.md` 的 `22 之四` link；
- `.dev/docs/upstream/retry-and-continuation/deferred.md` 的 target heading；
- retained current docs/evidence、`src/`、`tests/`、`pyproject.toml` 中 `archived-2604-rewrite` 与 `.dev/docs/tmp/<child>` consumers。

**限域 verdict：PASS。FPRR-01=closed，FPRR-02=closed。现在可以进入 final `.dev` checkpoint。** 本附录的后时点结论取代本报告正文中仅针对 FPRR-01/FPRR-02 的 open/NEEDS-FIX gate；它不宣称 checkpoint 已执行，也不提前授权 re-root/worktree 挂载。

### FPRR-01：closed

- `src/app/pipeline/driver.py` 的 comment 已改为 `.dev/docs/token-counting/history/2604-rewrite/tokenization.md`；target 是存在的 regular file。
- `src/app/server/routes/inference.py` 的 one-shot comment 已改为 `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary.md`；target 是存在的 regular file。
- 对 retained current docs/evidence、`src/`、`tests/`、`pyproject.toml` 共 683 个可读文件重扫 `docs/archived-2604-rewrite` 与 `.dev/docs/tmp/<child>` literals，`consumer_hits=0`。
- 扫描排除了任一 `history/`、`reports/`、`archive*` component 与整个 repair control-plane，未把故意保留的 provenance/path mapping 反算为 current consumer。

### FPRR-02：closed

- `decisions.md` 的最终 href 是 `deferred.md#22-之四-一条状态断言在写下时就已经过期--已移入教训文档2026-08-27`，target file 明确为同 topic 的 `deferred.md`，不再是 same-file fragment。
- `deferred.md` 存在；按 GitHub heading slug 规则解析其 heading，目标 fragment 与 `### 22 之四. 一条状态断言在写下时就已经过期 —— 已移入教训文档（2026-08-27）` 精确匹配。

### Final checkpoint 门

FPRR-01 的 retired/tmp current-consumer gate 已变为零，FPRR-02 的唯一 fragment 断链也已消失。结合本报告正文对其余门的既有通过结论，**可以进入 final `.dev` checkpoint**。顺序仍保持：

1. 建立可审查、可恢复的 final `.dev` checkpoint，并逐路径核对 active direct-root 与旧 nested tracked tree；
2. checkpoint 审查与恢复性确认通过后，才执行 dotdev re-root/worktree 挂载及其 direct-root、ancestor-chain、mount、主仓 `git status` 可见性验收。

本轮除追加本附录外未修改、移动或删除被检对象，未执行 `git add`、commit、push、checkpoint、re-root 或 worktree 挂载。
