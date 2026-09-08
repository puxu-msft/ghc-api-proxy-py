# Request log 收尾独立验收

## 范围、方法与证据强度

本次为只读验收；除本报告外未写入仓库，未执行任何 Git 写操作、源文件修改或删除。用户指定的 `my-skills:as-verifier` 未在本运行时注册，调用返回 `Unknown skill: as-verifier`，因此以下按同等的独立证据链执行：直接读取当前文件和指定历史承载者、以 `find` 与 `fd --hidden --no-ignore` 双重枚举、以精确文字检索排除旧样例、再以 AST 重数当前调用点。证据强度：足以裁决；所有结论均针对本报告形成时的当前工作树与指定 job 目录。

## 1．没有 live doc 需要更新

**结论：成立。**

检索范围包括 `docs/` 与 `README.md`，排除了 `docs/tmp/` 和 `docs/agents/**/archive-*/`；另检索了 `src/**/*.md`（实际没有此类文件）以及两个配置样例：`docs/.human-controlled/config.example.yaml` 与 `src/app/config/bundled-config.yaml`。执行的核心命令如下：

```bash
rg --line-number --fixed-strings -- 'request_id=' <docs-and-readme>
rg --line-number --fixed-strings -- 'anthropic-messages/' <docs-and-readme>
rg --line-number --fixed-strings -- '[ OK ]' '[FAIL]' '[GONE]' 'console line' 'request log' 'completion line' '↑' '↓' 'count(' 'provider(' <docs-and-readme>
```

其中 `<docs-and-readme>` 的输出再按路径排除了 `/docs/tmp/` 与 `/docs/agents/<topic>/archive-<date>/`。`request_id=`、`anthropic-messages/`、`[ OK ]`、`[GONE]`、`console line`、`request log`、`completion line`、`count(`、`provider(` 全为零命中；两份 YAML 样例对以上全部词也均为零命中。`[FAIL]` 的唯一有效文档命中是 `docs/agents/anthropic-responses-bridge/implementation.md:267` 中泛称「请求行报 `[FAIL]` 与成因」，未给字段顺序或样例行；`↑` 的唯一有效命中是 `docs/agents/history-forensics/proposal.md:74`，说明上游实际发送字节的取值来源，未描述控制台行格式。

关于 `request_id` 的有效文档命中只有三处：`docs/agents/anthropic-responses-bridge/architecture.md:206-213` 的 `RequestFacts` 字段、`docs/agents/history-forensics/proposal.md:207-209` 的 `UpstreamExchange`／`UpstreamChunk` 结构化取证字段。两者均不是控制台文本，且本次没有删改 JSONL／结构化记录中的 `request_id`。代码的当前合同也明确结构化记录持续保留该字段，见 `src/app/observability/request_log.py:314-318,373-375` 与 `tests/unit/test_request_log_file.py:88-129,156-158`。

因此没有仍生效的文档会因本轮「成功行省略 ID、失败行末尾 `req=`、count 前缀、由 verdict 决定行形和颜色」而失准。`docs/tmp/` 内确有旧样例，但它属于本断言明确排除的临时材料，不能构成 live doc 更新项。

## 2．处置标记准确

**结论：不成立。**

问题是 population 与顶层项数的陈述没有把处置记录自身排除，却声称运行了一个会包含它的命令。执行：

```bash
find /home/xp/.claude/jobs/56a35f57/tmp \( -type f -o -type l \) -printf '.' | wc -c
find /home/xp/.claude/jobs/56a35f57/tmp -mindepth 1 -maxdepth 1 -printf '%y %f\n' | sort
fd --hidden --no-ignore --type file . /home/xp/.claude/jobs/56a35f57/tmp | wc -l
fd --hidden --no-ignore --type symlink . /home/xp/.claude/jobs/56a35f57/tmp | wc -l
```

实际输出为：`find` 计 **874** 个文件／符号链接；顶层有 **4** 项，分别是 `d headcheck-1`、`f DISPOSITION.md`、`f stage_a.py`、`f stage_b.py`；`fd` 交叉结果为 **873** 个普通文件加 **1** 个符号链接，合计同为 **874**。`headcheck-1/` 自身确有 **871** 个文件／符号链接。只有特意以 `-path .../DISPOSITION.md -prune` 排除本处置记录时，才得到 **873** 与其余三个顶层工作产物。`DISPOSITION.md:6` 写出的命令没有该排除条件，所以它报告的「873 个文件／符号链接、顶层 3 项」与当前目录及它声明的计数方法不符。

其余逐项承载关系经独立核对成立：

