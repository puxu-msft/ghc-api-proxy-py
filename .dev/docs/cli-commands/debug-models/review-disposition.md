# `debug models` 评审处置记录

日期：2026-08-20
对象：`ghc-api-proxy debug models` 的实现，共六个提交：`a46eb8d`、`883b104`、`14a5012`（原为 `3bcf14c`，被并行会话 rebase，patch 逐字节一致）、`a224654`、`0f9abbc`、`aa1b2c4`
评审报告（四轮、五份，全部 0 blocker）：

- `reports/260820-review-debug-models-gpt.md`（异源独立评审，实跑证伪）
- `reports/260820-review-debug-models-opus.md`（同源设计评审）
- `reports/260820-review-endpoint-defaulting-gpt.md`（异源，针对 883b104 + 14a5012）
- `reports/260820-review-endpoint-defaulting.md`（同源，针对同两个提交）
- `reports/260820-review-endpoint-allowlist.md`（异源，针对 0f9abbc）

另有一份收尾文档事实核对：`reports/260820-closeout-factcheck.md`。

下表是逐条裁决，含**未采纳项及其理由**。

## 处置表

第一轮（GPT 独立证伪评审）：

| ID | 严重度 | 结论 | 落地 |
|---|---|---|---|
| F1 | major | 采纳 | `_read_config`（`src/app/cli.py`）把 `FileNotFoundError` / `ValidationError` / `YAMLError` 转成一行 `error:` + 退出码 1，保留 Pydantic 的字段路径，只丢掉调用栈。 |
| F2 | major | 采纳（收敛版） | `build_rows` 改为返回 `(rows, unreadable)`；无法产出行的 entry 被计数并写进摘要。新增 `malformed` 状态，覆盖「字段存在但类型不对」。 |
| F3 | major | 采纳 | 文本表的每个 cell 经 `_printable` 剥离 C0/DEL，复用 `app.observability.footer.CONTROL_CHARS`。`--json` 不做剥离。 |
| F4 | minor | 采纳 | `--json` 的 help 与 docstring 改为 “complete decoded upstream payload”，不再声称 verbatim。 |
| F5 | minor | 一半采纳，一半驳回 | 采纳 cell 计宽（`rich.cells.cell_len`）；**驳回**按终端宽度截断 id。 |
| F6 | minor | 采纳 | 补强弱断言，并为 F1～F3 各补了鉴别性用例。 |

第二轮（Opus 同源设计评审，读到的是修完第一轮的版本）：

| 条目 | 结论 | 落地 |
|---|---|---|
| summary 行漏了控制字符剥离 | 采纳 | 剥离点上移到 `status_of`——上游文本变成状态词的唯一入口，表格与摘要因此共用同一份处理。 |
| 上游 `policy.state` 与本地状态词撞名 | 采纳 | 改为 `policy:<state>`。上游发 `"ok"` 不再被读成可路由，发 `"disabled"` 不再与操作者禁用混淆。 |
| `collect_catalogs` 无自动化测试 | 采纳 | 新增 4 个用例：失败隔离、`--provider` 只问一家、每家读自己的 disabled 列表、建链失败时仍关 client。 |
| CLI 对外契约未裁决 | 不动手，上报用户 | 见下节。 |
| 双宽对齐那条红测试是「测试量错单位」 | 已独立发现并修正 | 断言改用 `cell_len` 计位；实现未动。 |

它同时明确同意第一轮的三条 major，但拒绝为 F3 套用「上游可能是恶意的」论证（真实抓取里控制字符数为 0）。这一点与项目「不做想象出来的安全戏码」一致，本仓库的修复也确实是按输出正确性立论的，不是按威胁模型。

第三轮（对 `883b104` + `14a5012` 的两份评审：`260820-review-endpoint-defaulting.md` 同源、`260820-review-endpoint-defaulting-gpt.md` 异源）：

两份**独立发现了同样的两个缺陷**，均已修复于 `a224654`。严重度评级不同：同源两条都判 major，异源判 F1 major、F2 minor。下表按较高的一档记。

