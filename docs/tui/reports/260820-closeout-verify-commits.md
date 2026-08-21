# Request log 提交收尾独立验收

验收日期：2026-08-20

验收范围：`ea0417c4dd7509f4dc7f5be71e109a4fe1a3a0b1`、`b97930b9b3650f34e46d75edfdb31b5170e536b1`、归档测试快照 `bbbcb37118779009d839387aca3f452932841e1e`，以及工作树残留检查快照 `8a36fe3623c843c59a9b2e5ff225929ce94a9fe8`。

方法限制：全程未执行 `git add/commit/stash/checkout/restore/reset/clean/push`，未修改源文件。除本报告外，仅在 `/tmp/ghc-api-proxy-head-verify.T0cU3r` 创建了 HEAD 归档测试副本。

结论权重：以下结论均为“强到足以据此收尾”，依据是目标 commit 的不可变对象、逐行 blame、工作树与 HEAD blob 对比，以及从固定 commit 归档后运行的完整非 TUI 测试。唯一需要区分的是断言 1：目标提交没有夹带同伴行这一核心命题成立，但整条断言还要求三行当前仍未提交，该要求与事实不符，因此整条判为“不成立”。

## 结论总表

| 断言 | 判定 | 摘要 |
|---|---|---|
| 1. `ea0417c` 与 `b97930b` 没有混入同伴改动，且三行仍是当前未提交改动 | **不成立** | 两个目标 commit 的 delta 都没有触碰三行，因此“没有混入”成立；但三行早在目标提交之前已由 `40681ce`、`9e3d374` 提交，当前工作树与 HEAD 相同，并非未提交状态。 |
| 2. 两个提交合起来完整包含列出的 request log 改动 | **成立** | 所列生产代码逐行归属 `ea0417c` 或 `b97930b`，目标文件相对 HEAD 无工作树残留。 |
| 3. 检出的 HEAD 不再是调用方与定义方错开的半截状态 | **成立** | 固定归档 commit `bbbcb371…` 并强制从归档 `src` 导入后，得到 `1546 passed, 3 skipped`。提交较主会话的早期样本更新，所以测试数不是 `1528`。 |
| 4. 三个指定文件没有遗留本次改动 | **成立** | 在快照 HEAD `8a36fe36…` 上，三个工作树文件的 blob 均与各自 HEAD blob 完全相同，限定路径的 `git status --short` 为空。 |

## 1. 同伴三行是否混入目标提交

### 判定：不成立

这是合取断言。其核心部分——两个目标 commit 的 delta 没有引入、删除或修改三行——成立；“三行当前仍是未提交状态”不成立。

目标提交及父链为：

```text
$ git -C /home/xp/src/ghc-api-proxy-py show --no-patch --format='%H%n%P%n%s' ea0417c
 ea0417c4dd7509f4dc7f5be71e109a4fe1a3a0b1
 86f4a46cd7694710830290a4c6427f33f0de2c50
 feat: say on the line which endpoint a count came from

$ git -C /home/xp/src/ghc-api-proxy-py show --no-patch --format='%H%n%P%n%s' b97930b
 b97930b9b3650f34e46d75edfdb31b5170e536b1
 ea0417c4dd7509f4dc7f5be71e109a4fe1a3a0b1
 fix: let the line's verdict decide how the whole line reads
```

逐个对目标 delta 搜索三段开头，没有任何匹配：

```text
$ for commit in ea0417c b97930b; do git -C /home/xp/src/ghc-api-proxy-py diff-tree --no-commit-id -p "$commit" -- src/app/observability/request_log.py tests/unit/test_request_log.py | rg -F -e 'Named for the thing' -e 'The parenthetical is the trail' -e 'A route with no upstream counter'; done
<no output>
```

这三行已经存在于 `ea0417c` 的父提交 `86f4a46cd7694710830290a4c6427f33f0de2c50` 中，位置分别是 `src/app/observability/request_log.py:176`、`src/app/observability/request_log.py:178`、`tests/unit/test_request_log.py:97`。历史 pickaxe 进一步给出首次引入它们的目标提交之前的提交：

