# Token-counting Spec review disposition

状态：closed。

本文件处置`reports/spec-review-2026-09-07-gpt-high.md`的发现。Living行为权威仍是`spec.md`；本文件只记录评审主张成立度、采纳决定、证据和复审去向。

## 收件回执

- `report_id`：`token-counting-spec-review-2026-09-07-gpt-high`
- `received_at`：2026-09-07。
- `reviewed_at_rev`：`sha256:ab4c000740a722fed456a79ea9a69f6e22fae774eedc845f560048d7dce9a1c7`。
- `counts_declared`：blocker 0、major 2、minor 0、nit 0。
- `counts_verified`：yes。报告含2个finding标题，尾部`finding_total: 2`及各档计数自洽；README、spec、plan、status与coordinator checklist的完整SHA-256均由coordinator独立重算并匹配报告。
- `snapshot_type`：hash。报告绑定的active四文件内容摘要和时间点写在报告frontmatter；没有把dotdev未同步WIP当评审对象。

## DISP-01：ordinary-text special spelling合同不可判否且转录不闭合

- `finding_id`：`token-counting-spec-review-2026-09-07-gpt-high-02`
- `statement_kind`：fact。
- `claim`：confirmed。
- `judgment_status`：concurred。
- `fix`：adopted。
- `level`：C，落进living Spec且可逆；已由fresh independent reviewer限定复审。
- `fix_evidence`：`reports/spec-review-2026-09-07-gpt-high-3.md`在README `sha256:56573075dd2843ead7dd9c0f1208fd9455e5cf018093ef94b065c01a35776add`、spec `sha256:cf83b6ad1bd0de5f2f5c0768a667a93f5c4e7219cc57038cd07bde2f8e932382`、plan `sha256:d1a71db01e2442d9fb3566c1558430bf8a1a773347ac5280b237cbdf2eb73608`、status `sha256:b7b8de0ab4685903dc736945da2a943207b89c37d8843c8233c87d76f216b812`上将finding 02判为closed，当前finding为none；报告SHA-256为`330fc9430965f43495241a1f73d0e4c0bf8d31fa5a6822be4f0035194804a58a`。
- `next_actor`：none。
- `response_required`：no。
- `pending_annotation_ids`：none。
- `evidence`：coordinator直接读取冻结Spec：§4.2只有“任何reserved spelling都作为ordinary text处理”的全称；§12.2 A1～A23没有`<|endoftext|>`正确样本、ordinary-token sequence／delta oracle、default guard或`allowed_special`反向控制；§11没有本轮六条被否路线；§13没有`test_local_token_worker.py`与`test_responses_estimator.py`的现有failure expectation及两条production ASGI local路径；§15没有本次事故修订记录。`reports/special-token-counting-research-2026-09-07-claude.md`已用`tiktoken 0.14.0`和mock production ASGI分别复现Anthropic local与Anthropic→Responses local 500，并证明`encode_ordinary()`与`encode(..., disallowed_special=())`token sequence相同且逐字round-trip。
- `承重前提`：ordinary-text成功必须区别于把字面串解释成special control token；它支撑“新增能判红default guard和`allowed_special`的验收与完整surface转录”这一动作。若前提为假，仅断言非500／正数即可；但`tiktoken`的两条编码路径对同一文本产生不同token sequence，且Spec已要求不赋控制语义，所以前提成立。
- `adopted_scope`：具名`<|endoftext|>`并覆盖configured tokenizer全部special spelling；明确Anthropic system／messages／tools和Responses instructions／messages／tools／function-call arguments／output；新增不同源ordinary oracle与default-guard／`allowed_special`两种目标变异；生产ASGI覆盖两条local target；更新§11、§13、§15；旧worker metrics failure改用synthetic estimator failure。
- `not_adopted`：没有。报告建议与现有living-Spec原则一致；数值oracle只裁ordinary encoding mechanics，不冒充provider账单精度。
- `recheck_outcome`：原reviewer的隔离worktree只能看见旧`.dev`快照，按身份门正确交付`blocked`报告`reports/spec-review-2026-09-07-gpt-high-2.md`；fresh independent reviewer随后在当前active冻结快照上完成限定复审并关闭本finding。

## DISP-02：四项“直接用户逐字裁决”来源归因失真

