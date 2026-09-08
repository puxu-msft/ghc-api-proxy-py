---
report_id: token-counting-spec-review-2026-09-07-gpt-high
attempt_id: token-counting-spec-review-20260907-gpt-high-01
status: in-review
reviewed_at_rev: sha256:ab4c000740a722fed456a79ea9a69f6e22fae774eedc845f560048d7dce9a1c7
reviewed_object: /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md
reviewed_context:
  README.md: sha256:c9e91c2dc9ec773cc0e5fc6d1c6953620e005a4779865fb225620a23472e47d8
  plan.md: sha256:26df43b16092f9886dd17d5105332d854495b64d405eda9f2d872b0045a4c790
  status.md: sha256:0f4093df040e10cedb746089caea8ba8ed5b9448eaade276928df22aaebbbef1
  coordinator_checklist: sha256:c2bfdbfbf3ad1b5d84f9ba2814b6611828bf17d2263ec929181fd70df64fe056
---

# Token-counting living Spec 独立评审

## 评审范围

被评对象是`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`的上述SHA-256内容快照。目标是判断它在任何production修改前是否达到0 blocker／0 major，并重点审查`<|endoftext|>`等configured-tokenizer special-token spelling的ordinary-text合同。

判据来源包括coordinator checklist、五份`docs/.human-controlled/`人控文档、项目living-Spec／no-bypass规则、Anthropic官方Token Counting、Context Editing与Vision文档，以及当前源码和测试的只读快照。`README.md`、`status.md`、`plan.md`和点时special-token调查只用于核对文档职责、实施闭合性与现状，不能反向定义Spec。

明确不在本轮范围内的是production实现验收、数值准确率验收、live upstream调用、完整测试套件和minor／nit清点。本轮按派活契约只报告blocker与major。

## 版本切换说明

评审过程中主树Spec由初读时的`sha256:8bb8c2ae8a86e46189566e454856727c6d7aa23e17713c1bc064b6d5fc4fc982`变为本报告绑定的`sha256:ab4c000740a722fed456a79ea9a69f6e22fae774eedc845f560048d7dce9a1c7`，README、plan与status也同步变化。旧快照上的初稿结论已在对话返回前作废并按当前完整内容重审；本报告的finding与计数只适用于当前摘要，不把旧快照发现混入当前状态。

## 总体判定

`needs-fix`。未发现blocker，发现2条major；因此尚未达到production implementation所需的0 blocker／0 major，§14 gate必须保持关闭。当前计数为blocker 0、major 2、minor 0、nit 0。

## Findings

### token-counting-spec-review-2026-09-07-gpt-high-02：special-token条款没有可判否验收、完整surface转录或权威被否路线

```yaml
finding_id: token-counting-spec-review-2026-09-07-gpt-high-02
severity: major
primary_location: /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §12.2 A3，第416行
related_locations:
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §4.2，第167至168行
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §11，第381至393行
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §13，第438至454行
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §15，第464至470行
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/spec-review-2026-09-07-coordinator-checklist.md C3、C8、C9
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/special-token-counting-research-2026-09-07-claude.md，第6至38行
  - /home/xp/src/ghc-api-proxy-py/tests/unit/tokenization/test_local_token_worker.py，第59至70行
```

**证据：** 当前§4.2只用一句“任何reserved spelling都作为ordinary text处理”表达意图，且known-field列表示例没有显式列出Anthropic顶层`system`；全文没有出现用户报告的字面`<|endoftext|>`、`allowed_special`或`encode_ordinary`。更关键的是，A1～A23没有任何一条给special-token spelling正确样本或目标缺陷注入：A3现在只验证opaque／media分类。即便未来只断言“返回正数”，`allowed_special={"<|endoftext|>"}`仍会把普通字符解释成一个控制token并返回正数，不能证明ordinary semantics。§13没有把本轮条款映射到当前旧failure test、Anthropic／Responses unit矩阵或production ASGI两条local path；§11也没有收录本轮已明确否决的四条实现路线；§15修订记录没有记录本次用户报告及其合同变化。点时调查已在`tiktoken 0.14.0`上区分默认guard、`encode_ordinary()`与`allowed_special`，并通过production入口分别复现Anthropic local与Anthropic→Responses local的500；当前唯一字面`<|endoftext|>`测试仍要求Responses worker抛`ValueError`。

