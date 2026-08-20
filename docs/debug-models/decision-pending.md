# 待裁决：`debug models` 与端点解析

本文件登记**需要用户拍板、我不代劳**的事项。与 `deferred.md` 的区别：那里是「想到了但这次不做」，这里是「做不做、怎么做取决于用户的裁决，我给出选项和倾向」。

权威来源：代码本身，以及 `docs/.human-controlled/MAIN.md`（用户亲笔）。本文件的事实陈述都标注了实测日期与证据强度；实测均在 2026-08-20 对单一个人账户、单次读取，不外推为上游长期契约。

相关提交：`a46eb8d`、`883b104`、`14a5012`、`a224654`、`0f9abbc`。逐条评审处置见主仓库 `docs/tmp/260820-debug-models-review-disposition.md`。

---

## 1. CLI 的对外形态从未被裁决

**现状**：`docs/.human-controlled/MAIN.md` 的 `app.cli` 一节是 `TODO`。实现 `debug models` 时我自行定了这些**对外可见**的词汇，它们是实现默认，不是契约：

| 类别 | 引入的内容 |
|---|---|
| 选项 | `--config`、`--provider <name>`、`--json` |
| 状态词 | `ok`、`disabled`、`no-driver`、`no-endpoints`、`malformed`、`policy:<state>` |
| 摘要子句 | `N unreadable entries skipped` |
| 端点标记 | `*`（上游声明了但本代理无驱动）、`?`（上游未声明，按模型类型补的） |
| JSON 形状 | 不带 `--provider` 时按 provider 名分组；带 `--provider` 时直出该 provider 的载荷 |

**为什么需要裁决**：这些是脚本会依赖的东西。一旦有人拿 `--json` 的形状或状态词去写自动化，改动就成了破坏性变更。现在改还是零成本。

**我的倾向**：先不写进 `MAIN.md`。`debug models` 是排障工具而非产品接口，过早固化会让它难以随上游演进调整。等 `debug info` / `debug usage` 也实现了，三者一起定契约更省事。

**若要固化**，需要用户确认的具体点：状态词表是否完整、`policy:` 前缀这种命名法可否接受、`--json` 的两种形状是否就是想要的。

**证据强度**：以上是设计选择的陈述，不是测量结论；唯一的事实成分是「`MAIN.md` 的 `app.cli` 目前是 TODO」，可直接核对。

---

## 2. 主产品路径够不到 22 个模型，因为两个翻译器不存在

**这是既存缺口，不是本次引入的**，但本次把它的影响面显著放大了，所以必须摆到台面上。

### 实测事实（2026-08-20）

翻译器注册表里实际只有两套：

```
wire format                  inbound    outbound
anthropic-messages           yes        yes
openai-chat-completions      NO         NO
openai-embeddings            NO         NO
openai-responses             yes        yes
```

于是从 `/v1/messages`（本项目的**主产品路径**）进来的请求，落到只提供 `/chat/completions` 或 `/embeddings` 的模型时，会因 `TranslatorNotFound` 而失败。按当前目录 42 个模型统计：

| | 数量 |
|---|---|
| 可达 | 19 |
| 被缺失的翻译器挡住 | 22 |
| 完全无端点（`gpt-41-copilot`） | 1 |

被挡住的 22 个是：4 个 gemini、`trajectory-compaction`、14 个 gpt-3.5/4/4o/4.1 系列、3 个 embeddings。

**本次改动的影响**：改动前只有 5 个卡在这个缺口上（4 gemini + `trajectory-compaction`）——其余 17 个当时因为目录没登记端点而根本不可路由，卡在更早的能力门上。改动后它们通过了能力门，于是**同一个缺口从挡住 5 个变成挡住 22 个**。

（注：第三轮评审给的数字是 3 → 23，我自己复测得 5 → 22。以本文件的数字为准，复现命令见下。）

### 这与 `debug models` 报的 `ok` 是什么关系

`ok` 表达的是 **provider 能力层**的判断：这个模型有一个本代理能驱动的上游端点。它不表示「任何入站格式都能打到它」——那要再过路由与翻译两层。两者是不同的层，报告没有说错，但一个只看 `ok` 的人会高估可用性。

### 需要裁决的是什么

| 选项 | 说明 |
|---|---|
| A. 补 `outbound.to-openai-chat-completions` | 收益最大：一次解锁 19 个模型（14 gpt 系列 + 4 gemini + `trajectory-compaction`）。工作量是一个独立切片，不该塞进 `debug models` 里。 |
| B. 补 `to-openai-embeddings` | 只解锁 3 个 embeddings 模型，且 Anthropic Messages 与 embeddings 语义差距大，翻译是否有意义存疑。 |
| C. 都不补，但让 `debug models` 把这层也报出来 | 例如给状态加一列「从 `/v1/messages` 可达吗」。让报告不再需要读者自己补这层知识。 |
| D. 什么都不做 | 记录在案，等有人真的撞上。 |

**我的倾向**：A 值得单独排期（它挡着 19 个模型，且主产品路径就是 Anthropic Messages 入站）；B 暂缓；C 有吸引力但会把 `debug models` 从「报告上游目录」扩成「报告端到端可达性」，是范围扩张，建议等 A 落地后再看还需不需要。

**证据强度：强到足以据此排期。** 翻译器缺口由注册表 API 直接探测确认；22 这个数字由当日目录逐模型计算。它描述的是当日的目录与当前代码，目录变化会改变数字。

### 复现

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

模型计数需要凭据（会真实读取上游目录），脚本见本会话记录；按上表的 wire format 可达性对 `provider.describe(mid).endpoints` 做交集即可。

---

## 已由实测解决，不再需要裁决

### `completion` 类型模型的端点（原第 3 条）

原本登记为「评审给出了与用户裁决相反的证据，请裁决」。用户追问是否实验过——**当时没有**，那是把评审的主张当证据转述。补测后结论明确，已按测量结果修复于 `0f9abbc`，无需裁决：

对全部 18 个缺 `supported_endpoints` 键的模型各发一次真实请求：14 个 `chat` 在 `/chat/completions` 全部 200；3 个 `embeddings` 在 `/embeddings` 全部 200；1 个 `completion`（`gpt-41-copilot`）在 `/chat/completions`、`/responses`、`/v1/messages` 全部 400 `model_not_supported`，`/completions` 404——它在这台主机上根本不可服务，与 VS Code 扩展把该类型送往另一台 proxy 主机的 `v1/engines/<model>/completions` 吻合（`refs/vscode-copilot-chat/src/extension/completions-core/vscode-node/lib/src/openai/fetch.ts:310`）。

用户「embedding 走其标准端点、其余走 `/chat/completions`」的两分裁决因此对 18 个里的 17 个成立，第 18 个是它未覆盖的第三种情况。兜底表已改为只含实测过类型的 allowlist。

**一条值得记住的教训**：第一次测 embeddings 时探针把 `input` 传成了字符串，三个模型全部 400，形态与「端点选错」完全一致；改成数组后全部 200。**探针自己的 bug 与它要找的发现无法区分**，差一点就把三个本来好用的模型判成不可服务。
