# Bridge 三个已放行 source 连续 squash 只读预检

- **评审范围**：只读预检主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39`，以及三个 clean、已放行 source：capability `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`、History `fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`、stream `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。覆盖各自完整 source range 与净 pathset、三对路径／hunk 重叠、连续 `merge --squash` 可行性、必须保留的语义并集、最小 main-side pytest selectors和 reviewed-source archive targets。本轮没有执行 merge、commit、ref更新、测试、部署、cutover或清理；唯一主树写入为本报告。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major。** 推荐且唯一受支持的顺序是 **capability → History → stream**。三片可以依次 `git merge --squash <exact-tip>`，但不能盲目自动接受结果：capability与History在 `src/app/anthropic/client.py` 有真实冲突；stream落到前两片组合态时，`src/app/anthropic/client.py` 与 `src/app/pipeline/executor.py` 必须语义合成；`tests/smoke/test_anthropic_responses_route.py` 虽为capability／stream共同修改路径，但成对预览可自动文本合并，仍须检查“保留capability测试、删除旧stream不支持预期”的语义结果。
- **blocker 数**：0。
- **major 数**：0。
- **明确禁止**：fast-forward、regular merge、`--ff`、`--ff-only`、`--no-ff`、单笔或range cherry-pick，以及把三个source的提交直接带入main ancestry。每片只允许exact source tip的 `git merge --squash`，解决该片冲突、核验并形成一个新的non-merge main commit后，才能开始下一片；不得在未commit的index／worktree上叠加第二次squash。
- **证据边界**：三个source各自已有exact-tip放行，不等于三片组合态已被运行验证。本报告回答直接集成形状，不把candidate-side绿灯冒充main-side组合结果，也不设计新的验证系统。

## 双视角覆盖证据

### 机械核对视角

1. 每个承载结论的shell都在同一调用内打印并验证物理cwd、Git top-level、branch与完整HEAD。主线精确为`main@b91e58a…`；三个source worktree分别精确为`8bff1c3…`、`b1df8f9…`、`f3922a9…`且status为空。
2. 三个source的merge-base均精确为`b91e58a…`，且`b91e58a…`均为source tip祖先。Capability为1个non-merge commit；History为4个线性non-merge commits；stream为3个线性non-merge commits。三个聚合range的`git diff --check`均无输出。
3. 以range diff交叉核对净pathset：capability为2路径，History为9路径，stream为17路径。三方净交集只有`src/app/anthropic/client.py`；History／stream另交叠`src/app/pipeline/executor.py`；capability／stream另交叠`tests/smoke/test_anthropic_responses_route.py`。
4. 以`git merge-tree b91e58a <left> <right>`做成对三方预览。Capability＋History为1个changed-both路径且有1组冲突标记；capability＋stream为2个changed-both路径但只有1组冲突标记；History＋stream为2个changed-both路径且有2组冲突标记。由此区分“同路径修改”与“真实文本冲突”，不把changed-both一律误报为冲突。
5. 逐版本读取共享函数确认冲突不是纯格式：capability给`_send_responses()`注入`ReasoningCapabilityFacts`；History把返回契约升级为`AnthropicAttemptResult`并把转换事实交给executor；stream给同一方法增加`stream`参数、raw upstream成功路径和stream finalize观测。任取一侧整文件都会丢失另外两侧合同。
6. `refs/archive/**`当前为空；下文三个推荐名称均未占用。Archive target取reviewed source tip，不取未来main squash commit。

### 第一人称执行视角

