# 两份收尾文档独立事实核查（2026-08-22）

## 范围与方法

核查对象：

- `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md`

只核事实，不评价文风。主仓库仅做只读查询；测试与探针在临时目录运行。本报告是唯一写入物。

用户要求先调用 `my-skills:as-reviewer`；当前 harness 的 skill 注册表未列出该项，显式调用返回 `Unknown skill: my-skills:as-reviewer`。这是工具能力缺失，不妨碍按用户给定判据完成核查。

初始观测时主仓库 `HEAD` 为 `5cb8dcf298b330e8dfd4166edb725963e80f383f`，分支状态为 `main...origin/main [ahead 32]`。工作树已有多项同伴未提交改动，后续会明确区分 `HEAD` 提交态与工作树叠加态。该仓库没有 `.codegraph/`，故采用 `git`、`rg`、直接读文件与隔离副本运行。

## 核查进度

- [x] 两份文档逐条断言账本
- [x] 提交存在性、祖先关系与提交内容初核
- [x] 提交归属与提交计数
- [x] `1b0cdd2` / `8703cad` / blob 归因链
- [x] CLI、环境变量与旧 import 代码事实
- [x] 当前 `HEAD` 干净归档全量测试
- [x] systemd 子进程探针实跑与证明边界
- [x] 反向断链与漏报扫描
- [x] 分级发现与总判决

## 已确认事实：七个交付提交

命令：

```bash
for c in ff0ac3c 5a1bb94 b9939ca d49fe23 5fc9dc4 92725a4 5cb8dcf; do git -C /home/xp/src/ghc-api-proxy-py cat-file -t "$c"; git -C /home/xp/src/ghc-api-proxy-py merge-base --is-ancestor "$c" HEAD; done
git -C /home/xp/src/ghc-api-proxy-py show --stat --oneline --summary ff0ac3c 5a1bb94 b9939ca d49fe23 5fc9dc4 92725a4 5cb8dcf
```

七个短哈希都唯一解析为 commit，且在初始观测 `HEAD=5cb8dcf` 下全部是 `HEAD` 祖先。逐提交 patch 与文档 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:8-14` 的内容摘要一致：`ff0ac3c` 切出 `gen-config` 并删除 `start --generate-config`；`5a1bb94` 收窄 token 环境变量并修复配置前缀冲突；`b9939ca`、`d49fe23`、`5fc9dc4` 完成所述源码与 component test 搬迁；`92725a4` 加覆盖确认；`5cb8dcf` 恰好修改 5 个 `exp/` 脚本的两个旧 import。

`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:8` 所列四个私有索引提交也都存在且为 `HEAD` 祖先。按 rename detection 计，各提交有 17、49、7、2 个 path entry，去重后 63 个路径；“共约 70 条路径”是近似陈述，没有造成范围误导。

## 发现 F1——minor：会话时间窗、提交数和第七个提交不能同时成立

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:2` 称会话窗口终止于 `2026-08-22T16:43Z`，窗口内 84 个提交，并把 `5cb8dcf` 算作本会话 7 个提交之一；同文档 `:14` 列出该提交。

**复现：**

```bash
git -C /home/xp/src/ghc-api-proxy-py rev-list --count --since='2026-08-21T17:40:18Z' --until='2026-08-22T16:43:00Z' HEAD
git -C /home/xp/src/ghc-api-proxy-py show --no-patch --date=iso-strict --format='%H%n%aI%n%cI%n%s' 5cb8dcf
```

第一条实际输出 `83`。`5cb8dcf` 的 author date 与 committer date 都是 `2026-08-22T16:46:17+00:00`，比所写窗口终点晚 3 分 17 秒。把它纳入才得到 84 个提交。因此，窗口实际只含 83 个，文档又把窗口外的第七个本会话提交列入交付。这是普通事实计数错误，既不是 false-green，也不是 false-red。

**级别理由：** 不影响代码与测试结论，但会误导后续按时间窗对账会话归属，故为 minor。

**证据权重：** 足以直接修正文档；依据是 Git commit object 的时间戳与 `rev-list` 对同一明确 UTC 闭区间的计数，而不是工作树状态。

## 当前 HEAD 干净归档全量测试

