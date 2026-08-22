# CLI 命令切分与模块迁移 —— 会话收尾记录（2026-08-21 → 08-22）

会话窗口：`2026-08-21T17:40:18Z` → `2026-08-22T16:43Z`。主仓库本会话共 7 个提交（窗口内 84 个，其余为同伴）。未派遣 subagent，未创建 worktree。

## 交付

| 提交 | 内容 |
|---|---|
| `ff0ac3c` | `start --generate-config` → 独立命令 `gen-config <out-path>`，路径必填 |
| `5a1bb94` | GitHub token 只接受 `GHC_API_PROXY_GITHUB_TOKEN`；含它与 `GHC_` 配置前缀冲突的修复 |
| `b9939ca` | `app.auth` → `app.ghc_client.auth` |
| `d49fe23` | `app.ghc_client` → `app.model_provider.ghc_client` |
| `5fc9dc4` | `tests/component` 同步嵌套 |
| `92725a4` | `gen-config` 覆盖既有文件前二次确认 |
| `5cb8dcf` | 修复 `exp/` 下 5 个探针脚本的旧 import（见下） |

索引事故与其修复另见 [`260821-shared-index-left-reverting-head.md`](260821-shared-index-left-reverting-head.md)。

## 决定与被否掉的选项

- **`gen-config` 的路径必填，不给默认值。** 旧标志的默认值是 `config_file_path()`（`$XDG_CONFIG_HOME`），而 `load_proxy_config` 读的是 `spec_config_file_path()`（`$XDG_DATA_HOME`）——两者不是同一个位置，所以「不给路径」生成的是一个服务永远不会读的文件。承载于 `cli.py` 的 docstring。
- **不加 `--force`。** `yes | ghc-api-proxy gen-config <path>` 已能在脚本中回答，且无 stdin 时 `typer.confirm` 是中止而非挂起（实测 `< /dev/null` 返回 1）。
- **`GHC_API_PROXY_GITHUB_TOKEN` 必须在 `environment_values` 里排除。** 它与配置的 `GHC_` 前缀同名空间，不排除则被解析成顶层键 `api_proxy_github_token`，`ProxyConfig` 以 `extra="forbid"` 拒绝，**进程启动即死**。与既有的 `GHC_CONFIG` 同形，故复用同一处 `NON_SETTING_VARIABLES`。
- **`ghc_client` 包 docstring 里「Imports nothing from `app.*`」被删除而非保留。** 该句在本次改动**之前**就已不成立（`errors.py` import `app.pipeline.exceptions`），且无任何测试执行它。改为陈述实际依赖。

## 改名的搜索范围：只扫 `src/` 和 `tests/` 会漏掉已跟踪的 `exp/`

两次模块迁移（`d49fe23`、`5fc9dc4`）都把改名范围限定在 `src/` 与 `tests/`，因为脑子里想的是「代码和测试」。结果 `exp/` 下 **5 个已跟踪的**探针脚本仍 import `app.ghc_client`，下一个运行它们的人会在 import 处直接失败。收尾扫描才发现，`5cb8dcf` 修复。

**判据**：改名的搜索范围是**整个仓库**，唯一该排除的是 `.git` 与生成物。「哪些目录会 import 这个模块」是个不能凭直觉回答的问题——`exp/`、`verification/`、`scripts/`、文档里的代码块都可能。做法是先 `rg -l <旧名> -g '!.git' .` 看完整清单再决定改哪些，而不是先决定范围再搜。

## 三处「命令跑了、输出真实、结论仍然错」

都发生在本次，都没有失败信号，全部靠事后复核或用户指出才纠正。

1. **`git grep` 找不到 f-string 拼出来的常量。** 用 `git grep -c "GHC_API_PROXY_GITHUB_TOKEN" HEAD -- src/app/config/loading.py` 判断改动是否还在，返回空，据此在报告里写了「HEAD 里查不到」。实际源码是 `f"{ENV_PREFIX}API_PROXY_GITHUB_TOKEN"`，字面量根本不存在。**搜一个可能由拼接产生的名字时，要搜它的构造式或它的符号名，不是搜成品字符串。**
2. **`awk` 会吞掉 `git status --porcelain` 的前导空格。** 用 `awk '$1 ~ /^[A-Z]/ {print $2}'` 想筛「有暂存改动」的文件，但 ` M path` 被 awk 切成 `$1="M"`，于是**所有**被修改的文件都被判成已暂存，归属表整个是错的。**porcelain 的两列状态必须按字节位读**（`cut -c1`、`cut -c2`），不能靠字段切分。
3. **「在历史里找不到」是搜索深度的函数。** 只扫最近 25 个提交就把 `composition.py` 的暂存 blob 判成「索引独有、可能是同伴的独有快照」；扫到 40 个才发现它与 `f025e3c` 逐字节相同。**用「找不到」下结论前必须把搜索深度写出来**，或者改用「该 blob 是否被任何 ref 可达」（`git rev-list --objects --all`）这种与深度无关的判据。

