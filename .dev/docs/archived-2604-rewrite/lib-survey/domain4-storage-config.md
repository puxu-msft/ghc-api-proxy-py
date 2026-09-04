# 域4：存储 / 持久化 / 配置 / CLI

调研范围：`history/sqlite/*`（异步 SQLite 后端）、`config/*`（四层配置合并）、`cli.py`（命令行）、`context/error_persistence.py`（错误持久化）。已读 `history-system.md`、`config-system.md`、`shutdown.md`（错误持久化消费者段）、`project-structure.md` 对应模块地图。当前仓库 `src/app/` 尚未实现这些模块（只有 `__init__.py`/`__main__.py`），本调研针对**目标设计文档**评估。

## 概览结论表

| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |
|---|---|---|---|---|---|
| 异步 SQLite writer（`history/sqlite/writer.py`） | `aiosqlite` | 中 | 否，但语义不等价 | **保留自研** | aiosqlite 内部是"每连接一条常驻线程 + 无界 `SimpleQueue`"，off-loop 目标能达成，但没有背压/丢弃语义，且**多一层线程+Future 桥接**的开销和复杂度，换不来功能收益 |
| 异步 SQLite writer（同上） | `asyncio.to_thread` / `run_in_executor(ThreadPoolExecutor(1))` + 自建 `asyncio.Queue` | 高 | 否 | **保留自研（即设计文档现状）** | 这就是文档已选方案，天然满足 P1，且显式队列给了背压/丢弃精细控制，是当前最优解 |
| schema/迁移（`history/sqlite/schema.py`） | `sqlalchemy` / `sqlalchemy[asyncio]` | 低 | 是（重量级 ORM 与连接池模型和"单 writer 持有唯一连接"的设计冲突） | **保留自研**（建表 DDL + 简单版本号迁移） | 表结构单一（仅 `entries` 一张表）、迁移诉求轻（增删列），上 SQLAlchemy 换来的抽象收益远小于引入 ORM 元数据/连接池/Session 生命周期管理的复杂度和与"单一 writer 连接"架构的摩擦 |
| session 聚合（`sessions_agg.py`） | `sqlalchemy-core`（仅借查询构造） | 低 | 否 | **保留自研**（原生 SQL 字符串） | 一条 `GROUP BY` 语句，用 Core 表达式构造反而更啰嗦，原生 SQL 更直接可读 |
| 四层配置合并（`config/loader.py`） | `pydantic-settings`（已在用） | 高（部分） | 否 | **部分采纳**：已用其 env/frozen 能力；YAML 合并与 CLI 覆盖建议评估迁移到其 `settings_customise_sources` + 内置 `YamlConfigSettingsSource`/`CliSettingsSource`，但**不强制**，见详述 | 官方支持四层优先级排列，但 per-key 深度合并（`model_mappings` 等）为项目定制语义，内置 `deep_merge` 只做 shallow 且不含 per-key/replace 区分，仍需自定义合并层 |
| 四层配置合并 | `dynaconf` | 低 | 否 | **不采纳** | 与项目已确定的 Pydantic frozen `AppSettings` 架构冲突（dynaconf 是独立配置门面，非 Pydantic 模型），迁移收益不足以推翻已有选型 |
| XDG 路径（`config/paths.py`） | `platformdirs` | 高 | 否 | **推荐替换**（借库不借架构） | 成熟、维护活跃、专门解决这个问题，比手写 `platform.system()` 分支更少踩坑（如 macOS/Windows 路径规范的边界情况） |
| YAML 解析 | `pyyaml`（`yaml.safe_load`，文档已用） | 高 | 否 | **保留 pyyaml** | 只做只读解析，无需 `ruamel.yaml` 的往返保留注释能力（配置文件非程序化写回，`PUT /api/config/yaml` 走整体替换不是 diff 编辑） |
| CLI（`cli.py`，argparse） | `typer` | 高 | 否 | **推荐迁移**（长期收益，非阻塞） | 见详述：多子命令树、类型化参数、自动 `--help`，长期可维护性明显优于手写 argparse |
| CLI（同上） | `click` | 高 | 否 | 次选，不采纳 | typer 建在 click 之上且提供更现代的类型标注 API，两者能力接近时优先 typer |
| 错误持久化（`context/error_persistence.py`） | 标准库 + `aiofiles`（文档已用） | 高 | 否 | **保留现状** | 单文件 JSON 写入，`aiofiles` 已经是恰当的最小依赖，无需额外库 |