按任务给出的命令结构，在一次 Bash 调用中重新读取当时的 `HEAD`、归档、证明 import 来源，再跑全量测试。并行会话已在初始观测后推进分支，因此本轮冻结到：

- `H=c796396378938ae5d5e136ea019832797b6c3691`
- `D=/tmp/ghc-review-current-head-G0byZU`
- import 证明输出：`/tmp/ghc-review-current-head-G0byZU/src/app/__init__.py`，明确位于 `$D` 下
- pytest 实际结果：`1 failed, 1795 passed, 2 skipped in 109.31s`
- 唯一失败：`tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses`
- 失败形状：归档内 `docs/.human-controlled/config.example.yaml` 含 `upstream_request_retry.strategies.streamReplay.max_retries`，而同一归档内 `ProxyConfig` 以 `extra="forbid"` 拒绝该键

复现命令：

```bash
H=$(git -C /home/xp/src/ghc-api-proxy-py rev-parse HEAD)
D=$(mktemp --directory /tmp/ghc-review-current-head-XXXXXX)
git -C /home/xp/src/ghc-api-proxy-py archive "$H" | tar --extract --directory "$D"
cd "$D" && PYTHONPATH="$D/src" /home/xp/src/ghc-api-proxy-py/.venv/bin/python -c "import app; print(app.__file__)"
cd "$D" && PYTHONPATH="$D/src" /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

这不反证 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:37` 对较早 `8469cfa` 的点时结果：任务明确要求改测当前 `HEAD`，且 `c796396` 比 `8469cfa` 晚很多个并行提交，测试总量与 authoritative document 的入树状态都已经变化。它也不是本会话文档的漏报缺陷。当前候选 HEAD 本身是红的，则是**强到足以阻止把 `c796396` 宣称为全量通过**的实时事实；失败是否由稍后的并行工作修复，需要按新的 HEAD 重测。

## 已确认代码事实

以下都以同一干净归档 `c796396` 为准，避免共享工作树中 `src/app/cli.py` 等未提交内容污染结果。

### CLI

- `/tmp/ghc-review-current-head-G0byZU/src/app/cli.py:40-46` 把 `out_path` 声明为无默认值的 Typer positional argument；实跑 `python -m app gen-config` 输出 `Missing argument 'out_path'` 并返回 2。
- `/tmp/ghc-review-current-head-G0byZU/src/app/cli.py:55-60` 在写文件前对既有路径调用 `typer.confirm(..., abort=True)`。实跑现有文件加 `</dev/null` 返回 1，前后 SHA-256 都是 `fa1332...4126`；实跑 `yes | python -m app gen-config <existing>` 成功，生成文件 SHA-256 与 bundled config 同为 `7c0ebd...43160`。
- `/tmp/ghc-review-current-head-G0byZU/src/app/cli.py:217-239` 的 `start` signature 没有 `generate_config`；实跑 `python -m app start --generate-config` 输出 `No such option: --generate-config` 并返回 2。正向对照是同一 signature 中实际存在的 `--config`（`:231-234`）。
- 对旧默认路径的理由也成立：`ff0ac3c^:src/app/cli.py:242` 用 `config_file_path()`，而 `ff0ac3c^:src/app/config/loading.py:106` 用 `spec_config_file_path()`；`ff0ac3c^:src/app/config/paths.py` 分别把它们置于 platformdirs 的 user config path 与 user data path。

### Token 与环境配置

- `/tmp/ghc-review-current-head-G0byZU/src/app/model_provider/ghc_client/auth/providers.py:56-79` 的 `EnvTokenProvider` 只对 `GITHUB_TOKEN_VARIABLE` 做一次 `os.environ.get`。实跑只设置 `COPILOT_API_GITHUB_TOKEN`、`GH_TOKEN`、`GITHUB_TOKEN` 得到 `None`；再设置项目变量得到 `TokenInfo(token='ours', source='env', ...)`。
- `/tmp/ghc-review-current-head-G0byZU/src/app/config/loading.py:20-28` 把该常量解析为 `GHC_API_PROXY_GITHUB_TOKEN` 并收入 `NON_SETTING_VARIABLES`；`:122-146` 在配置映射前排除集合成员。正向对照实跑同时传 `GHC_API_PROXY_PORT=4242` 与 token 后，`environment_values` 输出 `{'server': {'port': '4242'}}`，证明探针既能读取普通配置，又确实排除了 token。