- `finding_id`：`token-counting-spec-review-2026-09-07-gpt-high-03`
- `statement_kind`：fact与judgment的复合项，已拆分如下。
- `claim`：confirmed，限定为“§2.2四个完整长句都不是可逐字归于用户的原文；第1、3项有user-selected-from-proposal锚；第2、4项有更窄的direct user-natural-language原话；四项中超出proposal或原话的详细限定由assistant首次完整表述”。不支持“用户从未作出相关裁决”。
- `judgment_status`：concurred，major定级维持；该归因控制fallback合同、method集合／顺序和实施者授权边界。
- `fix`：adopted。
- `level`：A／C交叉。修订保留两项用户proposal选择与两条human queued-command原话，只纠正来源类型并把超出原文的增补归为实施者派生决定，没有扩大或缩小用户已决定的范围。
- `fix_evidence`：`reports/spec-review-2026-09-07-gpt-high-3.md`在同一冻结四文件快照上直接解析原始transcript anchors，将finding 03判为closed，当前finding为none；报告SHA-256为`330fc9430965f43495241a1f73d0e4c0bf8d31fa5a6822be4f0035194804a58a`。纠正后的来源取证见`reports/user-rulings-source-research-2026-09-07-sonnet.md`，SHA-256为`ed095957eb833d38898ce36e8ff9c4d2c13adb744bff290ce16728fd0982a2fb`。
- `next_actor`：none。
- `response_required`：no。
- `pending_annotation_ids`：none。
- `evidence`：`reports/user-rulings-source-research-2026-09-07-sonnet.md`首轮用JSON parser扫描2026-09-07T02:06:16Z快照内922个JSONL文件，区分176个主会话与746个subagent文件，解析失败0；Addendum恢复两组完整AskUserQuestion proposal与配对tool_result。该扫描器只遍历`message.content`，遗漏顶层`type=attachment`／`attachment.type=queued_command`，所以“TC-UR-02／04无真实user text”已被后续一手记录推翻；同一报告正在追加erratum。Coordinator已直接解析下面两条attachment并确认inner `origin.kind=human`、prompt、UUID与timestamp。
- `decision_origin`：TC-UR-01和TC-UR-03为`user-selected-from-proposal`。TC-UR-01的source是transcript`4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`中assistant UUID `8b378b42-2843-433c-8451-9eb94e4e60cc`提出的单选proposal与user-role tool_result UUID `42764806-9deb-4951-951d-a3584f076f88`的选择；TC-UR-03由assistant UUID `7b55326f-835a-4d47-b749-4e6eae40fdae`提出，user-role tool_result UUID `04f71c54-bc93-4e2a-a18b-cdd998987ed2`选择。TC-UR-02为`user-initiated`：attachment UUID `78db73d0-10df-4e90-9207-26eb6e1cd2ca`、source UUID `cdcbf829-3e18-432b-9be4-c732a8758715`、timestamp `2026-09-06T19:12:33.749Z`，用户原话“不要逃避问题了，我们的 local tokenzier 一定要努力做到精确，要增加历史学习能力”。TC-UR-04为`user-initiated`：attachment UUID `e0d60d1c-2593-4007-b507-af363b3dc812`、source UUID `0310b228-4c7c-4782-81e5-045ed2b4c968`、timestamp `2026-09-06T19:14:31.333Z`，用户原话“具体学习过程不要询问用户，你必须设立完善的精进机制”。Cold-start、single multiplier、八类具体机制与method不可删除等扩写仍是proposal选择与`agent-decided-within-delegated-scope`派生内容，不能继续标为用户逐字原话。
- `承重前提`：AskUserQuestion选择是用户对assistant proposal的选择，而不是用户亲笔撰写proposal全文；它支撑“保留选择结果、改标decision_origin并拆出agent派生增补”这一动作。若前提为假，须把第1、3项也降为未核；但tool_use_id一一配对、单选结果与时间顺序已经独立确认，因此该前提足以行动。
- `adopted_scope`：保留第1项所选proposal的完整授权边界——Responses opaque reasoning／media／unknown场景排除opaque bytes、估可见／结构部分、保留`estimated:true`并接受近cap低估；保留第3项所选proposal的完整授权边界——exact优先、append-only longest-prefix actual＋suffix、无prefix按provider／model／profile学习校准、可分阶段实现。按第2项用户原话保留“local tokenizer必须努力做到精确并增加历史学习能力”；按第4项用户原话保留“具体学习过程不再询问用户，由实现者设立完善的精进机制”。把upstream-no-counter、configured-tokenizer identity、new identity cold-start、single multiplier、详细eligibility／drift／bounds、八类机制清单与method不可删除等超出proposal和原话的部分明确归为实施者派生决定，并给出授权／推导依据。
- `not_adopted`：不采纳“因四个完整长句都不是用户逐字原文，而把其中真实用户决定整体降为未裁决”。这是C级暂定驳回；反例包括两条已确认`user-selected-from-proposal`记录和两条已确认human `queued_command`原话。原review finding本身要求按真实来源补锚或降低扩写部分的来源强度，因此本处只是防止过度纠正，不与reviewer形成分歧。
- `recheck_trigger`：文档owner完成来源分层、稳定锚与README／plan同步后，由原reviewer限定复审本finding、修订diff及相邻authority条款。

## 当前门状态

- production implementation gate：open。
- 打开依据：DISP-01与DISP-02均为`adopted`；fresh independent reviewer在冻结active四文件快照上交付0 blocker／0 major，并在交付声明前复核四个SHA-256未变。该结论只打开production implementation，不声称production已符合Spec或local estimate已达到provider billing精度。
- 状态同步：token-counting文档owner需把`status.md`中等待本轮复审的volatile状态更新为implementation可开始；这不是再次修改Spec或重新评审的前置条件。
