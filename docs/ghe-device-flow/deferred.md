# GHE Device Flow：待裁决与延后项

本文只放**未闭合**的条目。查清了、做掉了、或已被 Spec 吸收的，从这里移出，别留空号——编号是标识不是序列。

**2026-08-29 用户裁决后移出的**：D-5 已裁决并实现——`auth|logout <provider>` 改为必填位置参数、默认 token 文件按 provider 命名（`github_token-<provider>.txt`），见 [spec.md](spec.md) §3.5 与 §3.6；**含一次破坏性变更**，既有 `github_token` 需重命名或重新登录。

**2026-08-28 用户裁决后移出的**：D-1（支持 GHES）已实现，见 [spec.md](spec.md) §3.2；D-4 已裁决并实现，规则是「配置里的相对路径从 `config.yaml` 所在目录算起」，见 §3.8——**注意这与本台账原先提的问法不同**，原先问的是「要不要强制绝对路径」，用户给的是更好的一条：不强制，改解析基准；D-6（配置发现链的行为契约变更）已获追认，见 §3.5。

## D-2 · `GhcClientConfig` 的构造点应否收拢成一个 helper

**状态**：延后，属独立小补丁，不在 device flow 这一片里做。

`src/app/server/composition.py` 有三处（357、423、491）、`src/app/cli.py` 有一处，都在做「从 `ModelProviderConfig` 取字段构造 `GhcClientConfig`」。四处传的字段子集不完全相同。将来 `GhcClientConfig` 多一个需要从 provider 配置带过去的字段时，这几处会分头改并悄悄分叉。

**没有在本片做的理由**：它是一次自足的重构，主题是「provider 配置到客户端配置的映射」，与 Device Flow 的 OAuth 源无关。把它塞进本片会让 `composition.py` 无谓地进入这次的评审面。按项目「每个自足小补丁独立完成并集成」的做法，它该有自己的一片。

依据：[reports/260828-review-claude.md](reports/260828-review-claude.md) S1。

## D-7 · §3.8 那条规则的归属

**状态**：待将来处理，不阻塞。

§3.8「配置里的相对路径从 `config.yaml` 算起」是**配置加载层的通用规则**，作用域超出本主题。它记在这份 Spec 里，只是因为裁决发生在这里。将来若建立配置加载的专属主题文档，权威应当迁过去，本文改为引用。

在那之前，任何要引用这条规则的地方引用 [spec.md](spec.md) §3.8，不要另行复述。

## D-3 · 三处用户亲笔文档里的事实，待用户取舍

这三条都在 `docs/.human-controlled/` 下，由用户亲笔控制，**我方只报告、不代改**。

1. `ghc-api.md:17` 写 self-hosted 的 API Base URL 是 `msft.ghe.com`；按现有证据，data residency 租户的 Copilot 推理侧应当是 `copilot-api.<tenant>.ghe.com`。证据权重见 [spec.md](spec.md) §4，**只有旁证，无实测**。
2. `config.example.yaml` 没有文档化 `auth_base_url`（该字段已实装且已列入不可热重载清单）。早前登记于 `.dev/docs/tmp/260822-ghc-api-conformance-summary.md` 的 D2。
3. 同一文件推荐的 `github_token_file` 值带 `.txt` 后缀，与 `FileTokenProvider` 的默认路径 `github_token`（无后缀）不同名。Spec §3.5 的第 2 条行为变更已让 `auth` 侧不再受它影响——现在 `auth` 会写到配置指定的那个文件——但两处默认值仍然对不上。

依据：[reports/260828-review-claude.md](reports/260828-review-claude.md) F10；[spec.md](spec.md) §5。