```text
$ git -C /home/xp/src/ghc-api-proxy-py log --reverse --format='%H %s' -S'Named for the thing' -- src/app/observability/request_log.py | <取首行>
40681ce34ca4376f965abfcd9ef5c2920a3a7c9f refactor: call the count line's ending what the config calls it

$ git -C /home/xp/src/ghc-api-proxy-py log --reverse --format='%H %s' -S'The parenthetical is the trail' -- src/app/observability/request_log.py | <取首行>
40681ce34ca4376f965abfcd9ef5c2920a3a7c9f refactor: call the count line's ending what the config calls it

$ git -C /home/xp/src/ghc-api-proxy-py log --reverse --format='%H %s' -S'A route with no upstream counter' -- tests/unit/test_request_log.py | <取首行>
9e3d3749e2a74ee212255870818bb505be55d1e3 fix: say why a token count is an estimate, not just that it is
```

在最终工作树快照 `8a36fe3623c843c59a9b2e5ff225929ce94a9fe8` 上，相关文件与 HEAD 的 blob 相同：

```text
src/app/observability/request_log.py HEAD=c2466c09fc3b3661c5455e6a5214531612436e22 WORKTREE=c2466c09fc3b3661c5455e6a5214531612436e22 equal=yes
tests/unit/test_request_log.py HEAD=6964ce228f4981119809b633725c001a4742fec7 WORKTREE=6964ce228f4981119809b633725c001a4742fec7 equal=yes
```

因此没有证据表明 `ea0417c` 或 `b97930b` 夹带了同伴三行；相反，证据明确显示它们由更早提交引入并被目标提交继承。需要否定的是“同伴原样保留为当前未提交改动”这一时态性子断言，而不是目标提交边界。

## 2. 两个提交是否完整包含列出的改动

### 判定：成立

两个提交各自只修改以下三个文件：

```text
src/app/observability/request_log.py
tests/unit/test_request_log.py
tests/unit/test_request_log_file.py
```

在 `b97930b` 的树上逐行检查并用 blame 追溯，所有指定生产代码都归属于这两个目标提交：

```text
src/app/observability/request_log.py:55   ea0417c4dd750  COUNT_TOKENS_SUFFIX = "-count-tokens"
src/app/observability/request_log.py:63   b97930b9b3650  STATUS_COLOURS: dict[LogStatus, str] = {"ok": GREEN, "fail": RED, "gone": YELLOW}
src/app/observability/request_log.py:110  ea0417c4dd750  count_tokens: bool = False
src/app/observability/request_log.py:294  ea0417c4dd750  label = f"{line.inbound_format}{COUNT_TOKENS_SUFFIX}" if line.count_tokens else line.inbound_format
src/app/observability/request_log.py:312  b97930b9b3650  def format_completion_line(line: RequestLine, *, status: LogStatus, unicode: bool = True, color: bool = False) -> str:
src/app/observability/request_log.py:325  b97930b9b3650  succeeded = status == "ok"
src/app/observability/request_log.py:334  b97930b9b3650  parts.append(paint(str(line.status_code), STATUS_COLOURS[status], color=color))
src/app/observability/request_log.py:373  b97930b9b3650  rendered = f"{rendered}: {paint(line.detail, STATUS_COLOURS[status], color=color)}"
src/app/observability/request_log.py:374  b97930b9b3650  if line.request_id and status != "ok":
src/app/observability/request_log.py:376  b97930b9b3650  rendered = f"{rendered} {paint(f'req={line.request_id}', DIM, color=color)}"
src/app/observability/request_log.py:380  b97930b9b3650  def status_for(status_code: int | None, *, override: LogStatus | None = None) -> LogStatus:
```

`req=<id>` 的代码位于 detail 拼接之后，并且函数随即返回，所以它只在 `status != "ok"` 时出现且处于行尾。`STATUS_COLOURS[status]` 同时用于状态码和 detail。`status` 是 keyword-only 必传参数，没有默认值。所列各点均不是只存在于当前工作树的内容；第 4 节的 blob 对比进一步证实这三个目标文件无残留。

## 3. HEAD 归档是否自洽

### 判定：成立

实际固定并归档的提交是：

```text
ARCHIVE_COMMIT=bbbcb37118779009d839387aca3f452932841e1e
ARCHIVE_DIR=/tmp/ghc-api-proxy-head-verify.T0cU3r
```

归档命令：

```sh
repo=/home/xp/src/ghc-api-proxy-py
tmp=$(mktemp -d /tmp/ghc-api-proxy-head-verify.XXXXXX)
head=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" archive "$head" | tar -x -C "$tmp"
```

