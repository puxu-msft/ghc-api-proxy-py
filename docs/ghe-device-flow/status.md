# GHE Device Flow：实施状态

**权威**：行为契约看 [spec.md](spec.md)，本文只记「做到哪儿了」。两者冲突时以 Spec 为准。

**快照时点**：2026-08-29，工作树未提交，基线 `74b9dde`。

## 已落地

| Spec 条款 | 落点 | 备注 |
|---|---|---|
| §3.1、§3.2 | `src/app/model_provider/ghc_client/config.py` | `resolve_github_web_base_url()` 与 `GhcClientConfig.github_web_base_url`；含空 label、尾斜杠、解析器自抛异常三条边界 |
| §3.3 | 同上 | 推不出来一律 `ValueError`，无回落路径 |
| §3.4 | `device_flow.py` | client_id 未动 |
| §3.5 | `src/app/cli.py` 的 `_selected_provider` / `_authenticate` | 走 `resolve_config_path` 三级发现链；provider 是必填位置参数，永不推导 |
| §3.6 | `_authenticate`、`composition.github_token_path` | token 写 `github_token_path()`，未配置时默认 `github_token-<provider>.txt`；印出绝对路径；环境变量遮蔽时出声警告 |
| §3.7 | `logout` | 与 `auth` 同一套解析与同一套告知义务；不推导 OAuth 源 |
| §3.8 | `app/config/loading.py` 的 `_rebase_configured_paths` | 配置文件里的相对路径按 config.yaml 所在目录解析；只作用于文件那一层 |
| 注入点 | `device_flow.py` | 两个硬编码 URL 拆成 `web_base_url` + 路径常量，默认仍是 `https://github.com` |

## 验证做到哪一步

- `ruff check` / `pyright` 干净；全量 `pytest` 通过。**具体数字不在本文复述**，它每次提交都会变，看当次运行输出。
- 做过控制变异，确认新测试有分辨力：把 CLI 传下去的 origin 换成常量、以及让 `DeviceFlowClient` 收下参数却不用，都能打红对应用例。
- **没有做端到端实测。** 本机无 GHE 租户，用户 2026-08-28 裁定无需验证。因此「租户下能真的登录成功」这件事**未经证实**，Spec §4 记着这一权重，不得被下游改写成「已验证」。

## 走过的弯路（留着，因为它是这一片最贵的一课）

第一版把整个能力挂在显式 `--config` 后面：不给就完全不读配置。它通过了全部门禁，也通过了我自己的两次控制变异——因为变异钉的是「origin 有没有传下去」，而那一层确实是对的。

漏掉的是**入口**：租户机器上的运营者敲的是裸 `ghc-api-proxy auth`，那条路径当时根本走不到推导函数。更糟的是 `--provider` 单独给出时被静默吞掉，照旧登录 dotcom 并覆盖默认 token 文件——正是 Spec §3.3 花整段去消灭的那个形态，被我在另一个入口上重新造了一遍。

两份独立评审各自用一手探针抓到了它（[260828-review-gpt.md](reports/260828-review-gpt.md) F-01、[260828-review-claude.md](reports/260828-review-claude.md) F1/F2/F3）。**教训不是「该多写测试」**——测试写在了正确的层上，而且有分辨力。教训是：一个守卫是否有效，问的不是「它对不对」，而是「用户实际会敲的那条命令走不走到它」。

**还有更贵的一半，是复核轮才指出来的**（[260828-review-claude-r2.md](reports/260828-review-claude-r2.md) R2-8）：第一版不是缺测试保护，而是**有一条测试在为错误的规则站岗**。旧的 `test_auth_names_the_providers_when_several_are_configured` 断言「两个 provider 时必须失败」，把我自造的「恰好一个就用它」钉成了契约。任何后来者想把 provider 选择改回 `resolve_default_name`，都会先撞红这条测试，然后很可能认为「Spec 就是这么定的」而退回去。

所以「测试有没有分辨力」与「测试钉对了东西」是两个独立问题，**控制变异只能回答前一个**。这一半更难在下次避免，因为它长得完全像「测试覆盖良好」。

## 第二轮：复核又打回来一次

两份复核合计 1 blocker、1 major、10 minor，全部采纳。两位评审在同一个问题上给出了**相反的结论**——「配置发现链这个行为变更要不要交用户裁决」，gpt 记 blocker 说要，claude 记 0 blocker 说不要（但它给的免裁决理由只覆盖其中一种情形）。本文不替裁决：Spec §3.5 已按两者的交集改写——依据换硬、把「行为不变」的断言收回并逐条列出三处确实变了的行为、把是否追认交回用户。

顺带一提，我在 §3.5 里写下的那条免裁决依据**本身是假的**，反证就在我同一次提交里新写的测试中。这与第一轮的失效同形：一句可核查的断言被核查出是假的。

## 第三轮：用户裁决又改了形态

2026-08-29 用户对四条待裁项给出裁决，其中两条改变了已实现的行为，一条是破坏性的：

- **追认**配置发现链的行为契约变更（§3.5），保持现状。
- **支持 GHES**（§3.2 第三条映射），原「本次不做」一条从 §4 删除。
- **配置里的相对路径改从 config.yaml 所在目录解析**（新增 §3.8）。这条规则的作用域超出本主题，归属见 `deferred.md` D-7。
- **provider 改为必填位置参数，默认 token 文件按 provider 命名**（§3.5、§3.6）。`resolve_default_name` 在这两条命令上的使用随之删除，「歧义」与「dangling default」两条分支一并消失。

**破坏性变更需要一次迁移**：既有部署的 token 存在 `~/.local/share/ghc-api-proxy/github_token`，改动后服务按 `github_token-<provider>.txt` 查找。失败是响亮的（首个请求 `NoGitHubToken`），迁移是一次重命名或一次重新登录。**本机存在这样一枚 token，已告知用户，未代为处理。**

这一轮也留下一条工作方式上的记录：我给出的三个选项都不是用户最终选的那个。用户给的形态（位置参数 + per-provider 文件名）比我提的任何一个都更彻底，且顺手解掉了我没意识到的一个问题——多 provider 共用一个 token 文件时，后登录的那个会静默变成两者的凭据。**选项列得再周全，也不等于把问题的解空间穷举了。**
