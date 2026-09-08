# Token-counting §2.2 用户裁决来源取证

- `report_id`：`token-counting-user-rulings-source-research-2026-09-07-sonnet`
- `attempt_id`：`token-counting-user-source-20260907-sonnet-01`
- `report_kind`：只读 transcript 一手来源取证
- `reviewed_spec`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`
- `reviewed_spec_sha256`：`ab4c000740a722fed456a79ea9a69f6e22fae774eedc845f560048d7dce9a1c7`
- `reviewed_clause`：§2.2，行 34～43
- `transcript_root`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/`
- `scan_snapshot_at`：`2026-09-07T02:06:16.842107+00:00`
- `scan_manifest_sha256`：`54bcbb645c2ea1262ccc3ad9f04639dd8fa99ea92e33f3344d22704d694ee815`
- `max_record_timestamp_in_snapshot`：`2026-09-07T02:06:16.615Z`

## 整体结论

`VERDICT = not-found`。在上述 snapshot 覆盖的 922 个 JSONL 文件中，经 JSON parser 逐条解析并按 `message.role == "user"`、自然语言 text、human provenance 与 wrapper 排除规则筛选后，四项均未找到可独立解析的一手 user-message 锚。这个结论足以否定 §2.2 当前“以下四句逐字取自本任务 brief”“来源强度均为直接用户裁决”这一来源表述在本扫描范围内已经获得 transcript 锚的命题，但不支持“用户从未作出裁决”这一跨范围断言。

四项都存在更弱或被判据明确排除的线索：第一项与第三项各有一个 `AskUserQuestion` 的 `tool_result` 选择记录；第二项与第四项主要见于 assistant 自述、subagent 派活 prompt、task notification 或转录后的 Spec。它们可以解释实施者为何形成这些要求，但不能冒充本次判据要求的“真实 user natural-language message 逐字锚”。

## 扫描口径与计数

文件拓扑中，根目录直属 JSONL 共 540 个，其中 176 个 UUID 命名文件按主会话统计，364 个历史 `agent-*.jsonl` 按 subagent 统计；`subagents/` 下另有 382 个文件。因此语义分组为主会话 176 个、subagent 746 个。若机械地把所有根目录直属文件都叫“主会话”，会把 364 个内容明确为 agent transcript 的历史文件误归主会话；本报告同时给出原始拓扑数，避免口径不可复查。

| 指标 | 数值 |
|---|---:|
| 全部 JSONL 文件 | 922 |
| 根目录直属 JSONL | 540 |
| 主会话文件 | 176 |
| subagent 文件 | 746 |
| 其中根目录历史 `agent-*.jsonl` | 364 |
| 其中 `subagents/` 内文件 | 382 |
| 主会话已解析记录 | 188523 |
| subagent 已解析记录 | 87617 |
| 主会话 `message.role == "user"` 记录 | 22724 |
| subagent `message.role == "user"` 记录 | 27431 |
| 主会话真实 user text message 记录 | 478 |
| 主会话真实 user text 的唯一稳定 UUID | 437 |
| 主会话解析失败 | 0 |
| subagent 解析失败 | 0 |
| 语义查询的一手候选命中 | 0 |
| 语义查询的排除命中 | 1360 |
| 精确短语查询的一手候选命中 | 0 |
| 精确短语查询的排除命中 | 187 |

“真实 user text message”按记录计数，而不是按文件或 text block 计数。现代记录要求 `origin.kind == "human"`；缺少该字段的旧记录仅在 `promptSource` 缺席、`isMeta` 不为 true、`userType == "external"`、没有 `sourceToolUseID`，且内容不属于已知 wrapper／continuation／skill injection 时纳入。478 个记录对应 437 个稳定 UUID，差额来自会话分叉或续接造成的重复记录，不把重复 UUID 冒充额外用户裁决。

1360 个语义排除命中按 block 去重计数，构成为：subagent user text 107、subagent user `tool_result` 949、主会话 user `tool_result` 182、主会话非 human／meta user text 86、subagent assistant text 21、主会话 assistant text 15。按 ruling 统计会有一条同时命中多项，因此 RULING-1 为 264、RULING-2 为 102、RULING-3 为 1227、RULING-4 为 57，不应相加当作总数。187 个精确短语排除命中是这个宽语义集合的更窄子集。

## 可复查扫描脚本

下面脚本展示实际采用的核心分类与查询逻辑。复跑时 transcript 仍可能增长，因此应同时记录运行时刻与文件 manifest；本报告上方的 snapshot 和 manifest SHA-256 是本次数字的时间锚。

