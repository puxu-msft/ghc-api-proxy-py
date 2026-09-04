# `883b104` 与 `3bcf14c` 独立评审：endpoint defaulting 与 `--json` 形状

评审对象仅为 `883b104507bd26e19b14b58fa54b3c93042f9d9e` 和其后代 `3bcf14c5e3c8a2959255e24ec20d1c923bd3ddd4`。为避开共享工作树的并行改动，我从 Git object 建立了隔离检出 `/tmp/review-endpoint-defaulting-gpt.msECBR/repo`，固定在 `3bcf14c`；没有修改共享源文件，没有运行全量 pytest，没有接触 `4141` 端口上的 Bun 服务。

## 结论

**Verdict：needs-fix。** endpoint 缺键的正常路径和 `--json` 的两个用户入口均已实跑成功，但 endpoint resolver 把任意非 `list` 的畸形值也当成“缺键”，会把明确写成 `"/responses"` 的畸形字段改判为 `/chat/completions` 并实际发请求。这是 fail-open 的路由错误，严重度为 `Major`。显式空列表在 provider 的 `send()` 与 `count_tokens()` 上仍然 fail-closed，已由独立整链路探针确认；不过报告把它叫作 `no-driver`，与实际抛出的 `CapabilityMissing` 不一致，严重度为 `Minor`。

证据强度：上述两个行为判断均为“强到足以行动”。依据是固定 commit 的生产对象、独立构造的 catalog、真实 `GithubCopilotProvider.replace_catalog → describe/send/count_tokens` 调用链，以及真实 CLI 上游调用；64 个受影响单元测试全绿只作为旁证，不作为结论的 oracle。

## Findings

### F1 — `Major`：畸形 `supported_endpoints` 被扩权为默认 endpoint，并可真正发往错误路径

- 位置：`src/app/model_provider/types.py:79-92,113-124`，`src/app/model_provider/github_copilot.py:101-123,148-182`，`src/app/debug/models.py:131-143,171-197`，锚点为 `3bcf14c`。
- 可复现输入：`supported_endpoints="/responses"`、`supported_endpoints={}` 或显式 `supported_endpoints=null`；`model_type="chat"`。
- 实际输出：`resolve_endpoints("/responses", model_type="chat")` 与 `resolve_endpoints({}, model_type="chat")` 都返回 `OPENAI_CHAT_COMPLETIONS` 且 `advertised=False`。整链路中，`string-value` 的 descriptor 获得 `/chat/completions`，随后 `send(... OPENAI_CHAT_COMPLETIONS ...)` 返回 `chat-ok`，fake client 确认实际调用了 `chat`。显式 `null` 也同样被路由。
- 为什么是缺陷：`parse_endpoints()` 对任何非 `list` 都返回空集合，`resolve_endpoints()` 随后只用 `isinstance(advertised, list)` 区分“上游明确说空”与“使用默认值”，因此字符串、mapping、数字和缺键全部落入同一 fallback。更具体的反例是字符串 `"/responses"`：它至少携带了一个与默认值相反的路径文本，而实现忽略该值并向 `/chat/completions` 发送。与此同时，debug report 会把字符串标为 `malformed`，所以报告层与实际 provider 路由层对同一 catalog 项给出不同裁决。
- 建议：在 catalog membership 层保留“键不存在”的独立 sentinel，不要再用 `model.get()` 的 `None` 兼任缺键。只有 sentinel 触发默认 endpoint；显式 `null` 和其他非 `list` 形状应留下空 capability 或明确的 malformed 状态，使 `require_endpoint()` 在网络前拒绝。不要让一个畸形条目静默扩大能力。

### F2 — `Minor`：显式空列表路由虽 fail-closed，但报告误称 `no-driver`

- 位置：`src/app/debug/models.py:103-128,171-200`，`tests/unit/test_debug_models.py:116-133`，锚点为 `3bcf14c`。
- 可复现输入：`{"id": "explicit-empty", "capabilities": {"type": "chat"}, "supported_endpoints": []}`。
- 实际输出：`describe()` 得到空 endpoints；`send()` 与 `count_tokens()` 都抛 `CapabilityMissing: ghc advertises no endpoints for model 'explicit-empty'`，且 fake client 没有收到调用。`build_rows()` 却把同一项报告为 `no-driver`，本次新增测试还在 `tests/unit/test_debug_models.py:131-133` 固定了这个词。
- 为什么是缺陷：`no-driver` 表示“上游给了 endpoint，但本 proxy 没有对应 driver”；空列表表示“上游明确给了零个 endpoint”。两者修复方不同。当前报告会把 operator 指向编写 driver，而实际没有可驱动的 endpoint，且路由抛出的异常已经保留了正确区别。
- 建议：把 `resolved.advertised` 与“resolved 集合为空”传给 status 判定，为显式空集合恢复 `no-endpoints` 或等价的独立状态；缺键 fallback 仍应为 routable。

## `resolve_endpoints` 反例矩阵