**影响：** C3、C8与C9不成立，living-Spec的no-bypass要求也未闭合。§4.2足以说明default guard不应被当成合法local operational failure，但当前production gate没有任何oracle能阻止实现者采用`allowed_special`、只修Responses、漏掉Anthropic `system`／tool schema或保留旧failure expectation。用户报告的500因此可以在另一合法位置原样保留，或者以错误token语义“修绿”。

**承重前提检查：** 本finding依赖“ordinary-text成功必须区别于special-token控制语义，而不只是区别于异常”。若验收断言token sequence或精确delta等于独立ordinary oracle，`allowed_special`会被判红；当前A1～A23没有这类断言。点时调查只证明本地encoding mechanics和production入口故障位置，不冒充provider账单精度。

**建议：** 在§4新增具名ordinary-text条款，明确`<|endoftext|>`等所有configured-tokenizer special spelling在Anthropic `system`／messages／tool schema与Responses `instructions`／messages／tool schema／function-call arguments／output中都按普通字面文本处理；其拼写不改变known-text与opaque carrier分类。新增独立验收项：unit层以不同源ordinary oracle断言token sequence或精确delta，分别注入default guard与`allowed_special`并要求变红；production ASGI层分别覆盖Anthropic local与Anthropic→Responses local，断言完整成功对象、非500及provider调用次数，同时声明不证明账单精度。同步§11、§13和§15，并将旧worker metrics failure改为synthetic estimator failure。

### token-counting-spec-review-2026-09-07-gpt-high-03：四项“直接用户逐字裁决”缺少可独立解析的一手来源锚

```yaml
finding_id: token-counting-spec-review-2026-09-07-gpt-high-03
severity: major
primary_location: /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md §2.2，第33至40行
related_locations:
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/README.md，第11至18行
  - /home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md，“User ruling”与“Chosen architecture”
  - /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/api.md
  - /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/config.example.yaml
  - /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/ghc-api.md
  - /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md
  - /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/request-pipeline.md
```

**证据：** §2.2把四句话标成“逐字取自本任务brief”与“直接用户裁决”，但没有message／transcript锚、稳定原始引文位置或用户控制文档位置。五份人控文档只确认端点、provider配置和translation边界，没有记录这四项算法与fallback裁决。README与plan是同一组agent维护文档中的再次转述，不能作为独立一手来源。尤其“用户于某日选择”这种带解释性前缀的句式本身无法证明是用户原句还是实施者摘要。

**影响：** C1未达到评审所需的可核验归因。四项裁决控制public fallback、method集合与优先级以及实施者授权范围；错把agent归纳标成用户逐字裁决会永久关闭本应由用户决定的分叉。此finding不声称用户从未作出这些裁决，只判定当前Spec没有履行举证责任。

**承重前提检查：** 本finding依赖“已审文件中没有可解析的一手锚”。若原始用户消息确实存在并被加上稳定锚，归因可直接闭合；若不存在，则必须降低来源强度，不能继续称为逐字裁决。

**建议：** 为四项分别补上可解析的原始user-message／transcript锚与逐字引文，并逐项核对言语行为及scope；把实施者补入的日期、解释与限定拆出为派生说明。若原始锚不可恢复，改标为“agent维护的用户裁决转录，来源待核”并让coordinator取得用户确认，不能用plan／README之间的循环引用替代一手来源。

## Checklist C1～C10

