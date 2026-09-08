# 客户端端到端测试组（`tests/client_e2e/`）

日期：2026-08-20
性质：新测试层的说明 + 它立刻产出的一手发现

## 1. 它回答什么，别的组答不了

其余测试组都在**进程内**驱动代理：快、能断言对象而不是字节，对它们各自的目标是正确取舍。但它们都答不出决定 mock_result 设计的那个问题——**真实客户端拿到我们合成的东西会怎么做**。

这一组用真实的 `claude` 二进制回答它。

## 2. 结构

```
claude CLI (真实二进制)
   ↓ ANTHROPIC_BASE_URL
代理 (真实 app，真实端口，uvicorn 线程)
   ↓ httpx.MockTransport
ScriptedUpstream (进程内，可编程、可检视)
```

**中间全部是在产代码**：同一个 `create_pipeline_app`、同一条 chain、同一批订阅者。只有通往 Copilot 的那个 socket 被替换。任何重新实现中间环节的测试，都不再能回答客户端究竟收到了什么。

- `upstream.py`：脚本化上游。按顺序作答，完整记录收到的每个请求。
- `harness.py`：起代理、跑 CLI、读客户端写下的 transcript。
- `conftest.py`：本组入口，含隔离用的 `config_dir` fixture。

## 3. 隔离不是卫生问题，是功能前提

`CLAUDE_CONFIG_DIR` 指向临时目录，`ANTHROPIC_API_KEY` 是一个对真 API 必然失败的字符串，`no_proxy=*`。

**这一点由变异证明，不是推断**：去掉 `CLAUDE_CONFIG_DIR` 后，CLI 读到开发者的真实配置并直接以 `unrecognized_model` 拒绝 `claude-model`，upstream 一次都没被调用。所以隔离既保护开发者的凭证与会话历史，也是这组测试能跑起来的前提。

变异二：把 `ANTHROPIC_BASE_URL` 指向别处 → 两条测试超时失败（CLI 重试约 4 分钟）。所以「代理确实在路径上」是被证明的，不是假定的。

## 4. 默认 sweep 排除

`pyproject.toml` 的 `addopts` 增加 `--ignore=tests/client_e2e`，与 `tests/tui` 同样处理：它们驱动真实二进制与真实 socket，每条以秒计，且依赖一个仓库不安装的东西。

```
uv run pytest tests/client_e2e     # 显式运行
```

隔离逻辑放在本组自己的 `conftest.py`，不放根级——根级的 `CLAUDE_CONFIG_DIR` 会把这个选择从其余每一组手里拿走。

机器上没有 `claude` 时整组跳过，而不是以 `FileNotFoundError` 失败。

## 5. 立刻产出的一手发现

### 5.1 mock_result 在真实客户端上工作，且优于 drop —— 现在有证据

此前 `delivery/synthetic.py` 的 docstring 写着「未经真实客户端验证」。**现在验证了。**

客户端把我们合成的 `web_search_tool_result_error` 渲染成：

```
Web search results for query: "bun 1.3"

Web search error: unavailable


REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.
```

三条结论：

1. **客户端认得这个形态**，并把 `error_code` 翻成了可读的失败说明。
2. **模型被明确告知搜索失败**，而不是收到伪造的结果。这正是 drop 会造成的危害的反面——同一个抬头下，drop 给的是模型凭记忆编的内容。
3. **对话正常完成**：`returncode 0`，走到脚本的最终回复，没有重试循环、没有调用不存在的工具。

代理日志同时显示：代理处理了 **3** 个请求，而 upstream 只收到 **2** 个——中间那个 `↑0B` 就是被拦下并合成的搜索子请求。**upstream 从未看到 web search 声明。**

### 5.2 客户端不为此设 `is_error`

我最初断言 transcript 里的 `tool_result` 会带 `is_error: true`——**错了**。客户端把「搜索失败」当作一种它知道如何描述的**结果**，而不是坏掉的工具，失败信息在 content 文本里。

断言已改为读渲染文本。这条差异只有真实客户端能告诉我们。

### 5.3 那句 REMINDER 在没有来源时略显别扭

`REMINDER: You MUST include the sources above` 出现在一次没有任何来源的失败之后。这是客户端的固定文案，不由我们控制，记录备查。

## 6. 绿灯的分辨力

每条断言都做过变异：

| 变异 | 结果 |
|---|---|
| `ANTHROPIC_BASE_URL` 指向别处 | 2 条红（超时） |
| 去掉 `CLAUDE_CONFIG_DIR` | 2 条红（`unrecognized_model`，upstream 零调用） |
| 合成结果改为 `content: []`（谎称「搜了但没结果」） | 「模型被告知失败」那条红 |

最后一条尤其重要：它证明该断言真的在区分**告知失败**与**谎称无结果**，而不只是在检查字符串存在。

## 7. 后续可加的场景

本组是为「从 mock_result 开始」建的，结构上可继续覆盖：

- Responses 腿的能力门（`models_support_web_search` 不含该模型）在真实客户端上的表现
- `web_search_domain_restrictions: error` 那条 400 路径——**取证显示客户端会重试 3 次**，本组可以直接测出重试次数
- 其他 typed tool（`bash_20250124` 等）经 Responses 腿时的真实后果（§5.1 的已知缺口）
- 流式与非流式在客户端侧的等价性

## 8. 相关文档

- 客户端取证：[`260820-claude-code-websearch-request-forensics.md`](260820-claude-code-websearch-request-forensics.md)
- 映射与合成实现：[`260820-websearch-responses-leg-mapping.md`](260820-websearch-responses-leg-mapping.md)
