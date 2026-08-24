# Hosted web search：当前状态与遗留项

日期：2026-08-22
锚定提交：`767d0f23514eff350c961cf307bf6b6f7c71a761`
性质：本切片的收口记录 + 待决清单。**这是一份活文档**，不是报告原件；报告原件在同目录 `reports/` 下按日期前缀存放。

> 路径说明：本文件位于 `.dev/`（独立仓库，被主仓 ignore）。以 `exp/`、`src/`、`tests/` 开头的路径相对**主仓工作树根**；以 `../` 或 `reports/` 开头的相对本文件。

## 1. 现在的行为（一句话）

**默认关闭。** 打开后，Anthropic 客户端声明的 web search 会被翻成上游 Responses 端点自己的 `{"type":"web_search"}` 并真的执行；关闭时，或模型不被 `models_support_web_search` 的任何一条正则认领时，请求**不发往上游**，代理合成一个 200 响应，内容是 `server_tool_use` 配对 `web_search_tool_result`，后者 `content` 为单个 `web_search_tool_result_error` 对象（`error_code: "unavailable"`）。

## 2. 两个配置轴

| 键 | 默认 | 语义 |
|---|---|---|
| `model_translation.to_openai_responses.hosted_web_search` | `false` | 这条腿**是否提供**该功能 |
| `model_providers.<name>.models_support_web_search` | `["gpt-[5-9]\\.\\d+.*"]` | **哪些模型**跑得动；每条是正则，`fullmatch` 匹配上游 `model.id` |
| `model_translation.to_openai_responses.web_search_domain_restrictions` | `drop_fields` | 客户端给了域名限制而上游无此参数时怎么办 |

两个轴都不通过时的应答形态相同，但**日志与 error code 不同**（`server_tool_disabled` vs `server_tool_capability_unavailable`）——默认是关的，所以「没人打开过」是两者中更可能的那个，运维必须分得清自己看的是哪一种。

## 3. 为什么默认关

支持是真的，但**不完整**，而缺的部分对客户端不可见：

- 交给 Anthropic 客户端的是**一行文本**，而协议定义的是 `server_tool_use` + `web_search_tool_result` 块对（规格 §5.3 已规定形态，用户 2026-08-20 裁决 D6 要求还原成原生块，**未实现**）。
- 上游**确实**返回 `url_citation`（`output[].content[].annotations[]`，字段 `{type,url,title,start_index,end_index}`），我们**零处读取**。一手样本：`exp/260820-websearch-probe/raw/B7-responses-tool-choice-builtin-response.txt`。
- `max_uses` 无法发送（上游 `Unknown parameter`），剥离并记 loss。
- `allowed_domains` / `blocked_domains` 同样无法发送，默认丢弃——而实测 190/190 真实子请求都带非空 `allowed_domains`。
- `tool_usage.web_search.num_requests` 上游白给，我们不读。

把一个半成品设成每个请求的默认，是这条裁决要避免的事。

## 4. 遗留项

按「会不会给出错误答案」排序，不按工作量。

### 4.1 发出的类型不是上游广告的那个

我们发裸 `{"type":"web_search"}`（实测 gpt-5.5／gpt-5.6-sol 返 200 并真的执行）。而上游 400 的枚举里列的是 `web_search_preview` 与 `web_search_preview_2025_03_11`，**未列**裸 `web_search`。三份第三方实现都发 `web_search_preview`。

**未改的原因是需要真实上游调用**：cassette 的请求 digest 覆盖整个请求体（`tests/int/recorded/cassettes.py:228`），改类型会让两份 web-search cassette 失配，必须用 `record_cassette.py` 重录。**重录本身就是那次探针**——接受则同时拿到新证据，400 则当场知道。等用户授权。

对应规格探针项 P11。

### 4.2 D6（原生块对）已裁决未实现

规格 §5.3 规定了形态，§6.3 规定了流式成块时点。当前实现产出一行文本，正是 §5.2 里被用户推翻的那个起草偏好。

原料比原先认定的充足：`url_citation` 可填 `{type, url, title}`。仍缺摘要、`page_age`、`encrypted_content`，所以必须记 `DEGRADE`，且 §5.3「省略而非伪造」的裁决不变。

流式实现有一处真实风险：§6.3 要求成块时点从 `web_search_call` 的 `done` 挪到**紧随其后那个文本块的 `content_part.done`**（citation 比 call 的 done 晚到），这会动 assembler 的块序。

### 4.3 规格自身的失真

`../anthropic-responses-bridge/hosted-web-search-spec.md` 整篇按「实现 hosted web search」写成，未反映默认禁用。已知需要复核的至少有：§8.3 仍把「必须剥离、不得 REJECT」写成规范（已被用户裁决推翻）、§3.4 未反映 `drop_fields` 默认、MJ-1/2/4/5/7/8 标着「实现前必须关闭」而实现已落地。

**2026-08-22 已派专门对账**，结果见 `reports/260822-websearch-doc-reconciliation.md`。

### 4.4 其他 typed / server tool 仍会 400

`bash_20250124`、`web_fetch_*` 等在 Responses 腿上仍原样透传到 `/responses`，上游拒。`tool_choice` 除 web search 那一条外仍整体丢弃。

### 4.5 与本切片无关但同期发现

`tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` 在 `767d0f2` 上失败，**先于本切片**（把 `schema.py` 还原成 HEAD 内容同样复现）。用户 2026-08-22 08:26 在 `docs/.human-controlled/config.example.yaml` 里新增了两个 schema 尚未实现的键：`upstream_request_retry.strategies.streamReplay` 与 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`。**这是用户想要的功能的信号，不是配置笔误**——需要用户确认要不要实现。

**2026-08-22 后续（本节到此为止的判断仍然成立，下面是它的去向）**：

- `streamReplay` —— 用户已从 `config.example.yaml` 中撤下，这条不再是待办。
- `strip_anthropic_beta_flags` —— 用户确认要实现，已落地：schema 建模、新链路接线、单元与端到端测试齐备。经过与未采纳项见 `../hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`。

## 5. 证据在哪

| 主题 | 文件 |
|---|---|
| 参考实现如何把关（含未采纳的理由） | `reports/260821-responses-leg-websearch-capability-reference.md` |
| copilot-api-js 响应侧全链路 | `reports/260821-copilot-api-js-websearch-response-side.md` |
| 上游确实返回 citation 的取证 | `reports/260821-responses-websearch-citation-evidence.md` |
| 客户端两段式架构取证 | `reports/260820-claude-code-websearch-request-forensics.md` |
| 上游实测探针原始记录 | `exp/260820-websearch-probe/raw/` |
| 规定的目标形态与流式时点 | `../anthropic-responses-bridge/hosted-web-search-spec.md` §5、§6.3 |