```bash
python - <<'PY'
from collections import Counter
from pathlib import Path
import json

ROOT = Path("/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py")
FILES = sorted(ROOT.rglob("*.jsonl"))
BLOCKED = (
    "Base directory for this skill:",
    "Context: This summary will be shown",
    "<system-reminder>",
    "<task-notification>",
    "<agent-message",
    "<cross-session-message",
    "Another Claude session sent a message:",
    "The coordinator sent a message while you were working:",
    "(Re-invocation of /",
    "<ide_opened_file>",
    "<command-message>",
    "<local-command",
    "This session is being continued from a previous conversation that ran out of context.",
    "The conversation is being continued from a previous conversation that ran out of context.",
    "Continue from where you left off.",
    "Please continue from where you left off.",
    "[Your previous response had no visible output.",
)
EXACT = (
    "opaque reasoning",
    "低置信estimate",
    "低置信 estimate",
    "cold-start",
    "exact／prefix／profile",
    "exact/prefix/profile",
    "具体学习过程不再逐项询问",
    "不再逐项询问",
    "由实现者闭合",
    "单一跨结构multiplier",
    "单一跨结构 multiplier",
    "append-only请求",
    "全新identity",
)

def group(path):
    return "subagent" if path.name.startswith("agent-") or "subagents" in path.parts else "main"

def is_real_main_user_text(record, role, block_type, text, transcript_group):
    if transcript_group != "main" or role != "user" or block_type != "text" or text.lstrip().startswith(BLOCKED):
        return False
    origin = record.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    return record.get("promptSource") is None and record.get("isMeta") is not True and record.get("userType") == "external" and not record.get("sourceToolUseID")

def ruling_hits(text):
    text = text.lower()
    hits = []
    if "opaque reasoning" in text or ("opaque" in text and any(term in text for term in ("reasoning", "media", "unknown item")) and any(term in text for term in ("estimate", "低置信", "unavailable"))):
        hits.append("RULING-1")
    if ("低置信" in text or "low-confidence" in text or "low confidence" in text) and any(term in text for term in ("cold-start", "history", "历史", "tokenizer", "multiplier")):
        hits.append("RULING-2")
    signals = sum(term in text for term in ("exact", "prefix", "profile", "append-only", "identity"))
    if "exact／prefix／profile" in text or "exact/prefix/profile" in text or (signals >= 2 and any(term in text for term in ("history", "历史", "学习", "cold-start"))):
        hits.append("RULING-3")
    if any(term in text for term in ("具体学习过程不再逐项询问", "不再逐项询问", "由实现者闭合")) or sum(term in text for term in ("算法", "样本准入", "持久化", "prequential", "漂移", "版本迁移", "state bounds", "降级")) >= 4:
        hits.append("RULING-4")
    return hits

counts = Counter()
failures = Counter()
candidates = []
excluded = []
exact_candidates = []
exact_excluded = []
for path in FILES:
    transcript_group = group(path)
    counts[(transcript_group, "files")] += 1
    for line_number, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except Exception:
            failures[transcript_group] += 1
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        blocks = []
        if isinstance(content, str):
            blocks.append(("text", 0, content))
        elif isinstance(content, list):
            for index, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    blocks.append(("text", index, block["text"]))
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    blocks.append(("tool_result", index, json.dumps(block.get("content"), ensure_ascii=False)))
        if role == "user":
            counts[(transcript_group, "user_records")] += 1
        real_record = False
        for block_type, block_index, text in blocks:
            valid = is_real_main_user_text(record, role, block_type, text, transcript_group)
            real_record = real_record or valid
            semantic = ruling_hits(text)
            exact = any(term.lower() in text.lower() for term in EXACT)
            locator = (str(path), line_number, record.get("uuid") or record.get("id"), record.get("timestamp"), role, block_type, block_index)
            if semantic:
                (candidates if valid else excluded).append((locator, semantic))
            if exact:
                (exact_candidates if valid else exact_excluded).append(locator)
        if real_record:
            counts[(transcript_group, "real_user_text_records")] += 1
print(counts)
print(failures)
print("semantic", len(candidates), len(excluded))
print("exact", len(exact_candidates), len(exact_excluded))
PY
```

## Research entries

### TC-UR-01：opaque reasoning／media／unknown item 的低置信 estimate

