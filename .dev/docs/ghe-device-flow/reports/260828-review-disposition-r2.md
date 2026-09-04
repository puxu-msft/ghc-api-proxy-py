# 第二轮复核的处置记录

对象：[260828-review-gpt-r2.md](260828-review-gpt-r2.md)（1 blocker / 0 major / 3 minor）与 [260828-review-claude-r2.md](260828-review-claude-r2.md)（0 blocker / 1 major / 7 minor）。

第一轮的处置见 [260828-review-disposition.md](260828-review-disposition.md)，**其中一句已被本轮推翻**，那里已加更正指引。

**除 D-6（交用户裁决）外全部采纳。** 另有三条被识别为规范取舍、登记进 `deferred.md` 而非本次代定。

## 两位评审在同一个问题上给出相反结论，我怎么处理的

**问题**：`auth` / `logout` 改走配置发现链，是不是一次需要用户追认的行为契约变更？

- **gpt R2-01 记 blocker**：是。它列了五类反例，证明我那句「逐字不变」是全称命题而只有窄命题成立；Spec 正文自己都列了两处行为变化，与该断言直接冲突。
- **claude R2-1 记 major、blocker 0**：结论（不需要裁决）成立，但我写的依据是假的，应换成——同一配置状态下 `build_chain` 也抛同一个异常，所以那里不存在能被弄坏的、正在工作的部署。

**我的处理**：取两者的交集，不选边。

1. **依据换硬**：采纳 claude 给的 `build_chain` 论证，它比我原来那条强，因为不依赖「那个状态可不可达」。
2. **断言收回**：我原来那句「永远解析得出一个名字」确实是假的——反证就在我同一次提交里新写的测试 `test_auth_refuses_an_open_choice_and_a_dangling_default` 走的那条路上。已从 Spec 删除并登记进修订记录 R3。
3. **裁决交回用户**：claude 的免裁决理由只覆盖「provider 歧义」这一种情形，**不覆盖** gpt 列的其余几类（本地 stand-in 从登录 dotcom 变成 exit 1、`start --config` 与发现链指向不同文件）。这两类里确实存在原本能跑的部署。因此我按 gpt 的分流办：Spec §3.5 逐条列出三处确实变了的行为，并声明是否追认属用户裁决范围。条目 [deferred.md](../deferred.md) D-6。

**实测降低了这条的现实风险**：本机 `~/.local/share/ghc-api-proxy/config.yaml` 不含 `model_providers` 段，`GHC_API_PROXY_CONFIG` 与 `GHC_API_PROXY_GITHUB_TOKEN` 均未设置，裸 `auth` 的解析结果与改动前逐字相同。所以这是契约问题，不是故障。

## 逐条处置

| 编号 | 严重级 | 处置 | 落点 |
|---|---|---|---|
| gpt R2-01 | blocker | **部分采纳**：假断言删除、行为变更逐条列出、裁决交回用户；但**不**退回显式 `--config` 那道门（两位评审的产品倾向一致，且退回会让功能在其自然入口再次不可达） | [spec.md](../spec.md) §3.5；[deferred.md](../deferred.md) D-6 |
| claude R2-1 | major | **采纳**，依据换成 `build_chain` 那条 | [spec.md](../spec.md) §3.5 与修订记录 R3 |
| gpt R2-02 | minor | **采纳，且改法比它建议的更彻底**：不是逐个补空 userinfo／空 query／空 port 的判据，而是把整段前置校验换成「输入必须逐字等于它重建出的裸 origin」。一次比对覆盖全部字段与所有空分隔符，且不会被没人想到枚举的成分绕过 | `config.py`；[spec.md](../spec.md) §3.2 |
| gpt R2-03 | minor | **采纳**。`_read_config` 改接 `ValueError`——pydantic 的 `ValidationError` 与 `UnicodeDecodeError` 都是它的子类，loader 自己那条「must contain a mapping」也是 | `cli.py` `_read_config` |
| gpt R2-04 / claude R2-5 | minor | **采纳**（两份独立报出同一条）。§3.3 收窄为只影响 `auth`；§3.7 明写 `logout` 不推导 origin 且说明理由；`config.py` docstring 同步 | [spec.md](../spec.md) §3.3、§3.7 |
| claude R2-2 | minor | **采纳**。`logout` 同样在环境变量遮蔽时警告 | `cli.py`；[spec.md](../spec.md) §3.7 |
| claude R2-3 | minor | **采纳可观测那一半**：`auth` 印出实际写入的绝对路径。**「必须绝对路径」是规范取舍，不代定** | `cli.py`；[deferred.md](../deferred.md) D-4 |
| claude R2-4 | minor | **采纳**。「只查环境变量」成立的真正理由（`build_github_token_source` 把 CLI 级硬编码成 `CLITokenProvider(None)`、`--github-token` 在失效选项表里）写进 §3.6，并注明该前提一旦改变本检查须同步扩展 | [spec.md](../spec.md) §3.6；`cli.py` 的 `_warn_if_environment_shadows_the_token_file` docstring |
| claude R2-6 | minor | **采纳**。§3.5 的行为变更清单补第三条 | [spec.md](../spec.md) §3.5 |
| claude R2-7 | minor | **采纳可观测那一半**：`logout` 印出实际删除的路径。**「是否清全部 provider」是行为取舍，不代定** | `cli.py`；[deferred.md](../deferred.md) D-5 |
| claude R2-8 | minor | **采纳**。`status.md` 补上漏掉的那一半教训：第一版不是缺测试，是有一条测试在为错误规则站岗 | [status.md](../status.md) |

## 一条我做得比评审建议更远，说明理由

gpt R2-02 建议「按 netloc 里有没有 userinfo 分隔符检查存在性，并补空 username／空 password 的负例」，并提到空 query／fragment／port 分隔符也该在同一次判定里明确。

我没有逐个补判据，而是把整段前置校验换成一次整串比对。理由：逐字段枚举正是这条 bug 的成因——它要求实现者把 URL 的每一种成分都想到，而漏掉一种就是一个静默放行。整串比对反过来问「这是不是一个裸 origin」，默认拒绝一切没被明确允许的形态，因此不会有「下一个没想到的成分」。

## 重新验证

- `ruff check` / `pyright` 干净；全量 `pytest` 1926 passed / 2 skipped，覆盖率 90.71%。
- 两次**本轮新的**控制变异，钉的是本轮真正变了的两条判据：
  - 整串比对退回逐字段真假判断 → `test_config.py` **5 条**红（两种空 userinfo、空 query、空 fragment、空 port 分隔符）。
  - `_read_config` 退回只接 `ValidationError` → `test_cli.py` 1 条红（YAML 根为 list 时打出 traceback）。
- 两次均按快照还原并核对 SHA-256 一致。
- 前两轮的四次变异仍然成立，未重做。

## 未做的独立复核，如实声明

claude 那位在本轮明确声明**没有读过 gpt 的报告原文**，只按我的转述采信。所以 gpt 那三条发现**没有经过第三方独立复核**，只有我自己的一手复现（三条我都跑过探针）。若需要，那是一次单独的派发。