## 逐项详述

### 异步 SQLite 后端（`history/sqlite/writer.py` + `schema.py` + `reaper.py` + `sessions_agg.py`）

**现状**：`history-system.md` L47-108 给出完整设计——单一 `HistoryWriter` 协程持有唯一 `sqlite3.Connection`，请求路径只 `submit()` 塞入有界 `asyncio.Queue`（`maxsize=1000`），writer 协程消费队列后把实际 `sqlite3` 调用经 `asyncio.to_thread` 下沉线程池；`WriteJob.discardable` 区分背压丢弃策略；`reaper.py` 按 `success_limit`/`failure_limit` 分桶删最旧（`history-system.md` L266-309）；`schema.py` 负责建表 DDL；`sessions_agg.py` 做 `GROUP BY session_id` 聚合查询（`history-system.md` L181-221）。`project-structure.md` L158-163 确认这是四个独立文件的划分。

**候选库 1：`aiosqlite`**
- 版本/维护：最新 `0.22.1`（2025-12-23 发布），GitHub `omnilib/aiosqlite`，1567 星，最近 push 2026-03-01，MIT 许可证，有 `py.typed` 类型标注，纯 Python 无 C 扩展（3.14 兼容性问题小）。
- 实现机制（读源码 `aiosqlite/core.py` 确认）：每个 `Connection` 对象内部起一条**常驻后台线程**（`threading.Thread`），用 `queue.SimpleQueue`（**无界**）作为请求队列；每次 `execute`/`commit` 等调用把 `(future, function)` 元组 `put_nowait` 进队列，后台线程串行 `function()` 执行后把结果通过 `call_soon_threadsafe` 塞回 asyncio Future。
- 是否满足 P1 off-loop：**满足**——sqlite3 调用确实发生在独立线程，不阻塞事件循环。
- 与自研方案的关键差异：
  1. **无界队列，无背压语义**——`SimpleQueue` 不设容量上限，无法表达"队列满时丢弃 discardable job"这一设计要求（`history-system.md` L79-85）。若要在 aiosqlite 之上叠加背压，还是得在 aiosqlite 外面再包一层有界 `asyncio.Queue`——等于自研 writer 协程的活儿一件不少，只是把"调用 sqlite3"这一步换成调用 aiosqlite 的 API，多绕一层线程+Future 桥接（而当前设计本来就用 `asyncio.to_thread` 直接达到同等效果，无需常驻线程）。
  2. **连接生命周期是每库一线程**，而设计文档要求"SQLite 连接只被这一个 writer 持有，天然免锁"——aiosqlite 天然满足单连接单线程，但这本来就是自研方案已经做到的事，aiosqlite 不额外带来锁安全收益。
  3 API 层面 aiosqlite 提供了游标/连接的完整异步包装（`execute`/`executemany`/`iterdump`/`backup` 等），但设计中只需要"提交一个 job，线程池执行一段构造好的 DML/DDL"，这层丰富 API 面基本用不上。
- 结论：**不换库，保留自研**。理由：aiosqlite 解决的问题（sqlite3 阻塞调用 off-loop）当前设计已经用更轻量的 `asyncio.to_thread` + 显式有界队列解决了，且 aiosqlite 缺少背压/丢弃能力这一项目强需求，引入它反而需要在其上包一层队列，等于叠加而非替代复杂度。