1. **作为第一片执行者**：我先闭合并提交主树现有living docs，使index与tracked worktree为空，再重新gate actual main；然后只squash capability exact tip。该片在代码preimage未漂移时应形成两个精确source结果文件，运行capability selectors并提交一个non-merge commit。
2. **作为第二片执行者**：我从capability main commit开始squash History exact tip。Git必然在`client.py`要求裁决；我不会选整文件`ours`／`theirs`，而是保留capability model facts注入，同时采用History typed attempt result与request／response conversion facts。解决后先运行capability＋History selectors，再形成第二个non-merge commit。
3. **作为第三片执行者**：我从前两片组合main commit开始squash stream exact tip。在`client.py`合成raw stream与typed attempt result，在`executor.py`只删除旧stream拒绝门而保留History最终事实与callback顺序；在共享smoke测试中保留capability新增覆盖并删除旧`responses_stream_not_supported`参数行。解决后运行三片联合最小selectors，再形成第三个non-merge commit。
4. **作为归档执行者**：每片main commit及该阶段selectors通过后，才创建对应immutable reviewed-source archive ref，target必须是source tip。归档不隐含删除branch／worktree；三片最终组合门通过前不做清理。
5. **失败分支**：任何identity漂移、source pathset漂移、非目标path进入cached集合、意外冲突、语义清单缺项或selector失败都停止在当前阶段；不stash、不restore、不force、不切换为FF／regular merge／cherry-pick来绕过。

## 推荐顺序与理由

### 1. Capability `8bff1c3…`

先落最小的转换能力事实层。它只修改两个路径，先把“resolved model capability facts必须参与每次Responses request转换”的输入合同固定下来，也让下一片History在采集`converted_request.facts`时面对最终转换入口，而不是先建立facts采集后再回头改转换签名。

### 2. History `b1df8f9…`

第二片把non-stream send结果升级为typed `AnthropicAttemptResult`，并建立final response validation、conversion facts、usage、success callback与History commit顺序。它与capability只在`client.py`发生真实冲突，语义合成边界集中且可由两组既有selectors共同约束。

### 3. Stream `f3922a9…`

最后才放开raw stream transport。这样stream必须显式适配已经固定的capability输入合同与History typed result／lifecycle合同，不会以旧的`httpx.Response`返回形状或旧executor片段覆盖前两片。该阶段同时收口唯一跨模块接缝：client raw stream、executor旧拒绝门、route smoke旧失败预期。

顺序不是因为另外两种顺序在Git层面绝对不可行，而是为了把合同按“转换输入事实 → non-stream最终事实与发布顺序 → stream transport放行”单向叠加，减少返工与漏保留风险。无论顺序如何，`client.py`都不能整文件取一侧；推荐顺序使最后结果最容易按职责解释。

## 完整 source ranges 与净 pathsets

### Capability完整range

Base：`b91e58a29324b11840002efc53ed6f869b800c39`。Tip：`8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。

提交顺序：

1. `8bff1c3fbd721060a87f18b0ef9d90d7d998a997` — `fix: fail closed on ambiguous reasoning efforts`

净pathset：

- `M src/app/anthropic/client.py`
- `M tests/smoke/test_anthropic_responses_route.py`

### History完整range

Base：`b91e58a29324b11840002efc53ed6f869b800c39`。Tip：`b1df8f910c590033e83d5cafcd5e514f12bab937`。

提交顺序：

1. `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f` — `fix: persist Responses history facts`
2. `2e3a6d2022244a6bca0e2db05e079bc27d94a585` — `fix: harden response history facts`
3. `864cfa30e291768cbc7b080fce80d9be4cbf2d83` — `fix: publish response observers after final facts`
4. `b1df8f910c590033e83d5cafcd5e514f12bab937` — `fix: order response success callbacks`

净pathset：

- `M docs/2604-rewrite/BACKLOG.md`
- `M src/app/anthropic/client.py`
- `A src/app/anthropic/response_validation.py`
- `M src/app/history/consumer.py`
- `M src/app/pipeline/context.py`
- `M src/app/pipeline/executor.py`
- `M tests/component/test_history_store.py`
- `M tests/component/test_pipeline_executor.py`
- `A tests/unit/test_anthropic_response_validation.py`

### Stream完整range

Base：`b91e58a29324b11840002efc53ed6f869b800c39`。Tip：`f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。