实际输出如下。意外结果是字符串和 mapping 被默认成 chat；显式 `None` 与缺键不可区分，也会默认。`[]`、`[7]`、`[None]` 都保持空 capability 且 `advertised=True`，随后会 fail-closed；`["/responses", 7]` 保留有效字符串并忽略非字符串成员。`model_type` 只有精确小写 `embeddings` 走 `/embeddings`，其余值全部走 `/chat/completions`；这与当前“embeddings 之外均为 chat-completions”的裁决一致，但大小写变体不会被规范化。

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run python -c 'from app.model_provider.types import resolve_endpoints; advertised_cases = [None, [], [7], [None], "/responses", {}, ["/responses", 7]]; model_types = ["embeddings", "chat", "completion", "", None, "Embeddings", "EMBEDDINGS"]; print("advertised cases (model_type=chat)"); [print(repr(value), "=>", resolve_endpoints(value, model_type="chat")) for value in advertised_cases]; print("model_type cases (advertised=None)"); [print(repr(value), "=>", resolve_endpoints(None, model_type=value)) for value in model_types]'
```

```text
advertised cases (model_type=chat)
None => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
[] => ResolvedEndpoints(known=frozenset(), unknown=(), advertised=True)
[7] => ResolvedEndpoints(known=frozenset(), unknown=(), advertised=True)
[None] => ResolvedEndpoints(known=frozenset(), unknown=(), advertised=True)
'/responses' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
{} => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
['/responses', 7] => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_RESPONSES: '/responses'>}), unknown=(), advertised=True)
model_type cases (advertised=None)
'embeddings' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_EMBEDDINGS: '/embeddings'>}), unknown=(), advertised=False)
'chat' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
'completion' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
'' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
None => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
'Embeddings' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
'EMBEDDINGS' => ResolvedEndpoints(known=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=(), advertised=False)
```

## 缺键与显式空列表的整链路结果

证据强度：强到足以确认“显式空列表仍然 fail-closed”，但只覆盖当前 `GithubCopilotProvider` 的 production methods 与 fake client 边界，不声称真实上游会发送空列表。

探针输入脚本：

```python
import asyncio
from typing import Any

import httpx

from app.config.schema import ModelProviderConfig
from app.model_provider import ModelEndpoint
from app.model_provider.github_copilot import GithubCopilotProvider


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def send_chat_completions(self, payload: Any, *, stream: bool, extra_headers: Any) -> str:
        self.calls.append("chat")
        return "chat-ok"

    async def send_embeddings(self, payload: Any) -> str:
        self.calls.append("embeddings")
        return "embeddings-ok"

    async def send_responses(self, payload: Any, *, stream: bool, extra_headers: Any) -> str:
        self.calls.append("responses")
        return "responses-ok"

    async def send_anthropic_messages(self, payload: Any, *, stream: bool, extra_headers: Any) -> str:
        self.calls.append("messages")
        return "messages-ok"

    async def send_anthropic_count_tokens(self, payload: Any) -> str:
        self.calls.append("count_tokens")
        return "count-ok"


async def show_call(label: str, operation: Any) -> None:
    try:
        result = await operation
    except Exception as error:
        print(f"{label}: {type(error).__name__}: {error}")
    else:
        print(f"{label}: returned {result!r}")


async def main() -> None:
    fake = FakeClient()
    http = httpx.AsyncClient()
    provider = GithubCopilotProvider(
        "ghc",
        fake,  # type: ignore[arg-type]
        ModelProviderConfig(type="github_copilot"),
        http_client=http,
        base_url="https://example.invalid",
    )
    provider.replace_catalog(
        {
            "data": [
                {"id": "missing-chat", "capabilities": {"type": "chat"}},
                {"id": "explicit-null", "capabilities": {"type": "chat"}, "supported_endpoints": None},
                {"id": "explicit-empty", "capabilities": {"type": "chat"}, "supported_endpoints": []},
                {"id": "string-value", "capabilities": {"type": "chat"}, "supported_endpoints": "/responses"},
                {"id": "junk-list", "capabilities": {"type": "chat"}, "supported_endpoints": [7]},
            ]
        }
    )
    try:
        for model_id in ("missing-chat", "explicit-null", "explicit-empty", "string-value", "junk-list"):
            descriptor = provider.describe(model_id)
            print(f"describe({model_id!r}): endpoints={descriptor.endpoints if descriptor else None!r}, unknown={descriptor.unknown_endpoints if descriptor else None!r}")
        await show_call(
            "send missing-chat -> chat",
            provider.send(ModelEndpoint.OPENAI_CHAT_COMPLETIONS, {"model": "missing-chat"}, model_id="missing-chat"),
        )
        await show_call(
            "count_tokens missing-chat",
            provider.count_tokens({"model": "missing-chat"}, model_id="missing-chat"),
        )
        await show_call(
            "send explicit-empty -> chat",
            provider.send(ModelEndpoint.OPENAI_CHAT_COMPLETIONS, {"model": "explicit-empty"}, model_id="explicit-empty"),
        )
        await show_call(
            "count_tokens explicit-empty",
            provider.count_tokens({"model": "explicit-empty"}, model_id="explicit-empty"),
        )
        await show_call(
            "send explicit-null -> chat",
            provider.send(ModelEndpoint.OPENAI_CHAT_COMPLETIONS, {"model": "explicit-null"}, model_id="explicit-null"),
        )
        await show_call(
            "send string-value -> chat",
            provider.send(ModelEndpoint.OPENAI_CHAT_COMPLETIONS, {"model": "string-value"}, model_id="string-value"),
        )
        await show_call(
            "send junk-list -> chat",
            provider.send(ModelEndpoint.OPENAI_CHAT_COMPLETIONS, {"model": "junk-list"}, model_id="junk-list"),
        )
        print(f"fake client calls: {fake.calls!r}")
    finally:
        await http.aclose()