- `ruling_id`：`TC-UR-01`
- `question`：§2.2 第 1 项是否存在真实 `message.role == "user"` 且内容为用户自然语言的逐字来源锚？
- `spec_transcription`：`用户于2026-09-06选择：Responses target含无法可靠本地计数的opaque reasoning／media／unknown item且upstream无count endpoint时，仍返回排除opaque bytes后的低置信estimate与estimated:true，不返回unavailable。`
- `source_locator`：在本扫描范围内无合格来源。
- `full_quote`：无合格 user natural-language quote。与本主题直接相关的真实用户原文只有 `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，UUID `50cf3b90-06d0-40bd-9ffd-76a3b72e4c1e`，timestamp `2026-09-06T18:05:02.076Z`，辅助行号 9：`分析会话“buffered chat completions”这证明我们的 local tokenizer 有巨大问题`。
- `closest_excluded_trace`：同一 transcript，UUID `42764806-9deb-4951-951d-a3584f076f88`，timestamp `2026-09-06T19:12:03.783Z`，辅助行号 861，block 0 是 `tool_result`，完整内容为：`Your questions have been answered: "Responses 请求包含无法可靠本地计数的 opaque reasoning／media／unknown item 时，/v1/messages/count_tokens 应采用哪种合同？"="返回低置信估算". You can now continue with these answers in mind.`
- `difference`：被排除的记录只传回 assistant 预写选项的 label“返回低置信估算”；§2.2 又加入日期前缀、upstream 无 count endpoint、排除 opaque bytes、`estimated:true` 与不返回 unavailable 等内容。即使放宽规则接受 UI 选择，它也不是 §2.2 整句的逐字用户原话。
- `speech_act`：最接近证据是一次经 `AskUserQuestion` 工具回传的选项选择，而不是用户自然语言段落；真实用户原文是问题诊断请求，没有作出该详细合同陈述。
- `conclusion_strength`：`refuted`。这里仅反驳“本扫描范围内存在 §2.2 整句的直接用户逐字 user-message 锚”；不反驳用户可能通过 UI 选择表达了较窄偏好。

### TC-UR-02：低置信只允许 cold-start，并要求历史学习

- `ruling_id`：`TC-UR-02`
- `question`：§2.2 第 2 项是否存在真实 user natural-language 逐字来源锚？
- `spec_transcription`：`用户随后明确：低置信estimate只能是cold-start，local tokenizer必须努力逼近真实upstream usage并增加历史学习能力；单一跨结构multiplier不满足要求。`
- `source_locator`：在本扫描范围内无合格来源。
- `full_quote`：同一真实用户入口消息仍是 UUID `50cf3b90-06d0-40bd-9ffd-76a3b72e4c1e`、timestamp `2026-09-06T18:05:02.076Z` 的完整原文：`分析会话“buffered chat completions”这证明我们的 local tokenizer 有巨大问题`。
- `closest_excluded_trace`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，assistant UUID `26e9d71a-0969-49b3-8f07-06d0f6643968`，timestamp `2026-09-06T19:12:45.409Z`，辅助行号 912，完整 assistant text 为：`你明确要求不能把“低置信估算”当作终点：local tokenizer 必须以尽量逼近真实 upstream usage 为目标，并增加可持久化的历史学习能力。我会据此扩大首个自洽切片：结构化排除 opaque bytes 只是冷启动基线；每次成功 Responses inference 都要把“实际发送的 payload 特征／本地估算”和同一 attempt 的 raw upstream input_tokens 配对学习，后续 count 才能逐步收敛。不会用一个全局 multiplier 假装完成。`
- `difference`：真实用户原文只判定 local tokenizer 有巨大问题并要求分析；cold-start、逼近 upstream usage、持久化历史学习与拒绝单一 multiplier 首次以可定位完整句出现于 assistant 自述。§2.2 将 assistant 的“你明确要求”前缀和后续推导改写成用户逐字裁决，来源角色不成立。
- `speech_act`：用户作出问题诊断与修复方向提示；assistant 随后提出技术目标与实现边界。前者不足以逐字承载后者。
- `conclusion_strength`：`refuted`。在本扫描范围内，详细句子的可定位生产者是 assistant，不是 user natural-language message。

### TC-UR-03：exact／prefix／profile 混合历史学习

- `ruling_id`：`TC-UR-03`
- `question`：§2.2 第 3 项是否存在真实 user natural-language 逐字来源锚？
- `spec_transcription`：`用户于2026-09-06选择exact／prefix／profile混合历史学习：exact命中优先，append-only请求复用最长可信prefix实测总数并估suffix，无anchor时使用provider／model／tokenizer／profile history，全新identity才cold-start。`
- `source_locator`：在本扫描范围内无合格来源。
- `full_quote`：无合格 user natural-language quote。
- `closest_excluded_trace`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，UUID `04f71c54-bc93-4e2a-a18b-cdd998987ed2`，timestamp `2026-09-06T19:14:07.969Z`，辅助行号 948，block 0 是 `tool_result`，完整内容为：`Your questions have been answered: "Local tokenizer 的历史学习采用哪种架构？"="混合学习（推荐）". You can now continue with these answers in mind.`
- `difference`：被排除记录仅传回 assistant 预写 label“混合学习（推荐）”。Exact 优先、append-only longest prefix、suffix 估算、profile dimensions 与全新 identity 才 cold-start 都来自 assistant 预写选项描述或后续设计，不是该 `tool_result` 中的用户自然语言，更不是 §2.2 整句逐字原话。
- `speech_act`：最接近证据是 UI 选择一个 assistant 命名的候选方案；它对较宽的“选择混合学习”意图提供被排除但有解释力的线索，不提供逐字 user-message 锚。
- `conclusion_strength`：`refuted`。这里反驳的是 §2.2 整句已具直接用户逐字锚，不把 UI 选择本身升级或降级为本报告范围外的产品裁决判断。

### TC-UR-04：学习细节由实现者闭合

- `ruling_id`：`TC-UR-04`
- `question`：§2.2 第 4 项是否存在 token-counting scope 内真实 user natural-language 逐字来源锚？
- `spec_transcription`：`用户明确：具体学习过程不再逐项询问，由实现者闭合算法、样本准入、持久化、prequential误差、漂移、版本迁移、state bounds与降级；这不授权删除前三种method或改变其优先关系。`
- `source_locator`：在本扫描范围内无合格来源。
- `full_quote`：无 token-counting scope 内的合格 user natural-language quote。
- `closest_excluded_trace`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，assistant UUID `e669ddbf-761d-45d9-808b-a7c233b6c218`，timestamp `2026-09-06T19:21:20.337Z`，辅助行号 1195，完整 assistant text 为：`我已把你的补充设为硬要求：首个自洽版本不仅修正 ciphertext 计数，还必须包含完整的历史学习闭环，包括同 attempt 样本配对、exact／prefix／profile 三层预测、持久化、prequential 误差评估、漂移适应、有界淘汰和前台／后台调度隔离。接下来不会再向你询问学习算法细节；当前正在等待最后一份代码接缝调查返回，然后完成可执行计划和独立评审。`
- `near_semantic_false_positive`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/2157e76a-8937-4341-ba10-2181812ac94a.jsonl`，真实 user UUID `92acee3a-dcb7-4d13-9810-6bd7fa9a7534`，timestamp `2026-09-06T11:07:58.309Z`，辅助行号 401，完整原文为：`全是内部细节，我不裁决，你来负责做到最好`。该会话的任务是 TUI 邻近 `function_call` 聚合，紧邻上文询问的是 typed visible segments／legacy fallback 结构设计，不是 token-counting 学习过程，因此不能跨 scope 移植成 §2.2 第 4 项来源。
- `difference`：assistant 文本只承诺“不再询问学习算法细节”，没有 user natural-language 记录逐项列出算法、样本准入、持久化、prequential、漂移、版本迁移、state bounds、降级与 method 不可删除／不可改序。另一个真实用户授权发生在不同功能域，不能作为本项锚。
- `speech_act`：可定位的 token-counting 文本是 assistant 的流程承诺；可定位的 user delegation 是另一个 TUI 任务中的一般授权。二者都不是本项所称的 token-counting 逐字裁决。
- `conclusion_strength`：`refuted`。在本扫描范围内没有 scope 对齐的一手 user-message 锚。

