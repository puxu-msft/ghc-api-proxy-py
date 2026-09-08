# vcrpy 对异步 OpenAI SDK SSE 的 record-and-replay PoC

## 结论

**不适合用 vcrpy 作为本项目流式 Responses 路径的录制回放工具。**vcrpy 8.3.0 能在指定技术栈中录制并离线回放完整 SSE 正文，但它在录制时已经将原本由 `httpx.Response.aiter_bytes()` 逐块可见的三个 body chunk 合并为一个；回放也是一个完整 body chunk。项目的交付层按 chunk 消费，且要抓住真实上游中同一 output item 的 added/done ID 不一致，因此这个差异会改变被测行为并掩盖时序／边界相关缺陷，不能绕过为「只检查拼接后的字节相同」。

## 假设与成功判据

被验证的假设是：vcrpy 能在项目实际使用的 `AsyncOpenAI(..., http_client=httpx.AsyncClient())` → `AsyncOpenAI.post(..., cast_to=httpx.Response, stream=True)` → `response.aiter_bytes()` 路径上，录制后在无网络时重现一个多帧 SSE 的内容和 chunk 边界。

判定为适合的必要条件是：①录制 cassette 的解析后响应正文与真实直连消费的字节逐字节相等，保留 SSE 的 `\n\n` 分隔和三个事件；②录制和纯离线回放均保留真实直连时观察到的三个 `aiter_bytes()` chunk；③同一会话的多个端点按确定规则回放；④可去除敏感头。第②项失败，因此结论为不适合；这不是性能基准结论。

## 环境与可复现方式

PoC 代码留在一次性目录 `/tmp/vcr-poc/`，未改动被测仓库的源代码或依赖声明。使用 CPython 3.14.2、openai 3.2.0、httpx 0.28.1、vcrpy 8.3.0、pytest 9.1.1、pytest-asyncio 1.4.0、pytest-recording 0.13.4、uvicorn 0.52.3、Starlette 1.6.0。`pytest.ini` 设置 `asyncio_mode=auto`。

本地 Uvicorn SSE server 的 `/responses` 依次 yield 三个相隔 30 ms 的字节块：`response.output_item.added`（`item-added`）、`response.output_text.delta`，和 `response.output_item.done`（故意为不同的 `item-done`）。客户端不是裸 httpx 请求：它构造 `AsyncOpenAI(api_key=..., base_url=..., http_client=httpx.AsyncClient())`，再调用 SDK 的 `post`，取得 `httpx.Response` 后以 `aiter_bytes()` 消费。这与项目当前 `GhcApiClient._post_openai` 的调用形态一致，见 `src/app/ghc_client/client.py:59-73`。

执行命令及实测输出要点：

```bash
cd /tmp/vcr-poc && .venv/bin/python -m pytest -q -s test_vcrpy_sse.py test_pytest_recording.py
# ....
# 4 passed in 2.28s

cd /tmp/vcr-poc && .venv/bin/python - <<'PY'
from pathlib import Path
import yaml
from test_vcrpy_sse import EXPECTED
for name in ('sse.yaml', 'filtered-sse.yaml', 'matching.yaml'):
    obj=yaml.safe_load((Path('/tmp/vcr-poc/cassettes') / name).read_bytes())
    print(name, 'interactions=', len(obj['interactions']))
print('wire_bytes=', len(EXPECTED), 'sse_frames=', EXPECTED.count(b'event: '), 'blank_delimiters=', EXPECTED.count(b'\n\n'))
print('vcr_default_match_on=', __import__('vcr').VCR().match_on)
PY
# sse.yaml interactions= 1
# filtered-sse.yaml interactions= 1
# matching.yaml interactions= 4
# wire_bytes= 254 sse_frames= 3 blank_delimiters= 3
# vcr_default_match_on= ('method', 'scheme', 'host', 'port', 'path', 'query')
```

`254 bytes` 是本次固定 PoC SSE 载荷在上述命令、依赖版本与代码下的测量值；它由 Python 的 `len(EXPECTED)` 取得，并由 YAML 解析后的 cassette response body 与真实直连 `aiter_bytes()` 拼接字节分别比较，二者相等。该数值不是项目流量大小或吞吐量结论。

