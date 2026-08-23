# 复现探针：`app.server` 布局六步的那几个数字

status.md 里写着 106 → 83、247 → 169、77 + 48 这些数，但只写了「实测」。这个目录放的是**实际跑出那些数的脚本原件**，从会话临时目录逐字复制过来，一个字没改。留脚本而弃派生数据（`sets.json`、399K 的 wheel、几份模块集合 JSON）是有意的：脚本三五百字节，而数据是它们的输出。

**但「脚本在就一定能再生成」这句要打个折**，独立评审指出得对：`reach.py`／`count.py`／`importable.py` 在当前树上照跑无碍，**`sets.py` 不行**——它 import 的入口已随第 6 步归档，得先回到 `2248a69^` 的检出（方法见下面它自己那一节）。所以它那八份输出**在当前树上不可再生**，只是复现路径仍然存在且今天仍走得通。

**基线**：脚本产出于 2026-08-22 的六步实施期间。下表「当前复现值」一栏是 2026-08-23 06:35 在主仓 `7525f76`（工作树另有同伴未提交改动）上重跑的结果。

**统一跑法**（`--no-project` 是必要的，否则 uv 会去解析主仓的 `pyproject.toml` 并可能装出另一棵树）：

```bash
cd /home/xp/src/ghc-api-proxy-py
PYTHONPATH=src uv run --no-project python .dev/docs/server-layout/probes/<脚本> [参数]
```

**先跑正样本对照，再读任何数字**——本会话有三次探测给出了形状正确的假数字，三次都差点被当成结果读走，而且**三次的机制各不相同**：

1. **调用方把非零退出码吞成空列表。** 探针写的是 `mods = json.loads(out.stdout...) if out.returncode == 0 else []`，子进程因缺依赖直接抛异常、rc≠0，兜底把失败静默换成 `[]`，于是输出「`app.cli`: 0 app modules」——一个语法正确、格式正确、完全虚假的答案。**最值得记的不是它错了，而是它有一半是对的**：同一次输出里的 `app.core reachable = NO` 在探针修好之后仍然为真。部分正确的假结果比全错的更难识破。
2. **`uv run --project <主仓>` 在临时 worktree 里跑**，把主仓的 `src` 放进路径，量的是被改过的主树而不是那棵检出。数字形状正确，来源是错的。这就是本文统一跑法里 `--no-project` 的由来。
3. **依赖漂移让旧提交的树 import 不起来**，而 `uv run` 在这种情况下可能仍以退出码 0 返回（2026-08-23 在 `c170f0f^` 的 worktree 上实测：`ModuleNotFoundError: No module named 'httpcore2'`，`${PIPESTATUS[0]}` 为 0）。这正是第 1 条那个兜底会再次击发的场合。

所以正样本对照不是礼节：

```bash
PYTHONPATH=src uv run --no-project python -c "import app; print(app.__file__)"
# 必须是 /home/xp/src/ghc-api-proxy-py/src/app/__init__.py
```

并且**永远不要用退出码之外的东西判断探针是否跑过**——要么让失败直接冒出来（不写 `else []` 这类兜底），要么先跑一个已知应该非空的正样本，看它是不是真的非空。

## 这套判据被击穿过五次，五次的盲区各不相同

第 6 步移动 125 个文件，全部建立在「谁从哪个入口可达」这组数字上。**同一个判据在 2026-08-22 一天之内被四个不同的盲区各击穿一次**，四次都是数字真实、命令 rc=0、结论错；第五类是同一天另一位评审在「会不会成环」那张静态图上撞到的。单独看每一次都像偶发，放在一起才是这套方法的边界说明——**按 import 图分割一棵树时，图上至少有五类东西不在默认视野里**：

| # | 盲区 | 怎么发现的 | 后果 |
|---|---|---|---|
| 1 | **「活模块」的定义本身没有鉴别力** | 判「哪些测试混装两条链」时，把「活模块」定义成 `app.cli` 可达，**而那里面含 72 个共享模块**。于是一个纯旧链测试只要 import 了 `app.config.schema` 就被算成混装，数出 50 个 | 换成有鉴别力的判据「它有没有 import **新链独占**的模块」之后，结论翻转为**没有一个测试横跨两条链**——而这正是 49 个测试文件能整体归档的授权依据。**判据从「50 个混装」翻到「0 个横跨」，动作从「不能整体搬」翻到「可以」** |
| 2 | **差集只有两类，实际有三类** | 「仅旧链 = 旧链可达 − 新链可达」漏掉了第三类：**两条链都到不了的 27 个模块** | 这一类决定哪些顶层包能整体搬。`context/`、`repetition_detector.py`、`shutdown.py` 属于此类，`src/.archived/README.md` 单独点名它们正是因为它们不是「旧链」 |
| 3 | **探针看不见入口自身** | `app/__main__.py` 在三分类里显示「两条链都不可达」，而它正是 `python -m app` 的入口 | 这是这套数字**唯一已知会系统性给错**的位置。不能机械按数字搬 |
| 4 | **图上没有「测试之间的相互 import」这类边** | 归档 49 个测试之后 pytest 收集直接报错：`tests/systemd/test_systemd_pipeline_unit.py` import 了被归档的兄弟模块 `test_systemd_units`（取的是共享夹具 `SYSTEMD_DIR`／`http_request`／`read_unit`） | 取回 1 个文件。全仓只有这一条这样的边，但判据里原本没有这类边 |

