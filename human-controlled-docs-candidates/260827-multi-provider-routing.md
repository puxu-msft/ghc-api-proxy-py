# 候选材料：多 provider 路由带来的用户控制文档更新

> **这是候选材料，不是改动。** `docs/.human-controlled/` 下的文件由用户亲笔，本任务一律不修改它们。下面五条列出「哪一处因为什么而过期」以及建议的替换文本，供用户按自己的判断摘取。
>
> - 来源：`.dev/docs/multi-provider-routing/spec.md`，各条注明对应条款
> - 日期：2026-08-27
> - 触发：实现「配两个 GHC provider 并按模型路由」，见该 Spec §0
> - 第 2 条由规则评审 F-08 发现，其余由 Spec 自身推导。除第 1 条外，首版 Spec 都漏掉了。

## 1. ~~`config.example.yaml:71` — 计数腿改名~~ 已撤销

**这一条作废，`config.example.yaml:71` 不需要任何改动。**

原提案是把 `providers: [ghc, local]` 改成 `[upstream, local]`，依据是「这个值命名的是上游那条腿，不是 provider 名」。**那个依据是错的**——用户 2026-08-27 指出：`ghc` 有效正是因为 `model_providers` 里有一个叫 `ghc` 的 provider。

顺带被撤销的还有一条更糟的东西：我曾在 schema 里加静态校验去拒绝 `ghc`。那等于把「只有 provider 恰好叫 ghc 的部署能问上游要计数」写成了纪律，而这条规则没有人定过。

现在的实现：该字段类型是 `list[str]`，每项要么 `local`、要么一个已配置的 `model_providers` 键，校验相对本份配置进行。所以你这份示例配置**原样合法**，且把 provider 改名成别的之后写 `[<新名字>, local]` 也合法——那是原本表达不出来的。

详见 `.dev/docs/multi-provider-routing/spec.md` §1.3。

## 2. `config.example.yaml:100-102` — 解析算法的描述已被取代

**现状**：

```
# 若目标在可用模型列表中，直接解析命中；否则，当作别名再次尝试解析；仍不可用则放弃映射、直接透传（上游随后拒绝它）。
# If a target is in the available models list, it is resolved directly; otherwise, it is treated as an alias and resolved again;
# if still unavailable, the mapping is abandoned and passed through (the upstream then rejects it).
```

**建议**：

```
# 沿别名链解析，全程不查可用模型列表；读到带 provider 限定的值即为终点。链走完之后才查一次：命中则用目录里的拼写，仍不可用则放弃映射、回退到客户端原本请求的名字（那个名字可用就用它，否则报错）。
# The alias chain is walked without consulting the available models list; a value carrying a provider qualifier ends the walk. The catalogue is consulted once, after the walk: on a hit the catalogue's own spelling is used; if the target is still unavailable the mapping is abandoned and resolution falls back to the name the client asked for — which is served if it is itself available, and refused otherwise.
```

**理由**（Spec §2.5 与 §2.4）。两处变了：

- **第一句**：新算法**全程不查**可用模型列表，走到链末才查一次。必须如此，否则写在链末的 provider 限定永远读不到——`fable: claude-opus-5` 会在第一跳命中目录并返回，`claude-opus-5: A/claude-opus-5` 那条限定就成了死条目，同一个模型会因为客户端拼法不同而去不同的 provider。这是一处**单 provider 部署也会跟着变**的行为：链中间的名字可用而链末不可用时，旧算法就地返回中间那个，新算法透传。
- **最后一句的括号**：「上游随后拒绝它」不总成立。透传回退到的是**客户端原本请求的名字**，而那个名字本身可以是目录里的真模型——2026-08-27 实测，随包配置的 `claude-opus-4.5: claude-opus-5` 在缺 `claude-opus-5` 的账号上就会命中这条路径，请求以 `claude-opus-4.5` 正常发出并被上游接受。

## 3. `config.example.yaml:74-78` — 值的语义扩展了

**现状**（大意）：「模型名映射：请求模型 → 目标模型」「这是模型名映射的唯一来源」。

**建议**：补一句说明值可以携带 provider 限定，例如

```
# 值可以写成 `<provider>/<模型名>`，指定由哪个 model provider 服务它，例如 `claude-opus-4.8: A/claude-opus-5`。
# 不带限定的值只是别名，解析继续；带限定的值是终点。斜杠前必须是 `model_providers` 里已配置的键（精确匹配，不做大小写与 . - 折叠）。
# A value may be written `<provider>/<model>` to name the model provider that serves it. An unqualified value is an alias and resolution continues; a qualified value is a terminus. The name before the separator must be a configured `model_providers` key, matched exactly.
```

**理由**（Spec §1.1）：路由判据的载体就是这张表的**值**，这是用户在设计问答中选定的方案。「目标模型」这个说法本身没错，但它现在只描述了值的一半。

## 4. `config.example.yaml` — 新增顶层键 `fallback_model_provider`

**建议**新增一段：

```yaml
# 当某条映射的值指定了一个**未配置**的 provider 名时（例如打错字），请求改由这里指定的 provider 服务。
# 与 default_model_provider 分工不同：default 管「没写限定」，fallback 管「写了限定但认不出」。
# 不配置则这类请求直接报错，而不是悄悄落到 default —— 那是 fail-closed 的方向。
# 配置了一个不存在的 provider 名会导致启动失败，与 default_model_provider 一致。
#
# When a mapping value names a provider that is not configured — a typo, say — the request is served by this one instead.
# Distinct from `default_model_provider`, which answers "no qualifier was written"; this answers "one was written and is unrecognised".
# Leave it unset and such requests are refused rather than quietly served from the default.
#
# fallback_model_provider: ghc
```

**理由**（Spec §1.2、§5.3）：`config.example.yaml` 是带注释的完整样例，新键不在里面运维就无从知道它存在——而它决定了一整类请求（限定写错的那些）是被服务还是被拒。

## 5. `request-pipeline.md:11` — 映射写法与实现不一致，需用户裁决

**现状**：用 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses` 描述映射关系。

**问题**（Spec §2.1）：`model_mappings` 的**值**目前**不支持** `@format` 后缀。`split_format_suffix` 只作用于入站请求里的模型名；`src/` 与 `tests/` 中没有任何 mapping 值带 `@`。照该文档写出来的配置会得到一个含 `@` 的模型名，查不到目录，透传后报错。

**两条路，请用户裁**：

- **改文档**：把那处示例改成不带 `@` 的写法，明确 `@format` 只能出现在客户端发来的模型名上。
- **改实现**：让值也支持 `@format`，即配置可以钉死某条映射走哪个上游端点。这是一个独立特性，不在本次范围内。

本次实现按「不支持」落地，并在 Spec §2.1 明写了这一点，以免沉默被读成支持。