### 旧 module import 的否定断言

先跑正样本：

```bash
git -C /home/xp/src/ghc-api-proxy-py grep -n -E '^(from|import)[[:space:]]+app\.model_provider\.ghc_client([[:space:].]|$)' c796396 -- '*.py'
```

得到 72 个实际 import；随后把模式中的新前缀换成 `app\.(auth|ghc_client)`，退出码为 1 且零输出。另用 `rg` 扫同一归档全部 `*.py`、`*.md`，旧名只剩 `/tmp/ghc-review-current-head-G0byZU/src/app/model_provider/ghc_client/__init__.py:6,9` 的历史 docstring 提及；没有实际 import。该否定断言已通过有分辨力的正样本对照。

## 发现 F2——minor：token 前缀冲突的诊断细节已被同窗口内后续提交改写

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:22` 用现在时称 token 与配置的 `GHC_` 前缀冲突，若不排除会成为顶层 `api_proxy_github_token`。

**反证：** 同一文档所写会话窗口内的后续提交 `c5b9875` 把 `ENV_PREFIX` 从 `GHC_` 改成 `GHC_API_PROXY_`，并把 token 构造式从 `f"{ENV_PREFIX}API_PROXY_GITHUB_TOKEN"` 改成 `f"{ENV_PREFIX}GITHUB_TOKEN"`。当前干净归档 `/tmp/ghc-review-current-head-G0byZU/src/app/config/loading.py:20-28` 也明确写着：若不排除，形成的顶层键会是 `github_token`，不是 `api_proxy_github_token`。

核心判断——token 必须被 `environment_values` 排除，否则启动配置校验失败——仍然成立；过期的只是前缀名和错误字段路径。它不是 false-green，但会让按文档复现的人期待错误的 ValidationError 字段，故为 minor。

**证据权重：** 足以直接更新 closeout 的现状表述；提交 patch 和当前归档一致，且 `c5b9875` 是所列 session window 内、`HEAD` 祖先上的提交。

## 已确认事实：共享索引事故与后续 `cli.py` 回退

### 20:13 索引快照

`91f67a1` 是 parent 为 `2bcf03b` 的 commit，committer date 为 `2026-08-21T20:13:13+00:00`。重算 `git diff --find-renames --name-status 91f67a1^ 91f67a1` 恰好得到 51 个路径；把这 51 个路径与六个本会话提交 `ff0ac3c 5a1bb94 b9939ca d49fe23 5fc9dc4 92725a4` 的路径并集相交，恰好得到 43 个，余下 8 个恰好是文档所称同伴在制路径。`tests/unit/test_cli.py` 在该快照相对 parent 的 numstat 是 `0 39`，patch 确实把 39 行新增测试表现为删除。

`408e3fc`、`0a72f52` 都存在且是当前 `HEAD` 祖先；前者只改了另一组 pipeline / translation 文件，后者只改文档路径引用。逐树查询显示两个提交之后 `gen-config`、token 常量和新 module path 仍在，旧源码 package path 仍为空，未夹带上述回退。

原 backup ref 已不在；当前真实 ref 是：

```text
refs/evidence/260821-stale-index-snapshot  91f67a186292b283f16481196f854749eb6c0842
```

它与当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:35-43` 的“先删后恢复”结论一致。

### 23:02 索引与 `1b0cdd2`

以下 object identity 全部直接用 `git rev-parse <ref>:src/app/cli.py` 重算：

```text
8703cad^  b1f1e7a123efe206a2294e9d1f3014c6cf0243ed
8703cad   1e966a4fe026b8b64b4ee6ecd6e36ca52516b388
1b0cdd2^  1e966a4fe026b8b64b4ee6ecd6e36ca52516b388
1b0cdd2   9ac78d4dcfa2645214270b6bf6f6198a124c41cc
8469cfa^  9ac78d4dcfa2645214270b6bf6f6198a124c41cc
8469cfa   e459129df5743ada4741f8f5fa07e8f3f00b4014
92725a4   b1f1e7a123efe206a2294e9d1f3014c6cf0243ed
91f67a1   b09429bace0d67b9639bcbe92d6af0fe66a9c98e
```

