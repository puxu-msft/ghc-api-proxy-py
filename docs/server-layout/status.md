# `app.server` 布局：实施状态

**这份是活文档**，答「现在实际是什么样」。设计与当时的分析在 [README.md](README.md)（那份是提案时点的记录，其第 11 节的能力边界只对提案当时成立）；三条用户裁决在 [decisions.md](decisions.md)，冲突时以 decisions 为准。

**第二轮（步骤 3～5 之后）的支撑分析**，同样是点时点记录：[模块职责与依赖方向](reports/260822-app-server-structure-deps.md)、[死代码与文档漂移审计](reports/260822-app-server-dead-and-drift.md)、[两个大模块的内聚性](reports/260822-large-modules-after-step5.md)。

**最后更新**：2026-08-22 会话收尾。**基线**：主仓 `main` 当时为 `8a47534`（同伴随后仍在推进）。⚠️ 同伴在此期间 rebase 过 `main`，所以早先文档里引用的部分 SHA 已失效；下表是重新核对过的当前值。

## 六步：全部落地

| 步 | 内容 | 当前 SHA | 备注 |
|---|---|---|---|
| 1 | `server/tls.py` → `lifecycle/tls.py` | `928b355` | 重命名相似度 100% |
| 0 | `Chain` 记录 → `core/chain.py`，建造者留在 `composition` | `c170f0f` | 实测：只需该类型的代码不再拖进 23 个模块，含 `app.server` 本身（106 → 83） |
| 2 | 可观测性移出 `pipeline_app` → `observability/request_trace.py` | `28c1a7a` | ⚠️ 该提交的信息有 8 处符号名被 shell 反引号吃空，已无法 amend，见下 |
| 3 | `handler.py` 溶解为四个模块并删除原文件 | `1b34815` | `driver` / `delivery_policy` / `reply` / `server.http_errors`；分层 `routing ← driver ← delivery_policy ← reply`，经查无环 |
| 4 | 续写决策移出 HTTP 表面 → `pipeline/hand_over.py` | `b973ed0` | 流式分支的 181 行**有意未动**，见「门控」 |
| 5a | 重复的链访问器收成 `server/app_state.py` | `c01191f` | `CHAIN_STATE_KEY` 与访问器原本在两处各定义一份 |
| 5b | 建成追认路径 `app.server.routes` | `ef4defb` | `table` / `inference` / `ops` / `router`；`__init__` 保持零 import 以免包内成环 |
| 6 | 旧链移出标准源码位置 → `src/.archived/` | `2248a69` | **用户 2026-08-22 追加裁决**，取代 decisions.md 的 D-3 顺序（原为「先接新链再删」） |

`src/app/server/pipeline_app.py`：**1037 行 → 86 行**。`src/app` 被跟踪的 `.py`：**247 → 169**。

**这几个数怎么复现**：跑出它们的脚本原件在 [probes/](probes/)，那份 README 逐个说明测什么、当前复现值、正样本对照、以及各自不能证明什么。最有说服力的不是 83 这个数，而是它的对照——`import app.server` 现在只拉进 1 个模块（它自己）。注意 `sets.py` 已随第 6 步自我失效（它 import 的 `app.server.app_factory` 正是被归档的入口），README 给了回到 `2248a69^` 复现的方法。

## 第 6 步的实际范围

77 个源文件入 `src/.archived/`、48 个测试入 `tests/.archived/`（移了 49、取回 1，见下）。判据是机械的：从 `app.server.app_factory` 可达且从 `app.cli` 不可达，加上「整个顶层包没有一个模块活链可达」。做过反向自检（无活模块被卷走）与正向自检（剩余 169 个模块逐个 import 成功）。

**空目录一并删除**，因为一个只剩 `__pycache__` 的包目录仍是 PEP 420 命名空间包，`import app.routes` 照样成功并返回空模块——实测确认。`tests/unit/test_module_boundaries.py` 已改为断言归档名**不可解析**，比原先「新链没 import 旧链」更强，且不因有人复制回来而失效。

工具链：pytest 不递归点目录、pyright 默认排除 `**/.*`、**ruff 不排除**（已在 `pyproject.toml` 显式写明）。构建实测 wheel 174 个条目、不含 archived，正样本对照确认 `app/cli.py` 在内。

## 仍然门控、有意未做

- **流式字节记账**（`_StreamAccounting`、`_AccountedStreamingResponse`、`_counted_upstream`、`_tracked_delivery`，约 135 行）仍在 `server/routes/inference.py`。落点是 `pipeline/delivery/`，**排在 STR-04 切片之后**：`_AccountedStreamingResponse` 是 response body 的 close owner，撞 `architecture.md:340`，真正压住它的三条在 `spec.md`（2026-08-19 授权明文不覆盖该文档），且 `implementation.md:268` 已把邻近问题推迟到该切片。依据见 [reports/260822-architecture-constraints-readthrough.md](reports/260822-architecture-constraints-readthrough.md)。
- **`RequestTrace` 与 `RequestLine` 之间的 31 字段手抄**。第 2 步已把两者放进同一个包，消掉它现在是局部改动。
- **`Chain` 是否该出现在 driver 签名里**。设计评审提出、明确不在本次解决：`Chain` 是组装根的产物，而 `architecture.md` 要求 driver 读 typed facts。第 0 步只把它从 `app.server` 挪走，没有改签名。

## 已知的债与遗留

