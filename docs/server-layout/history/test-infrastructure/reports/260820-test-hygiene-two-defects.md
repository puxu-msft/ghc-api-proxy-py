# 两个测试卫生缺陷的只读诊断

日期：2026-08-20

调查范围：`/home/xp/src/ghc-api-proxy-py`。除本报告外，没有修改仓库文件。所有运行测试、探针和变异均在 `/tmp/ghc-api-proxy-py-test-hygiene.5yMIx0/repo` 这份副本中完成。

证据强度采用三档：**强——足以据此修改**，表示源码、可重复实验或正向变异控制直接支持结论；**中——明确候选**，表示静态机制完整，但没有逐条运行验证；**弱——搜索线索**，只用于指引后续检查，不据此宣称已有失败。

## 问题 A：`test_module_boundaries.py` 污染同进程后续测试

### A1. 精确机制

**结论 A1.1（强——足以据此修改）：`reachable_from()` 不是“卸载一个入口”，而是删除 `sys.modules` 中名称以字面量 `app` 开头的全部条目。** 列表推导在 `tests/unit/test_module_boundaries.py:19` 先冻结所有满足 `name.startswith("app")` 的名称，`tests/unit/test_module_boundaries.py:20` 逐个删除；该谓词包含裸包 `app`、所有 `app.*`，理论上也会误含名称如 `application`。随后 `tests/unit/test_module_boundaries.py:21` 才重新导入一个目标模块，`tests/unit/test_module_boundaries.py:22` 只返回导入结束后存在的 `app.*` 名称。原有模块对象并未消失：测试模块、函数的 `__globals__`、类和实例仍持有它们，只是它们已不再是 `sys.modules` 对同名模块给出的对象。

**结论 A1.2（强——足以据此修改）：在题给 `tests/unit tests/http` 的完整收集面上，三个边界测试连续制造了多代同名模块。** 我用一个仅放在 `/tmp` 的 pytest hook，在完整收集 1154 个测试、仅执行三个边界测试时，于每次调用前后按对象身份比较 `sys.modules`。第一次调用 `reachable_from("app.server.pipeline_app")`，调用前有 219 个 `app*` 模块；它全部删除后重新导入 113 个，113 个同名条目均换成第二代对象，另 106 个未重导入。第二次调用 `reachable_from("app.pipeline.translation_driver.content")`，又删除这 113 个，只重导入 4 个第三代对象。第三次调用 `reachable_from("app.pipeline.exceptions")`，删除这 4 个，最终只留下 `app`、`app.pipeline`、`app.pipeline.exceptions` 三个对象，其中前两个再次换代。对应调用点是 `tests/unit/test_module_boundaries.py:27`、`:40`、`:55`。第一次被替换的关键模块包括 `app.config.schema`、`app.model_provider`、`app.pipeline.rate_limiting`、`app.server.composition`、`app.server.pipeline_app`；第一次删除且未重导入的关键模块包括 `app.cli`、`app.debug.models`、`app.lifecycle.pidfile`、`app.pipeline.executor`、`app.routes.*`。精确删除集合无需人工枚举：它严格等于每次到达 `tests/unit/test_module_boundaries.py:19` 时所有满足 `name.startswith("app")` 的键。

**结论 A1.3（强——足以据此修改）：两条限流断言混用了第一代生产对象和边界测试结束后重新导入的第四代枚举。** pytest 在执行测试前先收集并导入测试模块；因此 `tests/http/test_pipeline_app.py:26-44` 在收集阶段绑定了第一代 `ProxyConfig`、`build_chain`、`create_pipeline_app` 等对象。第一代 `app.server.composition` 在 `src/app/server/composition.py:39` 把第一代 `RateLimiter` 绑定进模块全局，`build_chain()` 又在 `src/app/server/composition.py:229` 用这个绑定构造限流器；`RateLimiter` 在 `src/app/pipeline/rate_limiting.py:111`、`:171` 存放第一代 `RateLimitMode` 成员。三个边界测试结束时 `app.pipeline.rate_limiting` 已不在 `sys.modules`，于是两条 HTTP 测试在函数体内执行 `from app.pipeline.rate_limiting import RateLimitMode` 时重新生成另一代枚举，位置是 `tests/http/test_pipeline_app.py:519` 和 `:548`。`chain.rate_limiter_for("ghc").mode` 仍来自第一代类，断言右侧来自新一代类；即使两边 `repr` 都是 `<RateLimitMode.LIMITED: 'limited'>` 或 `<RateLimitMode.NORMAL: 'normal'>`，枚举成员身份仍不同，所以 `tests/http/test_pipeline_app.py:543` 和 `:570` 的 `is` 为假。