先严格执行题面给出的测试命令：

```sh
cd /tmp/ghc-api-proxy-head-verify.T0cU3r
uv run --project /home/xp/src/ghc-api-proxy-py python -m pytest tests -q --ignore=tests/tui
```

它得到：

```text
1 failed, 1545 passed, 3 skipped in 101.87s
FAILED tests/http/test_pipeline_app.py::test_a_model_not_listed_as_searching_refuses_rather_than_answering_anyway
```

但导入来源探针证明，这次运行没有测试归档的生产代码，而是加载了共享工作树：

```text
cwd=/tmp/ghc-api-proxy-head-verify.T0cU3r
app=/home/xp/src/ghc-api-proxy-py/src/app/__init__.py
pipeline_app=/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py
```

因此该红灯不能用于否定归档 HEAD；它是题面配方中 `uv run --project` 选择共享项目安装源所造成的 provenance 缺陷。为使被测生产代码与归档 commit 一致，保持同一依赖环境并显式将归档 `src` 放在导入路径首位：

```sh
cd /tmp/ghc-api-proxy-head-verify.T0cU3r
PYTHONPATH=/tmp/ghc-api-proxy-head-verify.T0cU3r/src uv run --project /home/xp/src/ghc-api-proxy-py python -c 'import app, app.server.pipeline_app, pathlib; print("cwd=" + str(pathlib.Path.cwd())); print("app=" + str(pathlib.Path(app.__file__).resolve())); print("pipeline_app=" + str(pathlib.Path(app.server.pipeline_app.__file__).resolve()))'
PYTHONPATH=/tmp/ghc-api-proxy-head-verify.T0cU3r/src uv run --project /home/xp/src/ghc-api-proxy-py python -m pytest tests -q --ignore=tests/tui
```

修正后的来源与结果为：

```text
cwd=/tmp/ghc-api-proxy-head-verify.T0cU3r
app=/tmp/ghc-api-proxy-head-verify.T0cU3r/src/app/__init__.py
pipeline_app=/tmp/ghc-api-proxy-head-verify.T0cU3r/src/app/server/pipeline_app.py
1546 passed, 3 skipped in 108.05s
```

这足以证实固定 commit `bbbcb371…` 上不存在题述“调用方有新参数或新字段，而定义方还没有”的半截状态。测试数高于主会话的 `1528 passed / 3 skipped`，原因是实际归档的 HEAD 已前移；本报告不把不同 commit 的测试总数强行视为应相同。

另外，目标提交与文档提交均是归档 commit 的祖先：

```text
ea0417c4dd7509f4dc7f5be71e109a4fe1a3a0b1 ancestor-of HEAD
b97930b9b3650f34e46d75edfdb31b5170e536b1 ancestor-of HEAD
7e65993d28f4e07a4e6e64eba1d165017de211ef ancestor-of HEAD
```

## 4. 三个指定文件是否还有本次改动残留

### 判定：成立

此项使用报告写入前的工作树快照：

```text
HEAD=8a36fe3623c843c59a9b2e5ff225929ce94a9fe8
SUBJECT=chore: move the GOAWAY investigation out of the branch into .dev
```

命令与结果：

```sh
git -C /home/xp/src/ghc-api-proxy-py status --short -- src/app/observability/request_log.py tests/unit/test_request_log.py tests/unit/test_request_log_file.py
```

```text
<no output>
```

工作树内容经只读 `git hash-object` 与 HEAD tree blob 对比：

```text
src/app/observability/request_log.py HEAD=c2466c09fc3b3661c5455e6a5214531612436e22 WORKTREE=c2466c09fc3b3661c5455e6a5214531612436e22 equal=yes
tests/unit/test_request_log.py HEAD=6964ce228f4981119809b633725c001a4742fec7 WORKTREE=6964ce228f4981119809b633725c001a4742fec7 equal=yes
tests/unit/test_request_log_file.py HEAD=5c811a09354468c1e20d612d27618e9e1ccb4e6f WORKTREE=5c811a09354468c1e20d612d27618e9e1ccb4e6f equal=yes
```

因此这三个文件相对该 HEAD 既没有 staged diff，也没有 unstaged diff；不存在可归于本次 request log 改动的工作树残留。范围外的其他脏文件没有用于本项判定。
