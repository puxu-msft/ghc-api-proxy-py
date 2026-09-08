# Direct buffered Chat Completions：延后项

本文件只记录当前设计之外仍未闭合的事项；行为权威在同主题 [`design.md`](design.md) 引用的 living Specs。

## D-1　CodeBuddy `stream:false` capability 尚未实测

**现状**：当前streaming-only判断只来自两份参考客户端都强制streaming，以及同一实现切片的代码注释／测试；仓库已有 `exp/260904-codebuddy-provider/probe.py` P6负控，但没有运行结果。

**本次处置**：用户于2026-09-06选择暂不实测，保守把streaming-only作为带provenance的per-model endpoint compatibility capability；pipeline按capability做mode adaptation，provider不处理内容。

**重开条件**：获得真实CodeBuddy `stream:false` response。若正常返回Chat JSON，只改capability数据即可关闭adaptation；若拒绝、返回SSE或挂起，则更新provenance为真实测量。

## D-2　Translated Chat→Anthropic 多 choice 投影

**现状**：当前 `ChatCompletionsAssembler`不以choice index分槽，一份 `_text`／`_thinking` 与只按tool index键控的tool drafts会把多个choice混进一条Anthropic block序列。Direct buffered设计的新 `ChatAttemptState`会按choice index正确保存全集，但本次只允许translated assembler复用纯event reader，不改变其client projection。

**为什么本次不做**：用户要求的是direct buffered `/chat/completions` retry与其observation；translated Chat→Anthropic需要另行决定单choice选择、拒绝multi-choice或其它合法投影，任何选择都会改变另一个client leg的可观察内容。本次不从TUI“显示最小choice”的presentation规则反推delivery语义。

**重开条件**：出现translated Chat multi-choice需求或真实样本，先在所属translation Spec定义projection，再修改assembler。