**结论 A1.4（强——足以据此修改）：这不是“全量扫描习惯”问题，而是任意同进程组合都可能触发的全局状态泄漏。** `/tmp` 副本中只运行三个边界测试再运行两条 HTTP 测试，稳定得到 `3 passed, 2 failed`，两条失败均显示“值和显示相同但对象身份不同”。只运行 HTTP 组时没有边界测试删除模块，因此不存在代际分裂。测试分组可以减少相遇机会，却不能把未还原的进程全局状态变成局部状态。

### A2. 影响面与搜索判据

搜索采用四类判据：一是 `is EnumType.MEMBER` 或其他命名对象身份比较；二是 `isinstance(value, AppClass)`；三是测试函数体内的 `from app...`，它会在边界测试后取得新一代对象；四是字符串形式的 `monkeypatch.setattr("app....", ...)`、模块级 cache 或 registry，它们会通过当前 `sys.modules` 命中另一代模块。搜索命令使用 `rg`，并以 AST/运行探针剔除普通的 `is None`、`is True` 和内建类型 `isinstance`。下列“候选”不等于每条都会失败：只有生产者和断言、patch 或 cache 落在不同代时才会受害。

#### 已实证的额外受害者

**结论 A2.1（强——足以据此修改）：`tests/unit/test_debug_models.py::test_a_missing_token_is_reported_with_the_command_that_fixes_it` 是同类的 `isinstance` 受害者。** 该测试在函数内于 `tests/unit/test_debug_models.py:375` 导入新一代 `NoGitHubToken`，但模块级绑定的第一代 `describe_failure` 仍用第一代异常类做类型识别。把边界测试排在它前面后，`tests/unit/test_debug_models.py:377` 从预期含 `ghc-api-proxy auth` 变成仅返回 `no token`，实测 `3 passed, 1 failed`。

**结论 A2.2（强——足以据此修改）：`tests/unit/test_config_paths.py::test_build_chain_gives_each_provider_its_own_token_file` 是模块对象身份/patch 受害者。** `tests/unit/test_config_paths.py:101` 的字符串 patch 通过当前 `sys.modules` 修改新一代 `app.server.composition.FileTokenProvider`，而 `tests/unit/test_config_paths.py:112` 调用收集期绑定的第一代 `build_chain`；后者读取第一代模块全局。边界测试在前时，记录列表在 `tests/unit/test_config_paths.py:113` 仍为空，实测 `3 passed, 1 failed`。

**结论 A2.3（强——足以据此修改）：`tests/unit/test_direct_driver.py::test_named_strategies_bound_each_reason_separately` 也是跨代类型/策略映射受害者。** 它在函数内于 `tests/unit/test_direct_driver.py:321-323` 导入新一代 config、budget 和 ledger，却把这些对象交给收集期绑定的第一代 driver、异常和 registry。边界测试在前时，`tests/unit/test_direct_driver.py:338` 得到 `failure is not retryable`，而非预期的 `githubTokenExpired`，实测 `3 passed, 1 failed`。同形的下一条测试在 `tests/unit/test_direct_driver.py:343-345` 再次作函数内导入，应视为明确候选。

#### 高风险候选清单

**结论 A2.4（中——明确候选）：函数内动态导入是最短的跨代桥。** 除上述已实证位置外，当前搜索还找到 `tests/unit/test_lifecycle_activation.py:134`、`tests/unit/test_lifecycle_pidfile.py:177`、`tests/unit/test_model_provider.py:435`、`tests/unit/test_translation_driver.py:269`、`:382`。其中 `test_translation_driver.py` 在题给执行顺序中位于边界测试之后而仍通过，说明它当前传递的值恰好不依赖类身份；这只能把它降为条件候选，不能证明删除/重导入是安全操作。