提交顺序：

1. `2087f8f02516136314985f5c48bdee20b2f4b861` — `feat: route Responses streams to Anthropic SSE`
2. `bc436af647507df4ea45f3b01ca8942fade4f036` — `fix: harden Anthropic Responses streaming`
3. `f3922a9ba9f90e4eea598dac1d899ebbe18985e8` — `fix: harden responses stream lifecycle`

净pathset：

- `M src/app/anthropic/client.py`
- `M src/app/delivery/__init__.py`
- `M src/app/delivery/anthropic_sse.py`
- `A src/app/delivery/responses_anthropic_stream.py`
- `M src/app/openai/responses_stream_parser.py`
- `M src/app/pipeline/executor.py`
- `M src/app/routes/anthropic.py`
- `M src/app/streaming/keepalive.py`
- `M src/app/streaming/openai_sse.py`
- `M src/app/streaming/sse.py`
- `M tests/http/test_anthropic_routes.py`
- `M tests/smoke/test_anthropic_block_delivery.py`
- `M tests/smoke/test_anthropic_responses_route.py`
- `A tests/smoke/test_anthropic_responses_stream_route.py`
- `M tests/unit/test_responses_stream_parser.py`
- `M tests/unit/test_streaming_resilience.py`
- `M tests/unit/test_streaming_sse.py`

## 重叠文件与hunks

### `src/app/anthropic/client.py`：三方交集，必须两轮语义合成

Capability在其source约`215–323`行修改`_send_responses()`并新增`_reasoning_capabilities()`：转换必须使用resolved model的显式effort／budget facts，多effort、重复／空effort、unknown limits均fail closed。

History在其source约`77–81`、`179–195`、`236–285`行新增`AnthropicAttemptResult`、`send_prepared_attempt()`与typed转换结果：executor需要拿到`converted_request_facts`和non-stream `converted_response`，而legacy `send_prepared()`仍返回裸`httpx.Response`。

Stream在其source约`164–239`行给`_send_responses()`增加`stream`参数，删除“Responses stream不支持”分支，把`stream`传给target，并在stream成功时不读body、不关闭upstream、直接把raw response交给stream route；约`286–341`行扩展stream finalize的estimated usage与error观测。

最终语义必须同时满足：

1. 保留`ReasoningCapabilityFacts`／`ReasoningEffortBand`导入与`_reasoning_capabilities(resolved_model)`。
2. 保留`AnthropicAttemptResult`、`send_prepared_attempt(prepared, stream=...)`，以及legacy `send_prepared()`只返回`result.response`。
3. `_send_responses(prepared, *, stream)`每次都用当前`prepared.resolved_model`重取capability facts，并以`reasoning_capabilities=...`转换当前prepared wire，保证PRE_SEND改写后的每次attempt重新转换。
4. target调用使用`stream=stream`。非成功响应经`_responses_error_response()`转换／关闭后，包装为`AnthropicAttemptResult(response=..., converted_request_facts=...)`。
5. stream成功响应不得`aread()`或`aclose()`；返回`AnthropicAttemptResult(response=upstream, converted_request_facts=converted_request.facts, converted_response=None)`，由stream route拥有后续读取与关闭。
6. non-stream成功路径保持History的typed result：解析、响应转换、`converted_request_facts`与`converted_response`均保留，并只在该路径finally关闭upstream。
7. 保留stream的`observe_stream_finalized(..., usage_estimated=False)`、ERROR payload与FINALIZE error字段。

禁止在该文件使用整文件`ours`／`theirs`，也禁止全局`-X ours`／`-X theirs`。Capability＋History、capability＋stream、History＋stream的成对预览都在此文件产生真实冲突标记，自动文本结果不是语义证明。

### `src/app/pipeline/executor.py`：History／stream交集，必须语义合成

