# 指令面覆盖核验：搬迁后还会不会有人写回 `docs/tmp/`

**日期**：2026-08-21
**角色**：独立证伪评审员（只读，未修改任何被检文件）
**待推翻的命题**：一个新会话或新 agent 读完当前生效的指令，不会再把报告写进 `docs/tmp/`，也不会重建 `docs/agents/`。
**基线**：主仓库 `main` @ `0a72f52`（工作树含并行会话的未提交改动，见下）；`.dev` @ `dotdev` `0d81c7b`。

## 结论

**命题被推翻。** 有一条完全可达的路径会让 agent 照旧写进 `docs/tmp/`，且写完之后会通过分支合并把 `docs/tmp/` 带回 `main`。另有一处该改而没改的指令面（`README.md`）当前看起来是干净的，但那是并行会话一份**未提交**的重写造成的，不是本次搬迁修的。

- blocker：1
- major：2
- minor：4
- 核对通过、无问题：5 项（列在最后一节）

严重度口径：**blocker** = 存在具体可复现路径直接推翻命题；**major** = 指令面确有缺口或错误陈述，但推翻命题需要额外条件；**minor** = 措辞、可执行性或引用规范问题，不改变命题成立与否。

---

## B-1 [blocker] 四棵活 worktree 各自带着**旧版**工作流规则和实体 `docs/tmp/` + `docs/agents/`

`0a72f52` 只改了主工作树里的那一份 `.claude/rules/00-development-workflow.md`。`.claude/rules/` 是**被跟踪文件**，因此每棵 worktree 都有自己的一份，停在各自分支的旧提交上。

四棵 worktree 全部满足两个条件：目录实体存在，且规则文本仍然指向它。

| worktree | HEAD | `docs/tmp/` | `docs/agents/` | 自带旧规则 |
|---|---|---|---|---|
| `.claude/worktrees/delivery-keepalive`（`worktree-proxy-priority`） | `1e4a228` | 有 | 有 | 有 |
| `.claude/worktrees/upstream-error-events`（`fix/upstream-error-events`） | `fd6b591` | 有 | 有 | 有 |
| `/home/xp/.claude/jobs/405f4b84/tmp/slice0/wt`（`slice0/exactly-once`） | `9557700` | 有 | 有 | 未逐项验（目录已验） |
| `/home/xp/.claude/jobs/826d4cda/tmp/review`（detached） | `7839b02` | 有 | 有 | 未逐项验（目录已验） |

旧规则原文（`.claude/worktrees/delivery-keepalive/.claude/rules/00-development-workflow.md:38-39`）：

> - `docs/` holds live conclusions, `docs/agents/<topic>/` holds in-flight development documents, and `docs/agents/<topic>/archive-<date>/` holds historical development records.
> - Subagent investigations, reviews, and PoCs exchange full reports through repository files. New temporary reports use a `YYMMDD-` prefix under `docs/tmp/` and are never overwritten. …

同一棵树里 `.claude/skills/project-review-principles/SKILL.md:302` 也仍是旧路径。

**为什么这直接推翻命题**：项目工作流规则本身写着 “Work incrementally in isolated worktrees when useful.”，即在 worktree 里派 agent 是**本项目推荐的做法**。一个被派进上述任一棵树的 agent，读到的“当前生效的指令”就是那份旧规则，且它 `ls docs/` 时会看到 `tmp/` 和 `agents/` 确实在那儿——两个独立信号相互印证，没有任何东西会让它起疑。它写下的报告落在该分支的 `docs/tmp/`，随后按项目约定 squash 进 `main`，`docs/tmp/` 就被重建了。

**复核命令**：

```bash
R=/home/xp/src/ghc-api-proxy-py
git -C "$R" worktree list
for wt in "$R/.claude/worktrees/delivery-keepalive" "$R/.claude/worktrees/upstream-error-events" \
          /home/xp/.claude/jobs/405f4b84/tmp/slice0/wt /home/xp/.claude/jobs/826d4cda/tmp/review; do
  echo "=== $wt ==="
  ls -d "$wt/docs/tmp" "$wt/docs/agents" 2>&1
  rg --line-number 'docs/tmp|docs/agents' "$wt/.claude/rules/00-development-workflow.md" 2>&1 | head -3
done
```

**判据强度**：目录实体与规则文本两项都是实测，足以据以行动。“harness 会加载 worktree 自己那份 `.claude/rules/`”一项，对两棵 job worktree（在主仓库目录之外、自身即项目根）置信高；对两棵嵌套在 `.claude/worktrees/` 下的，置信中上——本次会话的旁证是：我的 cwd 是 `/home/xp/src/ghc-api-proxy-py/.dev`，注入的正是**外层**仓库的 `.claude/rules/00-development-workflow.md`，说明规则是按 cwd 向上就近解析的，而这两棵 worktree 自身目录里就有 `.claude/rules/`。