- `stage_a.py:1,17-80` 和 `stage_b.py:1,18-40` 都实际存在，并分别以 `git hash-object -w` 与 `git update-index --cacheinfo` 构造索引 blob；前者构造 count-tokens 前缀切片，后者从工作树文本中复原同伴行再构造 verdict 切片。`git show` 确认 `ea0417c` 真正落入 `COUNT_TOKENS_SUFFIX`、`count_tokens` 及 `anthropic-messages-count-tokens/`，而 `b97930b` 真正落入 `STATUS_COLOURS`、`succeeded = status == "ok"` 与按 `STATUS_COLOURS[status]` 给 detail 着色。
- 三个指名提交存在：`ea0417c4dd7509f4dc7f5be71e109a4fe1a3a0b1`、`b97930b9b3650f34e46d75edfdb31b5170e536b1`、`7e65993d28f4e07a4e6e64eba1d165017de211ef`。`
- 所谓「终末报告」虽未在处置表中给出具体路径，但 job 的实际终末记录可在 `/home/xp/.claude/jobs/56a35f57/timeline.jsonl:70` 打开；它记有干净 HEAD 检出和 `1528 passed / 3 skipped`。因此该结论有实际承载者，不是 `DISPOSITION.md` 自证。
- 指名记忆确实存在且语义相同：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/memory/git-commit-takes-the-whole-index.md:10-17` 说明共享索引与 `git commit` 的关系；`:28-41` 记录 `hash-object`／`update-index --cacheinfo` 私有索引技法；`:58` 明说共享索引变体须用不带 pathspec 的 `git commit`，而带 pathspec 取工作树内容。`:45-56` 也记载了同伴 pathspec 提交带走 `pipeline_app.py` 与 `tests/http/test_pipeline_app.py` 未提交切片这一被纠正事实。
- 被推翻判断有 `docs/tmp/260820-review-request-id-and-count-prefix.md:14-24` 的原评审建议，及 `:56-71` 的用户裁决和采纳记录；变异与其恢复记录在同文件 `:105-115`，其中 `:111` 明载将固定 `RED` 变异后测试变红、还原后通过；断言原先无分辨力和改为 12 秒的原因也在 `:111`，当前回归对应 `tests/unit/test_request_log.py:105-111`。

故不是承载者缺失，而是处置文件把自己的存在从 population 中漏掉了。该误差是可复现的、足以否定「处置标记准确」这一绝对断言，但不影响三个工作产物已有承载者这一部分。

## 3．评审文档与实际代码一致

**结论：不成立，但仅有一处精确、非产品行为的计数失准；主会话处置描述的行为均与当前代码相符。**

主会话处置的实质内容均有当前源码佐证：

- 三档映射为 `ok → GREEN`、`fail → RED`、`gone → YELLOW`，见 `src/app/observability/request_log.py:56-63`；状态码和 detail 都以 `STATUS_COLOURS[status]` 着色，见 `:332-334,369-375`。这与评审记录 `docs/tmp/260820-review-request-id-and-count-prefix.md:60-67,107-113` 一致。
- `succeeded = status == "ok"`，见 `src/app/observability/request_log.py:311-334`；`_subject()` 只在 `succeeded` 为真时折叠为 `<inbound-format>/<model>`，否则保留 `METHOD /path`，见 `:278-300`。所以 `gone` 必然采取非成功行形，且 `status != "ok"` 时末尾保留 `req=`，见 `:373-375`。这符合评审 `:62,67,73,91-93`。
- `status: LogStatus` 是无默认值的 keyword-only 参数，见 `src/app/observability/request_log.py:311`。当前静态 AST 扫描 `src/` 和 `tests/` 的 **46** 个 `format_completion_line()` 调用，`calls_missing_status=[]`；函数 keyword-only 默认值结果为 `[('status', False), ('unicode', True), ('color', True)]`。
- 变异验证是历史操作，不能由当前代码单独重演；但评审记录 `:111` 有明确操作和结果，且当前测试 `tests/unit/test_request_log.py:105-111` 保留为 `gone` detail 使用黄色、行内不含红色 span 的有分辨力断言，和处置的说明一致。

失准处在同一文档的 `:79`：它称对 `src/app/observability`、`src/app/server` 与 `tests` 的 AST 检查得到「共 45 个 `format_completion_line()` 调用」。独立 AST 重数当前范围为 **46**，且将本次处置提交 `7e65993` 中的四个评审范围文件取出重数也是 **46**，缺 `status=` 均为 0。`git log 7e65993..HEAD -- tests/unit/test_request_log.py src/app/observability/request_log.py src/app/server/pipeline_app.py` 只显示两条随后文档提交，未显示这些代码文件的后续改动；故这不是后来代码变动造成的计数差异，而是评审文档当时的「45」本身少数了一个调用。

这处数字不改变「status 必传且没有漏传」的实质结论，也不要求更新 live doc，因为该评审位于 `docs/tmp/`。但它确实使「评审文档与当前实际代码一致」这一逐句断言不能成立。

## 汇总

| 断言 | 裁决 | 最重要证据 |
|---|---|---|
| 没有 live doc 需要更新 | 成立 | 有效文档、README、src Markdown 与 YAML 样例均无旧控制台行样例或旧格式前缀 |
| 处置标记准确 | 不成立 | 当前 job tmp 是 874 个文件／符号链接、4 个顶层项；873／3 仅在额外排除 `DISPOSITION.md` 时成立，原文命令未排除 |
| 评审文档与实际代码一致 | 不成立 | 行为处置均落地，但评审 `:79` 的 45 个调用实际为 46 个 |