Stream相对base只在约`193–201`行删除旧`responses_stream_not_supported`前置拒绝门。History在同一控制流大幅改写attempt send与success发布：约`280`行改用`send_prepared_attempt()`；约`304–389`行读取并验证final body、运行response hooks、写入normalized response、final payload、request／response conversion facts与usage；约`391–421`行要求success callbacks先于RESPONSE／FINALIZE／History commit且失败路径零成功发布。

最终结果只能删除旧stream拒绝门；必须完整保留History的typed attempt consumption、final response validation、facts写入、`coordinator.notify_success()`／`limiter.report_success()`失败转失败生命周期、RESPONSE一次、FINALIZE一次和History finalized一次。不得用stream tip的整文件覆盖History executor，也不得因stream请求不走non-stream body validation而删除History的`if not request.stream`边界。

### `tests/smoke/test_anthropic_responses_route.py`：capability／stream共同修改，可自动文本合并但需语义核对

Capability约`205–569`行扩展PRE_SEND hook、model catalog harness并新增六组reasoning capability route测试。Stream只删除旧参数化场景中“Responses streaming返回`responses_stream_not_supported`”的case。成对`merge-tree`把文件列为changed-both，但该pair只有`client.py`出现冲突标记；预计文本自动合并。

最终文件必须保留capability全部harness与六组测试，同时只删除已被stream实现推翻的旧“不支持stream”预期。若capability测试消失，或旧case仍期待400，均视为语义合并失败。

### 其余路径

除上述三路径外没有source间净pathset重叠。按推荐顺序，History的其余8路径应逐一等于History tip结果；stream的其余14路径应逐一等于stream tip结果。Standalone source的聚合patch-id和共享文件result blob只适用于“单片落到`b91e58a…`”的旧审计，不能拿来要求组合态共享文件等于任一source tip；组合态应以非重叠blob相等＋共享文件语义清单＋具名selectors验收。

## 最小 main-side pytest selectors

以下只覆盖关键主路径与本轮三片合成的失败机制，不替代未来完整Acceptance、部署或cutover验证。每次在actual main物理root与当时exact HEAD上运行，并确认进程加载的`app`位于主树`src/`。

### Capability阶段

- `tests/smoke/test_anthropic_responses_route.py::test_responses_only_reasoning_uses_resolved_model_capability_facts`
- `tests/smoke/test_anthropic_responses_route.py::test_unknown_reasoning_capabilities_fail_closed_without_model_name_guessing`
- `tests/smoke/test_anthropic_responses_route.py::test_ambiguous_reasoning_effort_set_is_rejected_independent_of_order`
- `tests/smoke/test_anthropic_responses_route.py::test_responses_reasoning_budget_uses_exact_catalog_boundaries`
- `tests/smoke/test_anthropic_responses_route.py::test_pre_send_reasoning_modification_is_reconverted_with_capability_facts`
- `tests/smoke/test_anthropic_responses_route.py::test_dual_capability_auto_keeps_existing_messages_leg`

这些selectors覆盖真实ASGI route主路径、unknown／ambiguous fail closed、预算闭区间、PRE_SEND后重新转换与dual-capability Messages保留。

### History阶段

在上述capability selectors基础上增加：

- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_failed_final_response_publishes_no_success_callbacks`
- `tests/component/test_pipeline_executor.py::test_body_read_failure_does_not_calibrate_builtin_success_observer`
- `tests/component/test_pipeline_executor.py::test_throwing_success_strategy_publishes_only_failure_lifecycle`
- `tests/component/test_pipeline_executor.py::test_success_callbacks_precede_response_commit_once`
- `tests/component/test_pipeline_executor.py::test_history_preserves_request_and_response_conversion_provenance`
- `tests/component/test_pipeline_executor.py::test_history_projects_only_final_success_attempt_conversion_facts`

这些selectors覆盖final hooked response与facts主路径、validation／read／success strategy失败时零成功发布、callback顺序、request／response provenance及只投影final success attempt。

### Stream阶段与最终三片组合门

在capability＋History selectors基础上增加：

- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`
- `tests/unit/test_responses_stream_parser.py::test_empty_text_delta_conflicts_with_nonempty_authoritative_text`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_max_output_tokens_without_usage_uses_estimated_zero_usage`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop`