- **`28c1a7a` 的提交信息残缺**：8 处反引号包裹的符号名被 shell 当命令替换吃空。发现时同伴已在其上提交，无法 amend；为一条信息改写同伴正在推进的分支不成比例。内容与验证无误。教训已入项目记忆。
- **历史里有两个同名的归档提交，其中一个是空的**：`git log --oneline | rg 'move the chain no entry point reaches'` 返回 **`2248a69`** 与 **`f7121ca`** 两条。带内容的是 `2248a69`（130 个文件），`f7121ca` 相对其父 `123f03d` **变更文件数为 0**——是同伴 rebase 时留下的空提交。**按信息文本找这次归档会命中两个，且先到的那个（`f7121ca`，19:16）是错的那个。** 认准 `2248a69`；用 `git show --stat` 一眼可分（空的那个 stat 为空）。
- **一个测试丢了一半**：`tests/systemd/test_systemd_units.py::test_service_permissions_restrict_real_state_writers` 原本同时断言 `history.db` 与 `tokenization.json` 的权限位；history writer 随链归档，保留了 tokenization 那一半，docstring 写明去向。该文件整体**未**归档——它是 systemd 部署路径的测试，且 `test_systemd_pipeline_unit.py` 从它取共享夹具。
- **`api.md` 追认但无人服务的端点**：~~Azure、Gemini、`/history/api/*`、`/history/ws`、`/api/status`、`/api/config`~~ → **2026-08-23 收窄为四个：Azure、Gemini、`/history/api/*`、`/history/ws`**。同伴的 `7525f76`（`feat: answer the ratified status and config endpoints on the new chain`）已把 `/api/status` 与 `/api/config` 接到新链，现在活在 `src/app/server/routes/ops.py:30` 与 `:88`。剩下四个的唯一实现仍在 `src/.archived/`。这在归档之前就已成立（那条链本就不可达），归档只是让它从潜伏变为可读。`src/.archived/README.md` 记录了这一点，以及 `management.py` 混装已追认与已裁决暂不支持端点、不能整体搬也不能整体删的障碍。

  **归档前排除过一条反对意见，值得留档**：一位事实核查评审主张「前身 `copilot-api-js` 仍在 `4141` 上服务这些端点」，据此反对归档。**该主张被进程表推翻**——`ss -ltnp` 与 `ps -eo pid,lstart,args` 显示 `4141` 由本项目占用（`uv run --directory /home/xp/src/ghc-api-proxy-py ghc-api-proxy start --port 4141 --restart`），两次观测分别是 pid 2254087（08-22 11:45:40）与 pid 3733161（08-23 06:06:51，会话期间被重启过，非本会话所为）。**这个观测能支持的只有一件事：那位评审所设想的「另一个进程正在服务这些端点」不成立，因此归档不会让任何在跑的东西失去实现。** 它**不**证明生产切换已获授权或已完成——按项目约束，替换前身需要用户单独的明确指令，本会话全程未信号、停止或重启该服务，只做了读取。
- **`spec.md` 与 `acceptance.md` 的跟进**：D-1 裁决后 `spec.md` 四处规范条款已改，但 `acceptance.md` 的 `CAL-04-GRAMMAR-v1` 只做了推翻标注、未升版，`architecture.md` 的 delayed-response-start owner 一族也只登记未改。两者都在 `spec.md`「文档状态」与本表登记，属独立切片。

## 验证（2026-08-23 06:4x，主仓 `79428bb`）

⚠️ **归因前提**：跑这轮时工作树带着同伴 7 个未提交文件（`request.py`、`inbound.py`、`routes/*`、两个测试），所以结果反映的是「HEAD 加同伴中途状态」，不是一个干净检出。

| 项 | 结果 |
|---|---|
| `uv run pytest tests --cov=app --cov-fail-under=80` | **1494 passed, 2 skipped**，覆盖率 **89.53%** |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_module_boundaries.py` | 3 passed（归档不可解析的守卫） |
| `uv run pyright src tests` | **21 errors**，全部在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py` |

那 21 个 pyright 错误**不属于本主题**：两个文件本会话一次都没碰过，最近提交是 08-21（`2b20be7`、`8703cad`，早于本会话开始的 08-22 14:40），属同伴的 httpx2／httpcore2 迁移，与归档链不相交。

**ruff 那一行需要一个正样本对照才读得出来**：`ruff check src tests` 全过，可能是因为 `extend-exclude` 生效，也可能是因为别的原因导致那些文件根本没被考察。显式指定 `ruff check --statistics src/.archived` 报 **32 个 I001**——归档文件确实有问题而常规扫描不报，这才证明排除是真的在起作用。

## 未采纳的方案（记录理由）

- **`pipeline/delivery/selection.py`** 作为选帧／选装配器的家：**否决**。`src/app/pipeline/request.py:17` 就 import `delivery.assembling`，delivery 在图上位于 `RequestContext` 之下，放进去就是把分层倒过来。落点改为与 `routing.py` 平级的 `delivery_policy.py`。
- **新增顶层 `app/chain.py` + `app/composition/`**：**否决**，因为它自身就是本文档第 3.4 节当作缺陷来数的那种「顶层包不在追认清单里」。改用追认过的 `core`（其 `__init__.py` 自述正是这条论证）。
- **方案 3「只改文档与命名」**：未采纳，但对它的反对理由被修正过一次——原理由「记录下来的现状没人回头看」被本主题自己的触发来源证伪（正是读 `server/__init__.py` 的 docstring 才发现整件事）。
