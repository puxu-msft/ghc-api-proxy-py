# 裁决记录：`debug models` 与端点解析

本文件记录**用户已裁决**的事项。它取代了同一路径下的 `decision-pending.md`——那份登记的三条待裁决事项已全部有了结论。

权威来源：代码本身，以及 `docs/.human-controlled/MAIN.md`（用户亲笔）。本文件的事实陈述都标注了实测日期；实测均在 2026-08-20 对单一个人账户、单次读取，不外推为上游长期契约。

相关提交（主仓库）：`a46eb8d`、`883b104`、`14a5012`、`a224654`、`0f9abbc`、`aa1b2c4`。逐条评审处置见同目录 `review-disposition.md`，五份评审报告在 `reports/`。

---

## 裁决 1 — CLI 现有选项保留（用户，2026-08-20）

`debug models` 当前的三个选项**按现状保留**，不再讨论：

| 选项 | 作用 |
|---|---|
| `--config PATH` | 指定配置文件 |
| `--provider NAME` | 只报告这一个已配置的 provider |
| `--json` | 输出完整的解码后上游载荷 |

一并按现状保留的还有报告自己的词汇（它们随选项一同交付，未被单独否定）：状态词 `ok` / `disabled` / `no-driver` / `no-endpoints` / `malformed` / `policy:<state>`，摘要子句 `N unreadable entries skipped`，端点标记 `*`（上游声明了但本代理无驱动）与 `?`（上游未声明，按模型类型补的），以及 `--json` 的两种形状（不带 `--provider` 时按 provider 名分组，带 `--provider` 时直出该 provider 的载荷）。

**仍未做的一件事**：把这套形态写进 `docs/.human-controlled/MAIN.md` 的 `app.cli` 一节（该节目前是 `TODO`）。那份文档只有用户能改，何时写、写多少由用户决定；本裁决不构成把它固化成对外契约的承诺。

---

## 裁决 2 — embeddings 不接入 LLM 入站路径（用户，2026-08-20）

**裁决原文**：「embeddings api 不可能接入 llm api，这没意义」。

因此 `outbound.to-openai-embeddings` 这个翻译器**不做**，从待办中移除。把 Anthropic Messages 这类对话请求翻译成 embeddings 请求在语义上不成立。

**这不影响 embeddings 模型的可用性**。实测（见下节）：同格式路由不需要任何翻译器，`POST /embeddings` 入站直达上游 `/embeddings`。目录里 3 个 embeddings 模型经各自的原生路由完全可用，它们从不曾是缺口。

---

## 裁决 3 — `outbound.to-openai-chat-completions` 由用户后续补上（用户，2026-08-20）

**裁决原文**：「用户未来会补 `outbound.to-openai-chat-completions`，不必担心」。

因此这条不再作为风险登记，也不需要 `debug models` 为它增加任何补偿性显示。曾考虑过的「给报告加一列端到端可达性」**不采纳**：它会把 `debug models` 从「报告上游目录」扩成「报告端到端可达性」，属范围扩张，而缺口本身即将被填上。

---

## 裁决 4 — `completion` 类型模型不给兜底端点（由实测确立，已实现于 `0f9abbc`）

原为待裁决项。用户追问「你实验过可行吗」，补测后结论明确，无需再裁决。

对全部 18 个缺 `supported_endpoints` 键的模型各发一次真实请求：

| `capabilities.type` | 数量 | 兜底端点 | 实测 |
|---|---|---|---|
| `chat` | 14 | `/chat/completions` | 全部 200 |
| `embeddings` | 3 | `/embeddings` | 全部 200 |
| `completion` | 1（`gpt-41-copilot`） | 曾给 `/chat/completions` | **400 `model_not_supported`** |

对那一个模型又逐一试了本主机其余端点：`/responses` 400、`/v1/messages` 400、`/completions` 404。**它在 `api.githubcopilot.com` 上根本不可服务**，与 VS Code 扩展把该类型送往另一台 proxy 主机的 `v1/engines/<model>/completions` 吻合（`refs/vscode-copilot-chat/src/extension/completions-core/vscode-node/lib/src/openai/fetch.ts:310`）。

用户「embedding 走其标准端点、其余走 `/chat/completions`」的两分裁决因此对 18 个里的 17 个成立，第 18 个是它未覆盖的第三种情况。兜底表已改为**只含实测过类型的 allowlist**；未实测的类型不给端点，由 `no-endpoints` 当场暴露，而不是留到请求时静默 400。

---

## 当前可达性全貌（实测 2026-08-20，42 个模型）

这张表是上面几条裁决的共同背景，也修正了此前一次框定错误。

