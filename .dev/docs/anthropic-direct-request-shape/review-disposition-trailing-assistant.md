# 尾随 assistant 守卫：评审的逐条处置

**对象**：[reports/260824-trailing-assistant-review.md](reports/260824-trailing-assistant-review.md)（异源模型，0 blocker / 2 major / 3 minor）。

**总处置：5 条全部采纳**，无驳回。评审自己也**驳回了我提出的一个问题**（要不要给合成文本加配置开关），我接受它的驳回，理由见末节。

| 编号 | 等级 | 结论 | 落在哪 |
|---|---|---|---|
| ATRA-01 | major | **采纳。** 判别器读 `original_payload["messages"]`，而 `/responses` 的原件里根本没有 `messages` 键——读不出来被当成「不是客户端写的」，于是在客户端确实自己以 assistant 结尾的路径上塞进了一句它没写过的话 | 判据改为**只有正面读到「客户端末尾是 user」才追加**；Spec 新增 §6.5 与 A-7 把留下的缺口写明；新增 `test_a_body_this_cannot_compare_is_never_given_synthetic_text` |
| ATRA-02 | major | **采纳。我写的全称是错的，而反例就在本仓库里。** `exp/260820-empty-text-probe/` 的 F4 与 F6 早已实测：末轮与中间位置的 `assistant content: []` 都是 200 | 判据加上「内容非空」；Spec §6.1 改写并写明这是两个正例被第三个既有反例证否；新增 `test_an_emptied_assistant_tail_is_left_alone` |
| ATRA-03 | minor | **采纳。** 判别器依赖 `build_context` 的深拷贝，而所有测试都自己造好两份副本，把 `deepcopy` 换成浅拷贝仍全绿 | 新增 `test_the_production_context_builder_keeps_the_original_readable`，经真实 `route_for_path` + `build_context` 入口 |
| ATRA-04 | minor | **采纳。** 插入 §6 后三处 `§7` 引用没同步 | Spec 两处、候选一处改为 `§8`；逐条核对了**该保持 §7 的那两处**（A-2、A-4 指的是「不做什么」，本就正确，没动） |
| ATRA-05 | minor | **采纳。** Spec §2.5 带了限定，供用户摘取的候选转述把限定丢了 | 候选原地补齐模型名、非流式、每格一次调用，并写明「200 只说明收下了，不说明照做了」与「射程仅限已测路径」 |

## 我提出、评审驳回的一条

我在派发时问：合成文本 `Please continue.` 会进入模型上下文，要不要换更中性的词、或加配置开关？

**评审判断不要，我接受。** 它的理由站得住：空白内容会被上游拒绝，所以合成内容必须非空；`Please continue.` 是对「继续生成」最窄的自然语言表达，没有额外任务语义，且与第一方 `messagesApi.ts` 的出货选择一致；加开关会把一个协议正确性问题变成运维偏好，而没有任何具体失败面支撑它。真正该收紧的是**触发谓词**，那正是 ATRA-01/02 干的事。

这条记下来是因为它是一次**问对了地方、答案却是「不要动」**的判断——不记的话，下一个人会把同一个疑虑再提一遍。

## 变异记录

评审做了两次，我在采纳后又做了两次验证新判据的：

| 变异 | 谁做的 | 预期 | 实际 |
|---|---|---|---|
| `build_context` 的 `deepcopy(dict(payload))` 改成 `dict(payload)` | 评审 | 若测试锁住了判别器依赖的嵌套隔离，应红 | **30 项全绿——假绿**，形成 ATRA-03。补测后此 seam 有了覆盖 |
| 合成 turn 的 role 从 `user` 改成 `assistant` | 评审 | anchor、count、幂等应红 | 8 项中 4 红，符合预期 |
| `_is_empty_content` 恒返回 False | 我 | 空内容 assistant 尾轮那条应红 | 变红 1 条，且只有那一条。已还原 |
| `if client_tail != "user"` 改回宽松的 `== "assistant"` | 我 | 「读不出原件就不追加」那条应红 | 变红 1 条，且只有那一条。已还原 |

## 这一轮最值得留下的一句

**两个正例不构成全称，而证否它的那个反例就躺在本仓库里。** 我拿两条实测的 400（非空 content 的 prefill）写下了「不得以 assistant 结尾」，而 `exp/260820-empty-text-probe/` 里 F4/F6 两条 200 早就说明角色不是充分判据。写守卫时我去测了新的东西，却没有回头查本仓已有的证据——**新证据的成本高，旧证据的成本近乎零，而我先花了贵的那份。**