**结论 A2.5（中——明确候选）：字符串模块 patch 会 patch 新模块，却可能调用旧函数。** 候选包括 `tests/unit/test_cli.py:136`、`:181`、`:197`、`:207`、`:217`、`:232`、`:243`、`:266`、`:268`、`:286`、`:288`，以及 `tests/unit/test_debug_models.py:456-457`、`:531-532`、`:554`、`:591`、`:611`、`:631`、`:646`。这些测试通常在当前文件顺序中早于边界测试，所以题给命令没有暴露它们；改变选择顺序或显式先运行边界测试即可使 patch 与调用点分代。`tests/unit/test_config_paths.py:101` 已由 A2.2 给出实证。

**结论 A2.6（中——明确候选）：自定义枚举的身份断言构成直接受害面。** 除两条已失败的 HTTP 断言外，搜索到以下组：`tests/unit/test_builtin_subscribers.py:106`；`tests/unit/test_lifecycle_shutdown.py:25`、`:32`、`:37`、`:42`、`:48`、`:53`、`:57`、`:70`、`:74`、`:79-80`；`tests/unit/test_direct_driver.py:118`、`:130-131`、`:142`；`tests/unit/test_rate_limiting.py:84`、`:100`、`:107`、`:115`、`:148`、`:152`、`:156`、`:165`、`:169`、`:171`、`:182`、`:189`；`tests/unit/test_phase5_core.py:12`、`:14`、`:17`；`tests/unit/test_models_common.py:72-75`；`tests/unit/test_sse_assembly.py:320-323`；`tests/unit/test_upstream_error_normalization.py:52`、`:61-62`、`:71`、`:78`、`:86`、`:94`；`tests/unit/test_pipeline_events.py:165`；`tests/unit/test_server_inbound.py:17-20`、`:27`、`:47`；`tests/unit/test_lifecycle_cleanup.py:171`。这些测试若生产者与期望值都来自收集时绑定的同一代，会继续通过；我把边界测试排在 `test_rate_limiting.py:96` 和 `test_upstream_error_normalization.py:65` 前面，两条代表样本仍通过，证实“出现 `is`”只是必要风险信号，不是充分失败条件。

**结论 A2.7（中——明确候选）：app 自定义类的 `isinstance` 断言也会在跨代时失效。** 主要位置是 `tests/unit/test_upstream_error_normalization.py:50`、`:60`、`:69`、`:85`、`:92`；`tests/unit/test_responses_stream_parser.py:68`、`:325`、`:352`、`:371`、`:485`、`:515`、`:573`、`:721-722`、`:771`、`:784`、`:829`、`:873`、`:898`、`:984`、`:1190`；`tests/unit/test_direct_driver.py:235`、`:257`、`:314`；`tests/unit/test_cli.py:191`。这里同样只有跨代才失败；普通内建类型和第三方类型断言已从清单排除。

**结论 A2.8（中——明确候选）：模块级 cache 与 registry 会被复制成互不相见的状态。** 当前唯一 `functools.cache` 是 `src/app/lifecycle/pidfile.py:199` 的 `_pidfd_signaller()`；删除并重导入会产生独立 cache，而旧调用者仍持有旧函数和旧 cache。模块级映射/registry 风格状态还包括 `src/app/server/inbound.py:46` 的 `_BY_PATH`、`src/app/pipeline/direct_driver/__init__.py:46` 的 `DRIVERS`、`src/app/pipeline/context.py:22` 的 `ALLOWED_TRANSITIONS`，以及以枚举成员为键的 `src/app/observability/request_log.py:33-44`。当前没有证据表明题给顺序已让这些状态产生额外红测；它们是进程内出现“两份真相”的结构性影响面，而非已确认失败数。

### A3. 修法选项与代价

#### 选项 A：在 `reachable_from()` 内保存并还原 `sys.modules` 快照

做法是先保存所有 `name == "app" or name.startswith("app.")` 的名称到模块对象映射；探测时删掉这些名称并导入目标；在 `finally` 中删除本次生成的所有 `app`/`app.*` 条目，再把旧映射放回。返回值必须在还原前冻结。前缀应改成精确的 `app` 包判定，避免误删 `application` 之类的模块。

**评价（强——足以据此决策）：该方案真正修复“`sys.modules` 未还原”这一根因，且改动最小。** 它会让后续 import 再次取得原模块对象，直接消除当前枚举、`isinstance`、字符串 patch 和 cache 分代。代价是实现必须用 `try/finally`，还要删除探测期间新增但快照中没有的 `app.*`；只做 `sys.modules.update(snapshot)` 不够，因为新条目会残留。它不能撤销 import 写到 `sys.modules` 之外的副作用，例如第三方 registry、logging handler 或后台任务；当前入口未见这类实证，但这是方案的语义上限。测试期间仍存在一个短暂的全局替换窗口，若同进程有并发 import，另一个任务仍可能观察到临时状态。