`git show 8703cad -- src/app/cli.py` 确实给两个 serve path 增加 `proxy_from_cli` 并传给 `build_http_client`；`git show 1b0cdd2 -- src/app/cli.py` 恰好撤掉这些参数，同时保留一处文档路径改写；`8469cfa` 恰好修回参数。`git log 8703cad..8469cfa -- src/app/cli.py` 只列 `1b0cdd2` 和 `8469cfa`，所以坏状态一直延续到后者。

独立运行时复现也成立：

- 在 `/tmp/ghc-review-1b0cdd2-C9nDH1` 归档中，先证明 `app.__file__` 位于该目录，再跑 systemd test，得到唯一失败 `TimeoutError`。
- 同一坏归档用当前文档探针可直接打印 `/tmp/.../src` 的 `PYTHONPATH`、token 变量名，以及 `serve_inherited` 内 `TypeError: build_http_client() missing 1 required keyword-only argument: 'proxy_from_cli'`。
- 另以相同 `_service_environment` 启动普通 `python -m app start --host ... --port ...`，返回 1，并在 `_serve_pipeline` 得到同一 `TypeError`。所以“`start` 与 `start --fd` 两条入口都坏”不是只由静态 patch 推断。
- 在 `/tmp/ghc-review-8469cfa-nlC8ib` 干净归档中先证明 import 来源，再跑全量，实际得到 `1660 passed, 3 skipped in 111.62s`，与文档的点时数字完全一致。

跨会话 transcript 的原始 tool result 还直接证明了 `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/6db002ea-ffcd-428a-9e04-b13de5f4842e.jsonl:90`：`2026-08-21T23:02:41.452Z` 时 `HEAD=8703cad`，共享 index 中 `src/app/cli.py` 正是 `9ac78d4d...`，而 HEAD blob 是 `1e966a4f...`。三分钟后 `1b0cdd2` 的 commit time 是 `23:05:32`。这支持 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:76` 的时间线。

**证据权重：** 上述提交归因、blob identity、两条真实进程入口与 `8469cfa` 点时全量数字均足以据此行动。

## systemd traceback 探针核查

当前文档 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:79-120` 的代码按其 `:112-114` 调用方式，在坏提交归档根目录实跑成功；自证行指向坏归档自身的 `src`，最后 4000 字符包含根因 `TypeError`。它不是 false-green。

“不证明什么”的声明诚实：探针只复用该 unit 的 setup 并启动 `--fd 3`，不发送 backlog request、不检查 readiness、不发 SIGTERM，也根本不走 standalone path。因此它确实不覆盖 `test_systemd_units.py` 的 backlog/socket-handover 场景或优雅退出。更严格地说，它连 `test_systemd_pipeline_unit.py` 的 success-path HTTP assertions 也没复现；但文档称它为“单条用例的复现”是诊断语境下的缩写，后面的明确排除项没有夸大证明力。

`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:118` 还把“手搓环境会复现另一个场景”明确标为未实测设计判断，没有把推理冒充观测。

## 发现 F3——minor / false-green：两次变异并非都由 `git status` 空输出确认逐字节还原

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:73` 称“两次变异均逐字节还原并以 `git status` 空输出确认”。

**反证：** transcript 中第一次 module-boundary 变异的目标文件原先干净，恢复后该 path 的 status 的确为空；但第二次 `cli.py` 变异发生在尚未提交的业务改动上。`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/bbb2909c-7abe-4d22-85bc-d33af0b9eec7.jsonl:1173` 的实际恢复后输出是：

```text
MM src/app/cli.py
 M tests/unit/test_cli.py
```

命令只复查了 `typer.confirm` 行存在以及预期业务 diff，并没有 `cmp` 或 hash 对比备份。`cp` 恢复和复跑 5 tests 都成功，随后 `92725a4` 的 tree 也含完整确认逻辑，因此没有发现实际残留；错误在于把一个没有发生的“status 空输出”写成验证证据。

**级别理由：** 这是 false-green 式证据归因错误，但最终 tree 与测试证明实际恢复正确，未留下产品缺陷，故为 minor。

## 发现 F4——minor：`1658` 是 passed 数，不是“本次测试总条数”

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:65` 称“本次 1658 条里只有”那条 subprocess test 变红。

