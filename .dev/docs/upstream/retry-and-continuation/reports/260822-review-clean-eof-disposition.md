# `78be0d4` 干净 EOF 细化评审的处置

**评审报告**：`260822-review-clean-eof-refinement.md`（异源评审）。**结论**：0 blocker、3 major、5 minor、6 条确认无误，`needs-fix`。
**处置日期**：2026-08-22。**处置提交**：主仓（见下）。

评审跑了 **7 次变异（6 次咬住）、10 个探针、8/8 sha256 还原复核**，且**没有在主工作树上做任何变异**——用 `git archive 78be0d4 | tar -x` 取只读副本，先验证 `app.__file__` 解析到副本再读数字。

它还先花了一整节核实**做对了的六条**，包括「先 yield 再 raise」两半都实测确认（帧确实到达客户端，调用方仍拿到异常）、`from_assembly` 身份标记无泄漏、三格穷尽且互斥、默认归上游是对的判断。

## 三条 major，全部采纳并已改

### 2.1 —— 最坏的那种失效，是我造的

**Responses 腿的 `_cut_short` 摘走草稿后 `_drafts` 就空了**，于是上游明说 `status:"incomplete"` 的流被 `cut_mid_block` 读成「块边界」，走进干净收尾，**那半个块被静默丢弃**——改动前它是一条 error 帧。

**从「响亮的截断」退化成「安静的丢内容」，是所有失败模式里最难被发现的一种。** 两条腿的 `_drafts` 生命周期本就不同：Anthropic 腿 `content_block_stop` 关块即交付，「块关了但没交付」这个中间态不存在；Responses 腿存在，而我的判据看不见它。

改法照评审建议：`bool(self._drafts) or self._cut_short is not None`。不动 `_cut_short` 的持有语义（那是另一条已裁决的规则）。

### 2.2 —— 一个观测被一个合成覆盖掉

`replace(terminal, stop_reason=settings.unterminated_stop_reason)` 是**无条件**覆盖。Anthropic 腿把结局拆成两半（`message_delta` 带原因、`message_stop` 只负责关闭），丢了后半的流其实已经说过为什么停。实测：上游明说 `max_tokens`，客户端被告知 `incomplete`。

**而同一棵树的调用方给出相反裁决**：`inference.py` 对「`terminal.stop_reason` 有值」的流不做覆写，于是同一次回合**日志说 `ok / max_tokens`、客户端收到 `incomplete`**。一个提交的两半对同一事实给出两个答案。

改法一行：`terminal.stop_reason or settings.unterminated_stop_reason`。既保住「不得静默变成 `end_turn`」，又让上游真说过的话优先。**同伴分支正是这么裁的**，所以这一行同时消解了与他们的一处分歧。

### 2.3 —— 唯一会真正触发的那条腿，一个测试都没有

评审做了双向常量变异：Responses 腿的 `cut_mid_block` 改成 `True` 和改成 `False`，全量套件**两个方向都零红**。而证据报告实测的 4 条块边界命中**全部在这条腿**（Anthropic 腿 32/32 全在块中途）。即：**这条细化唯一的真实触发面，判据有洞而且没有测试。**

已补两条 Responses 腿测试，其中一条专走 `_cut_short`。变异复核：把 2.1 的修法退回原样，只红那一条。

## usage 那条：评审的判断比我的强，按它改

我登记的是「把没测过写成了零，是本仓同一形状的第四次」。评审复核后**收窄了它**，理由按权重排：

1. **协议把 `output_tokens` 定成必填**（anthropic SDK 1.0.0，`MessageDeltaUsage.output_tokens` 无默认），零是唯一合法占位——「诚实」在这条线上**没有合法拼写**，省略是把记录问题换成协议违规。
2. 那条判据保护的资产是**我们自己的记录**，而这条链路上本方记录是干净的：`Terminal.usage` 保持 `{}` 不是零，`request_log` 用 `in` 判断。**这是它与另外三例的实质差别**——那三例污染的都是本方记录。
3. 想「不说谎」的操作员已有出口：配置留空 → 回到 error 帧，根本不发 `message_delta`。

**所以改的是可见性不是 wire**：把 `or {"output_tokens": 0}` 从 `terminal_frames` 的默认参数提到两个调用点，与它上面那行 `or "end_turn"` 一样显式，并把「协议不接受缺席」写进注释。`terminal_frames` 的 `usage` 参数改成必填，好让下一个调用方**必须说出它放的是什么**，而不是从签名里继承一个零。

**我先前在 `deferred.md` §5之二 的登记过头了**，已按此更正。

## 五条 minor

| 发现 | 处置 |
|---|---|
| **3.2** 新加的 `assert '"stop_reason":"end_turn"' not in body` **恒真**——只发一条 `message_delta`、只有一个 `stop_reason`，前一条断言通过即严格蕴含它。而提交信息说这条不变量「is asserted rather than described」，**它在实践中从未独立击发过** | 改成解析载荷后对 `delta.stop_reason` 做**等值**断言，一条同时钉死两个方向 |
| **3.1** framer 抛错与本方 attempt deadline 都被归到上游；后者与 `ClientDeadlineError` 归 INTERNAL 不一致（两个都是本方的时钟） | 登记，不改。前者提交注释已自认是 known limit；后者改动会与同伴分支的裁决交叉，留给合并时一并处理 |
| **3.3** `SlowAssembler.cut_mid_block` 是硬编码 `False` 的桩，将来某个测试恰好走到收尾分支会给出形状正确的假结果 | 登记。今天不触发 |
| **3.4** 新配置项没进 `config.example.yaml` | 该文件用户亲笔，不归我改。候选材料已写（supplements §九） |
| **3.5** 两条腿对同一个「没测过」口径不同（Responses 落 `null`，Anthropic 伪造零） | 登记，**并写进代码注释**，说明这个不对称是有原因的、不要将来被当成 bug 顺手「修齐」 |

## 一条我自己在处置中发现的

修完 2.2 之后重跑变异，**M9 没红**——我改了代码却没给它测试，评审是靠探针发现的缺陷。补测试时第一版夹具又挑错了值（用 `end_turn`，而它恰好与成帧器的兜底同值，**分辨不出 passthrough 与巧合**），换成 `max_tokens` 才有鉴别力。

## 未采纳

无。三条 major、五条 minor 全部处置：五条改代码或测试，两条登记（3.1 的一半、3.3），一条走候选材料（3.4）。

## 代价与收益（评审 §8，与证据报告合读）

这条细化改变的是 133 929 条流里的 4 条（0.003%）。**它不是止血。** 保留的理由是把「说完了」与「被切断了」分成两件事，而不是命中率——而 2.1 恰好说明，这个区分做不干净时会比不做更糟。