| ID | Verdict | 依据 |
|---|---|---|
| C1 | FAIL | 权威层级与派生决定分层清楚，但§2.2四项“逐字／直接用户裁决”没有一手来源锚，见finding 03。 |
| C2 | PASS | §3.1～§3.2规定合法Responses target的local success严格为`{"input_tokens": N, "estimated": true}`，且`type(N) is int`、`N >= 1`；§4.2～§4.3使opaque／media／unknown只降低confidence而不使local unavailable。 |
| C3 | FAIL | §4.2表达reserved spelling的ordinary-text意图并覆盖多类known fields，但没有具名`<|endoftext|>`、没有明确Anthropic `system`的文本计数位置，也没有跨Anthropic／Responses surface矩阵或可判否oracle，见finding 02。 |
| C4 | PASS | §3.2要求direct Anthropic remote success保留`input_tokens`及存在时的`context_management.original_input_tokens`，local不合成后者；Anthropic当前Context Editing文档给出同形count response。 |
| C5 | PASS | §3.1明确一次frozen target、lazy legs、具名provider transport及禁止count-time model reroute；A4覆盖顺序、调用次数、identity与结果的正反控制。 |
| C6 | PASS | 当前§4.1～§4.3已把known text、categorical `ProfileKey`、quantitative `FeatureVector`及opaque／media／unknown carrier分开；excluded bytes仍贡献framing／features／low-confidence reason，并进入deterministic cold-start或history。 |
| C7 | PASS | 当前§5～§9已固定profile pool／distance／tie、exact eligibility、prefix suffix／demotion／recovery、profile promotion、prequential顺序、production inference→learn→later exact／prefix闭环、transaction、bounds、durability和drift；A5～A23提供对应判据。 |
| C8 | FAIL | A1～A23大多声明证据不可冒充项并有目标变异，但没有任何special-token正确样本、default-guard变异或`allowed_special`控制，见finding 02。 |
| C9 | FAIL | 当前§13没有列出`test_local_token_worker.py`、`test_responses_estimator.py`的旧failure expectation，也没有把special-token条款转录到Anthropic feature与production ASGI两条local path，见finding 02。 |
| C10 | PASS（Spec层） | Spec明确是normative、living；§14只限制production code时序；§15记录round-1修订，status把production保持未改与re-review gate写为WIP。isolated-worktree guard阻止本reviewer对主工作树执行Git状态查询，因此主树Git状态由coordinator另行核验。 |

## 权威边界、公开wire、实现闭合与证据边界结论

除finding 03的来源锚外，当前Spec把人控需求、实施者派生算法、plan、status与现有实现的职责分开。成功wire和count-specific错误wire已经闭合：Responses local与所有local fallback只有`input_tokens`及`estimated:true`，direct remote保留官方可选context-management字段；§3.3逐项转录error-envelope authority的status／type／code／carrier及cause passthrough。本轮未发现其它blocker／major级public wire冲突。

special-token guard不是合法的local operational failure。§4.2已明确reserved spelling不能让合法请求变成错误，§3.3的“其它未识别local exception→500”只适用于真正不可恢复的local exception，不能覆盖该先行义务。点时ASGI调查也把当前500的首个偏差定位到estimator API选择而非HTTP mapping。当前缺口不是应否成功，而是Spec没有足以阻止错误修法和遗漏surface的验收与转录，见finding 02。

当前Spec的deterministic cold-start、profile partition、method eligibility、same-attempt raw-total learning、prequential ordering、SQLite transaction／bounds、durable与best-effort观察分界以及production闭环，已达到可实现的明确度。官方文档确认count endpoint接受messages、system、tools、images和PDF，Context Editing可返回original count，Vision当前定义28×28 patch及model-tier resize／limit；这些官方事实只裁协议面，不证明本代理实现或真实provider billing精度。

## 被否路线

1. `allowed_special={"<|endoftext|>"}`：否决。它把普通客户端字符解释为控制token；即使返回正数，也违反ordinary-text语义，且现有A1～A23无法判红这条路线。
2. 在endpoint捕获`ValueError`后fallback：否决。合法known text不应产生该错误；catch只会把根因改写成unavailable、伪造值或local operational failure，并且无法修复worker及其它入口。
3. 只修Responses不修Anthropic：否决。当前两条estimator都调用默认`Encoding.encode()`，点时production ASGI调查已分别复现Anthropic local与Anthropic→Responses local的500。
4. 保留旧special-token failure expectation：否决。它把产品缺陷钉成metrics测试的预期行为；failure metrics应改用synthetic estimator failure，special spelling本身应成为成功回归。
5. 只从`disallowed_special`移除`<|endoftext|>`：否决。合同必须覆盖configured tokenizer的全部special-token spelling；逐项白名单会把同根缺陷留给`<|endofprompt|>`或未来新增spelling。
6. 只修最初事故的message位置：否决。Anthropic `system`／messages／tool schema与Responses `instructions`／messages／tool schema／function-call arguments／output共享同一ordinary-text不变量，按单一触发样本打补丁会留下同根缺陷。