**反证：** 原始 clean-HEAD 测试输出位于 `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/bbb2909c-7abe-4d22-85bc-d33af0b9eec7.jsonl:1474`，摘要是 `1 failed, 1658 passed, 3 skipped`。所以 1658 是绿灯数；不计 skip 的运行条数为 1659，计入 skip 的 collected outcome 为 1662。核心事实“只有这一条红，其余运行项绿”成立。

**级别理由：** 不影响失败定位和测试分辨力，只是把 passed count 写成总数，故为 minor；既不是 false-green，也不是 false-red。

## 发现 F5——minor / false-green：`2bcf03b..8f654b44` 的范围数字套用了较早 HEAD-A

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:80` 称范围 `2bcf03b..8f654b44` 有 22 commits、72 个 commit-path 对，并概括为三个探测器加正样本对照。

**复现：**

```bash
git -C /home/xp/src/ghc-api-proxy-py rev-list --count 2bcf03b..8f654b44
# 每个 commit 再跑 git diff-tree --no-commit-id --name-only -r 并求和
```

实际是 23 commits、76 对、0 merge。被引用报告 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-audit-other-stale-blobs-committed.md:101-103` 清楚说明 22/72 是较早 `HEAD-A=51196e24` 的主扫描；`:245` 说明后到的 `8f654b44` 只补跑 detector 1 和 2 的 4 个路径，而不是再跑全部三个。

**级别理由：** 这是范围摘要的 false-green：把 HEAD-A 的数套到 HEAD-B，并略微夸大最后一提交的 detector coverage。不过被引用报告公开写明增量扫描边界，detector 2 对新增四对均为 `ok`，没有因此产生相反代码结论，故为 minor。

## 发现 F6——minor：引用 audit report 的路径已断

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:80` 给出 `docs/tmp/260822-audit-other-stale-blobs-committed.md`。

**复现：** 先以 `git ls-tree -r --name-only HEAD docs/.human-controlled` 得到 14 个 tracked path，证明 tree 查询有效；随后 `git ls-tree ... docs/tmp` 为零。文件真实存在于 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-audit-other-stale-blobs-committed.md`，而 `/home/xp/src/ghc-api-proxy-py/docs/tmp/...` 不存在。项目规则也明确禁止重新创建主仓库 `docs/tmp/`。

**级别理由：** 读者仍可按文件名在 `.dev` 找到报告，但写下的路径不能解析，属于 minor 断链。

## 发现 F7——minor：恢复时间与“24 次引用”均不符合当前 artifact

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:39` 称 ref 于“同日 16:5x”恢复，并称两份报告合计引用 `91f67a1` 24 次。

**反证：** 当前 loose ref `/home/xp/src/ghc-api-proxy-py/.git/refs/evidence/260821-stale-index-snapshot` 的 mtime 是 `2026-08-22 17:01:21.114933815 +0000`；原始 transcript 的 update-ref tool result 也是 `2026-08-22T17:01:21.202Z`。按 literal prefix `91f67a1` 计，当前两份文件分别有 6 与 11 次，共 17 次，不是 24 次。

**级别理由：** ref 已正确恢复且 target 正确，证据不再有 gc 丢失问题；错的是时间与引用计数两个审计细节，故为 minor。

## 发现 F8——minor：七次 `update-ref` 不等于七次 CAS

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:67` 标题称“本会话七次 CAS”。

**反证：** 在声明的会话窗口内对 raw transcript 的 Bash tool inputs 枚举，确有 7 条 `update-ref` 命令，但只有 5 条带 expected-old OID；其中第一条又被 PreToolUse hook 拦截，未执行。真正成功执行的 CAS 是四次业务更新 `b9939ca`、`d49fe23`、`5fc9dc4`、`92725a4`。另外两条分别是创建 backup ref 与 `update-ref -d` 删除 ref，都没有 expected-old OID，不是 CAS。

**级别理由：** 本节最终判断“没有触发 CAS 拒绝，七盏绿不能验证拒绝路径”方向仍对，甚至在正确计数后更强；错的是机制命名和次数，故为 minor，不是 false-green／false-red。

