# Task 4 独立 code review

> 本文件由coordinator从reviewer `af23b55d`完整末轮转录；reviewer受运行时上级规则限制未写目标文件。以下正文保持原结论与证据边界。

评审对象为固定 package `d824e4f..618fc54`，并对照Task 4 brief、implementer report、current Spec Responses→Anthropic矩阵及Target profile、Acceptance REQ-05A。按要求未重跑测试、mutation、Ruff、Pyright或production probe。

## Verdict

- **核心wire／终态实现：PASS。** 未发现合法输入被发送成错误thinking／output_config、拒绝路径错误调用upstream、profile顺序错误、direct Responses误入translator或sibling residual静默丢失。
- **完整Spec acceptance：NEEDS-FIX。** 一个capability intersection loss detail错误描述实际catalog；`minimal`两阶段loss组合没有可判否测试。
- **Code quality：NEEDS-FIX。** 两项均为minor，不涉及主要wire或路由正确性。

## Findings

### Minor m1：过滤capability后的loss detail错误声称model没有发布reasoning effort

位置：`reasoning.py:79-91`、`anthropic_messages.py:550-565`、`test_reasoning.py:67-74`、Spec反向矩阵。

`align_anthropic_effort()`正确地先把catalog与Anthropic五档取交集，但把过滤后的空tuple直接交给`align_effort()`。Catalog发布`("none","minimal","future-level")`、请求high时，wire正确保留thinking并省略output_config；loss却说：

```text
high effort was not sent to Anthropic: this model advertises no reasoning efforts
```

Model实际发布了efforts，只是没有Anthropic writer可发送的五档候选。混合集合`("minimal","medium")`、desired low时，writer正确发medium，但理由称low“weaker than anything this model offers”，忽略minimal。准确限定应为“Anthropic-compatible candidates”，不是整个catalog。问题不改wire或终态，但conversion loss是Spec产品事实，不能错误描述原因。

### Minor m2：`minimal`两阶段catalog alignment与双loss没有组合oracle

位置：`anthropic_messages.py:536-566`、`test_translation_driver.py:570-612`、Spec／Acceptance。

Production行为正确：minimal先记录`minimal→low`approximation，再把low送入capability alignment；target不发布low时再产生第二个approximation，capability缺席时再产生not-carried。

现有minimal测试只用完整五档catalog，固定exact low和第一阶段一条loss。Downward／floor／not-carried测试只用普通五档输入。以下缺陷可能保持现有测试全绿：minimal记录第一条后直接发low绕过alignment；或仍对齐wire但仅对minimal静默省略第二阶段loss。

建议以静态expected增加`minimal + ("medium",)`，固定output_config.medium和两条有序approximation；另加`minimal + catalog absent`，固定thinking保留、effort缺席以及approximation＋not-carried两条事实。Expected不能由产品resolver生成。

## Compliance walkthrough

- Responses reasoning缺席→intent None；对象存在且effort缺席／null→enabled无effort；non-object／非字符串／unknown／literal ultracode均精确拒绝。
- Profile按resolved model最后fullmatch；bundled正负域与用户追加pattern覆盖有静态测试。
- Enabled profile按modes顺序取首个可渲染项；不可渲染enabled继续adaptive；only-enabled缺budget／max或budget>=max时拒绝。
- Disabled要求profile及can_disable；disabled_max_effort缺席无额外上限，high允许、medium拒绝。
- Missing profile、always-on disabled、extended-only缺budget和request-time budget边界均400、稳定code／param、零upstream。
- Minimal先转low并记录第一阶段；五档来自catalog与Anthropic五档交集，除m1原因文字外wire正确。
- Reader把reasoning sibling放nested residual；同格式writer先重建再覆盖owned effort；跨格式逐context／mode／summary记录loss，不重复effort。
- Direct `/responses`结构性旁路registry，literal ultracode原始bytes测试能判translator误介入。
- Review package只修改brief六个production／test文件；catalog fixture扩展是Task 4支撑改动。
- Profile facts持久化属于Task 5，未列为Task 4缺陷。

## Test provenance与证据边界

新增测试的wire expected主要为静态literal。m1是测试固定了错误诊断，m2是组合状态未构造，不是一般性同源。

Implementer报告31 targeted、181 translation-driver unit、Ruff、Pyright、9／9mutation；controller报告merged-state 174 integration＋25 selected unit。均作为绑定package的既有证据，本reviewer未重跑；既有mutation不覆盖m1／m2。

SPEC: NEEDS-FIX
QUALITY: NEEDS-FIX
COUNTS: blocker=0 major=0 minor=2 nit=0