**未做修复**（本次只读）。可选处置方向留给主会话裁决：把 worktree rebase／cherry-pick 到含 `0a72f52` 的基线；或在合并前用一道检查拦住重新出现的 `docs/tmp/` 路径；或确认这些 worktree 已无活跃写者后清理。**注意 `.claude/worktrees/*` 两棵按 `git status` 判断可能仍是活跃的，删除属破坏性操作，需用户逐项授权。**

---

## M-1 [major] `README.md` 三处指向 `docs/agents/` 未被 `0a72f52` 修掉；工作树之所以干净，是并行会话一份未提交的重写顺带删掉了那一节

`0a72f52` 的提交信息声称修的是 “every comment, instruction and unit-file line naming them”，并逐一交代了故意留下的两个文件（`src/app/cli.py`、`tests/unit/server/test_http_client_build.py`，理由是别的会话已暂存）。**`README.md` 没被提到，也没被改。**

`0a72f52` 里 `README.md` 的三处：

- `README.md:56`：`行为规范以 [docs/.human-controlled](docs/.human-controlled) 为准；各专题的开发文档在 [docs/agents](docs/agents)。`
- `README.md:58`：`…暂以代码与 `docs/agents/` 下相关话题为准。`
- `README.md:59`：`systemd socket activation、优雅退出与 cgroup v2 部署模板见 [docs/agents/deployment-systemd](docs/agents/deployment-systemd/README.md)。`

`README.md` 是 README，是新人和新 agent 的首要入口，第 56 行更是直接以“各专题的开发文档在这里”的口吻做路由——这正是命题要防的那种指向。

**为什么当前 `rg` 看不到它**：工作树里的 `README.md` 被并行会话整体重写成了产品 README（把“开发验证”一节连同这三行一起删了），且该重写**未暂存也未提交**（`git status` 为 ` M README.md`）。也就是说，改后文本干净是**偶然的、且依赖别人一份随时可能被丢弃的改动**；那份重写一旦被 discard，`README.md` 立即回到指向一个不存在的目录。

**根因值得记下**：`0a72f52` 大概率是用工作树 `rg` 找的引用面，而工作树当时已被同伴的未提交重写“洗白”了 README——**在有并行未提交改动的仓库里，用工作树 grep 判断“还有没有残留”会漏掉已提交状态里的残留**。正确判据是 `git grep <commit>` 或 `git grep --cached`。

**复核命令**：

```bash
R=/home/xp/src/ghc-api-proxy-py
git -C "$R" grep -n -e 'docs/tmp' -e 'docs/agents' 0a72f52 -- README.md   # 提交态：3 处
rg --hidden -n 'docs/agents' "$R/README.md"; echo "rg exit=$?"            # 工作树：0 处，exit 1
git -C "$R" status --porcelain -- README.md                               # ' M'：改动未暂存未提交
```

**降级为 major 而非 blocker 的理由**：README 的三处是“去哪儿读”，不是“把新报告写哪儿”，单靠它不足以让 agent 新建 `docs/tmp/`；但第 56 行会让人相信 `docs/agents/` 仍是开发文档的正式落点，配合 B-1 的实体目录就足够危险。

---

## M-2 [major] 新规则要求把报告写进 `.dev/docs/…`，但 `.dev/` 只存在于主工作树，且规则没说这一点

`.claude/rules/00-development-workflow.md:39`：

> file one under the owning topic's `.dev/docs/<topic>/reports/`, or under `.dev/docs/tmp/` when the topic is not yet clear.

同一份规则第 37 行也只说 “`.dev/` is a separate repository, ignored by this one”，**没说它在哪棵树**。而实测：四棵 worktree 全都没有 `.dev/`（`.dev/` 被主仓库 gitignore，worktree 不会带上它）。

于是在 worktree 里工作的 agent 面对的是一条无处落地的指令，它的两种典型收场都不好：

1. 在 worktree 内 `mkdir -p .dev/docs/tmp` 就地写——文件落进一个被 gitignore 的、随 worktree 一起被清理的目录，等于写完即丢；项目规则本身还写着 worktree 干净后可以移除。
2. 判断这条指令不适用，退回 worktree 自己的 `docs/tmp/`——直接汇入 B-1。

用户级全局规则确实写了“落盘的报告产物应放入主工作树而非隔离工作树”，但**项目规则是更近的规则**，读者不一定回退到全局规则去补这一句；且项目规则在这里给的是一个看起来完整、实则漏了根路径的具体路径。

**复核命令**：