## 发现 F9——major / false-green：所谓“整个仓库”搜索仍会漏掉 tracked hidden files

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:31` 把 `rg -l <旧名> -g '!.git' .` 作为搜索整个仓库、仅排除 `.git` 与生成物的做法。

**反证与正样本：** 当前仓库有 tracked hidden file `/home/xp/src/ghc-api-proxy-py/.github/copilot-instructions.md:10`。先显式对该文件运行：

```bash
rg --line-number -F 'voting/graduation protocols' ./.github/copilot-instructions.md
```

得到正样本；再从仓库根按文档给出的命令形态运行：

```bash
rg --files-with-matches -F 'voting/graduation protocols' -g '!.git' .
```

退出码 1、零输出。原因是 rg 默认跳过 hidden path，并遵守 ignore files；`-g '!.git'` 不会开启 hidden / ignored surface。它可漏 `.github/`、`.claude/` 等 tracked 文件，正好违背“验收范围严格大于施工范围”的目标。当前 final-session tree 的旧 module 名经过 `git grep` 全 tracked tree 后只剩人写 requirement 与历史 docstring，因而**这次没有第二个漏改代码**；但文档留下的可复用命令仍是假绿探针。

**级别理由：** 这是本节唯一给出的全仓迁移判据，却结构性漏掉一整类 tracked path，未来可重复制造本次同型缺陷。它不是措辞问题，而是验证机制不可见，故为 major。可行方向是 tracked surface 用 `git grep`，如还要覆盖 untracked，再单独用 `rg --hidden --no-ignore` 加明确生成物排除；本评审不修改文档。

## 发现 F10——major：同一 live report 同时指示执行和禁止执行 `git read-tree 91f67a1`

**文档断言冲突：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-shared-index-left-reverting-head.md:29` 仍把 `git read-tree 91f67a1` 加粗标作“恢复办法”；同文件 `:35-43` 已裁决该对象只应作为 evidence anchor，`:41` 又加粗写“不要 `read-tree` 它”。

`91f67a1` 当前仍可由 `refs/evidence/260821-stale-index-snapshot` 到达，所以前一命令今天仍会成功，并把共享 index 替换成 2026-08-21 20:13 的 51-path 过期切片。`git read-tree` 不更新工作树，但会覆盖 index；如果同伴有 staged-only hunk，这种状态可能无法从当前工作树重建。遵守任务的只读约束，本评审没有实际执行该破坏性命令。

**级别理由：** 这是 live operational document 内互相否定的可执行指令，较早一条能直接重建本次事故形态并破坏共享 index，故为 major。不是 false-green／false-red，而是危险的现行指令冲突。

## 发现 F11——minor：`git archive` 副本并不缺 `pyproject.toml`

**文档断言：** `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-cli-and-module-move-closeout.md:116` 称“副本树（`git archive` 出来的）没有 `pyproject.toml`，`uv run` 起不来”。

**反证：** 本评审创建的三个 full-tree archive `/tmp/ghc-review-1b0cdd2-C9nDH1`、`/tmp/ghc-review-8469cfa-nlC8ib`、`/tmp/ghc-review-current-head-G0byZU` 都含 tracked `pyproject.toml`；`git ls-tree 1b0cdd2 pyproject.toml` 也直接列出它。archive 不含的是仓库自己的 `.venv`，不是 `pyproject.toml`。因此，直接指定主仓库现有 `.venv/bin/python` 是避免在副本里新建环境的高效做法，但文档给出的不能使用 `uv run` 的理由不成立。

**级别理由：** 推荐调用命令本身可用且本评审实跑成功；错误只在环境说明，故为 minor。

## 其余可验证断言账本

下列断言已逐项核对，未形成额外 finding：

