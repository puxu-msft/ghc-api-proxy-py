# 候选文档对账评审

基准为 `docs/.human-controlled/` 的用户裁决与当前 `src/`。以下是 D1～D7 逐项核验后达到 MAJOR 门槛的结果；未列项没有 blocker 或 major。

## MAJOR-01：已采纳的监听地址热重载说明仍以提案保留（D2）

- 文档说：`config-migration-gaps.md:30-36` 仍把 `server.host` / `server.port` 的「不支持热重载」列为待裁决，并提议补进规格。
- 实际：该说明已经是用户裁决，`config.example.yaml:30-37` 已在这两个字段前明确写出「不支持热重载（需重启）」。
- 代码佐证：`src/app/config/schema.py:29-39` 已将两个路径纳入 `NOT_HOT_RELOADABLE`。
- 这与 `README.md:38` 的「相应提案已删除」相矛盾；应删除候选文档的整个第一节，而不是保留为提案。

## MAJOR-02：`config-schema-gap.md` 仍要求用户重裁已冻结的七项配置契约（D6）

- 文档说：C-2～C-8 仍在 `config-schema-gap.md:50,62,78,86,98,108,118` 标作「待裁决／待确认」。
- 实际：`client_request_deadline`、超时值、无内置映射、日期后缀、XDG 数据路径、累计缓冲与 continuation 已分别由 `config.example.yaml:7-8,77-78,136-143,289-314,340-347,383-402` 定义。
- 这些内容可以保留为「代码尚未符合的实现缺口」，但不能继续要求用户重新决定；否则候选文档否定了指定的最终权威。
- 该文件的 `:136-138` 也仍保留「已裁决事项」标题，未满足 D6 所述的删除后仅指向 `existing-rulings.md` 的状态。

## MAJOR-03：`config-schema-gap.md` 将已有 TLS 与 provider 实现误报为「当前完全没有」（D4）

- 文档说：`config-schema-gap.md:120-125` 将 TLS 和具名 provider 列入「规格要求但当前完全没有的能力」。
- 实际：TLS 已有三态模式、首字节常量和自签名材料实现，见 `src/app/server/tls.py:1-7,22-23,58-127`，并由 `tests/unit/test_tls_and_count_tokens.py:47-105` 覆盖。
- 实际：具名 provider 已有 `ModelProviderConfig`、registry 与构造链，见 `src/app/config/schema.py:71-77`、`src/app/model_provider/registry.py:16-58`、`src/app/server/composition.py:165-203`。
- 若尚缺入口接线，应准确写作未接线或部分缺口；「完全没有」还重新引入了 D4 已从缺口表移除的 `app.model_provider`。

## MAJOR-04：事件订阅的已实现机制与已裁决异常语义仍被写成待采纳提案

- 文档说：`pipeline-subscriptions.md:24-53` 将唯一 id、before/after 拓扑排序和闭集异常处理描述为旧 hooks 与需求之间的未实现提案。
- 实际：`src/app/pipeline/events.py:29-99` 已在 freeze 时校验唯一 id、未知引用与环并拓扑排序；`direct_driver/base.py:114-122` 以冻结顺序投递。
- 实际：`src/app/pipeline/exceptions.py:1-6,60-74` 已实现已知异常的闭集，未知异常中止，正是 `MAIN.md:62-64` 的用户裁决。
- 应移除已采纳的第 3 节及其删线残留，并把其余内容按当前事件机制重新对账；保留「差距集中在两点」会误导后续实现。

## MAJOR-05：`pm2` 与注释配置项被无来源地写成用户已否决

- 文档说：`existing-rulings.md:89-90` 把「pm2 部署暂不实现」及全部被注释配置项「暂不实现」标为本轮用户裁决。
- 实际：指定权威中没有这两条裁决；相反 `config.example.yaml:224-238` 规定 pm2 跳过 pidfile 且其 `kill_timeout` 须满足关闭时限关系。
- 「被注释」不等于用户否决功能，也不能推出「用户尚未决定」；该写法会把仍可能有效的配置和部署需求静默排出候选范围。
- 应删除这两个无一手来源的裁决断言，或明确标为未核实事实，不能作为删提案的依据。