这些selectors覆盖真实ASGI stream主路径，以及本轮stream放行依赖的二次取消cleanup、authoritative text冲突、missing usage＋`max_output_tokens`、首body write uncertainty History和terminal seal顺序。最终门必须运行三组联合selectors；不能只运行stream六项，因为`client.py`与`executor.py`的合成可能让stream绿而capability／History退化。

最终联合selectors通过后，再对组合态受影响的`src`与上述tests运行项目既有Ruff／Pyright入口；这是常规静态检查，不新增验证基础设施。若主会话选择额外运行全仓pytest，可作为更强回归证据，但不把固定passed数量写成门。

## 可执行集成步骤

### 步骤0：主线前置

1. 完成主树现有living docs的独立checkpoint，或以其他已获授权方式使main index与tracked worktree为空；不得把本报告、`docs/tmp/**`、`verification/**`或并行WIP夹入三个代码squash commits。
2. 重新gate actual main，并确认`b91e58a…`仍为祖先。重新gate三个source worktree／branch／exact tip／clean状态，重新核对各完整range与净pathset。
3. 对三个source净pathset与actual main dirty paths求交。任一目标路径dirty即停，不stash、不restore、不覆盖。

### 步骤1：Capability squash

1. 只执行`git merge --squash 8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
2. Cached pathset必须精确为capability两路径；在actual main代码preimage仍为`b91e58a…`时，两个result blobs应等于source tip。
3. 运行capability六个selectors，检查cached diff与`diff --check`，形成一个新的non-merge main commit。
4. 禁止fast-forward、regular merge与cherry-pick。

### 步骤2：History squash

1. 从步骤1的新main commit只执行`git merge --squash b1df8f910c590033e83d5cafcd5e514f12bab937`。
2. 在`src/app/anthropic/client.py`按本文语义并集合成；其余History 8路径必须等于History tip结果。Cached pathset必须仍精确为History 9路径。
3. 运行capability六项＋History七项，检查无conflict markers、重复定义、失效import或旧裸response call-site，形成第二个新的non-merge main commit。
4. 禁止fast-forward、regular merge与cherry-pick。

### 步骤3：Stream squash

1. 从步骤2的新main commit只执行`git merge --squash f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。
2. 在`client.py`合成raw stream＋typed result＋capability facts；在`executor.py`只移除旧stream拒绝门并保留History lifecycle；核对共享route smoke测试保留capability覆盖且删除旧unsupported case。其余stream 14路径必须等于stream tip结果，cached pathset必须精确为stream 17路径。
3. 运行全部三组联合selectors，再运行常规Ruff／Pyright；检查最终commit相对parent只含stream 17路径，且三个source commits均未进入main ancestry。
4. 形成第三个新的non-merge main commit。禁止fast-forward、regular merge与cherry-pick。

### 步骤4：最终归档与收口

1. 三个main squash commits均为单parent；每片pathset符合本报告，非重叠result blobs匹配source tip，共享文件满足语义清单，最终联合selectors与静态检查全绿。
2. 创建并复读下列immutable reviewed-source archive refs；目标必须精确匹配，不能指向main squash commits：
   - `refs/archive/260807-responses-reasoning-capability` → `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`
   - `refs/archive/260807-responses-history-facts` → `b1df8f910c590033e83d5cafcd5e514f12bab937`
   - `refs/archive/260807-anthropic-responses-stream-route` → `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`
3. Archive完成不自动授权删除source branches／worktrees；清理另行确认main组合态、archive target与source clean后再做。

## 事实性发现

未发现blocker或major。三个已放行source都以`b91e58a…`为merge-base，完整range与净pathset闭合，Git可以按推荐顺序逐片形成squash载荷。真实文本冲突集中且有明确语义并集；没有合同互斥到无法组合的证据。