| 文档位置 | 断言 | 结果与依据 |
|---|---|---|
| closeout `:2` | 收尾阶段 2 个 reviewer subagent、未创建 worktree | raw transcript 在 `16:48:10`、`16:48:33` 各有一次 `Agent`；当前两份报告都存在。声明窗口内的 tool-use 正样本有 145 次 `Bash`，`Agent=0`、`EnterWorktree=0`；全 session 也无 `git worktree add`。因此“收尾阶段 2 个、工作 session 未建 worktree”成立，时间窗／提交数另见 F1。|
| closeout `:4` | `.dev` 提交 `ccb1eba`、`a96b324`、`59543b1` 及修订 | 四个相关 commit（含当前修订 `66f5bd8`）都存在并是 `.dev HEAD` 祖先，commit subjects 与文档用途一致。|
| closeout `:22-23` | config path 理由、无 `--force`、stdin 行为 | old flag 与 loader 的两个 platformdirs path 已按历史 commit 直接核对；`yes | ...`、`</dev/null`、fresh path 和拒绝覆盖均在 clean archive 实跑，结果与文档一致。|
| closeout `:25` | “Imports nothing” 在改动前已失真且无测试守卫 | `b9939ca^:src/app/ghc_client/__init__.py` 仍有该句，同时 `errors.py:29` 已 import `app.pipeline.exceptions`；先用现有 module-boundary test 名作正样本，再搜 tests 中该旧句得到退出码 1。|
| closeout `:29` | 5 个 tracked `exp/` probe 遗漏并由 `5cb8dcf` 修复 | `git show 5cb8dcf` 恰好改 5 个 tracked 文件；AST 提取其 `app.*` imports 后逐一 `find_spec`，全部解析到 clean archive 自身的新 module 文件。|
| closeout `:37-39` | 三个失败探针故事 | f-string 构造式、porcelain 前导空格与 `f025e3c` blob 的原始命令／输出均在 session transcript 中；Git object 与当前历史可重算。未发现与结果相反之处。|
| closeout `:43-54` | ruff temp misclassification 与 `--stdin-filename` 修法 | transcript 保留了误排序形状以及稍后 `--stdin-filename` 的成功输出；本评审也在 clean archive 根以现有 venv 的 `ruff check --stdin-filename src/app/cli.py -` 重跑，输出 `All checks passed!`。|
| closeout `:56-65` | transcript commit harvesting 两向漏计 | raw transcript 的第一次 closeout 明确先算 3/缺 `5fc9dc4`，再按写仓库命令算出 6；`git -C` 形态确实不匹配所述 `git <subcommand>` pattern。最终 authority 若使用准确窗口，得到 83 commits 与窗口内 6 个本会话提交，进一步支持 F1。|
| closeout `:70-72` | 两次 mutation failure shape | transcript 原始输出分别是 1 failed + 4 passed，以及 subprocess `CalledProcessError`；prefix probe 得到 10 个 modules。failure shape 与文档一致；恢复证据的过度陈述另见 F3。|
| shared-index `:4,8-18` | stale-index 机制与 51=43+8 | commit-tree、index snapshot、diff partition 与 39-line reverse patch 全部可重算；`git update-ref` 不更新 index 的机制陈述与 object 现状一致。|
| shared-index `:22-33` | snapshot、43-path reset、8 peer paths、1643 passed + 1 unrelated failure | `91f67a1` object、parent、tree 与 51-path diff 均存在；raw transcript 的修复后测试摘要确为 1 failed / 1643 passed，失败名符合文档。没有在共享 index 重放 `reset`／`read-tree`，因为任务明确限定 Git 只读。|
| shared-index `:35-43` | ref 先删后恢复为 evidence anchor | 当前 ref target 为 `91f67a1`，且可达；“16:5x / 24 次”两个细节另见 F7，冲突恢复指令另见 F10。|
| shared-index `:47-61` | bad HEAD、worktree 假绿、clean archive、editable import 风险 | bad commit 的两条真实进程入口均重现 TypeError；raw transcript 同一 test 在工作树通过、clean archive 超时；本评审每轮 archive 都先打印 `app.__file__`，路径位于副本。|
| shared-index `:63` | archive 中的 tracked symlink | `git ls-tree HEAD refs/` 输出 mode `120000` 的 `refs/CLIProxyAPIPlus`，`readlink` 为 `/home/xp/src/refs/CLIProxyAPIPlus`。关于解引用工具的范围说明符合 symlink 语义。|
| shared-index `:67-71` | CAS refusal 路径没有被本 session 验到 | 四次成功业务 CAS 都无 expected-old mismatch；第一条同形命令是在执行前被 shell hook 拦下，不是 Git CAS refusal。本 session 的绿色结果对拒绝路径无分辨力；次数误称另见 F8。|
| shared-index `:74-80` | 两个 stale-index 时点、blob 与时间线、static audit blind spots | `91f67a1`、`8703cad`、`1b0cdd2` 的 commit times 与 blobs 全部重算一致；23:02 index tool result直接可见 `9ac78d4d`。引用 audit 的 qualitative conclusion 与六个 blind spots 确实存在；范围数字和路径分别见 F5、F6。|
| shared-index `:84-85` | 两次错误归因 | 对应 raw transcript 与 audit report 都保留了 25→40 depth 的修正以及用户指出 index 归因错误的过程；未发现反证。|