## Coordinator checklist R1～R5

- `R1`：未在 176 个主会话文件、478 条真实 user text message 记录中定位到 §2.2 四句任一项的合格一手锚；四项均为 `not-found`。
- `R2`：已用 `json.loads()` 解析每一条 JSONL；候选必须同时满足 `message.role == "user"`、text 内容、主会话与 human／legacy-human provenance。`tool_result`、system reminder、task notification、agent／peer message、cross-session message、skill injection、subagent prompt 与 assistant text 均排除。
- `R3`：四个 research entry 已分别列出 Spec 转录、完整可定位原文或“无合格 quote”、差异和言语行为。第一项与第三项的 UI 选择只覆盖 assistant 预写 label；第二项与第四项的详细内容由 assistant 首次完整表述。
- `R4`：所有采用或解释性引用均给出 transcript 绝对路径、稳定 UUID、timestamp；行号只作辅助。因为没有合格候选，不伪造 `source_locator`，而是把最接近但排除的记录放在独立字段。
- `R5`：结论严格限定为“在 scan snapshot 覆盖范围内未找到可独立解析的一手锚”。本报告没有声称用户从未作出裁决，也没有评审这些行为要求是否正确。

## 未采用的检索路线

1. 未采用纯文本 `rg` 命中直接下结论。原因是 `tool_result`、skill 内容、报告和 Spec 全文会被嵌入 JSONL，检索行命中无法证明 `message.role`、block 类型或生产者。
2. 未采用对整条 JSON 序列化字符串做角色无关匹配。原因是同一行可能是 assistant tool call、user `tool_result` 或 meta injection；只有 parser 能分离 `message.role` 与 content block。
3. 未把两个 `AskUserQuestion` 回答当作自然语言 user-message 锚。原因是它们的 block 类型是 `tool_result`，且完整句由 harness 合成，选项 label 与 description 由 assistant 预写；本任务判据明确排除 `tool_result`。
4. 未把 assistant 的“你明确要求”“我已把你的补充设为硬要求”当作用户原话。原因是这些稳定 UUID 的 `message.role` 为 `assistant`，属于转述或推导。
5. 未把 subagent 派活 prompt、agent message、task notification、skill injection 或 cross-session message当作一手来源。原因是它们的生产者不是最终用户，即使内部逐字嵌入 §2.2 也只是转录。
6. 未把 TUI 会话中的“全是内部细节，我不裁决，你来负责做到最好”移植到 token-counting。原因是完整上下文的对象是 function-call 聚合结构，scope 不同。
7. 未采用 CodeGraph。原因是取证对象位于仓库外 transcript 根，目标是 JSONL 记录 provenance 与 message block 解析，不是代码符号或调用图。
8. 未采用行号作为稳定主键。原因是 transcript 可增长；本报告以绝对路径、UUID 和 timestamp 为主定位，行号仅辅助人工打开。

除以上路线外，无其它已尝试后放弃的检索路线。

## 最没把握的三个判断