#### 选项 B：把可达性探测放进子进程

父测试以 `subprocess` 启动同一解释器和项目环境，子进程从干净的 `sys.modules` 导入指定入口，将可达模块名以 JSON 或逐行文本写回；父进程只断言结果和退出码。三个入口可以各用一个子进程，确保每个入口都从同样干净的解释器开始，也可以用一个参数化 helper 每次独立启动。

**评价（强——足以据此决策）：这是最完整地消除根因的方案。** 父进程从不删除自己的模块；子进程内即使不还原，进程退出也同时丢弃模块、cache、registry 和 import 副作用。它还比当前做法更准确地测量“一个干净进程导入入口会带来什么”，而不是“保留所有第三方模块、只拔掉 app 后重导入会带来什么”。代价是每条用例多一次解释器启动，错误回传和 `PYTHONPATH`/当前工作目录必须明确；helper 应保持简单，不要扩张成验收框架或新门禁。

#### 选项 C：移出 `tests/unit`，成为独立测试组

例如放到 `tests/architecture/`，像 `tests/tui/` 一样在 `pyproject.toml:53-58` 的默认目录发现中排除，并提供按需命令 `uv run pytest tests/architecture`。这符合项目“目标不同的组各有入口”的规则，也避免常规 unit 进程遇到它。

**评价（强——足以据此决策）：单独移动只迁走症状，不修复根因。** 用户仍可显式把该目录和别的测试放进同一 pytest 进程，届时它继续泄漏全局状态。只有约定每次独立起 pytest 进程时，进程退出才带来操作上的隔离。因此该方案适合表达测试目标和运行成本，但应与选项 A 或 B 配对；不能单独宣称已修好。

#### 选项 D：改为静态 import graph/AST 检查

可以不执行 import，而解析依赖图或使用现有索引回答可达性。

**评价（中——明确候选）：它消除了运行时状态污染，却改变了被测事实。** Python 的 package `__init__`、条件 import、动态 import 和导出副作用正是该测试原先要看见的；静态图很容易漏掉这些行为。除非项目明确把“静态依赖”定为新契约，否则不宜用它替代当前运行时探测。

### A4. 首选

**首选（强——足以据此修改）：选项 B，把三个 import 可达性探测放进短小子进程 helper；测试是否另分 `tests/architecture/` 作为组织决策，不作为修复条件。** 理由有三点：第一，父 pytest 进程完全不碰 `sys.modules`，从机制上消除所有已实证和候选受害面；第二，每个入口从真正干净的解释器开始，测量对象比“在已收集 1154 个测试的进程里局部卸载 app”更符合测试名；第三，子进程天然回收 cache、registry 和包外 import 副作用，而快照只能恢复模块表。若启动成本经实测不合适，选项 A 是可靠的次选；但无论选哪一个，都不需要也不应引入全量测试门、CI 统一扫描、覆盖率目标或证明框架。

## 问题 B：`test_a_keep_alive_wait_leaves_no_asyncio_noise` 的断言面过大

### B1. 原始失效、提交历史与当前可达性

**结论 B1.1（强——足以据此修改）：该测试守的是一个具体的 shield observer 泄漏，不是泛化的“asyncio 必须永远无噪声”。** 测试注释位于 `tests/unit/test_stream_delivery.py:247-248`：一次 keep-alive 表示上游 pull 活得比一次等待更久；上游空流结束时，pull 以 `StopAsyncIteration` 完成，已经超时的 shield observer 会把这个正常结束报告为 `StopAsyncIteration exception in shielded future`。生产代码长注释位于 `src/app/pipeline/delivery/stream.py:69`，明确比较 `wait_for(shield(task))` 与 `asyncio.wait`：前者超时后让底层 task 继续，但遗留一个负责报告结果的 shield future；下一轮再 shield 同一个 pull 不会替换旧 observer，最终每个跨过 keep-alive 的旧 observer 都可能报告异常。