[minor] `src/app/anthropic/client.py`约`164–285`行 — 三片同时改变同一transport边界的参数、返回类型与ownership — 任一整文件冲突选择都会丢reasoning capability、History facts或raw stream ownership — 按本文七项语义清单手工合成，并在每轮运行两侧selectors。

[minor] `src/app/pipeline/executor.py`的base约`193–201`行与History约`280–421`行 — stream删除旧前置拒绝门，History重写同一pipeline success控制流，成对预览出现真实冲突 — 只删除旧拒绝门，保留History validation／facts／callback发布顺序。

[minor] `tests/smoke/test_anthropic_responses_route.py`的capability约`205–569`行与stream旧case约`450`行 — changed-both但预计自动文本合并，自动成功仍可能留下错误测试语义 — 保留capability六组测试并删除旧stream unsupported case。

## 主观建议

[建议] 每片独立commit而非三次squash后一次commit — 预期影响是保留三份reviewed-source到main本地提交的可审计边界，并让每阶段失败可精确归因 — 推荐严格执行“squash → resolve → stage gate → targeted tests → non-merge commit”，然后进入下一片。

[建议] 不要求组合态共享文件匹配任一source result blob／standalone patch-id — 预期影响是避免正确语义合成被错误blob门判为false-red，同时仍对所有非重叠路径保持强identity校验 — 推荐共享文件用语义清单＋联合selectors，非重叠文件继续用source blob相等。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/anthropic/client.py:164–285` | transport dispatch、capability policy、typed facts与stream ownership聚集为三方冲突热点 | 本轮必须语义合成，不在冲突解决中顺手重构；组合态稳定后可另记“拆分Responses attempt adapter”的长期重构候选 |
| `src/app/pipeline/executor.py:280–421` | success事实写入、外部callback与observer／History发布顺序集中，删除一个旧guard也会触碰大控制流 | 本轮只移除旧stream拒绝门，所有History顺序测试必须保留；不以简化控制流为由改回早发布 |
| `tests/smoke/test_anthropic_responses_route.py:205–569` | 同一harness同时承载route、hook与capability事实，未来继续成为高重叠测试热点 | 本轮保留既有结构以缩小集成变量；后续可单独提炼catalog／hook fixtures，但不得与本次squash混做 |

## 方案反思

1. **更好的内部替代方案**：一次性手工生成三片总patch会减少Git冲突次数，但会丢失每个reviewed source到main commit的边界，且更难判断哪片语义遗漏；不优于逐片squash＋独立commit。
2. **判据判别力**：仅看path交集会把共享smoke测试误报为真实冲突；仅看无conflict marker又会漏掉自动合并后的旧预期。因此本报告同时使用marker预览与第一人称语义检查，分别防false-red与false-green。
3. **成熟方案**：直接使用Git现有`merge --squash`与`merge-tree`，不手搓patch回放器、不创建新验证框架；测试沿用三个source已有具名pytest selectors。

## 报告评审状态

本会话是叶子reviewer，不能派生独立reviewer。本报告包含current-state断言与可执行步骤，主会话在采用前仍须安排独立复核；该义务不改变本轮`0 blocker／0 major`结论，但不能把本报告自述冒充第二轮评审。

## 最终结论

**推荐顺序：capability `8bff1c3…` → History `b1df8f9…` → stream `f3922a9…`。三片可依次`merge --squash`，每片必须立即形成独立non-merge main commit；明确禁止fast-forward、regular merge与cherry-pick。** `client.py`必须保留三方语义并集，`executor.py`必须删除旧stream gate但保留History lifecycle，共享route smoke测试必须保留capability覆盖并删除旧unsupported预期。按本文步骤完成每阶段selectors、最终联合selectors与三个reviewed-source archive targets后，可进入后续main组合态评审；本报告不声称这些写操作已执行。