```bash
R=/home/xp/src/ghc-api-proxy-py
for wt in "$R/.claude/worktrees/delivery-keepalive" "$R/.claude/worktrees/upstream-error-events" \
          /home/xp/.claude/jobs/405f4b84/tmp/slice0/wt /home/xp/.claude/jobs/826d4cda/tmp/review; do
  printf '%s -> ' "$wt"; [ -d "$wt/.dev" ] && echo "HAS .dev" || echo "no .dev"
done
rg -n '\.dev/' "$R/.claude/rules/00-development-workflow.md" | rg -c '主工作树|main worktree'; echo "exit=$? (1=规则里没这句)"
```

**建议方向**（不自行实施）：在第 37 行给 `.dev/` 加一句“位于主工作树根目录；在隔离 worktree 里工作时报告仍写进主工作树的 `.dev/`”。

---

## m-1 [minor] `.github/copilot-instructions.md:14` 的绝对断言在四棵 worktree 里不成立

> `docs/tmp/` and `docs/agents/` no longer exist — do not recreate them.

对主工作树与 `main` 的提交态成立（`git ls-tree -r --name-only HEAD -- docs/` 只返回 `docs/.human-controlled/*`），对 B-1 列出的四棵 worktree 不成立。读者在那些树里会亲眼看到这句话被现场证伪，进而有理由怀疑整条指令过时——**一条能被读者当场证伪的断言，比一条模糊的断言更有害**。

同样的问题以较弱形式存在于 `.claude/rules/00-development-workflow.md:39` 的 “both were emptied into `.dev/docs/` on 2026-08-21”，不过那句带了日期和成因，读者更容易理解成“主线上已搬完”而非“磁盘上处处没有”。

建议把断言限定到主分支／主工作树（例如 “no longer exist on `main`”）。

---

## m-2 [minor] 新规则里的活文档清单与 `.dev/README.md` 的布局块对不齐

- 规则 `:37` 列 `spec.md`, `status.md`, `plan.md`, `deferred.md`，**没有 `README.md`**；而 `.dev/README.md:29` 把 `README.md` 定义为话题的“入口：本目录有什么、怎么读”，是这套布局里唯一有导航职能的文件。
- 反过来 `.dev/README.md` 的布局块与第 41 行加起来列了 `README.md` / `spec.md` / `deferred.md` / `decision.md` / `decision-pending.md` / `status.md`，**没有 `plan.md`**；而 `plan.md` 实际在用（`httpx2-migration/plan.md`、`service-cutover/plan.md`、`systemd-rolling/plan.md`、`systemd-runtime/plan.md`）。

两处都写了省略号，所以不是硬矛盾，但一份写给“该往哪儿放”的读者的清单，漏掉唯一的入口文件是有代价的。

**复核**：`fd --max-depth 2 '^(plan|status|spec|deferred|README)\.md$' /home/xp/src/ghc-api-proxy-py/.dev/docs`

---

## m-3 [minor] 规则对 `.dev/` 的重述没有回指权威源

`.claude/rules/00-development-workflow.md:37` 重述了 `.dev/` 的三条性质（独立仓库、被 gitignore、随时提交但绝不推送），但没有链接回 `.dev/README.md`。`.dev/README.md:19-21` 才写了“绝不推送”背后那个**已经接好线的按钮**——`.dev` 的 `origin` 指向主项目同一个公开 GitHub 仓库（实测：`gh_puxu-msft:puxu-msft/ghc-api-proxy-py.git`）。规则里的 “never push” 因此读起来像一句原则性谨慎，而不是一个具体危险。

按 `one-authority-allows-contextual-restatement`，重述应当带回指。建议在该句尾加 `（see `.dev/README.md`）`。

---

## m-4 [minor] `contrib/systemd/ghc-api-proxy.service` 的 `Documentation=` 被机械重指到一个不会随部署分发的路径

`0a72f52` 把它从 `/opt/ghc-api-proxy/docs/agents/deployment-systemd/README.md` 改成 `/opt/ghc-api-proxy/.dev/docs/deployment-systemd/README.md`。`.dev/` 被 gitignore、不进主分支、也不随部署走，所以部署机上这个路径同样不存在。

这一条**已经被记录为待用户裁决**（`.dev/docs/docs-tmp-migration/README.md:75` 明确写了“无论指哪儿这一行都不完全成立”），因此不是漏项，只在这里做交叉确认，并指出它与命题无关——不会诱导任何人重建 `docs/agents/`。

---

## 核对通过、无问题的项

以下五项我按“待推翻”去查，没查出问题，记录在此以免下一个人重查。