asyncio.run(main())
```

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run python /tmp/review-endpoint-defaulting-gpt.msECBR/probe_chain.py
```

```text
describe('missing-chat'): endpoints=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=()
describe('explicit-null'): endpoints=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=()
describe('explicit-empty'): endpoints=frozenset(), unknown=()
describe('string-value'): endpoints=frozenset({<ModelEndpoint.OPENAI_CHAT_COMPLETIONS: '/chat/completions'>}), unknown=()
describe('junk-list'): endpoints=frozenset(), unknown=()
send missing-chat -> chat: returned 'chat-ok'
count_tokens missing-chat: EndpointNotSupported: model 'missing-chat' does not advertise /v1/messages on ghc
send explicit-empty -> chat: CapabilityMissing: ghc advertises no endpoints for model 'explicit-empty'
count_tokens explicit-empty: CapabilityMissing: ghc advertises no endpoints for model 'explicit-empty'
send explicit-null -> chat: returned 'chat-ok'
send string-value -> chat: returned 'chat-ok'
send junk-list -> chat: CapabilityMissing: ghc advertises no endpoints for model 'junk-list'
fake client calls: ['chat', 'chat', 'chat']
```

结论：缺键的 chat model 可发往 chat endpoint；其 `count_tokens()` 因只接受 Messages capability 而抛 `EndpointNotSupported`，这是现有 contract。显式空列表对 `send()` 与 `count_tokens()` 均抛 `CapabilityMissing`，且没有网络调用。畸形字符串与显式 null 则错误地走通 chat 调用，支持 F1。

## `--json` 形状开关

### 真实 CLI

无 `--provider` 时真实输出顶层为 `{"ghc": <catalog>}`；指定 `--provider X` 时顶层直接为原 catalog 的 `data`、`object`。两次调用均成功使用真实上游凭据。上游两次瞬时结果分别为 41 与 42 个 models；两次都恰有 18 项缺少 `supported_endpoints`、0 项显式 null、0 项显式空列表，缺键 type 分布均为 14 `chat`、3 `embeddings`、1 `completion`。模型总数的瞬时差异是两次真实上游响应的观察值，不归因于本次代码。

### 人工让两个条件冲突

`cli.py` 在有 `--provider` 时传 `keyed=False`，而 `render_json()` 只有 `not keyed and len(catalogs) == 1` 才解包。强制 collector 在 `--provider X` 下返回两个 catalogs 时，输出回到按 provider keyed 的 object；无 `--provider` 但只返回一个 catalog 时，仍保留 key。形状是确定的：cardinality 不为 1 时，避免丢失优先于 unkey 请求。正常 production collector 在 named-provider 路径最多产生一个 catalog，因此“named + two catalogs”只用于证伪 helper 的边界，不是可达生产状态。

探针输入脚本：