**候选库 2：`sqlalchemy[asyncio]`（`aiosqlite` 作为 SQLAlchemy 的 async driver）**
- 版本：SQLAlchemy 最新 `2.0.51`（2026-06-15），GitHub 11994 星，2.x 起原生支持 `asyncio`（`create_async_engine`），异步驱动需要 `aiosqlite` 作为 DBAPI 适配层（即栈叠加：SQLAlchemy async → aiosqlite → sqlite3）。
- 能力核对：Alembic 迁移、声明式模型、连接池、跨方言可移植性。
- 是否值得引入：**不值得**。理由：
  1. 本项目 schema 极简（一张 `entries` 表 + `pinned`/`pid` 等标量列），不存在"未来要支持多种数据库方言"的需求（历史系统明确绑定 SQLite，`history-system.md` 全文未提及可插拔数据库后端）。
  2. SQLAlchemy async engine 的连接池模型（`AsyncEngine` 管理多连接）与设计文档"单一 writer 持有唯一连接、免锁"的架构假设直接冲突——要维持单连接语义就得把 SQLAlchemy 的连接池收窄到 1，等于放弃它的核心价值,还要额外承担 Alembic 迁移脚本、ORM 关系映射等对本场景无用的复杂度。
  3 Session 聚合只是一条 `GROUP BY` SQL，SQLAlchemy Core 表达式构造不会比原生 SQL 更简洁。
  4. 与本项目"重 CPU/重抽象不进不该进的地方"的克制取向不符（`_briefing.md` 强调"别为省事牺牲…性能"，这里反过来是"别为省事牺牲…简洁"）。
- 结论：**保留自研**（DDL 字符串 + 简单 `PRAGMA user_version` 版本号迁移，若未来需要迁移可以在 `schema.py` 里加一个 `CURRENT_VERSION` 常量 + `if user_version < N: ALTER TABLE ...` 的手动迁移函数，量级足够小，不需要 Alembic）。

**候选库 3：`databases` / `sqlmodel` / `sqlite-utils`**
- `databases`（0.9.0，2024-03-01 发布，已 1年+ 未更新）——本身是对 SQLAlchemy Core + 各 async driver 的薄封装，活跃度明显低于 SQLAlchemy 本体，且同样与连接池模型绑定，不解决本场景的核心矛盾（单连接、有界队列背压）。**不采纳**。
- `sqlmodel`（0.0.39，2026-06-25 更新，FastAPI 作者维护）——本质是 Pydantic + SQLAlchemy 的桥接，用于"用同一套模型定义做 API schema 和 DB 表"。本项目 `HistoryEntry` 是纯 dataclass（`history-system.md` L112-152），且 API 层用 `EntrySummary` 做另一套轻投影，模型语义本就分离，没有复用同一模型定义两端的诉求。**不采纳**。
- `sqlite-utils`（4.1.1，2026-07-12 刚更新，Simon Willison 维护）——定位是 CLI 工具 + 便利 Python API，做**同步**操作（无 async 支持），若引入还要自己包一层线程池，等于给"直接写 SQL"多绕一层薄封装。**不采纳**。

**是否威胁 P1/P6/保真度**：均不威胁（都是 off-loop 可实现的），核心问题是「值不值得」而非「能不能」。

**推荐**：**保留自研 writer（`asyncio.to_thread` + 显式有界 `asyncio.Queue`）+ 手写 DDL/简单版本迁移 + 原生 SQL 聚合查询**。这是目前调研范围内 4 个候选路径中，功能匹配度最高、且不违反"单一 writer 免锁"架构假设的唯一选项。若团队未来出现"要同时支持 SQLite 和 PostgreSQL"或"表结构复杂到需要正式迁移工具"的新需求，可重新评估 SQLAlchemy + Alembic，但**当前范围内不成立**。

---

### 配置系统（`config/settings.py` + `loader.py` + `compat.py` + `paths.py`）

**现状**：`config-system.md` L1-92 描述四层合并（默认值 < YAML < 环境变量 < CLI），用 frozen Pydantic v2 `BaseSettings`（`env_prefix="GHC_"`, `env_nested_delimiter="__"`），`loader.py` 手写 `_deep_merge` 实现 per-key vs replace 两种合并策略（`model_mappings`、`timeouts.stream_idle_overrides`、`timeouts.response_header_overrides` per-key 合并，其余 dict 字段整体替换，见 L66-78）。`compat.py` 做精简弃用键迁移（L864-877）。`paths.py` 手写跨平台 XDG 路径解析（L827-862）。

