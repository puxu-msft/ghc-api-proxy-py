# 候选：Responses → Anthropic Messages thinking profile 配置示例

**性质**：本文是模型撰写的候选素材，**无效力**。用户只有把其中内容摘取到`docs/.human-controlled/`后，被摘取部分才成为权威。

**建议摘取到**：`docs/.human-controlled/config.example.yaml`的`model_translation`一节。本文只说明发生协议翻译时，Responses→Anthropic Messages writer如何按目标模型构造`thinking`；不改变direct Anthropic→Anthropic请求的原样转发合同，也不取代[候选：`thinking.type` 的按模型能力构造与 `output_config.effort`](anthropic-thinking-capability.md)所讨论的direct request整形问题。

## 一、现状：配置控制thinking形状，不控制effort档位

**实现候选现状**（`worktree-effort-translation@ed6addd017f461c15abc494584e727f1badec633`，尚待final scoped review与主树集成）：`model_translation.to_anthropic_messages.thinking_profiles`是translated Responses→Anthropic Messages writer选择thinking wire shape的唯一能力来源。随包默认值见`src/app/config/bundled-config.yaml:58-79`，schema见`src/app/config/schema.py:232-259`，compile／selection见`src/app/pipeline/routing.py:377-421`。

Profile不设置effort。当前生成的effort来自入站Responses`reasoning.effort`：`none`要求目标能写`thinking.type=disabled`；`minimal`先近似为Anthropic`low`；`low／medium／high／xhigh／max`按目标catalog中的Anthropic-compatible档位对齐。Profile只回答同一intent应写成`adaptive`、带手工budget的`enabled`，还是`disabled`。

**现状**：直接Anthropic→Anthropic与Responses→Responses不运行translator，因此不读本表来改写请求。配置缺失或没有任何正则命中时，只有确实需要构造Anthropic thinking的translated请求才fail closed；代理不从model name、vendor、catalog budget limits或相邻能力字段猜profile。

## 二、匹配与覆盖规则

**现状**：每个键都是正则，对**resolved model id**执行`fullmatch`，不是搜索子串，也不是匹配客户端原始别名。所有命中中最后一项生效。Bundled profiles先加载，用户新增的pattern随后加入，因此一个更窄的用户pattern可以覆盖较宽的默认pattern。

**现状**：配置各层通过recursive deep merge合并，见`src/app/config/loading.py:37-53`。如果用户配置使用与bundled config**逐字符相同的pattern键**，只写出的子字段覆盖默认值，未写字段继续继承；如果用户新增另一个pattern，则这是一个新的完整profile，必须给出required fields`modes`与`can_disable`。`tests/unit/config/test_config_loading.py:380-503`固定了默认正负匹配、最后命中和同pattern部分override。

## 三、字段语义

| 字段 | 现状语义 |
|---|---|
| `modes` | 非空有序列表，只允许`adaptive`与`enabled`且不得重复。Writer逐项尝试，选择本次请求第一个可渲染的mode。 |
| `can_disable` | Strict boolean。为`false`时，入站Responses`reasoning.effort=none`稳定拒绝，不用省略thinking伪装disabled。 |
| `disabled_max_effort` | 可选的Anthropic effort上限。只有`can_disable=true`时有意义；Responses`none`不携带Anthropic effort，因此按Anthropic默认`high`检查。低于`high`的上限会让该profile拒绝`none`。 |
| `manual_budget_tokens` | 可选strict integer，必须`>=1024`。它只让`enabled`mode能写合法manual thinking shape，不决定effort档位，也不从effort或catalog budget limits推导。 |

**现状**：`adaptive`可以直接渲染。`enabled`还要求当前请求有`max_tokens`，且`1024 <= manual_budget_tokens < max_tokens`。例如`modes: [enabled, adaptive]`在budget合法时优先写manual shape；budget缺失或与本次`max_tokens`不相容时继续尝试adaptive。`modes: [enabled]`在同样条件下没有fallback，稳定拒绝。

## 四、建议配置片段

### 方案A：给一个目标模型新增更窄的完整profile

下面的用户pattern晚于bundled默认表，并且只匹配resolved`claude-opus-4`及其可选日期后缀。因为这是**新pattern**，需要写完整profile：

```yaml
model_translation:
  to_anthropic_messages:
    thinking_profiles:
      # Keys are full-match regexes over the resolved model id.
      'claude-opus-4(?:-[0-9]{8})?':
        # Prefer manual extended thinking for this target.
        modes: [enabled]
        can_disable: true
        # Shapes thinking only; it does not select low/medium/high/etc.
        manual_budget_tokens: 4096
```

该profile只有在每个translated请求的`max_tokens > 4096`时可渲染；否则请求被拒绝。若希望budget不相容时还能fallback，可把顺序改为：

```yaml
        modes: [enabled, adaptive]
```

### 方案B：对bundled同pattern做部分override

下面的pattern与bundled Opus 5键逐字符相同，因此只覆盖`disabled_max_effort`，继续继承`modes: [adaptive]`与`can_disable: true`：

```yaml
model_translation:
  to_anthropic_messages:
    thinking_profiles:
      'claude-opus-5(?:-[0-9]{8})?':
        disabled_max_effort: medium
```

此例会让Responses`reasoning.effort=none`在该profile上拒绝：`none`映射到disabled，但没有Anthropic effort可随它携带，检查使用默认`high`，而`high > medium`。若目标是保留bundled当前可disable行为，不要写这项；bundled值是`high`。

### 方案C：为extended-only bundled族补manual budget

下面使用与bundled第六条逐字符相同的pattern，只补`manual_budget_tokens`并继承`modes: [enabled]`与`can_disable: true`：

```yaml
model_translation:
  to_anthropic_messages:
    thinking_profiles:
      'claude-(?:(?:opus|sonnet|haiku)-4[.-]5|opus-4[.-]1|opus-4|sonnet-4)(?:-[0-9]{8})?':
        manual_budget_tokens: 4096
```

这会同时作用于该pattern覆盖的所有resolved models。若只想改一个family，不要复用这个宽pattern；改用方案A那样的新窄pattern，并写完整profile。

## 五、运维可见性

**现状**：成功选择profile会记录`thinking-profile-selected`fact，包含resolved model与最终命中的pattern。Missing profile或profile无法承载当前intent时记录`thinking-profile-rejected`，成功和拒绝两条路径都进入durable request JSONL；这些facts不是conversion loss，不会把`lossless`改为false，也不出现在console单行摘要中。

**提案**：用户文档只需解释如何配置与如何读上述facts，不必把六条bundled官方快照重复到用户配置示例。随包默认表已在版本化配置中提供，用户配置应只覆盖确实不同的目标模型；复制整张表会让官方表以后更新时形成第二份易过期转录。