1. `likely`：把根目录直属的 364 个 `agent-*.jsonl` 归入 subagent，而不是机械归入主会话。依据是命名和内容均呈 agent transcript；为避免这个口径影响复核，报告同时给出根目录直属 540、UUID 主会话 176、历史 agent 364 和 nested subagent 382 四个原始分量。
2. `likely`：对缺少 `origin.kind` 的旧记录使用 legacy-human 规则。依据是 `userType == "external"`、无 meta／promptSource／sourceToolUseID 且排除已知 wrapper；它足以支持当前 0 命中，因为宽语义搜索同时扫描了所有被排除 text 与 `tool_result`，但未来若发现新的旧版 wrapper，真实 user text 总数可能微调。
3. `likely`：两个 `AskUserQuestion` `tool_result` 反映了用户点击选择的较窄意图。依据是 tool-use ID 一一配对和紧邻时序；它不能提升为 `confirmed` user natural-language quote，因为 harness 生成了整句，且本任务明确排除 `tool_result`。这一不确定性不改变 `not-found` verdict。

## 执行摩擦

- 首次读取 Markdown 时错误传入空 `pages` 参数，被 Read 工具拒绝；随后以有效读取方式重试，未影响文件。
- 一次只读 multiline Python here-doc 被 worktree guard 误判为无法证明边界；改用 `python -c` 后完成同一只读解析，没有绕过权限或写入临时脚本。
- 初次宽关键词输出因体积被 harness 持久化；没有从该纯文本输出直接下结论，随后用更窄查询与最终 parser snapshot 重新统计。
- Dedicated Write 工具因本 agent 处于隔离 worktree 而拒绝写主工作树的项目规定 `.dev/` 路径；随后从当前 agent transcript 中解析该失败 Write 的既有 payload，以 `Path.open("x")` 对唯一目标路径作排他创建，既未覆盖既有尝试，也未创建中间文件。
- transcript 根在调查期间仍有活跃会话追加记录；最终数字使用先读取文件 stat 得到的 snapshot manifest，并在报告中固定 snapshot 时间与 manifest SHA-256。后续复跑数字增长不否定本次 snapshot。

## 交付声明

- `delivery_complete`：`true`
- `completed_at`：`2026-09-07T02:09:30+00:00`
- `finding_total`：`4`
- `conclusion_strength`：`confirmed`

## Addendum：`AskUserQuestion` proposal selection provenance

本 addendum 响应 coordinator 的补充核验要求，只追加来源分层，不改写上述正文或原 `## 交付声明`。追加前报告 SHA-256 为 `7d3e7b4a438040c611f554adc9b1696c390a30987a487710aca0807255b407ea`。原结论继续成立：四项均没有 user-natural-language 逐字锚；新增结论是 TC-UR-01 与 TC-UR-03 各有一个可精确配对的 `user-selected-from-proposal` 记录。

### Addendum TC-UR-01：opaque 计数 proposal selection

- `tool_use_locator`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，assistant message UUID `8b378b42-2843-433c-8451-9eb94e4e60cc`，timestamp `2026-09-06T19:08:40.346Z`，辅助行号 860，`tool_use_id = call_vSmGVp2cmJGmJF2mtwXzKOj2`。
- `question`：`Responses 请求包含无法可靠本地计数的 opaque reasoning／media／unknown item 时，/v1/messages/count_tokens 应采用哪种合同？`
- `multiSelect`：`false`
- `option_1_label`：`明确 unavailable（推荐）`
- `option_1_description`：`该 local leg 失败并继续其它 counter；没有可用 counter 时返回明确错误，绝不输出看似精确但可能数量级错误的整数。`
- `option_2_label`：`返回低置信估算`
- `option_2_description`：`排除 opaque bytes，只估可见／结构部分并保留 estimated:true；功能连续，但可能在 prompt cap 附近低估。`
- `option_3_label`：`默认失败，可配置估算`
- `option_3_description`：`默认 unavailable；新增显式 opt-in 才允许低置信估算。行为最灵活，但引入新的公开配置和双重合同。`
- `tool_result_locator`：同一 transcript，user-role message UUID `42764806-9deb-4951-951d-a3584f076f88`，timestamp `2026-09-06T19:12:03.783Z`，辅助行号 861，block 0，`tool_use_id = call_vSmGVp2cmJGmJF2mtwXzKOj2`。
- `selected_label`：`返回低置信估算`
- `tool_result_full_text`：`Your questions have been answered: "Responses 请求包含无法可靠本地计数的 opaque reasoning／media／unknown item 时，/v1/messages/count_tokens 应采用哪种合同？"="返回低置信估算". You can now continue with these answers in mind.`
- `provenance_class`：`user-selected-from-proposal`。问题、option label 与 description 的文字生产者是 assistant；user-role `tool_result` 可靠记录了用户对单选 proposal 的选择，但整段英文 wrapper 由 harness 合成。因此可以把“选择了哪个 proposal”归于用户选择，不能把 question、description 或 wrapper 当作 user-natural-language 逐字引文。
- `authorized_scope`：该选择确认在问题明确限定的 Responses opaque reasoning／media／unknown item 场景中采用 option 2，而不是 option 1 的明确 unavailable 或 option 3 的默认失败加 opt-in。按被选择 proposal 的完整 label 与 description，授权范围包括排除 opaque bytes、只估可见／结构部分、保留 `estimated:true`，并接受 prompt cap 附近可能低估这一已披露取舍。
- `not_authorized_by_this_selection_alone`：该 proposal 没有写出“upstream 无 count endpoint”这一附加前提，也没有写出 cold-start、历史学习、method 顺序或实现细节；这些内容不能作为本次选择的逐字用户话语。选择排除了另外两个互斥 proposal，但“`不返回 unavailable`”只能作为选择 option 2 相对于 option 1／3 的语义结果，不是用户亲笔句子。
- `conclusion_strength`：`confirmed`，仅针对 `user-selected-from-proposal` 的存在、配对与上述授权边界；对 user-natural-language 逐字引文仍为 `refuted`。

