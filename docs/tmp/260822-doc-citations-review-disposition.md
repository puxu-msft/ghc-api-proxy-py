# 代码文档引用审计的评审处置

**处置日期**：2026-08-22。
**评审对象**：主仓 `598b778`「docs: point the code's citations at the documents that now hold them」。
**两份报告**：[映射正确性](260822-review-doc-citations-mapping.md)（异源，21 条逐条核）、[覆盖面与过度改动](260822-review-doc-citations-coverage.md)（同源，另一视角）。
**两份判定**：均 needs-fix，blocker 0、major 各 1。
**处置提交**：主仓 `1f29d0a`（12 文件、16 增 16 删，仍只动注释）。

## 采纳

| 来源 | 严重度 | 发现 | 处置 |
|---|---|---|---|
| 覆盖面评审 F1 | **major** | `src/app/server/__init__.py:3` **本次提交新写**了不存在的模块名 `app.server.routes`（抄自用户文档），而同一 docstring 八行后就列出真实模块清单——文件在十二行内自相矛盾。改之前那句虽引死文档，但没对代码说过假话 | **采纳，已独立复核**（`ls src/app/server/` 无 `routes`）。改成与同一提交里 `request.py` 相同的处理：记录「文档这么拼、代码不是这样」，而不是替文档断言。**这是本次最该记住的一条**——正确处理与错误处理并存于同一个提交，说明我当时没把 `request.py` 的判断推广开 |
| 映射评审 F1 + 覆盖面评审 | **major/minor** | 提交自陈「这六处是各自文件里没有路径可读的那些」不成立：另有 7 处漏网，其中 `test_responses_stop_reason.py:32` 写作 `# spec.md ...`（无反引号），我的正则要求反引号所以扫不到 | **采纳**。7 处全部补齐路径。**根因是同一个盲区第二次击发**：2026-08-20 那次清点按路径搜、看不见裸文件名；我这次按反引号搜、看不见不带反引号的。两次都是别人换个搜法才找出来的 |
| 映射评审 | minor | `request_log.py:106` 的引用被换成循环自指的无出处引号，测试侧正好被指向这个悬空终点 | **采纳**。两处都改成直接陈述规则 |
| 覆盖面评审 | minor | 3 处「the frozen Spec」连文件名都没有 | **采纳**。定位到 `.dev/docs/anthropic-responses-bridge/spec.md`「Downstream Anthropic SSE」第 5 条。**用小标题而非行号作锚**——行号带保质期 |
| 映射评审 F2 | minor | 可数事实错误：「eleven modules」实为 13 处引用横跨 12 个文件；「六份 `spec.md` 和六份 `deferred.md`」实为各 5 份 | **采纳，已独立复核**（`git grep -c` 得 files=12 sites=13；`fd` 严格限定 `.dev/docs/` 得各 5）。六这个数来自一条 `head -6` 截断且混入 worktree 副本的输出——又一次「读了没验证过的探针数字」。**无法 amend**：同伴已在 `598b778` 上提交了 `ea7a665`，所以更正写在 `1f29d0a` 的提交信息里 |

自查补充：修正过程中我一度用全角斜杠 `／` 抄了文档标题，被 `ruff` 的 RUF002/RUF003 逮到 3 处，也违反用户排版规则中「中文句子用半角 `/`」。已改用无全角字符的小标题作锚。

## 不采纳 / 留待裁决

| 来源 | 发现 | 处置与理由 |
|---|---|---|
| 覆盖面评审 F2 | `src/app/config/schema.py:137` 的 `docs/.dev/…/streaming-resilience.md` 是**根目录写反**（应为 `.dev/docs/`）**且含字面 `…` 路径段**，并仍声称「a spec behind it」，而该文档属过期笔记 | **不在本次动手**。该文件被同伴的未提交改动占着。评审指出更准确的表述是「这是提交边界问题，不是文本冲突」——采纳这个措辞修正：同伴的 hunk 与该行不重叠，但用 pathspec 提交会卷走他们未完成的 `pidfile_dir` 重命名。**正确答案已查明**：路径应为 `.dev/docs/archived-2604-rewrite/streaming-resilience.md`，且「a spec behind it」应改为指向 `docs/.human-controlled/config.example.yaml`——那里确实有用户亲笔的 `http2_ping_interval: 15` 及其注释，这才是「用户写的键」的真凭据。**需转达给正在改该文件的同伴** |
| 两份评审 | `docs/.human-controlled/README.md` 清单列了不存在的 `observability.md`、漏了存在的 `release-and-deployment.md` | **仅上报用户**。用户亲笔，agent 不得修改。可走 `.dev/human-controlled-docs-candidates/`，但要不要提由用户定 |
| 两份评审 | 代码的 `RequestContext` / `Attempt` 与文档的 `ClientRequest` / `UpstreamAttempt` 对不上，目前该分歧只活在 docstring 里 | **不改代码**。映射评审判这是本次最好的一处判断；两份评审都建议把分歧登记到某份活文档，但都说不出该登记到哪一份。**留给用户裁决**：改名是文档作者的事 |
| 覆盖面评审 | 6 处「撤销权威声称」是否给注释塞了不该由它承担的元信息 | 评审自己判**恰当而非过头**（理由：它改变的是读者被授权做什么，且是该事实目前唯一载体）。**维持** |

## 现状（`1f29d0a`，按提交态而非工作树核对）

- 死文档名 `MAIN.md` / `model-translation.md` / `message-format-sanitize`：**0 处**
- 裸话题文档名在本文件内不可解析：**0 处**；「the frozen Spec」这类无文件名锚点：**0 处**
- 代码引用的 24 条显式文档路径：**全部可解析**（该检查已用一条假路径做正样本对照，证明非恒绿）
- `ruff` 通过；`pyright` 在改动文件上 0 错；`tests/unit` + `tests/int` 共 **1688 通过**
- 全仓 `pyright` 另有 **21 个错，全在 `src/app/upstream/stream_cap.py`(4) 与 `tests/unit/upstream/test_stream_cap.py`(19)**，无一在本次改动文件内，与既有记录「main 上 21 个 pyright 错，全在 stream_cap 切片」吻合，属同伴切片的既存状态
