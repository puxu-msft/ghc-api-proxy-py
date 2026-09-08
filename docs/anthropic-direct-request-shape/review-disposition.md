# 实施评审的逐条处置

**对象**：[reports/260824-implementation-review.md](reports/260824-implementation-review.md)（异源模型，0 blocker / 3 major / 4 minor）。

**总处置：7 条全部采纳**，无驳回。下表记录每条改了什么、改在哪一层。`record-what-not-adopted` 在这里表现为最后一栏——ADTR-06 的**建议**没有整条采纳，只采纳了它的一半，理由写在下面。

| 编号 | 等级 | 结论 | 落在哪 |
|---|---|---|---|
| ADTR-01 | major | **采纳。** 客户端省略 `thinking` 时，配置的 effort 不上 wire——是我的 early return 越过了自己写的 Spec | Spec 新增 §4.5；`anthropic_thinking.py` 拆成 `_reshape_thinking` 与 `_attach_effort` 两段；新增两条测试（单元 + 全链路） |
| ADTR-02 | major | **采纳。** 目录只发布本地阶梯排不了序的名字时，会不发 effort 并谎报「这个模型没有发布任何 reasoning effort」 | Spec §4.2 新增规则 5 并写明两条腿兜底方向不同的理由；`align_effort` 新增该分支与两条准确的 reason；新增三条测试 |
| ADTR-03 | major | **采纳，且按它偏好的方向解。** 实现按 target format 判断而 Spec 写「直连腿」——**是 Spec 首稿写窄了，不是实现越界** | Spec 范围声明与 README 改为「所有出站目标格式为 Anthropic Messages 的请求」，并写明为什么按目标格式切而不按腿切 |
| ADTR-04 | minor | **采纳。** count_tokens 腿的刻意接线没有判别性测试 | 新增 `test_the_counting_leg_measures_the_body_that_would_actually_be_sent`，走 `handle_count_tokens` |
| ADTR-05 | minor | **采纳。** Spec A-1 把生产不可达的防御分支写成了「当前实现按透传」 | 改写 A-1；改写订阅者注释；测试改名为 `test_a_context_carrying_no_descriptor_falls_back_to_leaving_the_body_alone` 并在 docstring 里写明它只证明防御行为 |
| ADTR-06 | minor | **采纳发现，只采纳一半建议**（见下） | Spec 新增 A-6；候选片段向用户点明 |
| ADTR-07 | minor | **采纳。** module docstring 把「未配置就省略」也标成了用户裁定 | docstring 拆成两句；Spec §4.0 同样加了「以下由裁定推导、不属于它」的分界 |

## ADTR-06：为什么只采纳一半

它的发现成立：`model_thinking_effort` 与 `thinking.display` 在 `build_chain` 时被闭包捕获，改了要重启，而用户亲笔 `config.example.yaml` 的默认承诺是热重载。

它给的建议是二选一——**要么**让订阅者按请求读配置快照 / 重载时重建整个 registry，**要么**把两个 dotted path 加进 restart-only 权威表。两半都没有整条采纳，理由分别是：

- **不做请求级快照。** 同一个 `attempt.prepare` 上的 `builtin:hosted-web-search-gate` 与它的 `models_support_web_search` 是一模一样的闭包形状，而且它的注释把「绑在注册时」当作有意的设计写了下来。只给两个新键换一种时效语义，会造出「同一个 registry 里两种规则」——比缺口本身更难读，也更容易在下一个人加订阅者时被抄错。
- **不擅自往 `NOT_HOT_RELOADABLE` 加行。** 那张表的语义是「**规格**标注为需要重启的路径」。用户亲笔文档没有标注这两个键，我往里加就是替用户的文档做了一个它没做的声明。

评审自己也测到：全仓**没有任何生产代码调用 `ConfigProvider.reload()`**，热重载今天在实现上整体没接线。所以这不是本次新键的缺陷，是一处更宽的既有缺口。采纳的那一半是：**把它记下来并让用户看见**——Spec A-6 与候选片段各一处，等热重载整体接线时一并处理。

## 评审带来的、比修复本身更值钱的东西

两次变异证明我的判据当时是假绿的，这两处现在都补了测试并**重新变异确认会打红**：

| 变异 | 评审时 | 补测后 |
|---|---|---|
| 删掉 `align_effort` 的 `if desired in supported` 分支 | 21 项全绿（`xhigh`/`max` 都在本地阶梯上，`_at_or_below` 顺手给出同一个值） | `test_an_effort_name_this_proxy_cannot_rank_is_still_sent_when_published` 变红 |
| 在订阅者开头加 `if context.extras.get("counting_only"): return` | 两个测试文件 39 项全绿 | `test_the_counting_leg_measures_the_body_that_would_actually_be_sent` 变红 |

**这正是「绿灯没有分辨力」的教科书样本**：两处的断言都在跑、都在真的调用被测代码、输入也都是真的，但它们挑的输入恰好让被删掉的分支和另一条分支给出同一个答案。挑输入比写断言更决定分辨力。
