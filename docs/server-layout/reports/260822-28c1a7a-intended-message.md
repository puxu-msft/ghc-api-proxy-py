# `28c1a7a` 的提交信息原文（8 处符号名在落盘前被 shell 吃空）

**性质**：修复记录，不是分析。**git 里那条提交信息是残缺的，本文是它本来要说的话。**

**为什么会残缺**：这条提交用 `git commit -m "...."` 内联传信息，而信息里有 8 处用反引号包裹的符号名。**Bash 在双引号内仍然做命令替换**，于是每一处 `` `符号名` `` 都被当成命令执行，输出为空，静默替换掉。退出码为 0，提交成功，读起来只是少了几个词。发现时同伴已在其上提交，`--amend` 已不可用；为一条提交信息去改写同伴正在推进的分支不成比例，所以**历史保持原样**，信息记在这里。

**原文从哪里来**：主 transcript 里那条 `git commit -m` 的 argv 完整保留着——**命令替换发生在 shell 里，而 transcript 记的是 shell 收到之前的那份**。提取方式：从 `~/.claude/projects/-home-xp-src-ghc-api-proxy-py/be410f2e-*.jsonl` 里找 `type=="tool_use" and name=="Bash"` 且命令含 `move what a request accumulates` 的那条，取 `-m` 的参数。

**这一节本身是一条可复用的事实**：`git commit -m` 被 shell 吃掉的内容**不是不可恢复的**，只要那次调用还在 transcript 里。教训与恢复路径都在项目记忆 `never-pass-a-commit-message-inline-to-bash`。

## 原文

```
refactor: move what a request accumulates out of the module that routes it

pipeline_app.py was 1037 lines and a third of them were neither routing nor
dispatch: the connection snapshot, the trace record, the completion line and the
translation-loss reader. They are 836 and 247 now, split on what each part is
for rather than on where it happened to be written.

The tests had already filed these in observability. Before this,
tests/unit/observability/test_request_log_file.py imported three of them out of
the HTTP surface by their private spellings — a test package reaching across a
package boundary for `_Trace`, `_log_completion` and
`_snapshot_upstream_connection` is the layout telling you where they belong.
Crossing a module boundary in public makes the private spellings wrong, so they
are `RequestTrace`, `log_completion` and `snapshot_upstream_connection`, and
four `pyright: ignore[reportPrivateUsage]` comments went with them.

The byte accounting did not move and is not an oversight.
`_AccountedStreamingResponse` is the close owner of the response body, which
architecture.md:340 keeps away from observers, and the three clauses that
actually bind it are in spec.md — the one document 2026-08-19's authorisation
says it does not cover. Its landing spot is pipeline/delivery/ and it waits for
the STR-04 slice; implementation.md:268 has already deferred the neighbouring
question.

One test broke and deserved to: it patched get_logger on pipeline_app, and the
function it was watching had moved. Patch targets follow the code.
```

## 与 git 里那份的差异

5 行受影响，8 个符号名被吃空。左为原文，右为 git 里的实际内容：

```diff
11,12c11,12
< package boundary for `_Trace`, `_log_completion` and
< `_snapshot_upstream_connection` is the layout telling you where they belong.
---
> package boundary for ,  and
>  is the layout telling you where they belong.
14,15c14,15
< are `RequestTrace`, `log_completion` and `snapshot_upstream_connection`, and
< four `pyright: ignore[reportPrivateUsage]` comments went with them.
---
> are ,  and , and
> four  comments went with them.
18c18
< `_AccountedStreamingResponse` is the close owner of the response body, which
---
>  is the close owner of the response body, which
26a27
> 
```

被吃掉的 8 个是：`_Trace`、`_log_completion`、`_snapshot_upstream_connection`、`RequestTrace`、`log_completion`、`snapshot_upstream_connection`、`pyright: ignore[reportPrivateUsage]`、`_AccountedStreamingResponse`。

**注意这次损坏的形态**：被吃掉的全部是**符号名**，剩下的句子语法完整（「a test package reaching across a package boundary for ,  and  is the layout telling you where they belong」——逗号和连词都还在，只有名字没了）。所以它读起来不像损坏，像是作者写漏了词。**这正是它在几秒内没被发现的原因。**

## 这条提交的内容与验证均无误

残缺的只有信息。搬迁本身（`pipeline_app.py` 1037 → 836 行、`observability/request_trace.py` 247 行、三个符号从私有拼写改为公开拼写）已在 `main` 上，`.dev/docs/server-layout/status.md` 的六步表格第 2 行记录了它。