| 条目 | 严重度 | 结论 | 落地 |
|---|---|---|---|
| 兜底不只对「键缺席」生效：字符串／dict／数字等任何非 list 都被填默认端点，并**真的发往上游** | major | 采纳 | 只有 `None`（缺键或显式 null）才触发兜底；present-but-unparseable 一律 fail closed。字符串 `"/responses"` 的反例最尖锐——它携带的路径与默认值相反，却被忽略并发往 `/chat/completions`。修完后报告的 `malformed` 与路由的 `CapabilityMissing` 对同一条目给出一致裁决。 |
| 显式 `[]` 被报成 `no-driver`，责任方指反 | major | 采纳 | `no-endpoints` 仅为这一种情况恢复。用户裁决要去掉的是「缺键」那种情形，而缺键现在根本到不了这个分支。 |
| `capabilities.type` 被独立读两遍 | minor | 采纳 | 提升为 `model_type_of`，放在 `resolve_endpoints` 旁边，路由与报告共用一个读取口。 |
| 新增 provider 测试里 `embed-model` 那一半无分辨力 | minor | 采纳 | 改用一个 type 为 embeddings、却声明 `/chat/completions` 的模型——只有这样「声明值被保留」与「被默认值覆盖」才会给出不同结果。 |
| `render_json` docstring 漏了 `len==1` 条件 | minor | 采纳 | 补上。 |
| `completion` 类型映射到 `/chat/completions` 属推测；参考实现指向 `v1/engines/<model>/completions` | minor | **不改，上报用户** | 用户 2026-08-20 的裁决明文是「embedding 模型的标准 endpoint 和 `/chat/completions`」两分。评审给出的是相反证据而非等价方案，改它等于推翻裁决。影响面为 1 个模型（`gpt-41-copilot`）。见下节。 |
| 报告说 `ok`，但 `/v1/messages` 打到这些模型会 400 `TranslatorNotFound` | minor | **不改，上报用户** | 这是既存的翻译器缺口，本次把受影响模型从 3 个放大到 23 个。属于另一条产品线的工作，不在「实现 debug models」范围内。见下节。 |

同源评审另确认：commit 的核心声称「这些模型现在真能路由到」**成立**——`/chat/completions` 与 `/embeddings` 的入站路由加 direct driver 全链存在，已逐环验证。

## 用户裁决

**全部已裁决，权威载体是 `.dev/docs/cli-commands/debug-models/decision.md`。** 本文件是本话题的临时评审处置记录，不承载跨会话存活的裁决。

用户 2026-08-20 的四条：现有选项保留；embeddings 不接入 LLM 入站路径（`outbound.to-openai-embeddings` 不做）；`outbound.to-openai-chat-completions` 由用户后续补；`completion` 类型端点由实测确立。

那份文档还记了一处本文件早先的框定错误：同格式路由不需要翻译器，41 个有端点的模型经各自原生入站路由都可达，「22 个被挡住」只是从 `/v1/messages` 一个入口看的结论。

第四轮（对 `0f9abbc` 的异源评审：`260820-review-endpoint-allowlist.md`）——0 blocker、1 major、3 minor，全部采纳，修于 `aa1b2c4`：

| 条目 | 严重度 | 落地 |
|---|---|---|
| 未知类型无端点时仍标 `assumed=True`，于是图例打出「按模型类型取的标准端点」，而端点列是 `-` | major | `assumed` 改为「确实填入了东西」才为真。这是报告自相矛盾，与之前修的几条同类。 |
| 不可读的 `capabilities` / `capabilities.type` 被当成普通「无端点」，丢掉了「目录形状坏了」这个事实 | minor | 纳入 `_wrong_shape` → 报 `malformed`。**变异检验发现我加了代码却没加测试**，已补。 |
| 测试未覆盖「非空的未来类型」与错误的 `assumed` 状态 | minor | 用 `chat-v2` 替代单纯缺 type，并断言三种无端点情形均 `assumed is False`；另加一条「只有未知类型时不得出现 `?` 图例」。 |
| 「本主机根本不可服务」与单行归因过强 | minor | 改成点名实测过的四个 path；引用改为 `model.ts:112` + `fetch.ts:470` + `fetch.ts:310` 三处，因为 dispatch 跨这三行，line 310 自己不读 `capabilities.type`。 |
| `model_type_of` 保持大小写精确匹配 | 评审确认合理 | 未改。`"Embeddings"` 未被实测过，用 `casefold()` 自动扩权与 allowlist 的立论相悖。 |

## 未采纳项及理由

**F5 的截断建议（按探测到的终端列数截断 id 并加省略号）——驳回。**

理由有三：

1. F3 修好之后，超长 id 造成的已经只是终端软换行，不再是**谎报**。表格不会多出行、列也不会错位，读者看到的仍是真实的一行，只是被终端折了。这与 F3 修的那类缺陷不是一个量级。
2. 触发条件是假设的。上游真实目录里最长的 id 是 `text-embedding-3-small-inference`（32 字符），报告里 165 字符的样本是构造出来的。为一个未观察到的形态引入终端宽度探测 + 截断逻辑，属于项目开发约定明确拒绝的预建。
3. 截断会引入新的失真：被截断的 id 不能直接复制去做 `--provider` 之外的检索，而 `debug models` 的读者常常正要把 id 贴到别处。完整值目前由 `--json` 承载，这条路径没有被削弱。