**`pydantic-settings`（已在用，非新增候选）**
- 版本：最新 `2.14.2`（2026-06-19 发布），GitHub `pydantic/pydantic-settings` 1391 星，push 2026-07-15（当天），MIT 许可证，type hints 完整（Pydantic 生态标配）。
- 已确认能力（查官方文档 `pydantic.dev/docs/validation/latest/concepts/pydantic_settings/`）：
  1. `settings_customise_sources` 钩子可自定义源优先级顺序（"first item is highest priority"），因此**四层优先级完全可表达**：`(cli_source, env_settings, yaml_source, init_settings)` 这样的元组即可实现 defaults < yaml < env < cli。
  2. 内置 `YamlConfigSettingsSource`（`yaml_file`/`yaml_file_encoding` 参数），可以直接替代手写的 "读 yaml 文件 → dict → 塞进 settings_dict" 逻辑。
  3. 内置 `CliSettingsSource`，底层"is based on the argparse library"，且**可以把既有 `ArgumentParser` 对象设为 `root_parser`**——即可以与项目已有的 argparse 树共存/集成，不要求推倒重来。
  4. **关键限制**：dict 类型字段默认走"整体替换"合并（env 变量走 JSON 编码整体替换；配置文件源默认 shallow merge，需要显式 `deep_merge=True` 且该参数**不能通过 `SettingsConfigDict` 设置**，只能在自定义 source 里传）。且即使开启 deep_merge，也不区分"per-key 合并 vs replace"两类字段——`model_mappings` 要 per-key、`anthropic.effort_overrides` 要 replace 这种**按字段区分策略**的语义，pydantic-settings 内置源不提供，仍需项目自己在 `_deep_merge` 里维护 `RECORD_MERGE_STRATEGIES` 这类清单（`config-system.md` L78 已提到与上游 `RECORD_MERGE_STRATEGIES` 对齐的取向）。
- **评估结论**：pydantic-settings 已经是四层合并的地基（当前设计已经在用它的 env 自动读取 + frozen 特性），**建议进一步采纳其内置 `YamlConfigSettingsSource`/`CliSettingsSource` 通过 `settings_customise_sources` 表达四层优先级**，可以省掉 `loader.py` 里手写的"YAML 读取 → dict → 覆盖 CLI"这段管道代码，让四层合并声明式地体现在 `model_config`/`settings_customise_sources` 里。但 `_deep_merge` 的 **per-key vs replace 按字段区分**这段自定义逻辑无法被内置能力取代，仍需保留（作为在 `settings_customise_sources` 返回的自定义 source 内部实现，而不是完全推翻）。**这是一个「减少样板代码」级别的重构建议，不是新库引入**——因为 pydantic-settings 本来就已经是依赖。**是否值得现在做**这个内部重构，因涉及现有（未写）`loader.py` 的具体实现细节，建议留给 planner/implementer 阶段结合实际代码量评估，本次调研只确认"技术上可行、能表达四层语义"。

**`dynaconf`**
- 版本：最新 `3.3.2`（2026-06-29），GitHub 4314 星，push 2026-07-03，MIT，明确支持多层（settings.toml/yaml + `.env` + 环境变量 + 直接赋值）合并，且有 `merge` 显式控制 per-key vs replace（用 `dynaconf_merge` 标记）。
- **不采纳的理由**：dynaconf 是一个独立的、非 Pydantic 的配置门面（其核心对象是 `LazySettings`，字段访问走属性代理而非 Pydantic 模型验证）。项目已经确定用 Pydantic frozen `AppSettings` 作为配置的**类型系统与校验层**（`config-system.md` L13 明确这是相对上游的优化），迁移到 dynaconf 意味着放弃 Pydantic 校验/序列化能力，或者要在 dynaconf 之上再包一层 Pydantic 转换——这是"两套配置系统叠加"而非替代，复杂度不降反升。dynaconf 的多层合并能力虽强，但与"pydantic-settings 已经能做四层合并"相比没有增量收益，只有架构不一致的风险。

**`platformdirs`**
- 版本：最新 `4.10.0`（2026-05-28），GitHub `tox-dev/platformdirs` 957 星，push 2026-07-15（当天），license 未在 PyPI JSON 标出但项目主页为 MIT，纯 Python 无 C 扩展。是 `appdirs` 的维护分支，PyPI/pip 生态事实标准。
- 能力核对：`user_config_dir()`/`user_data_dir()` 直接覆盖 `paths.py` 里 `get_config_dir()`/`get_data_dir()` 的全部需求（Linux XDG、macOS `Library/Application Support`、Windows `%APPDATA%`），且对 XDG 环境变量覆盖（`XDG_CONFIG_HOME`/`XDG_DATA_HOME`）、Windows roaming/local 区分等边界情况处理更完备。
- 是否威胁硬约束：无（纯路径计算，无 I/O 热路径关联）。
- **推荐：借库替代手写实现**——`get_config_dir()`/`get_data_dir()` 两个函数可以直接委托给 `platformdirs.user_config_dir("ghc-api-proxy")`/`user_data_dir("ghc-api-proxy")`，`get_default_config_path()`/`get_token_path()`/`get_error_persistence_dir()` 在其结果上拼接子路径即可。这是`_briefing.md` 强调的「借类型/工具函数，不接管控制流」的典型场景——platformdirs 只是几个纯函数，替换风险极低、收益是减少手写平台分支的维护面。

