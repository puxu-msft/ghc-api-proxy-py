# 交付链路上的静默丢弃点：两个探针

**日期**：2026-08-22。**来源**：异源评审 `../../docs/tmp/260822-review-never-silent-failure-events.md` 的 §1（M1）与 §2（M2）。**探针原件按其落盘状态保存，未改动。**

## 回答了什么问题

用户 2026-08-22 裁决「已知不处理的路径绝不能静默，应该打日志」。主仓 `d19ae45` 只处理了三个上游失败事件；这两个探针问的是**它做对了没有**，以及**同一条链路上还有多少地方是静默的**。

| 脚本 | 问题 |
|---|---|
| `probe_failure_words.py` | `d19ae45` 的取词函数在畸形 payload 下会不会抛？在**上游真实的**事件形状下取得到词吗？ |
| `probe_other_silences.py` | 交付链路上还有哪些丢弃点，在**任何日志级别**都不产出记录？内容有没有真的丢？ |

## 结论

1. **健壮性成立**：21 组畸形 payload（`response` 不是 dict、`error` 是字符串、`code` 是数字或 `null` 等）**全部不抛**。
2. **但取词位置对我们这个上游是错的**：`error` 事件的 `code`/`message`，CAPI 把它们包在**嵌套 `error` 对象**里（官方客户端 `chatWebSocketManager.ts:124-140`），而 `d19ae45` 只读顶层扁平形。实测在真实形状上打出 `code='' message=''`——**该改动最主要的收益落空**。两种形状不冲突，修法是一行。
3. **另有 10 处静默丢弃点**，全部经正样本对照确认在任何级别都不产出日志记录。其中 **`_close` 找不到 draft 那一处已经在生产上击中过一次，导致整条回复归零**——而 `d19ae45` 所修的三个事件在 3000 万根帧里出现 **0 次**。

## 不能证明什么

- **它们不证明那 10 处会不会发生**，只证明**发生了也看不见**。频率问题需要另一种证据。
- **它们不证明第 2 条里的上游形状**。那条判据来自官方客户端源码这一**二手证据**——本仓五份 cassette 里零个失败事件，我们**没有一手录制**。嵌套形状是「参考实现这么写」，不是「我们录到过」。
- 探针 `sys.path` 硬编向隔离工作树 `260822-never-silent-upstream-failure` 的 `src`，**读的是 `d19ae45` 那一版**。该工作树被移除或分支被改写后，脚本会 import 失败或换成别的代码——它们量的是那个提交，不是「当前 main」。
- 只覆盖 assembler 与 `sse_source` 这一层；translation_driver、framer、pipeline_app 的丢弃分支不在射程内。

## 怎么重跑

```bash
python3 /home/xp/src/ghc-api-proxy-py/.dev/exp/260822-silent-drop-probes/probe_failure_words.py
python3 /home/xp/src/ghc-api-proxy-py/.dev/exp/260822-silent-drop-probes/probe_other_silences.py
```

换一棵树时改脚本顶部那行 `sys.path.insert`。两个脚本都**只读**：只 import 并喂 payload，不写任何文件、不改仓库。