## 搜索面与未覆盖面

已逐条读取coordinator checklist、当前被评Spec、当前README、当前status、五份人控文档，并补读plan、special-token点时调查、error-envelope Spec相关条款、Anthropic官方Token Counting／Context Editing／Vision文档，以及当前`estimators.py`、`worker.py`、`driver.py`、count route和相关unit tests。使用`rg`核对special spelling、估算入口与测试引用，并在当前快照上重新计算SHA-256。

未执行production测试、mutation、live upstream或完整代码审查。本轮结论针对Spec合同与现有转录面的可判否性，不声称当前实现通过；当前源码只作为“这些位置存在且旧failure expectation尚在”的只读证据。当前Spec的全面算法补写来自另一轮已落盘修订，本reviewer按最终内容独立重判，没有把status中的`fix-authored`当作已关闭。

## 我最没把握的三个判断

1. **finding 03的定级，信心中等。** 原始用户消息可能存在于本轮未提供的会话transcript；若coordinator补上稳定锚，事实缺口可快速关闭。当前仍定为major，因为四项规则控制核心产品分叉，且本reviewer可读的所有引用都是agent维护的循环转述。
2. **C3中“Anthropic system覆盖不足”的判断，信心中等。** §4.2的“所有已知可见／tokenizable fields”可被读为隐含覆盖system，但同句的具名列表只有`instructions`，而framing表对Anthropic system只定义4-token framing；本轮又要求逐surface审查，所以不能用隐含全称代替明确合同与验收。
3. **C7的PASS，信心中高。** 当前修订已把旧快照中的profile partition、prefix demotion／recovery和candidate tie补成确定规则；本轮没有执行algorithm mutation，只能确认文档可闭合与A9／A20的判据形状，不能宣称未来实现正确。

## 执行本契约时遇到的摩擦

- 首次批量`Read`错误地传入空`pages`参数，工具在读取前拒绝；随后以合法参数逐条重读，未形成缺页。
- 文件系统检查显示主树有`.codegraph/`目录，但CodeGraph MCP判定该项目没有可用索引；按其指示改用`rg`与`Read`，没有再次调用CodeGraph。
- 当前agent运行在隔离worktree，harness拒绝`git -C /home/xp/src/ghc-api-proxy-py status ...`指向共享主树；因此C10只完成文档门与源码快照核验，没有把主树Git洁净度包装成已验证事实。
- `Write`工具拒绝直接写主工作树中的指定REPORT_FILE；按用户明确授权改用简单、目标唯一的Bash创建与追加，未写其它仓库文件。
- 初次完整报告写成后、末轮返回前，Spec从`sha256:8bb8c2ae8a86e46189566e454856727c6d7aa23e17713c1bc064b6d5fc4fc982`变为`sha256:ab4c000740a722fed456a79ea9a69f6e22fae774eedc845f560048d7dce9a1c7`，README与status也变化。coordinator随后确认停止修改；本reviewer废弃旧结论、重读当前三份文件并重写本报告，未据旧哈希保留finding或计数。
- Anthropic API reference的WebFetch结果过大，由工具自动持久化到harness tool-results目录；只读检索显示通用response schema列出`input_tokens`，另由官方Context Editing页面确认启用该能力时count response可含`context_management.original_input_tokens`。该工具产物不在仓库内，也不是本报告创建的项目文件。

## 整体判定

当前Spec尚不能放行production implementation。0 blocker成立，但2条major分别阻断本轮special-token ordinary-text合同的可判否／转录闭合，以及四项核心用户裁决的可核验归因。其余C2、C4～C7与Spec层C10达到本轮判据。修订后应由同一reviewer按新SHA-256内容摘要复审；在0 blocker／0 major且coordinator完成逐条处置前，§14 gate保持关闭。


## 交付声明

delivery_complete: true
completed_at: 2026-09-07T01:57:03+00:00
finding_total: 2
blocker_count: 0
major_count: 2
minor_count: 0
nit_count: 0
