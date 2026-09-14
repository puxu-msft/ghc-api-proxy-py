# Round 3 final authority review

## 评审范围与证据边界

评审时间：2026-09-14。范围是当前 `.dev` 的 root `README.md`、repository-repair current entry、四个 topic README/status/deferred/disposition、raw-capture v25 Spec 与 observability implementation ledger。`history/archive/reports` 只作为 provenance，不作为 current authority。

代码事实按 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 核对；`git cat-file -e` 对 `src/app/history/archive.py`、`src/app/observability/request_journal.py`、`src/app/replay/process.py` 均返回 `present`。不使用共享主树状态或物理缺失路径作证据；已明确 accepted-deferred 的实现限制不重复升级。

## 总体 verdict

**pass**。未发现 blocker 或 major；发现 1 条 minor 版本导航问题。四主题入口、ledger authority、root repair current state 与 raw v25 的 accepted-deferred 分层均可供接手者使用，可以进入下一轮。

## Root README / repository repair current state

- `.dev/README.md:3,20-31,77-88` 明确 `.dev` 当前仍是访问 dotdev 的工作树、re-root/worktree 尚未闭合，并把 repository-repair README 指定为结构修复 owner；没有把最终挂载写成已完成。
- `.dev/docs/dotdev-repository-repair/README.md:1-3,23-29` 把“迁移/候选退役已完成”与“re-root 不得执行”分开；`:23-29` 明列最终独立复扫、`.dev` checkpoint、再执行挂载的唯一顺序。
- `README.md:42` 自述 local links `missing=0`；定向 link probe 输出 `.dev/README.md: links=11 missing=0`、`.../dotdev-repository-repair/README.md: links=60 missing=0`。
- 结论：root README 与 repair current entry 没有把历史完成数、候选退役或 checkpoint 误写成最终挂载完成；**通过**。

## Authority 与 implementation ledger

- `.dev/docs/observability/README.md:3,5-14,16-23` 明确四主题各有独立 Spec，本页只导航/状态边界；review disposition 不升级为合同。
- `implementation-ledger.md:5,11-17,21-30` 只保留 task 状态、commit、验证证据和 current owner；#2–#4 使用 `done-with-deferred-hardening`，#5–#6 使用 `partial-accepted`，没有复制合同字段或安全边界。
- `review-disposition.md:5,7-17` 把 History restart、Journal taxonomy、Replay result、per-attempt capability 与 user-controlled candidate 分别落到 status/deferred/候选 owner。
- 结论：**authority 唯一，ledger 仅作状态/证据索引；通过**。

## Raw capture v25 与 disposition

- current authority 是 `raw-capture/spec.md:3-5,50-76,104-109` 的 **ACTIVE v25**；v25 明确 History-owned normalized identity 与 raw transport headers/credentials 的边界。
- `raw-capture/deferred.md:3,11-23` 以 v25 为依据，并将 D-3/D-4 明确标为 `accepted-deferred`；`review-disposition.md:10-24` 逐条映射到 deferred/current owner，未把 v25 全部 hardening 写成 closed。
- `raw-capture/status.md:4,18-20` 仍以“v24 full-header slice”描述落地切片，且末句仍写“不得反推 v24”；这与 v25 current Spec 的版本导航不一致，但 README 仍直接指向 `spec.md`，未形成第二 authority。
- 结论：raw v25 合同与 accepted-deferred 内容可理解；仅版本指针需刷新，见 M-R3-001。

## 四主题入口与 accepted limitations

- Root inventory `.dev/README.md:54,57,59,61,75,77-82` 已列出 History、Observability、Raw capture、Replay，并要求从 topic README 进入。
- Observability README `:5-14,16-23`、History README `:3-8`、Raw README `:3-8`、Replay README `:3-8` 均提供 Spec → status → deferred/disposition 路径。
- 已接受限制均有 owner：History `status.md:16-24` / `deferred.md:3-7`，Observability `status.md:24-31` / `deferred.md:5-10`，Replay `status.md:18-24` / `deferred.md:3-8`，Raw `status.md:16-20` / `deferred.md:11-23`。
- 结论：新接手者能够区分 current contract、已落地切片和 accepted-deferred；**通过**。

## Major findings

未发现 blocker/major。

## 可记录不修

### M-R3-001 — raw-capture v24/v25 版本指针滞后

- `raw-capture/review-disposition.md:4` 已写 current Spec 为 ACTIVE v25，但 `:6` 仍写“当前状态由 v24 Spec、status.md 和本表共同导航”。
- `raw-capture/status.md:4,20` 仍以 v24 命名 full-header slice，并把候选材料的禁止反推句落到 v24；`raw-capture/deferred.md:3` 已改为 ACTIVE v25。
- 影响限于点时导航不精确：topic README/spec 直接链仍指向当前 v25，故不构成 major；应在下一次文档整理中统一为 v25。

## 搜索面与停止条件

已读取 root README、repository-repair current entry、四主题入口/状态/deferred/disposition、raw v25 Spec 与 ledger；核对 committed HEAD 的代码存在性并执行 root/repair README 定向 Markdown link probe。未扩大到无关 topic，未把历史报告当 current authority，未操作 4141，未执行写入性仓库命令。