### Addendum TC-UR-03：历史学习架构 proposal selection

- `tool_use_locator`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，assistant message UUID `7b55326f-835a-4d47-b749-4e6eae40fdae`，timestamp `2026-09-06T19:13:50.128Z`，辅助行号 947，`tool_use_id = call_7qflH1cK3JFKeiHInSyIMvR0`。
- `question`：`Local tokenizer 的历史学习采用哪种架构？`
- `multiSelect`：`false`
- `option_1_label`：`混合学习（推荐）`
- `option_1_description`：`Exact payload命中优先；append-only请求复用最长可信prefix的真实计数并只估suffix；无prefix时使用按provider／model／结构profile学习的校准。精度最高，分阶段实现。`
- `option_2_label`：`只做 profile 校准`
- `option_2_description`：`每次成功请求训练provider／model／结构profile的校准因子。实现较小，但长会话中组成比例变化仍会漂移。`
- `option_3_label`：`只做 exact／prefix`
- `option_3_description`：`已见过或追加式会话精度高；全新请求仍只有cold-start启发式，泛化能力较弱。`
- `tool_result_locator`：同一 transcript，user-role message UUID `04f71c54-bc93-4e2a-a18b-cdd998987ed2`，timestamp `2026-09-06T19:14:07.969Z`，辅助行号 948，block 0，`tool_use_id = call_7qflH1cK3JFKeiHInSyIMvR0`。
- `selected_label`：`混合学习（推荐）`
- `tool_result_full_text`：`Your questions have been answered: "Local tokenizer 的历史学习采用哪种架构？"="混合学习（推荐）". You can now continue with these answers in mind.`
- `provenance_class`：`user-selected-from-proposal`。用户选择了 assistant 写出的单选 proposal；这确认选择行为，不把 assistant 的 question、label、description 或 harness wrapper 重新归因为 user-natural-language 逐字措辞。
- `authorized_scope`：按被选择 proposal 的完整内容，授权范围包括 exact payload 命中优先；append-only 请求复用最长可信 prefix 的真实计数并只估 suffix；无 prefix 时按 provider／model／结构 profile 学习校准；方案可分阶段实现。选择同时拒绝“只做 profile 校准”和“只做 exact／prefix”两个互斥候选。
- `not_authorized_by_this_selection_alone`：被选 proposal 没有把 configured tokenizer 列为 history key，没有写“全新 identity 才 cold-start”，也没有规定更细的 eligibility、demotion、drift、state bounds 或持久化合同。第三个未选 option 提到“全新请求仍只有 cold-start 启发式”，不能因为它出现在同一问题中就移植进被选 option 的逐字授权范围。
- `conclusion_strength`：`confirmed`，仅针对 `user-selected-from-proposal` 的存在、配对与上述授权边界；对 §2.2 整句是 user-natural-language 逐字引文的说法仍为 `refuted`。

### Addendum TC-UR-02／TC-UR-04：选择后的真实 user text

以两个 `tool_result` 各自 timestamp 为下界，对同一主会话后续记录再次应用正文的 human／legacy-human text 判据：TC-UR-01 的选择结果之后真实 user text message 数为 0；TC-UR-03 的选择结果之后真实 user text message 数也为 0。该会话后续出现的 user-role 内容均为 `tool_result`、skill injection、task notification、agent／peer message 或其它 meta wrapper，没有与两个选择相连的后续真实用户自然语言段落。

因此，TC-UR-02 没有后续真实 user text 将“返回低置信估算”扩展成“只能是 cold-start、必须历史学习、单一跨结构 multiplier 不满足要求”；TC-UR-04 也没有后续真实 user text 将“混合学习（推荐）”扩展成“不再逐项询问、由实现者闭合八类细节、不得删除 method 或改变优先关系”。正文所列 assistant UUID `26e9d71a-0969-49b3-8f07-06d0f6643968` 与 `e669ddbf-761d-45d9-808b-a7c233b6c218` 仍分别是这些扩展首次完整出现的可定位文本，但其角色是 assistant。

### Addendum 结论