```python
import importlib

from typer.testing import CliRunner

from app.debug.models import ProviderCatalog, render_json

cli = importlib.import_module("app.cli")
runner = CliRunner()
one = ProviderCatalog(name="X", base_url="https://x.invalid", raw={"data": [{"id": "x"}]}, rows=())
two = ProviderCatalog(name="Y", base_url="https://y.invalid", raw={"data": [{"id": "y"}]}, rows=())

print("direct render_json matrix")
for label, catalogs, keyed in (
    ("one,keyed=True", [one], True),
    ("one,keyed=False", [one], False),
    ("two,keyed=False", [one, two], False),
    ("zero,keyed=False", [], False),
):
    print(label)
    print(render_json(catalogs, keyed=keyed))


async def returns_two(config: object, only: str | None = None):
    print(f"fake collect only={only!r}")
    return (one, two), ()


async def returns_one(config: object, only: str | None = None):
    print(f"fake collect only={only!r}")
    return (one,), ()


cli.collect_catalogs = returns_two
result = runner.invoke(
    cli.app,
    [
        "debug",
        "models",
        "--config",
        "/tmp/review-endpoint-defaulting-gpt.msECBR/named-provider.yaml",
        "--provider",
        "X",
        "--json",
    ],
)
print("forced CLI: --provider X but collector returns two catalogs")
print(f"exit={result.exit_code}")
print(result.stdout, end="")

cli.collect_catalogs = returns_one
result = runner.invoke(
    cli.app,
    [
        "debug",
        "models",
        "--config",
        "/tmp/review-endpoint-defaulting-gpt.msECBR/named-provider.yaml",
        "--json",
    ],
)
print("forced CLI: no --provider but collector returns one catalog")
print(f"exit={result.exit_code}")
print(result.stdout, end="")
```

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run python /tmp/review-endpoint-defaulting-gpt.msECBR/probe_json_shape.py
```

```text
direct render_json matrix
one,keyed=True
{
  "X": {
    "data": [
      {
        "id": "x"
      }
    ]
  }
}
one,keyed=False
{
  "data": [
    {
      "id": "x"
    }
  ]
}
two,keyed=False
{
  "X": {
    "data": [
      {
        "id": "x"
      }
    ]
  },
  "Y": {
    "data": [
      {
        "id": "y"
      }
    ]
  }
}
zero,keyed=False
{}
forced CLI: --provider X but collector returns two catalogs
exit=0
fake collect only='X'
{
  "X": {
    "data": [
      {
        "id": "x"
      }
    ]
  },
  "Y": {
    "data": [
      {
        "id": "y"
      }
    ]
  }
}
forced CLI: no --provider but collector returns one catalog
exit=0
fake collect only=None
{
  "X": {
    "data": [
      {
        "id": "x"
      }
    ]
  }
}
```

判断：`3bcf14c` 的形状开关本身通过评审，没有发现 correctness defect。

## 新增断言的分辨力

以下断言即使相邻实现写错也能保持绿色，不能单独承担其注释中的全称命题：

1. `tests/unit/test_debug_models.py:65,93-113,219-224` 把所谓“省略字段”构造成 `supported_endpoints=None`，实际 JSON 形状是键存在且值为 null。`assert rows["silent"].status == "ok"`、四个 endpoint equality 和 `assert all(...status == "ok")` 无法区分“真正缺键”与“只对显式 null fallback”。它们还直接把当前显式 null 的 fail-open 行为固定为期望值。
2. `tests/unit/test_model_provider.py:402-409` 的 `assert provider.describe("embed-model") is not None` 只证明 descriptor 存在，不证明 upstream 明示的 `/embeddings` 没被 default 覆盖。该测试对 empty-list 的 `mute.endpoints == frozenset()` 有分辨力，但对注释中 named embeddings 的“不被替换”没有分辨力。`tests/unit/test_debug_models.py:116-133` 在报告投影上有更强断言，但不能替代 provider routing 断言。
3. `tests/unit/test_debug_models.py:372-378` 的 `assert set(document) == {"ghc", "other"}` 只证明 wrapper keys 存在；两个 payload 都为空、payload 对错 provider、或 payload 被截断仍会绿。若该测试要承担“没有一个 answer silently winning”的内容保持命题，应直接比较完整 object。
4. `tests/unit/test_debug_models.py:658-680` 的 named-provider CLI fake 不断言 `only == "ghc"`，所以这个新增测试单独看时，CLI 忘记把 provider 传给 collector 也可绿。不过既有 `tests/unit/test_debug_models.py:600-615` 独立断言 `seen == ["ghc"]`，所以组合测试集仍能抓住该 wiring 错误。

以下新增断言具有足够分辨力，不应与上述薄弱项一并否定：`tests/unit/test_debug_models.py:679-680` 和 `:700-701` 对 CLI 输出做完整 JSON equality，能区分 named/unwrapped 与 unnamed/keyed；`tests/unit/test_model_provider.py:380-399` 走到 provider `send()` 并断言真实 request path；空列表还受到既有 `tests/unit/test_model_provider.py:184-203,228-255` 的 send/count fail-closed 检查。

测试绿灯的权重：只支持“这 64 个被枚举测试在隔离的 `3bcf14c` checkout 中通过”，不支持“畸形输入 fail-closed”。F1 的字符串反例正是全绿之外的独立正样本。

## 受影响测试文件

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run pytest --color=no -q tests/unit/test_debug_models.py tests/unit/test_model_provider.py
```

```text
................................................................         [100%]
64 passed in 2.36s
```

## CLI 实跑记录

临时配置输入：

`/tmp/review-endpoint-defaulting-gpt.msECBR/one-provider.yaml`

```yaml
{}
```

`/tmp/review-endpoint-defaulting-gpt.msECBR/named-provider.yaml`

```yaml
model_providers:
  X:
    type: github_copilot
default_model_provider: ghc
```

由于配置采用 deep merge，第二份配置的有效 provider names 是 `X, ghc`；`--provider X` 只请求 `X`。

`/tmp/review-endpoint-defaulting-gpt.msECBR/bad-config.yaml`

```yaml
model_providers:
  ghc:
    type: github_copilot
    mystery: true
```