## MAJOR-06：README 的目录摘要与正文、实际候选内容不一致（D7）

- 文档说：`README.md:29` 称 `existing-rulings.md` 有「7 项缺口」，`:38` 称 D1 对应提案已经删除。
- 实际：`existing-rulings.md:70-75` 的缺口表只有 4 行；`config-migration-gaps.md:30-36` 仍留着 D1 的监听地址提案。
- 证据：在当前 review worktree 的 `main`，`git rev-list --count main..feat/systemd-rolling-apply` 仍为 14，故 `deployment.md:53` 的数字此刻正确；README 的问题不是该数字。
- README 应改为与四行缺口表和候选文件的实际删留状态一致，避免其一行摘要成为第二个错误状态源。

## 复评

前轮 MAJOR-01、MAJOR-02、MAJOR-04、MAJOR-06 已闭合。MAJOR-05 的处置接受：协调方提供了用户会话原话，`existing-rulings.md:77-92` 已区分会话与文档来源并收窄 pm2 的未实现范围，故不再将其视为无来源裁决。

## MAJOR-07：第四节仍将已经接入生产处理链的能力报为「尚未具备」

- 文档说：`config-schema-gap.md:67-80` 把具名重试策略、三档 `buffering_policy` 与 `synthesized_response_headers_after_sec` 列为当前未具备。
- 实际：`server/handler.py:83` 用 `RetryLedger(chain.config.upstream_request_retry)`，`:163-199` 把三项 `client_delivery` 配置传入 `BlockBuffer` 与 `StreamSettings`。
- 实际：`pipeline/retry.py:25-30,65-119` 实现五种具名策略及 continuation；`pipeline/delivery/blocks.py:55-80` 和 `stream.py:21-24,117-120` 实现缓冲策略与合成头块。
- 应从「尚未具备」表移除这些已接线项，或精确改写为尚未实现的特定行为；否则重现了前轮 MAJOR-03 的「完全没有」误报。

## MAJOR-08：热重载节把未接线的 `ConfigProvider` 当成当前请求语义

- 文档说：`config-schema-gap.md:51-53` 称消费者会在工作开始取快照、在途请求沿用受理版本，且只缺触发机制。
- 实际：`ConfigProvider` 的该语义只存在于 `src/app/config/provider.py:95-123`；`rg -l 'ConfigProvider|pin_restart_only' src --glob '*.py'` 仅输出该文件，测试消费者也仅为 `tests/unit/test_config_loading.py`。
- 因而当前生产路径没有调用 `reload()`，也没有证据表明请求取得该 provider 的快照；真正缺口不只是 signal／文件监视触发器，而是 provider 整体尚未接入。
- 应把 C-3 的现状收窄为「已实现但未接线的快照原语」，保留热重载粒度与触发机制的用户待裁决。

## 第三轮

MAJOR-07 的反例处置成立：`synthesized_response_headers_after_sec` 只有配置传递、无字段读取或构件调用；`continuation_messages()` 仅由测试调用。MAJOR-08 的 C-3 改写和 `existing-rulings.md` C-4 亦与当前代码和 CLI 实测一致。

## MAJOR-09：`config-schema-gap.md` 重编号后留下三个错误的 C 节引用

- 文档说：结构对照的 `config-schema-gap.md:13,17,20` 分别引用 C-4、C-2、C-3 来说明模型映射、关闭时限和上游超时。
- 实际：当前第二节仅有 C-1 `buffer_cap_bytes`、C-2 continuation、C-3 热重载；不存在 C-4，后两处分别错误地指向无关的 continuation 与热重载问题。
- 证据：同文件 `:27-55` 是重编号后的唯一 C 节，且 `rg -n '见 C-[0-9]' .dev/human-controlled-docs-candidates/config-schema-gap.md` 仅命中上述三处。
- 应把三个交叉引用改为第三节的相应实现缺口行或删除引用；否则读者按结构对照追溯时会落到错误结论。