## A．能不能录

### A1．异步 SDK 请求

**能录。**录制测试在 SDK 请求返回的 `httpx.Response` 上消费 `aiter_bytes()`，生成 `cassettes/sse.yaml` 的一个 interaction。未过滤时，cassette 中确实包含 OpenAI SDK 发出的请求、URL、请求 JSON 和 `Authorization`：

```yaml
interactions:
- request:
    body: '{"input":"PoC","stream":true}'
    headers:
      authorization:
      - Bearer super-secret-token
      user-agent:
      - AsyncOpenAI/Python 3.2.0
    method: POST
    uri: http://127.0.0.1:<ephemeral-port>/responses
  response:
    body:
      string: 'event: response.output_item.added

        data: {"item":{"id":"item-added","type":"message"}}


        event: response.output_text.delta

        data: {"item_id":"item-added","delta":"hello"}


        event: response.output_item.done

        data: {"item":{"id":"item-done","type":"message"}}


        '
```

### A2．SSE 正文完整性

**正文内容能完整录下。**直连本地服务器的客户端实际收到三个 `aiter_bytes()` chunk；其拼接字节含三个 `event:` 帧、三个空行分隔和 added/done 的不同 ID。VCR 录制结果、解析 YAML 后的 `response.body.string`、以及离线回放结果都逐字节等于该直连结果。把 cassette 副本里的 `item-done` 有意改成等长的 `item-bad!` 后，字节比较立即失败，证明比较不是恒真断言。

注意：YAML 文件的引号与缩进是序列化表达，不是 wire bytes；「逐字节」比较的是 YAML 解析后的 response string `.encode()` 与真实 HTTPX 直连结果，而非把 YAML 文件本身与网络包比较。

## B．能不能放

### B3．`aiter_bytes()` 分块行为

**不能保留分块。**正控中不包 VCR 的完全相同 SDK → HTTPX 路径断言得到三个 chunk，恰为服务器依次 yield 的三个 SSE 帧。包上 `vcr.use_cassette(..., record_mode="all")` 后，录制阶段就得到一个等于三块拼接的 chunk；`record_mode="none"` 离线回放同样得到一个 chunk。cassette 只存单个 `response.body.string`，没有 chunk 边界或间隔的表示。

这是决定性阻塞项。项目 `src/app/server/pipeline_app.py:80-85` 把 `response.aiter_bytes()` 交给按块交付链；使用 vcrpy 会使录制样本无法重现真实 chunk 输入。即使上游 added/done ID 不一致仍被保存在拼接正文中，任何依赖「在哪一个 chunk 可见」的解析、buffer flush、异常或背压路径都会被合并输入改变。

### B4．离线回放

**能纯离线回放。**在录制后显式停止唯一的 Uvicorn server，记录停止前的 server hit 数，再以 `record_mode="none"` 和 `api_key="offline-not-a-credential"` 重放；请求成功、hit 数不变、正文逐字节一致。SDK 仍要求传入非空字符串 API key，因此这里使用无效占位值；没有网络、GitHub/Copilot 调用或有效凭据。

## C．实用性

### C5．请求匹配与顺序

实测 vcrpy 默认 `match_on` 为 `('method', 'scheme', 'host', 'port', 'path', 'query')`，**不含 request body 或 headers**。同一 cassette 录制 `/models`、`/token`、以及两次 body 分别为 `{"label":"first"}` 与 `{"label":"second"}` 的同一 `/ordered-responses` 请求，共四个 interaction；停止 server 后按原顺序离线重放，结果正确返回四个原始响应。

但这不是按 JSON body 正确匹配：负控在离线阶段把两次 `/ordered-responses` 的请求 body 顺序反过来，vcrpy 未报 mismatch，仍按 cassette 消费次序分别返回 `{"recorded_for":"first"}`、`{"recorded_for":"second"}`。所以它适合严格固定顺序的会话录制，不适合把同 URL 的不同请求安全地按内容区分；若仍采用它，至少需要显式加入 `body` matcher 并为并发／重试的 cassette 策略另做验证。