1. **指令面枚举已穷举。** 主工作树能对 agent 下指令的位置只有：`CLAUDE.md`、`.claude/rules/00-development-workflow.md`、`.claude/skills/{project-review-principles,real-copilot-backup-canary}/SKILL.md`、`.claude/settings.json`、`.github/copilot-instructions.md`、`README.md`、`TODO_CURRENT.md`。**不存在** `.claude/agents/`、`AGENTS.md`、`GEMINI.md`、`.mcp.json`、`.cursorrules`、`CONTRIBUTING.md`；`.claude/settings.json` **没有 `hooks` 键**（只有 `permissions` 与 `enabledPlugins`）。
   ```bash
   R=/home/xp/src/ghc-api-proxy-py
   fd --hidden --type f . "$R/.claude" --exclude worktrees
   fd --hidden --type f . "$R/.github"
   fd --hidden --max-depth 1 --extension md . "$R"
   fd --hidden --max-depth 2 '(AGENTS|GEMINI|CONTRIBUTING|\.cursorrules|\.windsurfrules|\.mcp\.json|\.aider)' "$R" \
      --exclude .claude/worktrees --exclude .git --exclude .dev
   rg -c 'hooks' "$R/.claude/settings.json" || echo "no hooks key"
   ```

2. **`CLAUDE.md:9` 的“有意未改”确已记录。** `.dev/docs/docs-tmp-migration/README.md:76` 原文：“**CLAUDE.md 第 9 行已过时**，说「曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移」——迁移已经做完。该文件由用户控制，未改动。” 这是漏项与有意保留的区分点，记录到位。**顺带一个低权重观察**（仅供参考，不作决策依据）：本次会话 cwd 在 `.dev/` 时，注入到上下文里的是外层的 `.claude/rules/00-development-workflow.md`，而**项目根的 `CLAUDE.md` 没有被注入**——若这个行为稳定，则 `CLAUDE.md:9` 的实际到达率低于规则文件，那条过时句的风险相应更低。样本量为 1，未做对照实验。

3. **归档报告原件里的旧路径确属有意保留，且理由成文。** `.dev/docs/docs-tmp-migration/README.md:58` 与 `.dev/README.md:48` 两处互相印证：报告里的 `docs/tmp/xxx.md:251` 是当时那一刻的快照，改写等于伪造记录；约 2400 处保持原样。

4. **迁移数字全部对得上。** `.dev/README.md:70` 的“417 份报告与 8 个话题目录”是精确的，不是约数：
   - `0b01cdc` 共 106 条纯删除（`docs/tmp/` 63 + `docs/agents/` 43），其余 354 份原本就未被跟踪 —— 与 README 的“300 多份本来就未被跟踪”一致。
   - `docs/agents/` 恰好 8 个话题目录：`anthropic-responses-bridge`、`delivery-keepalive`、`deployment-systemd`、`documentation-restructure`、`httpx2-migration`、`service-cutover`、`systemd-rolling`、`systemd-runtime`。
   - `.dev` 接收提交 `5e94b75` 为 482 个纯新增，拆开是：`docs/<topic>/reports/` 414（其中 10 份是本次搬迁自己的 `docs-tmp-migration` 批次报告，不属于被搬的 417）+ `docs/tmp/` 14（13 份未分类 + 1 份 `.md~` 残件）+ 43 份活文档 + 11 份 `docs-tmp-migration` 的 `BRIEF.md`／`batches/`。404 + 13 = **417** ✓，43 ✓。
   ```bash
   R=/home/xp/src/ghc-api-proxy-py
   git -C "$R" show --name-status --format= 0b01cdc | awk 'NF{print $1}' | sort | uniq -c
   git -C "$R" show --name-only --format= 0b01cdc | rg '^docs/agents/' | cut -d/ -f3 | sort -u
   git -C "$R/.dev" show --name-only --format= 5e94b75 | rg '^docs/[^/]+/reports/' | cut -d/ -f2 | sort | uniq -c
   ```

5. **“主仓库 `docs/` 现在只剩 `docs/.human-controlled/`”成立。**
   ```bash
   git -C /home/xp/src/ghc-api-proxy-py ls-tree -r --name-only HEAD -- docs/ | cut -d/ -f1-2 | sort -u
   ls -a /home/xp/src/ghc-api-proxy-py/docs/
   ```
   两条都只返回 `.human-controlled`。另外新规则文本本身是可执行的：话题明确 → `.dev/docs/<topic>/reports/`，话题不明 → `.dev/docs/tmp/`，两条落点都与 `.dev/README.md:36,64` 及磁盘实况一致（20 个话题有 `reports/`，10 个 `archive-*/` 目录存在）。**唯一的可执行性缺口是 M-2 的根路径。**

---

## 未做的事

- 未修改任何被检文件。本报告是本次会话唯一的写入。
- 未对四棵 worktree 做任何操作（不 rebase、不删除、不改其中的规则文件）——删除或改写活跃 worktree 属破坏性操作，需用户逐项授权。
- 未验证 job worktree（`/home/xp/.claude/jobs/*`）自带规则文件的逐行内容，只验证了两个目录实体存在。若要把 B-1 的处置扩展到它们，需补这一步。