还有第五类盲区，机制与上面四条不同——**上面四条讲的是「谁可达」这个判据，这一条讲的是「会不会成环」那张静态图本身**（第三轮评审读 subagent 日志时查到，`a656a8f` 的两次运行都在日志里）：

设计评审为判断「新建 `pipeline/delivery/selection.py`、`observability/wire_accounting.py` 会不会造成 import 环」，写了一个 AST import 图做假想模块注入。**第一次只连显式 `import` 边，五个候选全部报「no cycle」，命令正常、退出码 0、格式正确。** 第二次补上两类边之后，结论反转：

| 候选 | 只有显式边 | 补边之后 |
|---|---|---|
| `pipeline/delivery/selection.py` | no | **父包再导出时成环**：`composition → translation_driver.registry → pipeline.request → delivery.assembling → delivery.sse_source → delivery → delivery.selection` |
| `observability/wire_accounting.py` | no | **父包再导出时成环**：`composition → observability.terminal → observability → observability.wire_accounting` |

要补的两类边是：**「import `a.b.c` 会先初始化它的每一级祖先包」**，以及**「该模块是否被父包 `__init__` 再导出」这个开关**。后者把同一个落点从「无环」翻成「硬 ImportError」。这条发现最后成了那次评审的 blocker 之一。

**它不能证明什么**（原报告自己写明，一并带走）：那是**静态推导**，不是一手证据。要变成一手证据得在树里真写一个 `selection.py` 并改 `delivery/__init__.py`，该评审按只读约束没做。

**与 status.md 第 3 步那句「经查无环」的关系**：那句靠的**不是**这张静态图，而是 `handler.py` 溶解**已经落地并跑通全量测试**——真 import 成环会直接 ImportError，跑得起来就是一手证据。**这个区别是这条盲区的实用出口**：静态图适合在动手前筛掉明显的坏落点，**但它报「无环」不足以下结论**；真正的判据是把模块写出来 import 一次。

最后还有一件事既不属于「可达性判据的盲区」也不属于「静态图的盲区」，而是**守卫失效**，记在这里因为它同源：归档之后，`tests/unit/test_module_boundaries.py` 原本那条「新链不得 import 旧链」**变成了恒真断言**——旧链的名字已经不在 `src/` 里，这条断言从此什么都不证明，而它照样是绿的。改成「这些名字解析不到」（`importlib.util.find_spec` 在全新解释器里返回 `None`）之后才重新有内容。**一条断言的意义会被它所守护的代码的移动悄悄抽空，而测试全绿正是这件事发生时的表现。**

## 逐个探针

### `reach.py` + `count.py` —— 一个模块拖进来多少东西

`reach.py <模块名>` 在全新解释器里 import 该模块，然后把 `sys.modules` 里所有 `app.` 前缀项打成 JSON。`count.py` 从 stdin 读那份 JSON，分类计数。

```bash
PYTHONPATH=src uv run --no-project python probes/reach.py app.core.chain | \
  PYTHONPATH=src uv run --no-project python probes/count.py
```

| | 当前复现值 |
|---|---|
| `app.core.chain` | `total app.* = 83 \| app.pipeline.* = 25 \| app.pipeline.delivery.* = 9`，`app.observability reachable = True` |
| `app.server`（**正样本对照**） | `total app.* = 1`，其余全零，`app.observability reachable = False` |

第二行才是重点。搬迁前 `Chain` 定义在 `app.server` 里，所以任何只想要那个类型的模块都会把整个 server 包拖进来（当时 106）。现在 `import app.server` 只拉进它自己一个模块——**这是「`Chain` 不再拖着 `app.server`」的直接证据，比 83 这个数本身更有说服力**，因为 83 里还剩什么取决于 `Chain` 字段的类型，而 1 是干净的。

`app.pipeline.* = 25` 是驳倒「把 `Chain` 搬走它就退化成薄记录」那条评审意见的数：这 25 个依赖来自 `Chain` 的字段类型，搬到哪儿都跟着走。

**它不能证明什么**：这是 import 时的静态可达性，不是运行时实际用到的集合；延迟 import（函数体内的 `import`）它一概看不见。

**计数口径写死在这里，因为它已经造成过一次分歧**：`reach.py` 数的是 `sys.modules` 里 `n.startswith("app.")` 的项，**带点，所以不含裸 `app` 这个顶层包本身**。第三轮评审发现三个 agent 独立测同一件事得出 139 与 140，差的正是这一个；同样的 ±1／±2 分歧也出现在 104/81 与 106/83 那一组（那组差 2，是 `app.core` 与 `app.core.chain`）。**本目录所有数字一律按「`app.` 前缀、不含裸 `app`」口径**，`src/.archived/README.md` 里的 151 与 status.md 里的 83／106／25 都是这个口径。读到别处的 139／140／104／81 时，先问它数没数裸包、以及是在搬迁前还是搬迁后测的。