### C6．敏感信息

未经配置时，`Authorization: Bearer super-secret-token` 原样写入 `sse.yaml`，如 A1 片段所示。以下配置在实际异步 SSE 录制中通过：`filter_headers=["authorization"]` 从请求 cassette 删除 Authorization；`before_record_response` 删除响应的 `x-upstream-secret`。结果 `filtered-sse.yaml` 中不含这两个测试秘密：

```yaml
request:
  headers:
    accept:
    - application/json
    # 没有 authorization
response:
  headers:
    content-type:
    - text/event-stream; charset=utf-8
    # 没有 x-upstream-secret
```

这个结论仅证实本次头字段配置。它不会自动擦除 URL、请求 JSON 或 SSE `data:` 中的秘密；录制真实流前仍需为那些载体单独配置过滤／替换并审阅 cassette。

### C7．pytest-recording

**配合本身顺畅，但不解决分块问题。**`test_pytest_recording.py` 使用 `@pytest.mark.vcr(record_mode="all")`，在 `pytest-asyncio` 自动模式下通过并写出 `plugin-cassettes/test_pytest_recording_marker_records_async_openai_sse.yaml`。该 marker 路径仍观察到一个拼接后的 chunk，符合 pytest-recording 委托 vcrpy 的行为，不能作为规避 B3 的方式。

## D．建议与边界

不建议把 vcrpy／pytest-recording 接入本项目的 Responses SSE 集成测试，也不建议给出「最小接入形态」，因为它违反了此任务的核心判据。可以绕过的不是一行 VCR 配置，而是录制层：需要选择或实现一个位于 `httpx.AsyncBaseTransport`／`AsyncByteStream` 层的 recorder，录制每次实际 `aiter_bytes()` yield 的有序 byte chunk，并在 replay 时以同一 chunk 序列产生 `AsyncByteStream`。该替代路径在本 PoC 中**未实现、未验证**；其必须额外验证 chunk 边界、空 chunk／终止、错误中途发生、重试与并发请求匹配。

可保留 vcrpy 的用途仅限于不关心 HTTPX body chunk 边界的非流式请求或粗粒度 HTTP fixture，且要显式 `filter_headers`、过滤 body 中的秘密，并按需要增加 body matcher。它不能证明或回归本项目此次要防的「真实 SSE 字节分块触发的组装失败」。

## 结构怪味审视与本轮反思

- `/tmp/vcr-poc/test_vcrpy_sse.py`：没有在被测仓库引入重复实现；PoC 把 local Uvicorn server、SDK client、VCR 录制、离线 replay 和正／负控放在单个临时测试模块，处置为本轮保留，因为用户要求一次性项目且该模块是最小可复现闭环。
- `/tmp/vcr-poc/test_pytest_recording.py`：复用前一模块的 server fixture 与 SDK helper；处置为本轮保留，避免为仅一个 marker 验证复制服务器和请求栈。
- 更好的内部替代是针对项目现有 `httpx.MockTransport` 建立一个 chunk-preserving transport fixture，而不是让 VCR 做 HTTP 层全局 monkey patch；这是建议而非本轮实现。
- 判据判别力：直连三块和 VCR 一块构成正样本差异；cassette 中 ID 变异使字节比较失败，反转同 URL 请求也暴露默认 matcher 的 false-green。它没有覆盖真实 Copilot TLS、HTTP/2、压缩、超时与并发，因此这些均未能证实。
- 成熟第三方方案：本轮只实测 vcrpy／pytest-recording，不声称已比较或找到成熟的 chunk-preserving recorder；替代库／实现的可行性未能证实。

## 未能证实

未能证实真实 GitHub/Copilot 的协议行为、TLS／HTTP/2／压缩条件下的结果、真实凭据过滤、长流性能／磁盘占用、并发和重试下的 cassette 分派，或上述 chunk-preserving transport 替代方案的可行性。这些不影响本 PoC 的否定结论：本地真实异步 HTTPX SSE 已足以证明 vcrpy 改变了本项目关心的 `aiter_bytes()` 分块行为。