**结论 B1.2（强——足以据此修改）：引入修复和测试的是提交 `7a51902c58551bc7e81a72ac4ee183047728c908`，提交信息为 `fix: wait on the upstream pull without leaving asyncio a last-resort observer`。** `git log -S'wait_for(asyncio.shield'` 与 `git log -S'StopAsyncIteration exception in shielded future'` 都命中该提交。提交把原先的 `yield await asyncio.wait_for(asyncio.shield(task), timeout=timeout)` 改成直接 `await asyncio.wait({task}, timeout=timeout)`，并同时新增当前测试。

**结论 B1.3（强——足以据此修改）：当前代码结构已经排除这个“旧 shield future 未取回异常”的精确机制，但回归仍可能重新引入。** 当前 `_events_with_ping` 在 `src/app/pipeline/delivery/stream.py:70` 直接等待原 task，不创建 shield future；task 完成后在 `src/app/pipeline/delivery/stream.py:71-75` 直接读取 `task.result()` 并把正常的 `StopAsyncIteration` 转成生成器结束。当前路径没有可遗留的 shield wrapper，所以该精确失效现在不可达。它仍值得回归测试，因为把 `asyncio.wait` 换回看似等价的 `wait_for(shield(...))` 是合理但错误的维护变更。

**结论 B1.4（强——足以据此修改）：当前断言捕获的是整个共享 loop 在 1.2 秒窗口内报告的所有消息，超出了自己的对象。** `tests/unit/test_stream_delivery.py:249-252` 取得当前 loop、替换它唯一的 exception handler，并把所有 context 的 `message` 无条件追加到同一列表；`tests/unit/test_stream_delivery.py:253-257` 在全局 handler 生效期间运行等待并只在最后恢复；`tests/unit/test_stream_delivery.py:258` 断言整个列表为空。asyncio 的“exception was never retrieved”由 future 的析构/GC 时机触发，别的测试早先留下、绑定到同一 loop 的对象只要在这个窗口被回收，就会进入这份列表。该测试既没有检查 context 的 `future`/`task` 是否由自己创建，也没有给自己一个私有 loop，因此偶发假红符合实现机制。

### B2. 变异验证：测试仍有分辨力

**结论 B2.1（强——足以据此修改）：测试没有失去分辨力；把实现改回 shield 形状会因目标消息而变红。** 实验副本由 `cp -a /home/xp/src/ghc-api-proxy-py/. /tmp/ghc-api-proxy-py-test-hygiene.5yMIx0/repo` 创建；复制时源与副本 HEAD 均为 `1a21acd4a082d91ea6ba824d4493c701949be59c`。运行时显式设置 `PYTHONPATH=/tmp/ghc-api-proxy-py-test-hygiene.5yMIx0/repo/src`，并在每轮先用 `inspect.getsourcefile()` 证明加载的是 `/tmp` 下的 `stream.py`，而非仓库或已安装副本。

基线：`uv run pytest tests/unit/test_stream_delivery.py::test_a_keep_alive_wait_leaves_no_asyncio_noise -q` 为 `1 passed in 1.70s`。变异：仅把 `src/app/pipeline/delivery/stream.py:69-82` 的直接 `asyncio.wait` 分支替换为 `await asyncio.wait_for(asyncio.shield(task), timeout=timeout)`，保留当前 cleanup 结构；运行时探针显示 `HAS_ASYNCIO_WAIT=False`、`HAS_SHIELD=True`。同一测试随即在 `tests/unit/test_stream_delivery.py:258` 失败，`reported` 精确为 `['StopAsyncIteration exception in shielded future']`，结果 `1 failed in 1.81s`。恢复变异后，探针显示 `RESTORED_ASYNCIO_WAIT=True`、`RESTORED_NO_SHIELD=True`，同一测试恢复为 `1 passed in 1.71s`。

**结论 B2.2（强——足以据此修改）：问题只在观察范围，不在测试的正向控制能力。** 上述红灯由预期消息触发，不是超时、hang 或无关异常；因此删除测试会丢掉一个已证明能咬住真实回归的行为见证。

### B3. 修法选项与代价

#### 选项 B-A：给测试创建私有 event loop，保留行为级断言

把该用例改成同步测试，在内部 async helper 中安装 handler、运行 `collect()`，再用 `asyncio.run(helper())` 或显式 `asyncio.Runner` 创建并关闭只属于本测试的 loop。此前的 future 不可能绑定到一个尚未创建的新 loop；这个 loop 上的 task/future 都由本次 helper 及其调用链创建，所以 `reported == []` 的范围从“共享 loop 的所有历史对象”收窄到“本测试这次运行产生的对象”。