**YAML：`ruamel.yaml` vs `pyyaml`**
- `pyyaml` 最新 `6.0.3`（2025-09-25），成熟事实标准，纯读取场景（`yaml.safe_load`）性能与生态兼容性最佳。
- `ruamel.yaml`（0.19.1，2026-01-02）的核心优势是"往返保留"（round-trip：保留注释、原始顺序、原始格式），适用于**程序生成后再写回、且需要保留用户注释**的场景。
- 本项目的 YAML 使用场景：只读解析（`loader.py` 读取合并），以及 `PUT /api/config/yaml` 热重载端点——但该端点是"提交新 YAML 触发热重载"（`config-system.md` L806-816），是**整体替换**而非"读取现有文件、局部编辑、写回并保留注释"的语义。`--generate-config` 生成默认配置文件（`config-system.md` L801）是一次性写出，不需要往返保留。
- **结论：保留 pyyaml，不换 ruamel.yaml**——当前无任何"编辑后写回并保留注释"的真实使用场景，ruamel.yaml 的核心差异化能力用不上，换库只会增加一个非标准 YAML 解析器依赖（ruamel.yaml 的 API 与 pyyaml 不同，`safe_load` 行为也有细微差异需要重新验证）。

---

### CLI（`cli.py`，argparse 多子命令）

**现状**：`project-structure.md` L269-274、`config-system.md` L771-804 描述：`argparse` 定义子命令树 `start`（默认）/`auth`（别名 `login`）/`logout`/`debug`（子命令 `info`/`models`/`usage`）/`setup-claude-code`/`setup-codex`/`list-claude-code`，`start` 子命令有 15+ 个选项（`--config`/`--port`/`--host`/`--verbose`/`--account-type`/`--rate-limit`/`--no-rate-limit`/`--manual`/`--generate-config` 等，含多个 `--x`/`--no-x` 布尔对开关）。

**候选：`typer`**
- 版本：最新 `0.26.8`（2026-06-26），GitHub `fastapi/typer`（Sebastián Ramírez 维护，与 FastAPI 同作者生态）19759 星，push 2026-07-13，MIT，原生基于类型标注生成 CLI（底层用 click），完整 type hints。
- 能力核对：
  1. 多级子命令树（`typer.Typer()` 嵌套 `add_typer`）天然支持 `debug info`/`debug models`/`debug usage` 这种两级子命令，比 argparse 手写 `add_subparsers` 嵌套更简洁。
  2. `--rate-limit/--no-rate-limit` 这类布尔对开关，typer 用 `bool` 类型标注 + `--flag/--no-flag` 语法**原生支持**（无需手写 `action="store_true"` + 反义参数两套定义）。
  3. 自动生成 `--help`、参数校验、错误信息格式化均比 argparse 默认输出更友好，且随类型标注自动获得（如 `Literal["individual","business","enterprise"]` 自动转为选项校验+补全提示）。
  4. 可选 shell 自动补全（`typer[all]` 或独立插件），argparse 无此能力。
- 是否威胁硬约束：无（CLI 解析发生在进程启动期，非请求热路径）。
- **迁移成本与收益权衡**：当前 `cli.py` 规模中等（7 个顶层子命令 + `debug` 二级子命令 + `start` 的 15+ 选项），argparse 写法本身没有报错，"能跑"；但从长期可维护性角度（`long-term-wins`/`against-yagni-on-feature` 原则要求不因"当前够用"而放弃长期收益）：
  - 每新增一个子命令或选项，typer 只需加一个函数 + 类型标注参数，argparse 需要维护 parser 对象树 + `Namespace` 字段映射 + 手写 `--flag/--no-flag` 样板，心智负担和样板代码量随选项数线性增长，typer 明显更平；
  - typer 与 FastAPI 同作者、同风格（类型驱动），团队认知负担较低（`fastapi==0.129.0` 已是本项目依赖，typer 的"用类型标注表达接口"心智模型可直接复用）；
  - typer 底层是 click，代码规模成熟稳定，无重量级依赖风险。