如果将来上游真的出现长 id，这条随时可以重新捡起——届时它就有了具体的触发场景，而不是现在的假想。

## 一处评审未提、但实现时自行发现并修掉的问题

首轮实跑真实上游时，42 个模型里有 18 个被报成 `no-driver`。查证后发现它们的 `supported_endpoints` 键在上游载荷里**根本不存在**（包括全部 embeddings 模型）。因此先拆成了 `no-endpoints` 与 `no-driver` 两个状态。

**用户随后裁决（2026-08-20）：不要 `no-endpoints`。** 该情况分两种，embedding 模型走其标准 endpoint，其余走 `/chat/completions`。

（后续修正：被推翻的是**缺键**那种情形——它现在根本到不了这个分支。`no-endpoints` 这个词在第三轮评审后为「上游显式发来空列表」这唯一一种情况恢复，见上方第三轮处置表。）

实测枚举证实了这条二分：18 个缺失项 = 3 个 `embeddings` + 14 个 `chat` + 1 个 `completion`，且全目录没有任何条目给出空列表。

落地位置的选择很关键。只改报告是不行的——`require_endpoint` 对空能力集是 fail-closed 的，路由本来就会拒绝这 18 个模型，报告若说 `ok` 就成了谎。所以判定放进 `model_provider/types.py` 的 `resolve_endpoints`，由 provider 的 `replace_catalog` 与报告的 `build_rows` 共用，两者不可能给出不同答案。

**连带的行为变化（需用户知晓）**：这 18 个模型此前会被本地 `CapabilityMissing` 拒绝，现在可以真正路由了。这是该裁决的直接后果，不是附带扩权。

两条边界守住了：

- **缺键**才填默认值；**显式空列表**是上游在说「没有」，原样保留，`CapabilityMissing` 继续成立。真实目录从未出现空列表形式，所以这条区分不影响现状，只是不让填充越界。
- 填出来的 endpoint 在报告里带 `?` 标记并有图例说明「非上游声明，按模型类型取的标准端点」。把推断当成上游原话呈现，与评审 F2 反对的「把无法读取伪装成上游没提供」是同一类缺陷。

## 验证

- 变异检验十四处（五轮），全部确认能变红：
    - 删掉 `status_of` 的 `no-endpoints` 分支
    - 删掉 provider 的 `self._raw_catalog = dict(raw)`
    - 让表格最后一列也补齐宽度
    - `collect_catalogs` 改成重抛而不是隔离失败
    - 去掉 `finally` 里的 `aclose()`
    - `policy.state` 不加前缀直接上报
    - 清空 `_DEFAULT_ENDPOINT_BY_TYPE`（embeddings 模型落到 `/chat/completions`）
    - 取消「显式空列表」那一支（空列表也被填默认值）
    - provider 不再读 `capabilities.type`
    - `render_json` 忽略 `keyed=False`
    - `keyed=False` 时连多 provider 也去掉外层键
    - CLI 不把 `keyed` 开关传下去
    - 畸形（非 list 非 None）的 `supported_endpoints` 重新被填默认端点
    - 显式空列表重新报成 `no-driver`
证据强度声明：上述变异结果、首次 8 项枚举与真实上游的运行数字都是**本会话的一手执行记录**，没有留下独立于会话之外的持久证物。它们足以支撑本文档的判断，但一个不读会话记录的复核者无法重新验证；能被独立复核的是提交内容、测试断言与再跑一次命令的结果。

- 用评审报告里的原始畸形载荷复跑：8 个 entry → `4 models, 2 routable, 2 malformed (4 unreadable entries skipped)`，输出中无 ESC，无被换行伪造出来的行。
- CLI 错误路径复跑：坏 config 与缺失 config 都是一行 `error:` + 退出码 1，无 traceback，Pydantic 的字段路径保留。
- 真实上游复跑：`42 models, 42 routable`，`--provider ghc --json` 顶层键为 `['data','object']`，不带 `--provider` 时为 `['ghc']`。

变异还原应当用文件副本比对，不用 `git checkout`。本会话两次违反这一点并两次造成损失：第一次把一个未跟踪文件的还原变成了对同名已跟踪文件的回退；第二次是在已经把这条教训写进本文档之后，仍在一条顺手的清理命令里用了它，`debug/models.py` 上本轮四处评审修复被整体回退，重新落了一遍。

skill `trusting-a-green-result` 已明文覆盖这一失效（并注明该技术此前已毁掉真实工作六次），所以这属于未执行既有规则，不新增资产。值得记下的是第二次的形态：规则已知、已写下，仍在被当作杂务的那一步上被绕过。