**同格式路由不需要翻译器**（`decide_route` 探测，四种入站格式打到各自原生端点时 `translation_required=False`；复现见本节末）。因此：

| | 数量 | 说明 |
|---|---|---|
| 有端点、经原生入站路由可达 | 41 | 无需任何翻译器 |
| 无端点 | 1 | `gpt-41-copilot`，见裁决 4 |

从 `/v1/messages`（本项目**主产品路径**）这一个入口看：

| | 数量 |
|---|---|
| 可达（模型提供 `/v1/messages` 或 `/responses`） | 19 |
| 需要 `outbound.to-openai-chat-completions`（用户将补，裁决 3） | 19 |
| 语义上不该从这里去（3 个 embeddings，裁决 2） | 3 |
| 无端点 | 1 |

**此前的框定错误**：我一度把这 22 个（19 + 3）笼统说成「被缺失的翻译器挡住」，那是只从 `/v1/messages` 一个入口看得出的结论，读起来却像「这些模型不可用」。它们经各自的原生路由都可用；3 个 embeddings 更是按裁决 2 根本不属于这个问题。

翻译器现状（`default_registry` 探测）：

```
wire format                  inbound    outbound
anthropic-messages           yes        yes
openai-chat-completions      NO         NO
openai-embeddings            NO         NO
openai-responses             yes        yes
```

### 复现（都不需要凭据）

翻译器现状：

```bash
cd ~/src/ghc-api-proxy-py
uv run python - <<'EOF'
from app.config.loading import load_proxy_config
from app.pipeline.translation_driver.registry import default_registry, TranslatorNotFound
from app.server.inbound import ROUTES
reg = default_registry(load_proxy_config().model_translation)
for w in sorted({r.wire_format for r in ROUTES}, key=lambda w: w.value):
    def ok(fn):
        try: fn(w); return "yes"
        except TranslatorNotFound: return "NO"
    print(f"{w.value:28} {ok(reg.inbound):6} {ok(reg.outbound)}")
EOF
```

同格式路由是否需要翻译器：

```bash
cd ~/src/ghc-api-proxy-py
uv run python - <<'EOF'
from app.model_provider import ModelEndpoint, ModelDescriptor
from app.pipeline.routing import decide_route
from app.server.inbound import ROUTES

class P:
    name = "ghc"
    def __init__(self, ep): self._d = ModelDescriptor(id="m", endpoints=frozenset({ep}))
    @property
    def available_ids(self): return frozenset({"m"})
    def describe(self, mid): return self._d if mid == "m" else None

wires = {r.wire_format.value: r.wire_format for r in ROUTES}
for name, ep in [("anthropic-messages", ModelEndpoint.ANTHROPIC_MESSAGES),
                 ("openai-chat-completions", ModelEndpoint.OPENAI_CHAT_COMPLETIONS),
                 ("openai-responses", ModelEndpoint.OPENAI_RESPONSES),
                 ("openai-embeddings", ModelEndpoint.OPENAI_EMBEDDINGS)]:
    r = decide_route(requested_model="m", inbound_format=wires[name], provider=P(ep), mappings={})
    print(f"{name:26} -> {r.endpoint.value:20} translation_required={r.translation_required}")
# 跨格式对照：Anthropic 入站打到只有 /chat/completions 的模型
r = decide_route(requested_model="m", inbound_format=wires["anthropic-messages"],
                 provider=P(ModelEndpoint.OPENAI_CHAT_COMPLETIONS), mappings={})
print(f"{'cross-format control':26} -> {r.endpoint.value:20} translation_required={r.translation_required}")
EOF
```

按上表的 wire format 可达性对 `provider.describe(mid).endpoints` 做交集，即可复算模型计数（那一步需要凭据，因为要真实读取上游目录）。

---

## 两条方法教训（不新增规则，只记录形态）

**探针自己的 bug 与它要找的发现无法区分。** 本会话撞了两次：

1. 测 embeddings 时 `input` 传成字符串，三个模型全部 400，形态与「端点选错」完全一致；改成数组后全部 200。差一点把三个本来好用的模型判成不可服务。
2. 查翻译器时第一个探针报 `outbound.to-openai-responses` 缺失——那是主产品路径，不可能缺。是探针在瞎猜注册表内部结构，换成走公开 API 才拿到正确结果。

两次都是「先取原始错误、先质疑探针」才没有把错误结论写进代码。

**转述评审的主张不等于有证据。** 裁决 4 那条最初被我写成「评审给出了相反证据，请裁决」，实际上我没有做过任何实验。用户一问就露了。评审的引用本身属实，但它描述的是另一台主机上的另一套子系统——只有实测才分得清这个区别。
