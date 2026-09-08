# Token-counting user-ruling source research coordinator checklist

性质：finding 03的一手来源取证清单，不是用户裁决本身，也不替代living Spec或review disposition。

## 待核命题

- R1．Spec §2.2的四句文字是否能在`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/`下某个主会话transcript中定位到真实用户消息。
- R2．候选记录必须是JSONL中`message.role == "user"`的自然语言内容；排除`tool_result`、system-reminder、task-notification、agent-message、cross-session-message、subagent派活prompt以及assistant对用户意图的转述。
- R3．若原始用户措辞与Spec中的“用户于某日选择／随后明确”并非逐字相同，应分别记录原文、Spec转录、差异及言语行为，不能把实施者前缀冒充用户原话。
- R4．每项来源锚至少包含transcript绝对路径、稳定message UUID或等价记录键、timestamp，以及足以辨认scope的完整用户段落；行号只能辅助。
- R5．若只找到agent／tool转述而没有真实user record，结论只能是“在已扫描范围未找到可独立解析的一手锚”，不能升级成“用户从未作出裁决”。

## 搜索范围与方法要求

1. 枚举项目transcript根下所有JSONL，但把主会话和`subagents/`分开统计；先从主会话真实user message中搜索，再将subagent命中只作排除证据。
2. 用JSON parser读取记录，不用纯`rg`命中整行，因为tool result会嵌入完整Spec并制造大量同源假命中。
3. 同时搜索精确短语和语义关键词：`opaque reasoning`、`低置信estimate`、`cold-start`、`exact／prefix／profile`、`具体学习过程不再逐项询问`、`不再逐项询问`、`由实现者闭合`。
4. 对任何候选读取完整user message；不能只复制命中行或截断转折后的限定。
5. 报告必须声明扫描到的主会话文件数、真实user text message数、subagent文件数、命中数和无法解析的记录数，使“未找到”的分母可重查。

## 结果分流

- 四项均有可解析一手锚：finding 03的事实缺口可由文档owner补锚闭合，但“逐字”仍要按原文差异判断。
- 部分有锚：有锚项保留其实际来源强度；无锚项降级或请求用户重裁，不能把四项整体写成同一来源强度。
- 全部无锚：finding 03维持major；不得由agent转述替代用户授权。