## 反向检查结果

- final-session tree `5cb8dcf` 上，以 87 个新 module 名命中作为正样本，再全 tracked tree 搜 `app.auth` / `app.ghc_client`，只剩 `docs/.human-controlled/module-org.md` 的规范性迁移描述和新 package docstring 的历史说明；没有 actual import、dynamic import string 或旧 package path。
- `src/app/auth`、`src/app/ghc_client`、`tests/component/ghc_client` 在 `5cb8dcf` tree 中均不存在；新 `tests/component/model_provider/ghc_client` 有 7 files。
- `start --generate-config` 在 executable CLI 上实跑为 no-such-option；final-session tree 余下两处文本命中在 `cli.py` 历史 docstring 与 2026-07-16 point-in-time acceptance report，不是现行入口或 runnable probe。`verification/final_acceptance/probes/00_cli_smoke.sh` 已由 `ff0ac3c` 更新为新命令。
- 5 个 `exp/` probe 的新 imports 均可解析。没有发现本会话代码在其它目录留下第二处坏 import。
- 反向扫描找到的漏报缺陷就是 F9（全仓搜索方法仍漏 hidden）、F10（live report 的 read-tree 指令冲突）、F6（报告路径断链）；未发现 blocker 级代码断链。

**证据权重：** 对“当前 session 交付没有第二处 actual old import”足以据此行动，范围固定为 commit `5cb8dcf` 的 tracked tree；不覆盖之后并行会话的未提交工作树内容。对 untracked / ignored surface 不作否定断言，这也正是 F9 要求把两个搜索 surface 分开说清的原因。

## 总结

### Major

- F9：全仓旧名搜索配方默认跳过 hidden / ignored surface，是可重复产生遗漏的 false-green。
- F10：同一 live incident report 同时把 `git read-tree 91f67a1` 写成恢复办法和禁止动作，前者会覆盖共享 index。

### Minor

- F1：会话窗口实际 83 commits，并且第七个本会话 commit 在窗口外。
- F2：token 前缀冲突的字段路径已由窗口内后续提交改写。
- F3：第二次 mutation 没有得到文档声称的 `git status` 空输出。
- F4：`1658` 是 passed count，不是总测试数。
- F5：audit 的 HEAD-B 范围实际 23 commits / 76 pairs，且最后 4 pairs 未跑 detector 3。
- F6：audit report 路径误写成已不存在的主仓库 `docs/tmp/`。
- F7：evidence ref 实际 17:01 恢复，当前两文档合计 17 次 literal 引用，不是 16:5x / 24 次。
- F8：7 次 `update-ref` 里只有 4 次是实际成功的业务 CAS。
- F11：full `git archive` 含 `pyproject.toml`，缺的是本地 `.venv`。

没有 blocker。提交内容、核心 CLI 行为、token 行为、module move、两个真实进程入口的坏状态、`8469cfa` 的修复与点时全量数字均得到独立证实；未发现第二处 actual old import。

最终复核时主分支已由并行会话推进到 `fb06150348b3ea4758ec838e0e9ea93ae0c3583d`，所有被核提交仍是其祖先。本文的 required current-HEAD test 则严格记录命令启动时冻结的 `c796396378938ae5d5e136ea019832797b6c3691`，不把稍后 HEAD 混入同一组数字。

执行卫生补记：为重做历史 Pyright 数字，我有一次误用 `uv run --active`，它短暂把主项目 `.venv` 内 editable `app` 的来源改成 `/tmp/ghc-review-1b0cdd2-C9nDH1`。发现后立即仅重装同版本、`--no-deps` 的 editable main project，最终 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python -c 'import app; print(app.__file__)'` 输出 `/home/xp/src/ghc-api-proxy-py/src/app/__init__.py`。主仓库代码、文档、Git index 与 refs 均未因此改变。

VERDICT: 0 blocker / 2 major / 9 minor