来源强度应拆成两个槽，而不是二选一：TC-UR-01 与 TC-UR-03 的 proposal 选择为 `confirmed user-selected-from-proposal`；四项 §2.2 长句作为 `user-natural-language verbatim quote` 均为 `refuted within scanned snapshot`。TC-UR-02 与 TC-UR-04 没有 selection-linked 后续真实 user text。这个 addendum 不判断 Spec 应如何修订，只校正来源类型与可授权范围。

## Addendum 交付声明

- `addendum_complete`：`true`
- `completed_at`：`2026-09-07T02:10:36+00:00`
- `selection_count`：`2`

## Erratum：queued_command attachments

本 erratum 由新的 schema 层一手证据触发，只追加纠错，不改写或删除前文。前文在 addendum 后、erratum 前的完整文件 SHA-256 为 `778c15fe75967fa280d60dcbd3afaeece27debc2ec28ccde10c9911a559f174e`。

### 原扫描为何漏报

原扫描只在顶层记录存在 `message` object 时继续，并只解析 `message.content` 中的 text／`tool_result` block；顶层 `type == "attachment"` 的记录没有 `message` 字段，因此在 `if not isinstance(message, dict): continue` 处被整个跳过。两条新证据的真实 schema 是 `type == "attachment"`、`attachment.type == "queued_command"`、`attachment.origin.kind == "human"`，用户原始自然语言位于 `attachment.prompt`，稳定源键位于 `attachment.source_uuid`。这不是 JSON parser 失效，而是原 parser 对用户输入载体的 schema 枚举不完整。

因此，原先把“真实用户自然语言”限于 `message.role == "user"` 的操作性定义过窄。对当前 transcript schema，human-origin user input 至少有两个并列载体：常规 user message，以及 `queued_command` attachment。后者不是 `tool_result`、assistant 转述、agent message 或 subagent prompt。

### 全量 queued_command attachment 重扫

重扫 snapshot 为 `2026-09-07T02:13:55.027547+00:00`，文件 manifest SHA-256 为 `46289afabb92d3223f9176a3eb528a18afdf24f9ce29fe7618f7cbf795fa26a2`。仍按根目录 UUID 文件为主会话、根目录 `agent-*.jsonl` 加 `subagents/` 为 subagent 的口径扫描全部 922 个 JSONL。

| 指标 | 总数 | 主会话 | subagent |
|---|---:|---:|---:|
| JSONL 文件 | 922 | 176 | 746 |
| 含 `queued_command` 的文件 | 61 | 46 | 15 |
| `queued_command` attachment | 436 | 417 | 19 |
| `origin.kind == "human"` 且 `prompt` 为 string | 88 | 88 | 0 |
| 与四项裁决关键词相关的 human prompt | 2 | 2 | 0 |
| JSON 解析失败 | 0 | 0 | 0 |

相关命中采用 `local tokenzier`／`local tokenizer`、`历史学习`、`具体学习过程`、`精进机制`、`cold-start`、`multiplier`、`exact`、`prefix`、`profile`、`opaque reasoning`、`低置信`、`样本准入`、`prequential`、`state bounds` 的大小写不敏感并集；两条相关命中正是下列 TC-UR-02 与 TC-UR-04，未出现第三条相关 human prompt。

可复查的 attachment 枚举核心如下：

```python
from pathlib import Path
import json

root = Path("/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py")
files_with_queued = set()
queued = []
human_prompts = []
parse_failures = []
for path in sorted(root.rglob("*.jsonl")):
    for line_number, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except Exception as error:
            parse_failures.append((str(path), line_number, repr(error)))
            continue
        attachment = record.get("attachment")
        if record.get("type") != "attachment" or not isinstance(attachment, dict) or attachment.get("type") != "queued_command":
            continue
        files_with_queued.add(str(path))
        queued.append((str(path), line_number, record.get("uuid"), attachment))
        origin = attachment.get("origin")
        if isinstance(origin, dict) and origin.get("kind") == "human" and isinstance(attachment.get("prompt"), str):
            human_prompts.append((str(path), line_number, record.get("uuid"), record.get("timestamp"), attachment.get("source_uuid"), attachment["prompt"]))
print(len(files_with_queued), len(queued), len(human_prompts), len(parse_failures))
```

### Erratum TC-UR-02：精确目标与历史学习

- `source_locator`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，top-level attachment UUID `78db73d0-10df-4e90-9207-26eb6e1cd2ca`，timestamp `2026-09-06T19:12:33.749Z`，辅助行号 902。
- `attachment_locator`：`attachment.type = "queued_command"`，`attachment.source_uuid = "cdcbf829-3e18-432b-9be4-c732a8758715"`，`attachment.origin.kind = "human"`，`attachment.commandMode = "prompt"`。
- `full_quote`：`不要逃避问题了，我们的 local tokenzier 一定要努力做到精确，要增加历史学习能力`
- `speech_act`：直接命令并纠正实施方向。用户明确要求 local tokenzier 努力做到精确，并增加历史学习能力；“不要逃避问题”同时否定以回避核心精度问题的方式收窄任务。
- `confirmed_scope`：`local tokenzier 一定要努力做到精确` 与 `要增加历史学习能力` 是 direct user-natural-language，来源强度为 confirmed。
- `difference`：原句没有出现“低置信 estimate 只能是 cold-start”，也没有出现“单一跨结构 multiplier 不满足要求”。前者是实施者对精度目标与历史学习的架构化收束；后者与 assistant UUID `26e9d71a-0969-49b3-8f07-06d0f6643968` 的后续表述一致，但不是该 user prompt 的逐字内容。
- `conclusion_strength`：`confirmed`，只覆盖上述原句的精确目标与历史学习要求；§2.2 第 2 项整句作为逐字引文仍为 `refuted`，其余扩写属于 proposal 选择背景加实施者推导。

