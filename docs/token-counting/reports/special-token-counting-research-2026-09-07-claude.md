# Special-token spelling count failure investigation

状态：point-in-time investigation，2026-09-07。

## 事故输入与结果

用户报告`POST /v1/messages/count_tokens`在`opus → gpt-5.6-sol`路由上返回500，异常为`tiktoken`拒绝字面`<|endoftext|>`。本轮用生产ASGI入口和mock provider复现同一故障：`gpt-model`翻译到OpenAI Responses后返回500，`claude-model`配置local-only后也返回500；两次`upstream_calls`均为0。此观察强到足以判定故障发生在provider dispatch之前，并排除具体远端provider响应为本次500的原因。

运行环境为锁文件中的`tiktoken 0.14.0`。`o200k_base.encode("before <|endoftext|> after")`稳定抛出`ValueError: Encountered text corresponding to disallowed special token '<|endoftext|>'`。同一encoding的`encode_ordinary(text)`与`encode(text, disallowed_special=())`产生完全相同的token序列，且`decode()`逐字恢复原文；该观察足以证明本地ordinary-text机制可以无损接收此输入，但不能证明估算等于任一provider的真实账单token数。

## 根因链

1. `src/app/server/routes/inference.py`把count请求交给`handle_count_tokens()`。
2. `src/app/pipeline/driver.py`在任何provider leg前无条件执行`chain.local_token_worker.estimate(protocol, context.payload)`，因此即使remote counter排在local之前，local estimator异常也会先终止请求。
3. `src/app/tokenization/worker.py`在worker process中调用`estimate_anthropic_input()`或`estimate_responses_input()`，并把估算异常原样送回parent。
4. `src/app/tokenization/estimators.py`对system／instructions、message content、tool JSON与Responses item text调用`Encoding.encode()`且不传special-token选项。`tiktoken`默认把encoding已注册的special-token spelling列入`disallowed_special="all"`，所以客户端普通字符串一旦逐字含`<|endoftext|>`或`<|endofprompt|>`就抛异常。
5. 异常经count chain变成所有counter失败或直接内部失败，并最终映射为HTTP 500。请求没有违反Anthropic Messages body schema，也没有给special spelling任何控制语义；首个可控偏差因此是estimator选择了会拒绝ordinary input的encoding API，而不是HTTP错误映射。

根因结论的权重是“强到足以直接实施”：移除默认special-token guard会消除两个协议目标上的同一故障；恢复默认`encode()`会稳定复现。数值精度仍只是local estimate的既有边界，不由这次输入接收修复改变。

## 同仓库正常模式

`src/app/tokenization/admission.py::_count_ordinary()`已经用`encoding.encode_ordinary(text)`处理独立文本字段，明确表达“输入是ordinary text，不从字符串内容获得控制token语义”。这为修复提供了同依赖、同仓库、已运行的对照模式；不需要在HTTP边界新增异常分支。

## 最小修复边界

- 在`src/app/tokenization/estimators.py`集中使用ordinary-text token count，并替换Anthropic与Responses estimator的全部`tiktoken`文本编码调用。
- 生产ASGI回归覆盖Anthropic local和Responses local两个目标，输入含用户报告的字面`<|endoftext|>`，断言完整成功对象和零upstream调用。
- Unit回归覆盖system／instructions、message与tool JSON，避免只修触发日志里的message路径。
- 现有worker metrics测试不能继续用special-token spelling制造“真实编码失败”；它应改用显式synthetic failure，继续保护failure timing传播，而另设ordinary-text成功断言保护本次修复。

## 被否路线

- `allowed_special={"<|endoftext|>"}`：否决。它把客户端普通字符序列解释为一个控制token，改变输入语义和token数；请求并没有越过允许控制token的类型边界。
- 仅从`disallowed_special`集合移除`<|endoftext|>`：否决。`o200k_base`当前还有`<|endofprompt|>`，未来configured tokenizer也可增加其它special spelling；逐个放行会把同一根因留给下一种字面串。
- HTTP endpoint捕获`ValueError`并fallback或返回默认数：否决。两种local estimator都受影响，endpoint没有第二个可用estimate；吞掉异常会伪造成功或把根因藏在终端症状后。
- 只修Responses：否决。生产入口已复现Anthropic local-only同样500，且两条路径共享错误API选择。
- 保留`test_real_worker_keeps_encoding_failure_and_stage_metrics`对special spelling必须失败的断言：否决。该断言只为metrics failure path寻找了一个方便触发器，却把产品缺陷钉成预期行为；应改为synthetic estimator failure并把special spelling转成成功回归。
- 继续直接调用`encode(..., disallowed_special=())`：可行但未采用。实测与`encode_ordinary()`等价；采用后者是因为名称直接陈述合同，而且同仓库`admission.py`已有该模式。若未来需要`allowed_special`的控制语义，必须由typed boundary另行显式建模，不能从客户端字符串猜。

## 尚未声称

本报告没有声称local tiktoken estimate等于Claude或OpenAI模型的真实token usage，也没有执行live upstream。Mock ASGI只证明本代理的失败位置、错误投影和修复后应保持的公开wire；真实provider计费精度由living token-counting Spec的学习机制另行负责。
