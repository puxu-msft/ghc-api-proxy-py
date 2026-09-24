# bridge provider 本地模型信息配置候选

> 候选材料，不是用户控制的 Spec。用户确认后再摘取到 `docs/.human-controlled/config.example.yaml`。

有些 bridge 上游的 `/models` 只报 id。opencode Zen Go 档返回 `{id, object, created, owned_by}`，没有名称、能力、上下文长度或价格，于是 `/models` 和 `?format=pi` 里每个模型都是空的描述。这类事实由运维掌握，写进一个本地文件即可。

新增一个可选字段：

```yaml
model_providers:
  opencode:
    type: bridge
    api_base_url: "https://opencode.ai/zen/go/v1"
    api_key: "your-opencode-go-api-key"

    openai_responses_endpoint: true
    anthropic_messages_endpoint: true

    # 本地模型信息文件。留空 → 上游目录原样采信（默认）。
    # 提供 → 以该文件与上游 `/models` 的「交集」为准：只有两边都点名的模型才被服务，
    #         且文件条目补全上游不提供的名称、能力、上下文长度、价格与逐模型协议。
    # 支持 `~`、`$VAR`、`${VAR:-fallback}`；写在配置文件里的相对路径相对本文件所在目录解析。
    # `${GHC_PACKAGE_DIR}` 记的是本包的位置（不是环境变量），uvx 运行没有 checkout 时
    # 用它直接引用随包发布的快照，无需复制。
    # 与 api_base_url 一样不支持热重载（需重启）。
    # 采样文件名带上采样日期，便于一眼看出样本新旧；重新采样后要改这里的路径并重启。
    model_info_json: "${GHC_PACKAGE_DIR}/model_provider/opencode-go-20260916.json"
```

文件格式（`schema_version: 1`）：

```json
{
  "schema_version": 1,
  "source": "出处（可选）",
  "retrieved_at": "2026-09-16（可选，采样日期）",
  "models": {
    "kimi-k3": {
      "name": "Kimi K3",
      "supported_endpoints": ["/chat/completions", "/v1/messages"],
      "capabilities": {
        "supports": { "vision": true, "reasoning_effort": ["high"] },
        "limits": { "max_context_window_tokens": 1048576, "max_output_tokens": 131072 }
      },
      "pricing": {
        "input": 3.0, "output": 15.0, "cacheRead": 0.3, "cacheWrite": 0.0,
        "tiers": [
          { "name": "default", "input": 3.0, "output": 15.0, "cacheRead": 0.3, "cacheWrite": 0.0 },
          { "name": "above-200000", "input_min_tokens": 200001,
            "input": 6.0, "output": 30.0, "cacheRead": 0.6, "cacheWrite": 0.0 }
        ]
      }
    }
  }
}
```

条目字段就是目录条目的形状（`/models` 读的同一形状），因此合并下游不需要任何转换层。

**分段定价**写进 `pricing.tiers`：`tiers[0]` 是 `name: "default"` 的基础档，其后每档带 `input_min_tokens`（生效阈值，`?format=pi` 会换算成 `cost.tiers[].inputTokensAbove = min - 1`）。**每档四档费率都要齐**——`cacheRead`/`cacheWrite` 上游没报时写显式 `0`，漏一个不会降级，而是让 `?format=pi` 的整个 `cost` 块消失。

**`retrieved_at` 只用于判断新旧，不阻止启动。** 超过 90 天会打一条告警，并在 `/api/status` 里报出来：

```json
"providers": { "opencode": { "model_info": {
  "path": "/home/u/.local/share/ghc-api-proxy/opencode-go-20260916.json",
  "retrieved_at": "2026-09-16", "age_days": 0, "stale": false
} } }
```

日期缺失或读不出来时 `age_days` 与 `stale` 都是 `null`（不是 `0`/`false`）——未知既不是「今天采的」，也不是「已核实」。

规则：

- **交集**。上游广告而文件未描述的模型 → 不服务，也不出现在 `GET /models`；文件描述而上游未广告的 → 同样不服务。剩下的才是既确认过、又描述过的集合。
- **合并**。映射逐键合并（文件为准，上游已发布的同级键如 `object`、`created` 保留）；标量与列表由文件整体覆盖（列表是替换而非追加）。
- **`supported_endpoints` 决定该模型的可达协议**，仍与三个 endpoint 字段取交集：文件说某模型服务 Anthropic Messages、而 `anthropic_messages_endpoint` 没启用，该腿依然不可达。显式写 `[]` 表示「什么都不服务」，不会放宽成配置启用的集合。
- **只写确有把握的字段。** 尤其不要填 `capabilities.tokenizer`：它连着 `max_prompt_tokens` 构成 `prompt_token_limits`（local Responses 准入的事实），编一个就是伪造准入依据。
- **文件读错就启动失败**。不可读、JSON 非法、`schema_version` 不符、`models` 为空、模型 id 为空或带首尾空白、条目不是对象——任一都让 provider 构造失败（`ModelInfoError`），不会降级成「裸目录」。
- 与 `models`（allowlist）同时配置时两者都收窄，`GET /models` 不列出被 allowlist 挡掉的模型。

opencode Go 的现成文档**随包发布**：`src/app/model_provider/opencode-go-20260916.json`（2026-09-16 实测生成，30 个模型；上游广告但因 `Model is unavailable` 而打不通的 7 个被有意排除，这样交集就不会让 `/models` 继续承诺它们）。它进 wheel，所以 uvx 运行也能用 `${GHC_PACKAGE_DIR}` 直接引用，**无需复制**。它**不随包自动加载**，也不存在任何隐式默认——配置里不写就是不用它。

这份样本有两处已知缺口，别当成完整事实：30 个模型里 17 个有 `reasoning_effort` 阶梯，其余上游只报「思考开关」而非档位（无从补全，`?format=pi` 因此报 `reasoning: false`）；4 个模型上游报的是思考预算**上限**，写在 `capabilities.supports.max_thinking_budget` 里，它是描述性字段——预算上限并不等于上游接受 `budget_tokens`，本项目也不据此推断 `reasoning`。

另有一个**滚动别名**要在文件里说清：上游 `/models` 广告 `deepseek-flash`，它的含义是「最新 Flash」。写这份样本时（2026-09-16）它指向 `deepseek-v4.1-flash`，所以文件里这一条镜像了 v4.1-flash 的名称、长度、费率与能力，`supported_endpoints` 保留该 id 自己探测的结果，并在 `description` 里写明是滚动别名。请求仍发 `deepseek-flash`，上游换指时会跟着走，但文件里的数字要等你重新采样才会跟着更新——想反过来**钉死**在具体版本，用既有的 `model_mappings`：

```yaml
    model_mappings:
      deepseek-flash: deepseek-v4.1-flash
```

映射名会继承目标模型的元数据，代价是上游换指后你仍钉在旧版本。