- **推荐：迁移到 typer**。这不是阻塞性任务，可作为独立的重构工作项排期，但不应因"argparse 现在能用"而永久搁置——按用户 `battle-tested-over-hand-rolled` 与 `long-term-wins` 原则，这是一个"正确且长期有收益"的改动，值得纳入计划，而非归入 BACKLOG"可选/延后"。

**候选：`click`**
- 版本：最新 `8.4.2`（2026-06-24），17583 星，push 2026-07-10，成熟度与 typer 相当（typer 底层即用 click）。
- **次选，不单独采纳**：typer 在 click 之上提供了类型标注驱动的更现代 API，两者能力覆盖面接近的情况下，优先 typer；如果团队更偏好显式装饰器风格（不依赖类型标注推导），click 也是合理选择，属于团队风格偏好判断，非本调研强制项——**留给用户/主会话在两者间二选一**。

---

### 错误持久化（`context/error_persistence.py`）

**现状**：`shutdown.md` L395-427 描述 `ErrorPersistenceSink`——请求失败时把错误信息（`request_id`/`timestamp`/`model`/`endpoint`/`error.{type,message,status_code}`/`attempts`）序列化为 JSON，用 `aiofiles.open` 异步写入 `~/.config/ghc-api-proxy/errors/{ctx.id}.json`，写入异常被捕获降级为 warning 日志（never-throw，因响应已完成，抛错无意义）。

**评估**：
- 数据结构简单（一次性整体 JSON dump，无需增量更新/并发写同一文件），标准库 `json.dumps` 已足够，无需 `orjson`/`ujson` 等第三方 JSON 库（这些库的价值在高吞吐序列化场景，此处是低频错误落盘，不构成瓶颈）。
- I/O off-loop 需求：`aiofiles`（已是文档选定方案，25.1.0，2025-10-09 发布，Apache-2.0，3253 星，纯 Python，其实现同样是"经 `asyncio` 的线程池 executor 包装同步文件 I/O"，与 P1 的"off-event-loop"要求一致）。
- **是否有必要引入更多库**：不必要。写目标是本地文件系统单文件、无查询/索引/压缩需求，标准库 `pathlib.Path.mkdir` + `json` + `aiofiles` 已是最小复杂度实现，任何额外库（如引入一个"结构化错误日志"框架）都会是过度设计。
- **推荐：保留现状**（标准库 + `aiofiles`），无需调整。

---

## 遗留疑问 / 需主会话或用户裁决的点

1. **pydantic-settings 内置 `YamlConfigSettingsSource`/`CliSettingsSource` 重构 `loader.py`**：技术上可行且能省样板代码，但涉及现有（尚未落地代码的）`_deep_merge` per-key/replace 定制逻辑如何嵌入自定义 source，具体重构收益需要等 `config/loader.py` 真正编码时再评估工作量，本调研只给出「可行、值得纳入候选」的结论，不强制作为唯一实现路径。
2. **CLI 从 argparse 迁移到 typer**：属于长期收益改动，按用户原则不应因 YAGNI 而搁置，但**这是一次性、跨越多个子命令的重构，建议明确排入实施计划的一个独立阶段**（而非在其他模块开发过程中顺带做），需要主会话/用户确认是否现在就纳入 2604-rewrite 的实施范围，还是先用 argparse 起步、typer 迁移作为后续里程碑。
3. **SQLAlchemy 是否要为未来"可插拔数据库后端"预留**：当前调研结论是"不需要"，因为设计文档从未提及要支持 SQLite 以外的数据库；若用户对未来技术路线有不同预期（如计划支持 PostgreSQL 作为可选历史存储后端），需要提前告知，会改变本结论。
4. **ruamel.yaml 的"往返保留注释写回"能力**：当前设计的 `PUT /api/config/yaml` 是整体替换语义，不需要该能力；但如果未来产品面要做"配置文件可视化编辑器局部字段编辑并保留其余注释"，需要重新评估引入 ruamel.yaml，目前先记录不采纳的理由，供未来复查。