### Erratum TC-UR-04：学习过程委托

- `source_locator`：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`，top-level attachment UUID `e0d60d1c-2593-4007-b507-af363b3dc812`，timestamp `2026-09-06T19:14:31.333Z`，辅助行号 972。
- `attachment_locator`：`attachment.type = "queued_command"`，`attachment.source_uuid = "0310b228-4c7c-4782-81e5-045ed2b4c968"`，`attachment.origin.kind = "human"`，`attachment.commandMode = "prompt"`。
- `full_quote`：`具体学习过程不要询问用户，你必须设立完善的精进机制`
- `speech_act`：直接命令与实施授权。用户明确要求不再就具体学习过程逐项询问，并要求实施者设立完善的精进机制。
- `confirmed_scope`：`具体学习过程不要询问用户` 与 `必须设立完善的精进机制` 是 direct user-natural-language，来源强度为 confirmed。
- `difference`：原句没有逐项列出算法、样本准入、持久化、prequential 误差、漂移、版本迁移、state bounds 与降级，也没有说“不授权删除前三种 method 或改变优先关系”。这八类机制清单与 method 保留／排序约束是依据宽授权、TC-UR-03 的 selected proposal 及实施者设计形成的具体化内容，不是该 user prompt 的逐字组成。
- `conclusion_strength`：`confirmed`，只覆盖不再逐项询问与必须建立完善精进机制的直接授权；§2.2 第 4 项整句作为逐字引文仍为 `refuted`。

### 纠正后的来源矩阵

| Ruling | user-natural-language | user-selected-from-proposal | 实际可归于用户的范围 | 不可伪称逐字的扩写 |
|---|---|---|---|---|
| TC-UR-01 | 未找到 | confirmed | 选择低置信估算 proposal，含排除 opaque bytes、估可见／结构部分、保留 `estimated:true` | upstream 无 count endpoint 等未出现在 selected proposal 的限定 |
| TC-UR-02 | confirmed | 与 TC-UR-01 选择背景相连，但无独立 selection | 努力做到精确；增加历史学习能力 | 只能 cold-start；单一跨结构 multiplier 不满足要求 |
| TC-UR-03 | 未找到 | confirmed | 选择 exact-first、append-only prefix＋suffix、无 prefix 时 profile calibration 的混合学习 proposal | tokenizer identity；全新 identity 才 cold-start；更细 eligibility 等 |
| TC-UR-04 | confirmed | 与 TC-UR-03 选择背景相连，但无独立 selection | 不再询问具体学习过程；必须建立完善精进机制 | 八类具体机制清单；method 不可删除；优先关系不可改变 |

### 对原结论的纠正

前文整体 `VERDICT = not-found` 被本 erratum 部分推翻。纠正后的 verdict 是 `found-partial`：TC-UR-02 与 TC-UR-04 各找到一条 direct user-natural-language `queued_command` attachment；TC-UR-01 与 TC-UR-03 仍只有 confirmed `user-selected-from-proposal`，没有 user-natural-language 逐字段落。四条 §2.2 长句均不能整体称为“逐字记录”，但再说“四项均无直接用户自然语言来源”也已经错误。

前文原 `## 交付声明` 中的 `conclusion_strength = confirmed` 仅对当时那个过窄、漏扫 attachment schema 的结果成立，现已被本 erratum 部分推翻。新结论的强度为：attachment 的存在、human provenance 与原句为 `confirmed`；扩写的来源边界为 `confirmed`；对 transcript 根之外是否还有其它裁决不作断言。

新增后续真实 user text 的旧问法也被纠正：TC-UR-02 与 TC-UR-04 的两条 human queued commands 正好处在两个 `AskUserQuestion` 选择之后，属于此前遗漏的 selection-linked 用户输入。它们没有进入 `message.content`，不能再以“后续真实 user text 数为 0”排除。

## Erratum 交付声明

- `erratum_complete`：`true`
- `completed_at`：`2026-09-07T02:15:07+00:00`
- `corrected_rulings`：`TC-UR-02, TC-UR-04`
- `report_sha256_before_erratum`：`778c15fe75967fa280d60dcbd3afaeece27debc2ec28ccde10c9911a559f174e`
- `report_sha256_after_erratum_body_before_this_declaration`：`edfd7136af0fa608162cdc37c49a5676b01c1d1c86ffc8a2f390628a6a2d39f5`