### Help

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run ghc-api-proxy debug models --help
```

退出码：`0`。

```text
[1m                                                                                [0m
[1m [0m[1;33mUsage: [0m[1mghc-api-proxy debug models [OPTIONS][0m[1m                                   [0m[1m [0m
[1m                                                                                [0m
 Show upstream model information.                                               
                                                                                
[2m╭─[0m[2m Options [0m[2m───────────────────────────────────────────────────────────────────[0m[2m─╮[0m
[2m│[0m [1;36m-[0m[1;36m-config[0m          [1;33mFILE[0m                                                       [2m│[0m
[2m│[0m [1;36m-[0m[1;36m-provider[0m        [1;33mTEXT[0m  Report only this configured provider.                [2m│[0m
[2m│[0m [1;36m-[0m[1;36m-json[0m            [1;33m    [0m  Print the complete decoded upstream payload, keyed   [2m│[0m
[2m│[0m                         by provider name unless [1;36m-[0m[1;36m-provider[0m names one.        [2m│[0m
[2m│[0m [1;36m-[0m[1;36m-help[0m            [1;33m    [0m  Show this message and exit.                          [2m│[0m
[2m╰──────────────────────────────────────────────────────────────────────────────╯[0m
```

判断：帮助准确说明 keyed/unwrapped 行为，可读。

### 无 `--provider` 的真实 `--json`

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run ghc-api-proxy debug models --config /tmp/review-endpoint-defaulting-gpt.msECBR/one-provider.yaml --json
```

退出码：`0`。以下为完整 stdout，未裁剪。

```json
{
  "ghc": {
    "data": [
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.6",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.6",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.6](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.7",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.7",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.7",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.7 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.7](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.7",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.8",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.8",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.8",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.8 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.8](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.8",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-5",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 5](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-sonnet-4.6",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-sonnet-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Claude Sonnet 4.6",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Sonnet 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Sonnet 4.6](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/v1/messages"
        ],
        "vendor": "Anthropic",
        "version": "claude-sonnet-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-sonnet-5",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-sonnet-5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Claude Sonnet 5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude model from Anthropic. [Learn more about how GitHub Copilot serves Claude](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-sonnet-5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "edu",
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.1-pro-preview",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.1-pro-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Gemini 3.1 Pro",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3 Pro model from Google. [Learn more about how GitHub Copilot serves Gemini 3 Pro](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": true,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.1-pro-preview",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.5-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 24000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "minimal",
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.5-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "Gemini 3.5 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.5 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.5 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.5-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.6-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "minimal",
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.6-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Gemini 3.6 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.6 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.6 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.6-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.7-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.7-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Gemini 3.7 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.7 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.7 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.7-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "edu",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.3-codex",
          "limits": {
            "max_context_window_tokens": 400000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 272000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.3-codex",
        "is_chat_default": true,
        "is_chat_fallback": true,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.3-Codex",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.3-codex",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "edu",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.4-mini",
          "limits": {
            "max_context_window_tokens": 400000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 272000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.4-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5.4 mini",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.4 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4 mini](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.4-mini",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.4",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.4",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.4",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.4 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "/chat/completions",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.4",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.5",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.5 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.5](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-luna",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-luna",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Luna",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Luna model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Luna](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-luna",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-sol",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-sol",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Sol",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Sol model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Sol](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-sol",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-terra",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-terra",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Terra",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Terra model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Terra](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-terra",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "grok-4.5",
          "limits": {
            "max_context_window_tokens": 500000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 372000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "grok-4.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Grok 4.5",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "xAI",
        "version": "grok-4.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "grok-4.6",
          "limits": {
            "max_context_window_tokens": 500000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 372000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "grok-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Grok 4.6",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "xAI",
        "version": "grok-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "max",
            "business",
            "enterprise"
          ]
        },
        "capabilities": {
          "family": "oswe-vscode-modelD",
          "limits": {
            "max_context_window_tokens": 256000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 128000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "mai-code-1-flash-picker",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "MAI-Code-1-Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": ""
        },
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "Microsoft",
        "version": "mai-code-1-flash-picker",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "individual_trial",
            "max"
          ]
        },
        "capabilities": {
          "family": "trajectory-compaction",
          "limits": {
            "max_context_window_tokens": 262144,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 245760
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "trajectory-compaction",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Trajectory Compaction",
        "object": "model",
        "preview": true,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Fireworks",
        "version": "trajectory-compaction",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-5-mini",
          "limits": {
            "max_context_window_tokens": 264000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5 mini",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5 mini](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/responses",
          "ws:/responses"
        ],
        "vendor": "Azure OpenAI",
        "version": "gpt-5-mini",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o-mini",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-mini-2024-07-18",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o mini",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-mini-2024-07-18",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-11-20",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-11-20",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-08-06",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-08-06",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-3-small",
          "limits": {
            "max_inputs": 512
          },
          "object": "model_capabilities",
          "supports": {
            "dimensions": true
          },
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-3-small",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V3 small",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-3-small",
          "object": "model_capabilities",
          "supports": {
            "dimensions": true
          },
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-3-small-inference",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V3 small (Inference)",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "claude-haiku-4.5",
          "limits": {
            "max_context_window_tokens": 200000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 136000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-haiku-4.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "Claude Haiku 4.5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Haiku 4.5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Haiku 4.5](https://gh.io/copilot-anthropic)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/v1/messages"
        ],
        "vendor": "Anthropic",
        "version": "claude-haiku-4.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4.1-2025-04-14",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4.1",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
        },
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4.1-2025-04-14",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "object": "model_capabilities",
          "supports": {
            "streaming": true
          },
          "tokenizer": "o200k_base",
          "type": "completion"
        },
        "id": "gpt-41-copilot",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": false,
        "name": "GPT-4.1 Copilot",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-41-copilot",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-3.5-turbo",
          "limits": {
            "max_context_window_tokens": 16384,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-3.5-turbo-0613",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 3.5 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-3.5-turbo-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4",
          "limits": {
            "max_context_window_tokens": 32768,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 32768
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4",
          "limits": {
            "max_context_window_tokens": 32768,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 32768
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4-0613",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4-turbo",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4-0125-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0125-preview",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-05-13",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-05-13",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4-o-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-05-13",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4.1",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": false,
        "name": "GPT-4.1",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
        },
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4.1-2025-04-14",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "max",
            "business",
            "enterprise",
            "individual_trial",
            "edu"
          ]
        },
        "capabilities": {
          "family": "gpt-3.5-turbo",
          "limits": {
            "max_context_window_tokens": 16384,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-3.5-turbo",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 3.5 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-3.5-turbo-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o-mini",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o mini",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-mini-2024-07-18",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-11-20",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-ada-002",
          "limits": {
            "max_inputs": 512
          },
          "object": "model_capabilities",
          "supports": {},
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-ada-002",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V2 Ada",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      }
    ],
    "object": "list"
  }
}
```

### `--provider X --json` 的真实调用

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run ghc-api-proxy debug models --config /tmp/review-endpoint-defaulting-gpt.msECBR/named-provider.yaml --provider X --json
```

退出码：`0`。以下为完整 stdout，未裁剪。

```json
{
  "data": [
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "individual_trial",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-opus-4.6",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-opus-4.6",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "Claude Opus 4.6",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Opus 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.6](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/v1/messages",
        "/chat/completions"
      ],
      "vendor": "Anthropic",
      "version": "claude-opus-4.6",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-opus-4.7",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-opus-4.7",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "Claude Opus 4.7",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Opus 4.7 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.7](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/v1/messages",
        "/chat/completions"
      ],
      "vendor": "Anthropic",
      "version": "claude-opus-4.7",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-opus-4.8",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-opus-4.8",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "Claude Opus 4.8",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Opus 4.8 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.8](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/v1/messages",
        "/chat/completions"
      ],
      "vendor": "Anthropic",
      "version": "claude-opus-4.8",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-opus-5",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-opus-5",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "Claude Opus 5",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Opus 5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 5](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/v1/messages",
        "/chat/completions"
      ],
      "vendor": "Anthropic",
      "version": "claude-opus-5",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "individual_trial",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-sonnet-4.6",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 5,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-sonnet-4.6",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Claude Sonnet 4.6",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Sonnet 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Sonnet 4.6](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions",
        "/v1/messages"
      ],
      "vendor": "Anthropic",
      "version": "claude-sonnet-4.6",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "claude-sonnet-5",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 5,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "adaptive_thinking": true,
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-sonnet-5",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Claude Sonnet 5",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude model from Anthropic. [Learn more about how GitHub Copilot serves Claude](https://gh.io/copilot-claude-opus)."
      },
      "preview": false,
      "supported_endpoints": [
        "/v1/messages",
        "/chat/completions"
      ],
      "vendor": "Anthropic",
      "version": "claude-sonnet-5",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "edu",
          "pro",
          "pro_plus",
          "individual_trial",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gemini-3.1-pro-preview",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 10,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/heic",
              "image/heif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "max_thinking_budget": 32000,
          "min_thinking_budget": 256,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gemini-3.1-pro-preview",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "Gemini 3.1 Pro",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Gemini 3 Pro model from Google. [Learn more about how GitHub Copilot serves Gemini 3 Pro](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
      },
      "preview": true,
      "supported_endpoints": [
        "/chat/completions"
      ],
      "vendor": "Google",
      "version": "gemini-3.1-pro-preview",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gemini-3.5-flash",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 10,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/heic",
              "image/heif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "max_thinking_budget": 24000,
          "min_thinking_budget": 256,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "minimal",
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gemini-3.5-flash",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "Gemini 3.5 Flash",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Gemini 3.5 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.5 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions"
      ],
      "vendor": "Google",
      "version": "gemini-3.5-flash",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gemini-3.6-flash",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 10,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/heic",
              "image/heif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "max_thinking_budget": 32000,
          "min_thinking_budget": 256,
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "minimal",
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gemini-3.6-flash",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Gemini 3.6 Flash",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Gemini 3.6 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.6 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions"
      ],
      "vendor": "Google",
      "version": "gemini-3.6-flash",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gemini-3.7-flash",
        "limits": {
          "max_context_window_tokens": 1000000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 936000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 10,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/heic",
              "image/heif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gemini-3.7-flash",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Gemini 3.7 Flash",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Gemini 3.7 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.7 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions"
      ],
      "vendor": "Google",
      "version": "gemini-3.7-flash",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "edu",
          "pro_plus",
          "individual_trial",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.3-codex",
        "limits": {
          "max_context_window_tokens": 400000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 272000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.3-codex",
      "is_chat_default": true,
      "is_chat_fallback": true,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "GPT-5.3-Codex",
      "object": "model",
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.3-codex",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "individual_trial",
          "edu",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.4-mini",
        "limits": {
          "max_context_window_tokens": 400000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 272000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.4-mini",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "GPT-5.4 mini",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.4 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4 mini](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.4-mini",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "individual_trial",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.4",
        "limits": {
          "max_context_window_tokens": 1050000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 922000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.4",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "GPT-5.4",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.4 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "/chat/completions",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.4",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.5",
        "limits": {
          "max_context_window_tokens": 1050000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 922000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.5",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "GPT-5.5",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.5 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.5](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.5",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "free",
          "edu",
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.6-luna",
        "limits": {
          "max_context_window_tokens": 1050000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 922000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.6-luna",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "GPT-5.6 Luna",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.6 Luna model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Luna](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.6-luna",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.6-sol",
        "limits": {
          "max_context_window_tokens": 1050000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 922000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.6-sol",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "powerful",
      "model_picker_enabled": true,
      "name": "GPT-5.6 Sol",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.6 Sol model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Sol](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.6-sol",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "gpt-5.6-terra",
        "limits": {
          "max_context_window_tokens": 1050000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 922000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5.6-terra",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "GPT-5.6 Terra",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5.6 Terra model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Terra](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/responses",
        "ws:/responses"
      ],
      "vendor": "OpenAI",
      "version": "gpt-5.6-terra",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "grok-4.5",
        "limits": {
          "max_context_window_tokens": 500000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 372000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "grok-4.5",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Grok 4.5",
      "object": "model",
      "preview": false,
      "supported_endpoints": [
        "/responses"
      ],
      "vendor": "xAI",
      "version": "grok-4.5",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "business",
          "enterprise",
          "max"
        ]
      },
      "capabilities": {
        "family": "grok-4.6",
        "limits": {
          "max_context_window_tokens": 500000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 372000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high",
            "xhigh"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "grok-4.6",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": true,
      "name": "Grok 4.6",
      "object": "model",
      "preview": false,
      "supported_endpoints": [
        "/responses"
      ],
      "vendor": "xAI",
      "version": "grok-4.6",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "promo": {
          "discount_percent": 10,
          "ends_at": "2026-08-25T00:00:00Z",
          "id": "mai_flash_1_1_2026_08",
          "message": "Enjoy 10% off MAI-Code-1.1-Flash."
        },
        "restricted_to": [
          "free",
          "edu",
          "individual_trial",
          "pro",
          "pro_plus",
          "max",
          "business",
          "enterprise"
        ]
      },
      "capabilities": {
        "family": "oswe-vscode-modelD",
        "limits": {
          "max_context_window_tokens": 256000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 128000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "mai-code-1.1-flash",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "MAI-Code-1.1-Flash",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": ""
      },
      "preview": false,
      "supported_endpoints": [
        "/responses"
      ],
      "vendor": "Microsoft",
      "version": "mai-code-1.1-flash",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "free",
          "edu",
          "pro",
          "pro_plus",
          "max",
          "business",
          "enterprise"
        ]
      },
      "capabilities": {
        "family": "oswe-vscode-modelD",
        "limits": {
          "max_context_window_tokens": 256000,
          "max_output_tokens": 128000,
          "max_prompt_tokens": 128000
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "mai-code-1-flash-picker",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "MAI-Code-1-Flash",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": ""
      },
      "preview": false,
      "supported_endpoints": [
        "/responses"
      ],
      "vendor": "Microsoft",
      "version": "mai-code-1-flash-picker",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "free",
          "edu",
          "pro",
          "pro_plus",
          "individual_trial",
          "max"
        ]
      },
      "capabilities": {
        "family": "trajectory-compaction",
        "limits": {
          "max_context_window_tokens": 262144,
          "max_output_tokens": 16384,
          "max_prompt_tokens": 245760
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "trajectory-compaction",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "Trajectory Compaction",
      "object": "model",
      "preview": true,
      "supported_endpoints": [
        "/chat/completions"
      ],
      "vendor": "Fireworks",
      "version": "trajectory-compaction",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-5-mini",
        "limits": {
          "max_context_window_tokens": 264000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 128000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "reasoning_effort": [
            "low",
            "medium",
            "high"
          ],
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-5-mini",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "GPT-5 mini",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-5 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5 mini](https://gh.io/copilot-openai)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions",
        "/responses",
        "ws:/responses"
      ],
      "vendor": "Azure OpenAI",
      "version": "gpt-5-mini",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o-mini",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 12288
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o-mini-2024-07-18",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o mini",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-mini-2024-07-18",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 16384,
          "max_prompt_tokens": 64000
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o-2024-11-20",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-2024-11-20",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 16384,
          "max_prompt_tokens": 64000
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o-2024-08-06",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-2024-08-06",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "text-embedding-3-small",
        "limits": {
          "max_inputs": 512
        },
        "object": "model_capabilities",
        "supports": {
          "dimensions": true
        },
        "tokenizer": "cl100k_base",
        "type": "embeddings"
      },
      "id": "text-embedding-3-small",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "Embedding V3 small",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "text-embedding-3-small",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "text-embedding-3-small",
        "object": "model_capabilities",
        "supports": {
          "dimensions": true
        },
        "tokenizer": "cl100k_base",
        "type": "embeddings"
      },
      "id": "text-embedding-3-small-inference",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "Embedding V3 small (Inference)",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "text-embedding-3-small",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "claude-haiku-4.5",
        "limits": {
          "max_context_window_tokens": 200000,
          "max_non_streaming_output_tokens": 16000,
          "max_output_tokens": 64000,
          "max_prompt_tokens": 136000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 5,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "max_thinking_budget": 32000,
          "min_thinking_budget": 1024,
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "claude-haiku-4.5",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "lightweight",
      "model_picker_enabled": true,
      "name": "Claude Haiku 4.5",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest Claude Haiku 4.5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Haiku 4.5](https://gh.io/copilot-anthropic)."
      },
      "preview": false,
      "supported_endpoints": [
        "/chat/completions",
        "/v1/messages"
      ],
      "vendor": "Anthropic",
      "version": "claude-haiku-4.5",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4.1",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 16384,
          "max_prompt_tokens": 128000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4.1-2025-04-14",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4.1",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
      },
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4.1-2025-04-14",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4.1",
        "object": "model_capabilities",
        "supports": {
          "streaming": true
        },
        "tokenizer": "o200k_base",
        "type": "completion"
      },
      "id": "gpt-41-copilot",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": false,
      "name": "GPT-4.1 Copilot",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-41-copilot",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-3.5-turbo",
        "limits": {
          "max_context_window_tokens": 16384,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 12288
        },
        "object": "model_capabilities",
        "supports": {
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "cl100k_base",
        "type": "chat"
      },
      "id": "gpt-3.5-turbo-0613",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT 3.5 Turbo",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-3.5-turbo-0613",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4",
        "limits": {
          "max_context_window_tokens": 32768,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 32768
        },
        "object": "model_capabilities",
        "supports": {
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "cl100k_base",
        "type": "chat"
      },
      "id": "gpt-4",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT 4",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4-0613",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4",
        "limits": {
          "max_context_window_tokens": 32768,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 32768
        },
        "object": "model_capabilities",
        "supports": {
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "cl100k_base",
        "type": "chat"
      },
      "id": "gpt-4-0613",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT 4",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4-0613",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4-turbo",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 64000
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "cl100k_base",
        "type": "chat"
      },
      "id": "gpt-4-0125-preview",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT 4 Turbo",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4-0125-preview",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 64000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o-2024-05-13",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-2024-05-13",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 64000
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4-o-preview",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-2024-05-13",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4.1",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 16384,
          "max_prompt_tokens": 128000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif",
              "application/pdf"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "structured_outputs": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4.1",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_category": "versatile",
      "model_picker_enabled": false,
      "name": "GPT-4.1",
      "object": "model",
      "policy": {
        "state": "enabled",
        "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
      },
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4.1-2025-04-14",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1,
        "restricted_to": [
          "pro",
          "pro_plus",
          "max",
          "business",
          "enterprise",
          "individual_trial",
          "edu"
        ]
      },
      "capabilities": {
        "family": "gpt-3.5-turbo",
        "limits": {
          "max_context_window_tokens": 16384,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 12288
        },
        "object": "model_capabilities",
        "supports": {
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "cl100k_base",
        "type": "chat"
      },
      "id": "gpt-3.5-turbo",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT 3.5 Turbo",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-3.5-turbo-0613",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o-mini",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 12288
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o-mini",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o mini",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-mini-2024-07-18",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "gpt-4o",
        "limits": {
          "max_context_window_tokens": 128000,
          "max_output_tokens": 4096,
          "max_prompt_tokens": 64000,
          "vision": {
            "max_prompt_image_size": 3145728,
            "max_prompt_images": 1,
            "supported_media_types": [
              "image/jpeg",
              "image/png",
              "image/webp",
              "image/gif"
            ]
          }
        },
        "object": "model_capabilities",
        "supports": {
          "parallel_tool_calls": true,
          "streaming": true,
          "tool_calls": true,
          "vision": true
        },
        "tokenizer": "o200k_base",
        "type": "chat"
      },
      "id": "gpt-4o",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "GPT-4o",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "gpt-4o-2024-11-20",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    },
    {
      "billing": {
        "is_premium": true,
        "multiplier": 1
      },
      "capabilities": {
        "family": "text-embedding-ada-002",
        "limits": {
          "max_inputs": 512
        },
        "object": "model_capabilities",
        "supports": {},
        "tokenizer": "cl100k_base",
        "type": "embeddings"
      },
      "id": "text-embedding-ada-002",
      "is_chat_default": false,
      "is_chat_fallback": false,
      "model_picker_enabled": false,
      "name": "Embedding V2 Ada",
      "object": "model",
      "preview": false,
      "vendor": "Azure OpenAI",
      "version": "text-embedding-3-small",
      "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
    }
  ],
  "object": "list"
}
```

### 不存在的 provider

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run ghc-api-proxy debug models --config /tmp/review-endpoint-defaulting-gpt.msECBR/named-provider.yaml --provider does-not-exist
```

退出码：`2`。

```text
[33mUsage: [0mghc-api-proxy debug models [OPTIONS]
[2mTry [0m[2;34m'ghc-api-proxy debug models [0m[1;2;34m-[0m[1;2;34m-help[0m[2;34m'[0m[2m for help.[0m
[31m╭─[0m[31m Error [0m[31m─────────────────────────────────────────────────────────────────────[0m[31m─╮[0m
[31m│[0m Invalid value: no model provider named 'does-not-exist' is configured        [31m│[0m
[31m│[0m (configured: X, ghc)                                                         [31m│[0m
[31m╰──────────────────────────────────────────────────────────────────────────────╯[0m
```

判断：错误列出无效名字与有效 provider names，没有 traceback，足够可读。

### 坏 config

命令：

```bash
cd /tmp/review-endpoint-defaulting-gpt.msECBR/repo && uv run ghc-api-proxy debug models --config /tmp/review-endpoint-defaulting-gpt.msECBR/bad-config.yaml --json
```

退出码：`1`。

```text
error: 1 validation error for ProxyConfig
model_providers.ghc.mystery
  Extra inputs are not permitted [type=extra_forbidden, input_value=True, input_type=bool]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

判断：错误保留完整 Pydantic field path `model_providers.ghc.mystery`、拒绝原因与输入值，没有 traceback，足够可读。

## 建议处置顺序

1. 先修 F1：把真正缺键与 malformed value 分开，保证 provider routing 对畸形 catalog fail-closed，并新增至少一个 `"/responses"` 字符串反例走 `replace_catalog → send` 的测试。
2. 再修 F2：让显式空列表的报告状态与 `CapabilityMissing` 对齐。
3. 把 debug-models 的“缺键”fixture 改为实际省略 key，并另列 explicit null；加强 named embeddings 与 multi-provider JSON payload 的 assertions。
4. `3bcf14c` 的 CLI shape change 可保留，不需因 endpoint finding 回退。