### `importable.py` —— 剩下的模块是不是每个都还能 import

无参数。用 `git ls-files src/app` 取清单，逐个 `importlib.import_module`，报失败数与前 70 字符的错误。跳过 `app.__main__`（import 它会执行入口）。

**当前复现值：`检查了 169 个模块，import 失败 0 个`** —— 同时复现 status.md 的两个数（`src/app` 被跟踪 `.py` 从 247 降到 169；归档后剩余模块全部可 import）。

**已知盲区，用之前必须知道**：清单来自 `git ls-files`，**它看不见刚创建、尚未 `git add` 的文件**。归档那次是在提交之后跑的所以没踩到，但如果在一次尚未暂存的重构中间跑它，新写的模块一个都不在检查范围内，而结果照样报 0 失败。要覆盖未跟踪文件，把清单换成 `git ls-files src/app` 并上 `git ls-files --others --exclude-standard src/app`。

### `sets.py` —— 归档范围的机械判据（**已自我失效**）

它 import `app.cli` 与 `app.server.app_factory` 两个入口，各自记录可达的 `app.*` 集合，两集合相减就是「旧链独有」的那批。第 6 步的 77 + 48 个文件就是这么划出来的。

**现在跑它会报 `ModuleNotFoundError: No module named 'app.server.app_factory'`。** 这不是脚本坏了——`app_factory` 正是第 6 步归档掉的那个入口，探针的失效本身就是归档成功的证据（`tests/unit/test_module_boundaries.py::test_the_archived_chain_is_not_importable_at_all` 把同一件事固化成了断言）。

要复现原始划分，得回到归档提交之前的树：

```bash
git -C /home/xp/src/ghc-api-proxy-py worktree add --detach /tmp/pre-archive 2248a69^
cd /tmp/pre-archive && PYTHONPATH=src uv run --no-project python <probes>/sets.py
```

**它不能证明什么**：两个入口的差集给出的是「旧链独有」，而第 6 步实际用的判据更严——还加了「整个顶层包没有一个模块活链可达」，才把 `context`、`delivery`、`history`、`hooks`、`openai`、`routes` 六个包整体搬走。差集本身不足以支持删整个包。

### `drop_emptied_dirs.py` + `delete-manifest.json` —— 删掉被搬空的包目录

一次性操作，已执行完毕（那六个目录现在都不存在，脚本会逐个打印 `absent, skipped`）。**两个文件是一对：脚本是执行者，清单是授权书**，分开留任何一个都读不出当时到底删了什么、凭什么删。

留下它们是因为三点值得复用的写法：

- **目标是字面路径、一行一个**，不跑脚本也能读出它会删什么；
- **删之前 `assert` 拒绝删非空目录**（排除 `__pycache__` 之后仍有文件就中止）；
- **清单里 `allow_unenumerated_targets` 是打开的，而 `note` 字段说明了为什么**——删除护栏读不出被调用的 Python 脚本内容，这个开关是唯一的出路。**但开关关掉的是护栏的检查，不是自己的**：同一份清单仍然把六个目标逐条列明，`preserved` 字段记下「46 个 `.py` 已由 `git mv` 迁走、rename 检测保留历史」与那条 `assert`。一份写成这样的清单，事后可以独立于脚本被审。

保留它们的真正理由是记录了一个反直觉的事实（清单 `note` 里也写着）：**把包目录下的 `.py` 全部删光并不等于该包不可 import**。PEP 420 命名空间包让一个只剩 `__pycache__` 的目录照样满足 `import app.routes` 并返回一个空模块——实测确认，所以才需要连目录一起删。**这正是删除动机本身**：那六个目录留着会让「旧链是否还可达」这类判断给出错误答案。

## 没有保留的东西，以及为什么

- `probe_chain.py` —— `core/chain.py` 落地前的前瞻探测（试算「只 import `Chain` 字段类型所需的那些模块」会拉进多少）。结论已经变成 `chain.py` 本身和它的 docstring，探针没有二次价值。
- `A.json` / `B.json` / `sets.json` / `legacy_files.txt` / `legacy_tests.txt` / `tests_only_legacy.txt` / `tests_archive.txt` / `move.txt` —— `sets.py` 那条差集流水线的输出。**它们的最终形态已经是 `2248a69` 里 125 条 100% 相似度的 rename 记录**，比任何中间清单都权威；要重跑那条流水线得先回到 `2248a69^`（见 `sets.py` 一节）。
- **`delete-manifest.json` 原本也在这个「没保留」清单里，评审指出那是误判——它不是任何脚本的输出，而是手写的删除授权书。已保留**，见上面 `drop_emptied_dirs.py` 那一节。
- `dist/app-0.1.0-py3-none-any.whl`（399K）—— 构建实测的产物。结论（wheel 174 个条目、不含 `.archived`、正样本对照确认 `app/cli.py` 在内）已写进 status.md，重建一次 `uv build` 即可。
