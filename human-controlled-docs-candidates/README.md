# 候选文档（`.dev/human-controlled-docs-candidates/`）

本目录是**给用户挑选的素材**，不是权威文档。

2026-08-20 由 `docs/.human-controlled-candidates/` 迁入，并从主分支移出：素材是开发过程产物，不随代码发布。`docs/` 下仍有若干文档链接到这里，那些链接指向工作树而不是分支内容——只取主分支的读者看不到本目录。

## 与 `docs/.human-controlled/` 的关系

| 目录 | 作者 | 效力 |
|------|------|------|
| `docs/.human-controlled/` | 用户亲笔 | 最终 ADR，压过一切推导产物 |
| `.dev/human-controlled-docs-candidates/`（本目录） | 模型撰写 | **无效力**，供用户摘取；未被摘取的内容不构成任何裁决 |

用户从本目录摘取内容写入自己的文档后，被摘取的部分才获得权威；留在本目录的部分始终只是提案。

## 撰写约定

每份候选文档区分两类内容，读者不必回查代码即可分辨：

- **现状**——已在代码中成立的事实，附 `file:line` 或可复算的命令。
- **提案**——模型的建议，用户可整段丢弃。

标注为「现状」的内容若与代码不符，是本目录的缺陷，请直接指出。

## 当前候选

**2026-08-22 重整索引。** 原表的表头是「覆盖 `MAIN.md` 未涉及的哪一面」，而 `MAIN.md` 已在提交 `2afa0c4` 里被拆成 `module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` 等多份。表头改为中性说法，并补上此前漏列的三份。各份的逐条状态见 `.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md`，本次刷新做了什么见 `.dev/docs/tmp/260822-candidate-docs-refresh-log.md`。

| 文档 | 覆盖哪一面 |
|------|-----------|
| [config-schema-gap.md](config-schema-gap.md) | **`config.example.yaml` 与现有实现的对照**——语义重定义项与全新能力项 |
| [config-migration-gaps.md](config-migration-gaps.md) | **切到新配置会静默丢掉的功能**——`history` 与 `observability` 两个运维配置节仍缺失 |
| [existing-rulings.md](existing-rulings.md) | 既有实现与用户文档的相容性对照——需再次裁决的违背项、尚未存在的缺口、已解决项 |
| [deployment.md](deployment.md) | 部署子系统的模块级补充；主体已被 `lifecycle.md` 取代，rolling 相关内容已随功能删除而撤下 |
| [systemd-shutdown.md](systemd-shutdown.md) | **回答 `lifecycle.md:52` 的 TODO**——提案已被否决（只做两级），仅第一节的 systemd 行为事实与第五节的四处文档不一致仍然有效 |
| [rolling-removal.md](rolling-removal.md) | rolling 已删除，`lifecycle.md:65-89` 的「代（generation）生命周期」整节等待用户追认删除或改写为历史记录 |
| [pipeline-subscriptions.md](pipeline-subscriptions.md) | 事件订阅如何吸收现有 hooks；附四个待裁决点，含文档名 `ClientRequest` 与代码名 `RequestContext` 的不一致 |
| [proactive-rate-limiter.md](proactive-rate-limiter.md) | **`proactive_rate_limiter` 那三行的表述**——已生效却仍被注释、示例值与默认值不符、未写明超限行为是等待；附一个待裁决点（排队时间不计入任何 deadline） |
| [pidfile-port-scoping.md](pidfile-port-scoping.md) | pidfile 已改为 `pidfile_dir` 目录语义并按端口命名（已采纳）；剩一个待裁决点（`GHC_API_PROXY_PORT` 这个拼写像环境变量却不是）与一项切换时的一次性影响 |
| [instructions-shape-conflict.md](instructions-shape-conflict.md) | **`message-translation.md:34-62` 的 `instructions` 对象数组形态被 GHC 拒绝**——六种数组形态全部 400，只有字符串可用；待用户裁决是否改规格 |
| [anthropic-thinking-capability.md](anthropic-thinking-capability.md) | **`message-format-reshape.md` 第 65 节缺一条**——`claude-sonnet-5` 拒绝 `thinking.type: enabled`（2026-08-24 线上 400，出站请求体已落盘）；提案含新顶层键 `model_thinking_effort` 与 `thinking.display` 开关，附四个待裁决开口 |
| [upstream-retry-and-continuation-supplements.md](upstream-retry-and-continuation-supplements.md) | 对 `upstream-retry-and-continuation.md` 的补充与提问；该文件由主会话另行维护 |
| [uncovered-modules.md](uncovered-modules.md) | 其余未被用户文档描述的包，各一行 |

## 已被采纳的部分

`docs/.human-controlled/lifecycle.md`（2026-08-16）采纳了本目录 `deployment.md` 的部分内容，并作出了候选文档没有的裁决：两种部署方式、standalone 三级关闭与信号语义、`SO_REUSEPORT` 平滑重启、退出时限改以客户端请求超时为基数、cgroup 要求，以及模块名定为 `app.lifecycle`。被取代的候选内容已从 `deployment.md` 删除。

`docs/.human-controlled/config.example.yaml`（2026-08-16 更新）采纳了：`server.host` / `server.port`、`model_providers.*.github_token_file`、`hooks` 六个订阅点、`history.enabled`，并把 `rate_limiter` 定名为 `reactive_rate_limiter`、把客户端请求超时定名为 `client_delivery.client_request_deadline`。此外规格已给 `server.host` / `server.port` 标注「不支持热重载（需重启）」，采纳了候选文档就此提出的判断。相应的候选提案已从 `config-migration-gaps.md` 删除，仅保留其中尚未被承载的部分。

**2026-08-22**：`module-org.md` 采纳了 `uncovered-modules.md` 的 `config` / `history` / `observability` / `cli` 四行，并给 `pipeline.delivery` 一个位置；`config.example.yaml` 采纳了 `pidfile_dir` 的目录语义与按端口命名、`stream_idle` 中文注释的「活动之间」措辞、并删掉了 `streamReplay` 与 `continuation` 两块；`client-side-block-delivery.md:16` 采纳了 `upstream_request_timeouts.upstream_request_deadline` 这个节名。同日也有明确**未被采纳**的建议（半开 `message_start` 的实现者提醒、删掉 `hand_over_stop_reasons` 里的 `max_output_tokens`、保留 `pidfile` 文件语义、systemd 三级关闭重组），各自的否决理由记在对应文档里，请勿换个说法再提一遍。
