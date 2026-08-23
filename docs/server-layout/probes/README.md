# 复现探针：`app.server` 布局六步的那几个数字

status.md 里写着 106 → 83、247 → 169、77 + 48 这些数，但只写了「实测」。这个目录放的是**实际跑出那些数的脚本原件**，从会话临时目录逐字复制过来，一个字没改。留脚本而弃派生数据（`sets.json`、399K 的 wheel、几份模块集合 JSON）是有意的：脚本三五百字节，能把整个数据集再生成一遍。

**基线**：脚本产出于 2026-08-22 的六步实施期间。下表「当前复现值」一栏是 2026-08-23 06:35 在主仓 `7525f76`（工作树另有同伴未提交改动）上重跑的结果。

**统一跑法**（`--no-project` 是必要的，否则 uv 会去解析主仓的 `pyproject.toml` 并可能装出另一棵树）：

```bash
cd /home/xp/src/ghc-api-proxy-py
PYTHONPATH=src uv run --no-project python .dev/docs/server-layout/probes/<脚本> [参数]
```

**先跑正样本对照，再读任何数字**——本会话有两次探测给出了形状正确的假数字（一次 `uv run --project` 加载了错的树，一次 `cd src` 后包根变了），两次都差点被当成结果读走：

```bash
PYTHONPATH=src uv run --no-project python -c "import app; print(app.__file__)"
# 必须是 /home/xp/src/ghc-api-proxy-py/src/app/__init__.py
```

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

### `drop_emptied_dirs.py` —— 删掉被搬空的包目录

一次性操作，已执行完毕（那六个目录现在都不存在，脚本会逐个打印 `absent, skipped`）。留下它是因为两点值得复用的写法：

- **目标是字面路径、一行一个**，不跑脚本也能读出它会删什么；
- **删之前 `assert` 拒绝删非空目录**（排除 `__pycache__` 之后仍有文件就中止）。

保留它的真正理由是它记录了一个反直觉的事实：**把包目录下的 `.py` 全部删光并不等于该包不可 import**。PEP 420 命名空间包让一个只剩 `__pycache__` 的目录照样满足 `import app.routes` 并返回一个空模块——实测确认，所以才需要连目录一起删。

## 没有保留的东西，以及为什么

- `probe_chain.py` —— `core/chain.py` 落地前的前瞻探测（试算「只 import `Chain` 字段类型所需的那些模块」会拉进多少）。结论已经变成 `chain.py` 本身和它的 docstring，探针没有二次价值。
- `A.json` / `B.json` / `sets.json` / `legacy_files.txt` / `legacy_tests.txt` / `move.txt` / `delete-manifest.json` —— 上面几个脚本的派生数据。脚本在，数据可再生；而且这批的最终形态已经是 `2248a69` 里 125 条 100% 相似度的 rename 记录。
- `dist/app-0.1.0-py3-none-any.whl`（399K）—— 构建实测的产物。结论（wheel 174 个条目、不含 `.archived`、正样本对照确认 `app/cli.py` 在内）已写进 status.md，重建一次 `uv build` 即可。