**评价（强——足以据此决策）：该方案保留用户可见失败信号，同时真正收窄观察主体。** 它不需要按错误字符串放宽断言，也不依赖 `_events_with_ping` 的内部变量。代价是该测试不再使用 `pytest.mark.asyncio` 提供的 loop，并需确保 helper 完成后再断言列表。我在 `/tmp` 另做了候选验证：私有-loop 版本对当前代码为 `1 passed in 1.62s`；同一 shield 变异已由运行时探针确认生效后，它仍以目标消息失败，`1 failed in 1.88s`。因此这个收窄没有牺牲分辨力。

#### 选项 B-B：仍用共享 loop，但只接收本测试创建对象的 context

可以记录本测试创建的 task/future，并让 handler 只收集 `context["task"]` 或 `context["future"]` 属于该集合的报告。

**评价（中——明确候选）：理论上最窄，实际实现对本缺陷不自然。** 原失效报告中的 `future` 是 `asyncio.shield()` 内部返回的 wrapper，不是测试直接持有的 pull task；要拿到它，需要 monkeypatch `asyncio.shield`、增加生产注入点或依赖 asyncio 私有关系。复杂度高于私有 loop，而且容易把未来的等价 observer 泄漏过滤掉。

#### 选项 B-C：改成实现级守卫，禁止该路径调用 `asyncio.shield`

测试可 monkeypatch `asyncio.shield` 为立即失败，运行一个确实跨过 keep-alive 的场景；或用静态检查固定 `_events_with_ping` 不含 shield。

**评价（中——明确候选）：确定且没有 GC 噪声，但守的是实现拼写，不是失效行为。** 它能拦住本次回退，却可能漏掉另一种同样遗留 observer 的包装方式；静态检查还容易演化成被等价写法绕过的 architecture guard。既然私有 loop 能保留行为观测且变异已证明有效，没有必要降级为实现字符串检查。

#### 选项 B-D：子进程运行这条测试

让一个新 Python 进程创建 loop、执行场景并回传报告。

**评价（强——足以据此决策）：隔离最彻底，但比需要的更重。** 它能排除所有同进程历史对象，代价是解释器启动和错误回传。问题 A 的 import 测试本身需要新进程语义；问题 B 只需要一条新 loop，进程隔离的收益有限。

#### 选项 B-E：删除测试

**评价（强——足以据此决策）：不推荐。** shield 变异已经让它以精确目标消息变红，证明它仍有分辨力。删除会解决假红，也会同时删除对提交 `7a51902` 真实失效的唯一直接行为见证。

### B4. 首选

**首选（强——足以据此修改）：选项 B-A，把测试改成同步外壳加 `asyncio.run()`/`asyncio.Runner` 私有 loop，并保留现有行为断言。** 它直接收窄 loop 级观察范围，不按消息白名单掩盖未知错误，不绑定 shield 的内部对象；更重要的是，`/tmp` 正反变异已经证明“当前实现绿、旧 shield 实现红”。无需删除测试，也无需新测试组、全量门禁或证明基础设施。

## 实验隔离与仓库未修改说明

**结论（强——足以审计）：所有可执行实验和所有变异都发生在 `/tmp` 副本。** 创建副本后，所有测试命令都在绝对路径 `/tmp/ghc-api-proxy-py-test-hygiene.5yMIx0/repo` 下执行，所有 `Edit` 目标也都在该路径；运行时用 `inspect.getsourcefile()` 和显式 `PYTHONPATH` 验证加载层。每次 shield 变异后都精确反向替换并重跑基线；恢复后 `/tmp` 的 `stream.py` 与活跃仓库对应文件按 `cmp` 相同。调查期间活跃同伴又修改了 `tests/unit/test_stream_delivery.py:534` 附近一条无关测试的超时保护，因此最终整文件 `cmp` 不同；差异只在副本创建后同伴新增的那段，目标测试 `:245-258` 已恢复为副本基线。仓库调查前就有多处活跃修改；本调查没有执行任何针对仓库源码或测试的写命令。唯一写入仓库的是用户授权的新报告 `docs/tmp/260820-test-hygiene-two-defects.md`。