## 一条被放弃的路线：不要在副本目录里用 ruff 重建 import 顺序

为了给一个夹带了同伴改动的文件重建「HEAD + 只有我的改名」的内容，我把它拷到临时目录、连同 `pyproject.toml`，想让 `ruff check --fix` 复现 isort 顺序。**结果是错的**：副本目录里 ruff 把 `httpcore2` / `httpx2` 判成了非第三方，把它们整体挪到了 `app.*` 之后，与仓库内的真实排序不一致。

改用按明确锚点手工搬那一个 import 块，并用一句断言校验 `app.*` 的字母序。**判据**：import 分类依赖运行环境（已安装的包、`src` 布局），把文件搬出仓库再跑格式化工具，得到的顺序不是仓库里的顺序。

## 执行过的变异及其失败形状

- **`src/app/cli.py` 删掉 `if out_path.exists(): typer.confirm(...)` 两行** → 只有 `tests/unit/test_cli.py::test_gen_config_keeps_an_existing_file_when_the_answer_is_no` 变红（断言 `exit_code != 0` 失败）。另两条 gen-config 新测试在无确认时行为本就不变，仍绿——这是预期，不是覆盖不足。
- **`src/app/pipeline/exceptions.py` 顶部加 `from app.model_provider.ghc_client import GhcApiClient`** → `tests/unit/test_module_boundaries.py::test_pipeline_exceptions_stay_importable_without_the_pipeline` 变红，但**形式是 `subprocess.CalledProcessError`（探针子进程因循环导入崩溃），不是断言触发**。该测试用子进程测量可达模块集，任何进入该包的 import 都会先撞上循环导入。所以它确实有分辨力，但它证明的是「不可导入」，不是「前缀断言写对了」；前缀非空转另用一次实测确认（`import app.model_provider.github_copilot` 后有 10 个模块以该前缀开头）。

两次变异均逐字节还原并以 `git status` 空输出确认。

## 可复用：怎么看到 systemd 单元测试里那个子进程自己的报错

`tests/systemd/test_systemd_pipeline_unit.py` 用 `subprocess` 拉起真实的 `python -m app start --fd 3`，失败时 pytest 只报 socket 超时，**子进程的 traceback 完全看不到**。本会话两次关键诊断（`GHC_` 前缀冲突、`build_http_client` 缺参）都靠下面这个探针才拿到根因：

```python
import socket, subprocess, sys, tempfile, time
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread

sys.path.insert(0, "tests/systemd")
import test_systemd_pipeline_unit as m          # 复用它自己的 _service_environment 与 _CopilotFake

state = Path(tempfile.mkdtemp()) / "state"; state.mkdir()
m._CopilotFake.requests = []
up = ThreadingHTTPServer(("127.0.0.1", 0), m._CopilotFake)
Thread(target=up.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{up.server_address[1]}"

ln = socket.socket(); ln.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ln.bind(("127.0.0.1", 0)); ln.listen(8)
launcher = ("import os, sys; source = int(sys.argv[1]); os.dup2(source, 3); "
            "os.set_inheritable(3, True); "
            "os.execv(sys.executable, [sys.executable, '-m', 'app', 'start', '--fd', '3'])")
p = subprocess.Popen([sys.executable, "-c", launcher, str(ln.fileno())],
                     cwd=Path("."), env=m._service_environment(state, url),
                     pass_fds=(ln.fileno(),),
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(8)
if p.poll() is None: p.kill()
print(p.communicate(timeout=20)[0][-4000:])     # 这里才是真正的 traceback
```

关键点是**复用测试模块自己的 `_service_environment`**，而不是手搓环境——手搓会漏掉 unit 文件里的 `Environment=` 条目，于是复现出来的是另一个场景。

**它不证明什么**：这是单条用例的复现，不覆盖 `test_systemd_units.py` 里的 backlog/socket-handover 场景，也不测优雅退出。
