# `docs/tmp` 与 `docs/agents` 搬入 `.dev/docs`（2026-08-21）

主仓库的 `docs/tmp/`（417 份报告）与 `docs/agents/`（8 个话题、43 份文档）整体搬入 `.dev/docs/`。这两个目录**已不存在，不要再重建**。主仓库 `docs/` 现在只剩 `docs/.human-controlled/`。

- 主仓库删除提交：`0b01cdc`（106 条纯删除，其余 300 多份本来就未被跟踪）
- `.dev` 接收提交：`5e94b75`（482 个文件，纯搬迁，内容零改动）
- 用户裁决（2026-08-21）：`docs/agents/` 下的活文档**全部话题整体搬入**，不只搬报告。CLAUDE.md 早前已授权「可逐步按主体迁移」，这次一次做完。

## 搬到哪了

一个话题一个目录。话题的**活文档**（`spec.md`、`status.md`、`plan.md`、`acceptance.md`、`deferred.md` 等）在话题根，**报告原件**在 `<topic>/reports/`。

| 话题 | 报告 | 活文档 |
|---|---:|---:|
| `anthropic-responses-bridge` | 193 | 11 |
| `documentation-restructure` | 43 | 2 |
| `systemd-runtime` | 42 | 3 |
| `service-cutover` | 31 | 3 |
| `hosted-web-search` | 22 | — |
| `delivery-keepalive` | 16 | 20 |
| `architecture-audit` | 9 | — |
| `empty-text-block` | 8 | — |
| `httpx2-migration` | 6 | 1 |
| `pipeline-rewrite-parity` | 5 | — |
| `git-housekeeping` | 5 | — |
| `tui` | 4 | — |
| `copilot-token-identity` | 4 | — |
| `test-infrastructure` | 3 | — |
| `project-review-principles-skill` | 3 | — |
| `lifecycle-reorg` | 3 | — |
| `hooks-subscription-migration` | 3 | — |
| `count-tokens` | 3 | — |
| `history` | 1 | — |
| `deployment-systemd` | — | 1 |
| `systemd-rolling` | — | 2 |
| **`tmp/`（未分类）** | **13** | — |

`tui`、`history` 是 `.dev` 里早已存在的话题，这次只是往里加报告。另有一份编辑器备份残件 `refs-go-bridges.md~` 与正本内容不同，一并留在 `tmp/`。

## 怎么分的

417 份逐个被打开读过，不是按文件名猜的。分 10 批派给 10 个 agent，每批的判据、逐文件表和置信度在 `reports/260821-classify-batch-*.md`，共享判据在 `BRIEF.md`，批次清单在 `batches/`。并集校验过：10 批无重、无漏，恰好 417。

判据的要点：

- **按内容判，不按文件名判。** 文件名里的 `review` / `audit` / `verify` 只说明体裁，不说明话题。
- **一个文件只归一个话题。** 跨话题的按「它评审的那个被改对象属于谁」定；仍判不了就留未分类。
- **未分类不是失败。** 硬塞进一个话题比留在 `tmp/` 更糟。

三个新话题由分类 agent 提出：`pipeline-rewrite-parity`、`hooks-subscription-migration`、`project-review-principles-skill`。另有两个是我在合并 10 份报告时补的——`copilot-token-identity`（4 份）与 `git-housekeeping`（5 份）：它们分散在不同批次里，每批都不足 3 份而被判为未分类，合起来才够成话题。这是分批本身的产物，不是 agent 判错。

## 未分类的 13 份，以及为什么

绝大多数是**同一时刻对分属不同话题的两三份活文档做的联合评审**——`260807-review-main-foundations-systemd.md` 同时评 bridge 的 reasoning／liveness 与 systemd 的 unit／shutdown，`260807-review-identity-living-checkpoint.md` 横跨 bridge 与 service-cutover。给它们挑一个话题就等于丢掉另一半。剩下两份是流程记录而非产品话题：`260820-review-session-closeout.md`（会话收尾）与 `260820-system-reminder-wire-shapes.md`（`<system-reminder>` 上行形态普查）。

## 引用重指：改了什么、没改什么

**归档报告原件里的路径一律不动。** 报告里写的 `docs/tmp/xxx.md:251` 是**当时那一刻**的位置，把它改成今天的布局等于伪造记录。`.dev/README.md` 的「归档文档里的路径与行号是快照」那条讲的就是这件事。所以 `.dev/docs/**/reports/` 与 `archive-*/` 下的约 2400 处旧路径保持原样，读的时候当快照读。

**活文档重指了。** 27 个活文档、180 处引用，分两遍：

1. 字面 `docs/tmp/x.md` 与 `docs/agents/<topic>/y.md` → 新位置的相对路径。
2. 原文里就写成相对形式的（`../../tmp/x.md`），按**旧位置**解析出它当时指向谁，映射到新位置，再按**新位置**重算相对路径。第二遍必须跳过第一遍已经改对的，否则会把正确路径按旧基准重新解析成垃圾——这个坑踩过一次。

顺手修了更早一次搬迁遗留的 `docs/2604-rewrite/` → `../archived-2604-rewrite/`（6 处）。

**主仓库里 11 处引用**（`src/`、`tests/`、`exp/`、`pyproject.toml`、`.claude/rules`、`.claude/skills`、`contrib/systemd`）改为 `.dev/docs/...`。这些是从被跟踪文件指向 gitignored 目录的链接——对 clone 本仓库的人是断的，但它准确说明了那份文档现在在哪，比指向一个已经不存在的路径强。

链接可达性检查跑过，检查器先用正样本证明过能报出坏链（第一版检查器自己崩了、退出码恰好也是 1，差点当成通过）。

## 留下的问题

- **没做蒸馏。** 这次只搬和分类，没把报告里的结论提炼进活文档。`.dev/README.md` 说「归档要重写，不要堆」——现在各话题的 `reports/` 就是堆着的，缺 `README.md` 入口。193 份的 `anthropic-responses-bridge` 尤其需要。
- **3 处断链是搬迁之前就断的**，目标文件在仓库里根本不存在，不是这次搬出来的：`systemd-runtime/plan.md` 引的 `260807-systemd-user-manager-diagnosis.md`（疑似指 `reports/260807-review-systemd-user-manager-diagnosis.md`，但名字对不上，没有替它猜）、`systemd-rolling/plan.md` 引的 `copilot-api-js-comparison.md` 与 `tests/systemd_vm/README.md`。
- **`contrib/systemd/ghc-api-proxy.service` 的 `Documentation=` 需要用户裁决。** 它原本指 `/opt/ghc-api-proxy/docs/agents/deployment-systemd/README.md`；那份文档现在在 `.dev/`，而 `.dev/` 不随部署分发。我做了机械重指，但无论指哪儿这一行都不完全成立：指旧路径是指向不存在的文件，指新路径是断言了一个不会被部署的位置，指 `README.md` 则那里没有 systemd 内容。
- **CLAUDE.md 第 9 行已过时**，说「曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移」——迁移已经做完。该文件由用户控制，未改动。
