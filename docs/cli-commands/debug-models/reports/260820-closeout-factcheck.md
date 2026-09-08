# `debug models` 收尾文档事实对账

日期：2026-08-20。

范围：只核对 `docs/tmp/260820-debug-models-review-disposition.md`（下称“处置记录”）与 `/home/xp/.claude/jobs/792a44f0/tmp/DISPOSITION.md`（下称“任务处置”）对当前仓库和仍在的 job 临时目录所作的事实声称；不作代码质量评审，不修改被核查的文件，不运行会写入缓存的测试。代码证据锚定于本次读取时的 `HEAD=4511aa3b362e7107141e55834d4c42766c9840b3`。下列受检源码与测试路径相对 HEAD 无未提交改动，故其内容可作为当前历史状态的证据：`src/app/cli.py`、`src/app/debug/models.py`、`src/app/model_provider/types.py`、`src/app/model_provider/github_copilot.py`、`tests/unit/test_debug_models.py`、`tests/unit/test_model_provider.py`。

证据权重：Git object、当前未修改源码、当前临时文件的逐字节比较，以及两份点名评审报告，均为足以直接裁决相应静态命题的一手证据。2026-08-20 的真实上游响应、历史变异是否实际执行并转红、历史第一次枚举数，以及两次 `git checkout` 的事故，当前无可独立重放或可归属的原始运行记录；这些只可裁为“无法核实”，不能据此否定当前静态实现。

## 汇总

- 一致：提交对象均存在；`a46eb8d`、`883b104`、`14a5012`、`a224654` 都可从当前 HEAD 到达；`3bcf14c` 存在但不可达。`14a5012` 与 `3bcf14c` 在题定三个文件上的 patch 逐字节相同。
- 一致：处置记录“十四处”的列表实际为 14 条；当前实现和测试能静态证实抽查的 6 个守卫存在且有对应断言。
- 一致：处置表中所有“采纳”项均能在当前代码或点名测试中找到，含题目特别指定的 endpoint、状态、accessor、docstring 与 CLI 接线。
- 不一致：任务处置把 `models.py.orig`、`models.py.v2` 说成“已提交于 `a46eb8d`”；两份快照均不等于该提交的 `src/app/debug/models.py` blob，也不在任何可达 ref 的 object 清单中。其余 6 份源码快照确实逐字节等于所称提交版本。
- 不一致：处置记录称第三轮两份评审“独立发现了同样的两条 major”；GPT 报告明确是 1 major + 1 minor，另一份报告才是 2 major。两者独立发现了同两项问题，但严重度不相同。
- 不一致：任务处置把“用 `no-endpoints` 作为一个 STATUS 状态”列作被用户推翻的路线，然而处置记录和当前代码均明确保留该状态给“显式空列表”。被推翻的只是“缺键时报 `no-endpoints`”，不是这个状态本身。
- 不完整：任务处置开头把本会话实现列为三个提交，遗漏其后自身快照表和处置记录都点名的第四个提交 `a224654`。该句没有显式“仅有三条”的量词，但作为 session commit 清单不能代表完整事实。

## 1. 提交哈希、可达性与 rebase 对应

### 1.1 四个实现提交和旧 rebase 版本

文档原话：任务处置第 3 行：“Session: `debug models` 的实现（提交 a46eb8d、883b104、14a5012，均可从 main 的 HEAD 到达）。”处置记录第 39～41 行：“第三轮（对 `883b104` + `14a5012` 的两份评审……）”；“两份独立发现了同样的两条 major，均已修复于 `a224654`。”题目背景另明确本会话有四个提交，并说明 `14a5012` 原为 `3bcf14c`。

核对命令：

```bash
git -C /home/xp/src/ghc-api-proxy-py rev-parse HEAD
for sha in a46eb8d 883b104 14a5012 a224654 3bcf14c; do
  subject=$(git -C /home/xp/src/ghc-api-proxy-py show --no-patch --format=%s "$sha")
  if git -C /home/xp/src/ghc-api-proxy-py merge-base --is-ancestor "$sha" HEAD; then reached=yes; else reached=no; fi
  printf '%s reachability=%s subject=%s\n' "$sha" "$reached" "$subject"
done
```

真实输出：

```text
4511aa3b362e7107141e55834d4c42766c9840b3
a46eb8d reachability=yes subject=feat(cli): implement debug models
883b104 reachability=yes subject=fix(model-provider): serve the models whose endpoint the catalog leaves unstated
14a5012 reachability=yes subject=feat(cli): drop the provider wrapper from --json when --provider named one
a224654 reachability=yes subject=fix(model-provider): refuse an endpoint field we could not read instead of guessing one
3bcf14c reachability=no subject=feat(cli): drop the provider wrapper from --json when --provider named one
```

判定：前三个提交的存在、可达性和 subject 与任务处置一致；`a224654` 也存在、可达、subject 与处置记录所述修复一致。任务处置开头若意在枚举本会话的完整提交集合，则不一致，正确集合为 `a46eb8d`、`883b104`、`14a5012`、`a224654`。`3bcf14c` 是存在但已不从 HEAD 到达的旧版本，这与 rebase 背景一致。

### 1.2 `14a5012` 与 `3bcf14c` 是否为同一改动

文档原话：题目背景：“`14a5012`（原为 `3bcf14c`，被并行会话 rebase）。”

核对命令：

```bash
for path in src/app/cli.py src/app/debug/models.py tests/unit/test_debug_models.py; do
  git -C /home/xp/src/ghc-api-proxy-py diff --no-ext-diff 3bcf14c^ 3bcf14c -- "$path" > /tmp/factcheck-old.patch
  git -C /home/xp/src/ghc-api-proxy-py diff --no-ext-diff 14a5012^ 14a5012 -- "$path" > /tmp/factcheck-new.patch
  if cmp --silent /tmp/factcheck-old.patch /tmp/factcheck-new.patch; then printf '%s PATCH=identical\n' "$path"; else printf '%s PATCH=DIFFERENT\n' "$path"; fi
done
```

真实输出：

```text
src/app/cli.py PATCH=identical
src/app/debug/models.py PATCH=identical
tests/unit/test_debug_models.py PATCH=identical
```

补充命令与输出：

```bash
git -C /home/xp/src/ghc-api-proxy-py show --no-patch --format='%h|%H|%s' 14a5012 3bcf14c
```

```text
14a5012|14a501237c6d79bb56119da672d46808509adbb7|feat(cli): drop the provider wrapper from --json when --provider named one
3bcf14c|3bcf14c5e3c8a2959255e24ec20d1c923bd3ddd4|feat(cli): drop the provider wrapper from --json when --provider named one
```

判定：一致。题定三个文件的 commit patch 逐字节相同，subject 也相同；可据此确认二者是该改动的旧、新 rebase 版本，而不是仅 subject 相同的不同改动。

## 2. “变异检验十四处（五轮）”

### 2.1 清单数目与轮数陈述

文档原话：处置记录第 107～121 行：“变异检验十四处（五轮），全部确认能变红”；任务处置第 42 行：“已执行的变异（共 14 次，五轮，全部变红）”。

核对命令：

```bash
python - <<'PY'
from pathlib import Path
p = Path('/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-debug-models-review-disposition.md')
lines = p.read_text().splitlines()
start = next(i for i, line in enumerate(lines) if '变异检验十四处' in line)
end = next(i for i, line in enumerate(lines[start + 1:], start + 1) if line.startswith('- 用评审报告'))
bullets = [line for line in lines[start + 1:end] if line.lstrip().startswith('- ')]
print(f'mutation_section_lines={start + 1}-{end + 1}')
print(f'mutation_bullets={len(bullets)}')
for number, line in enumerate(bullets, 1):
    print(f'{number}. {line.strip()[2:]}')
PY
```

真实输出：

```text
mutation_section_lines=108-123
mutation_bullets=14
1. 删掉 `status_of` 的 `no-endpoints` 分支
2. 删掉 provider 的 `self._raw_catalog = dict(raw)`
3. 让表格最后一列也补齐宽度
4. `collect_catalogs` 改成重抛而不是隔离失败
5. 去掉 `finally` 里的 `aclose()`
6. `policy.state` 不加前缀直接上报
7. 清空 `_DEFAULT_ENDPOINT_BY_TYPE`（embeddings 模型落到 `/chat/completions`）
8. 取消“显式空列表”那一支（空列表也被填默认值）
9. provider 不再读 `capabilities.type`
10. `render_json` 忽略 `keyed=False`
11. `keyed=False` 时连多 provider 也去掉外层键
12. CLI 不把 `keyed` 开关传下去
13. 畸形（非 list 非 None）的 `supported_endpoints` 重新被填默认端点
14. 显式空列表重新报成 `no-driver`
```

判定：条目数一致，正确值为 14。两份文档均写五轮，彼此无矛盾。

“全部确认能变红”的历史执行结果判定：无法核实。当前目录保留的是快照与文档，不是每次变异的命令输出、退出码或测试日志；我按要求没有在共享工作树施加变异。当前代码和测试足以证明下述守卫可施加、且存在直接断言，但不能独立证明历史上的全部 14 次都实际执行且均转红。正确的可证表述应收窄为：“列出 14 个变异目标；当前至少抽查的 6 个目标均有实现分支和断言覆盖。”

### 2.2 抽查一：`no-endpoints` 分支与显式空列表

文档原话：变异第 1 条“删掉 `status_of` 的 `no-endpoints` 分支”，第 14 条“显式空列表重新报成 `no-driver`”。

核对命令：

```bash
rg --line-number --context 3 --fixed-strings 'no-endpoints' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出摘录：

```text
src/app/debug/models.py:115:    `no-endpoints` … means upstream sent an explicit empty list …
src/app/debug/models.py:128:        return "no-endpoints"
tests/unit/test_debug_models.py:124:                _model("explicitly-none", supported_endpoints=[]),
tests/unit/test_debug_models.py:134:    assert rows["explicitly-none"].status == "no-endpoints"
```

判定：一致。分支确实存在，输入确为显式 `[]`，断言确实要求 `no-endpoints`，所以删分支或改为 `no-driver` 都是可施加且具有直接测试覆盖的变异。

### 2.3 抽查二：原始 catalog 的保留

文档原话：变异第 2 条“删掉 provider 的 `self._raw_catalog = dict(raw)`”。

核对命令：

```bash
rg --line-number --context 3 --fixed-strings -e 'self._raw_catalog = dict(raw)' -e 'def test_the_catalog_is_kept_as_upstream_sent_it' -e 'assert provider.raw_catalog == CATALOG' /home/xp/src/ghc-api-proxy-py/src/app/model_provider/github_copilot.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_model_provider.py
```

真实输出摘录：

```text
src/app/model_provider/github_copilot.py:114:        self._raw_catalog = dict(raw)
tests/unit/test_model_provider.py:462:def test_the_catalog_is_kept_as_upstream_sent_it() -> None:
tests/unit/test_model_provider.py:469:    assert provider.raw_catalog == CATALOG
```

判定：一致。赋值与直接依赖它的断言都存在；删除赋值可施加，且这条测试有能力检出 raw catalog 未被保存的结果。

### 2.4 抽查三：`collect_catalogs` 的失败隔离与关闭

文档原话：变异第 4、5 条：“`collect_catalogs` 改成重抛而不是隔离失败”；“去掉 `finally` 里的 `aclose()`”。

核对命令：

```bash
rg --line-number --context 12 --fixed-strings -e 'except Exception as error:' -e 'failures.append(CatalogFailure' -e 'finally:' -e 'await http_client.aclose()' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py
rg --line-number --context 9 -e '^async def test_one_dead_provider_does_not_hide_a_healthy_one' -e '^async def test_the_outbound_client_is_closed_even_when_the_chain_cannot_be_built' /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出摘录：

```text
src/app/debug/models.py:230:            try:
src/app/debug/models.py:232:            except Exception as error:
src/app/debug/models.py:233:                failures.append(CatalogFailure(name, describe_failure(error)))
src/app/debug/models.py:248:    finally:
src/app/debug/models.py:249:        await http_client.aclose()
tests/unit/test_debug_models.py:499:async def test_one_dead_provider_does_not_hide_a_healthy_one(
tests/unit/test_debug_models.py:513:    assert [catalog.name for catalog in catalogs] == ["healthy"]
tests/unit/test_debug_models.py:517:    assert client.closed
tests/unit/test_debug_models.py:557:async def test_the_outbound_client_is_closed_even_when_the_chain_cannot_be_built(
tests/unit/test_debug_models.py:575:    assert client.closed
```

判定：一致。异常被记录而后继续，`finally` 关闭 client；健康 provider 存活和 build-chain 抛异常两个测试分别覆盖相应守卫。

### 2.5 抽查四：`policy.state` 前缀

文档原话：变异第 6 条：“`policy.state` 不加前缀直接上报”。

核对命令：

```bash
rg --line-number --context 8 -e '^def test_an_upstream_policy_state_cannot_impersonate_one_of_our_own_words' -e 'return f"policy:' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出摘录：

```text
src/app/debug/models.py:126:        return f"policy:{_printable(policy_state)}"
tests/unit/test_debug_models.py:158:def test_an_upstream_policy_state_cannot_impersonate_one_of_our_own_words() -> None:
tests/unit/test_debug_models.py:169:    assert rows["says-ok"].status == "policy:ok"
tests/unit/test_debug_models.py:170:    assert rows["says-disabled"].status == "policy:disabled"
tests/unit/test_debug_models.py:172:    assert rows["says-ok"].status != "ok"
```

判定：一致。分支可施加，且正反断言覆盖裸 `ok`/`disabled` 混淆。

### 2.6 抽查五与六：endpoint fallback、`keyed` 及 CLI 接线

文档原话：变异第 8～13 条分别涉及显式空列表、`model_type_of`、`render_json(keyed=False)`、多 provider 时 wrapper、CLI 传参以及畸形字段默认化。

核对命令：

```bash
rg --line-number --context 8 -e '^def resolve_endpoints' -e 'if advertised is not None:' -e '^def render_json' -e 'if not keyed and len\(catalogs\) == 1' /home/xp/src/ghc-api-proxy-py/src/app/model_provider/types.py /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py
rg --line-number --context 4 -e 'render_json\(catalogs, keyed=provider is None\)' -e '^def test_json_drops_the_wrapper_when_one_provider_was_named' -e '^def test_json_stays_keyed_for_several_providers_even_unkeyed' -e '^def test_cli_json_is_unwrapped_when_the_provider_is_named' /home/xp/src/ghc-api-proxy-py/src/app/cli.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出摘录：

```text
src/app/model_provider/types.py:138:    if advertised is not None:
src/app/model_provider/types.py:140:    default = _DEFAULT_ENDPOINT_BY_TYPE.get(model_type, DEFAULT_ENDPOINT)
src/app/debug/models.py:372:def render_json(catalogs: Sequence[ProviderCatalog], *, keyed: bool = True) -> str:
src/app/debug/models.py:379:    if not keyed and len(catalogs) == 1:
src/app/cli.py:444:            render_json(catalogs, keyed=provider is None) if as_json else render_text(catalogs)
tests/unit/test_debug_models.py:387:def test_json_drops_the_wrapper_when_one_provider_was_named() -> None:
tests/unit/test_debug_models.py:391:    assert document == CATALOG
tests/unit/test_debug_models.py:394:def test_json_stays_keyed_for_several_providers_even_unkeyed() -> None:
tests/unit/test_debug_models.py:400:    assert set(document) == {"ghc", "other"}
tests/unit/test_debug_models.py:680:def test_cli_json_is_unwrapped_when_the_provider_is_named(
tests/unit/test_debug_models.py:702:    assert json.loads(result.stdout) == CATALOG
```

判定：一致。当前实现和断言分别覆盖这些变异的判别面；历史“全部变红”仍如 §2.1 所述无法独立核实。

## 3. 处置表中每个“采纳”的落地

### 3.1 第一轮 F1～F6

文档原话：处置记录第 19～24 行分别声称采纳 config 错误转一行 `error:`、`build_rows → (rows, unreadable)`、C0/DEL 剥离、JSON 文案改为 decoded payload、`cell_len`、以及为 F1～F3 补鉴别性用例。

核对命令：

```bash
rg --line-number --context 16 -e '^def _read_config' -e 'except \(FileNotFoundError, ValidationError, YAMLError\)' -e 'complete decoded upstream payload' -e 'render_json\(catalogs, keyed=provider is None\)' /home/xp/src/ghc-api-proxy-py/src/app/cli.py
rg --line-number --context 14 -e '^def _printable' -e '^def build_rows' -e 'unreadable \+= 1' -e 'malformed=_wrong_shape' -e 'cell_len\(' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py
rg --line-number -e '^def test_cli_reports_a_bad_config_without_a_traceback' -e '^def test_a_field_that_arrived_wrong_typed_is_not_answered_as_if_it_were_read' -e '^def test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it' /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出摘录：

```text
src/app/cli.py:398:    except (FileNotFoundError, ValidationError, YAMLError) as error:
src/app/cli.py:399:        typer.echo(f"error: {error}", err=True)
src/app/cli.py:400:        raise typer.Exit(code=1) from error
src/app/cli.py:417:            help="Print the complete decoded upstream payload, keyed by provider name unless --provider names one."
src/app/debug/models.py:93:def _printable(text: str) -> str:
src/app/debug/models.py:100:    return CONTROL_CHARS.sub("", text)
src/app/debug/models.py:149:def build_rows(
src/app/debug/models.py:153:) -> tuple[tuple[ModelRow, ...], int]:
src/app/debug/models.py:170:            unreadable += 1
src/app/debug/models.py:195:                malformed=_wrong_shape(model),
src/app/debug/models.py:302:    filler = " " * max(0, width - cell_len(cell))
src/app/debug/models.py:312:        max(cell_len(header), max((cell_len(row[index]) for row in rows), default=0))
tests/unit/test_debug_models.py:224:def test_a_field_that_arrived_wrong_typed_is_not_answered_as_if_it_were_read() -> None:
tests/unit/test_debug_models.py:334:def test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it() -> None:
tests/unit/test_debug_models.py:601:def test_cli_reports_a_bad_config_without_a_traceback(tmp_path: Path) -> None:
```

判定：一致。F1～F6 所称的实现点和鉴别性测试均存在。

### 3.2 第二轮四项采纳

文档原话：处置记录第 30～34 行：“剥离点上移到 `status_of`”；“改为 `policy:<state>`”；“新增 4 个用例：失败隔离、`--provider` 只问一家、每家读自己的 disabled 列表、建链失败时仍关 client”；“断言改用 `cell_len` 计位”。

核对命令：

```bash
rg --line-number --context 8 -e '^def status_of' -e 'return f"policy:' -e 'cell_len\(' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
rg --line-number -e '^async def test_one_dead_provider_does_not_hide_a_healthy_one' -e '^async def test_the_named_provider_is_the_only_one_asked' -e '^async def test_each_provider_gets_its_own_disabled_list' -e '^async def test_the_outbound_client_is_closed_even_when_the_chain_cannot_be_built' /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出：

```text
src/app/debug/models.py:103:def status_of(
src/app/debug/models.py:126:        return f"policy:{_printable(policy_state)}"
tests/unit/test_debug_models.py:13:from rich.cells import cell_len
tests/unit/test_debug_models.py:362:    status_column = [cell_len(line[: line.index("ok")]) for line in lines[1:]]
tests/unit/test_debug_models.py:499:async def test_one_dead_provider_does_not_hide_a_healthy_one(
tests/unit/test_debug_models.py:520:async def test_the_named_provider_is_the_only_one_asked(monkeypatch: pytest.MonkeyPatch) -> None:
tests/unit/test_debug_models.py:537:async def test_each_provider_gets_its_own_disabled_list(monkeypatch: pytest.MonkeyPatch) -> None:
tests/unit/test_debug_models.py:557:async def test_the_outbound_client_is_closed_even_when_the_chain_cannot_be_built(
```

判定：一致。

### 3.3 第三轮五项采纳及题定重点

文档原话：处置记录第 44～48 行：“只有 `None`（缺键或显式 null）才触发兜底”；“`no-endpoints` 仅为这一种情况恢复”；“提升为 `model_type_of`……路由与报告共用一个读取口”；“type 为 embeddings、却声明 `/chat/completions`”；“`render_json` docstring 漏了 `len==1` 条件，补上”。

核对命令：

```bash
rg --line-number --context 18 --fixed-strings 'def resolve_endpoints' /home/xp/src/ghc-api-proxy-py/src/app/model_provider/types.py
rg --line-number --fixed-strings 'capabilities.type' /home/xp/src/ghc-api-proxy-py/src /home/xp/src/ghc-api-proxy-py/tests
rg --line-number --context 5 --fixed-strings -e 'def render_json' -e 'keyed=provider is None' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py /home/xp/src/ghc-api-proxy-py/src/app/cli.py
rg --line-number --context 12 -e '^def test_an_endpoint_upstream_did_name_is_never_replaced_by_the_default' -e '^async def test_an_unreadable_endpoint_field_is_refused_before_the_network' /home/xp/src/ghc-api-proxy-py/tests/unit/test_model_provider.py
```

真实输出摘录：

```text
src/app/model_provider/types.py:126:def resolve_endpoints(advertised: object, *, model_type: str = "") -> ResolvedEndpoints:
src/app/model_provider/types.py:135:    known, unknown = parse_endpoints(advertised)
src/app/model_provider/types.py:138:    if advertised is not None:
src/app/model_provider/types.py:140:    default = _DEFAULT_ENDPOINT_BY_TYPE.get(model_type, DEFAULT_ENDPOINT)
src/app/model_provider/types.py:102:def model_type_of(model: Mapping[str, Any]) -> str:
src/app/debug/models.py:177:            model_type=model_type_of(model),
src/app/model_provider/github_copilot.py:105:                model_type=model_type_of(model),
src/app/debug/models.py:372:def render_json(catalogs: Sequence[ProviderCatalog], *, keyed: bool = True) -> str:
src/app/debug/models.py:377:    `keyed` reflects what was asked for … The wrapper is dropped only when it also leaves exactly one payload to return …
src/app/debug/models.py:379:    if not keyed and len(catalogs) == 1:
src/app/cli.py:444:            render_json(catalogs, keyed=provider is None) if as_json else render_text(catalogs)
tests/unit/test_model_provider.py:402:def test_an_endpoint_upstream_did_name_is_never_replaced_by_the_default() -> None:
tests/unit/test_model_provider.py:413:                    "capabilities": {"type": "embeddings"},
tests/unit/test_model_provider.py:414:                    "supported_endpoints": ["/chat/completions"],
tests/unit/test_model_provider.py:427:    assert endpoints("odd-embedder") == {ModelEndpoint.OPENAI_CHAT_COMPLETIONS}
tests/unit/test_model_provider.py:434:async def test_an_unreadable_endpoint_field_is_refused_before_the_network() -> None:
tests/unit/test_model_provider.py:450:        with pytest.raises(CapabilityMissing):
tests/unit/test_model_provider.py:459:    assert seen == []
```

判定：一致。`resolve_endpoints` 的 fallback 的确只在 `advertised is None` 时发生；显式空列表经过 `advertised is not None` 返回空 endpoint，随后 `status_of` 的 `not offered` 分支给 `no-endpoints`。实际读取 `capabilities.type` 的口只有 `model_type_of` 函数，两个消费者均通过它调用。`render_json` 文档与实现在 `keyed=False and len(catalogs)==1` 的同一条件上；CLI 也确实把 `provider is None` 作为 keyed 开关传入。

## 4. 任务处置的 11 项文件清单与持久载体

### 4.1 当前总体枚举

文档原话：任务处置第 8～15 行：“关闭处置前重新列举得 11 项”；`find … → 11`；`fd … → 11`；“两法计数一致，11 项即为全集。”

核对命令：

```bash
job=/home/xp/.claude/jobs/792a44f0/tmp
find "$job" \( -type f -o -type l \) -printf '%P\n' | sort
printf 'COUNT='; find "$job" \( -type f -o -type l \) -printf . | wc -c
fd --hidden --no-ignore --type f --type symlink . "$job" --exec-batch sh -c 'for p; do printf "%s\n" "${p#"/home/xp/.claude/jobs/792a44f0/tmp/"}"; done' sh | sort
printf 'COUNT='; fd --hidden --no-ignore --type f --type symlink . "$job" | wc --lines
```

真实输出：

```text
DISPOSITION.md
bad.yaml
cli.py.v4
ghc.py.v3
models.py.orig
models.py.v2
models.py.v4
models.py.v6
probe.py
types.py.v3
types.py.v5
COUNT=11
DISPOSITION.md
bad.yaml
cli.py.v4
ghc.py.v3
models.py.orig
models.py.v2
models.py.v4
models.py.v6
probe.py
types.py.v3
types.py.v5
COUNT=11
```

判定：当前枚举一致。当前 job `tmp` 下 11 项正好等于表中 11 行，`find` 与 `fd -H -I` 等价选项的结果相同。历史“首次枚举 8 项”没有留存当时的目录清单，无法核实。

### 4.2 `bad.yaml` 和 `probe.py` 的测试载体

文档原话：任务处置第 21～22 行列出 `bad.yaml` 的 `test_cli_reports_a_bad_config_without_a_traceback`，以及 `probe.py` 的三个测试函数。

核对命令：

```bash
rg --line-number --fixed-strings -e 'test_cli_reports_a_bad_config_without_a_traceback' -e 'test_entries_that_yield_no_row_are_counted_rather_than_dropped' -e 'test_a_field_that_arrived_wrong_typed_is_not_answered_as_if_it_were_read' -e 'test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it' /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出：

```text
212:def test_entries_that_yield_no_row_are_counted_rather_than_dropped() -> None:
224:def test_a_field_that_arrived_wrong_typed_is_not_answered_as_if_it_were_read() -> None:
334:def test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it() -> None:
601:def test_cli_reports_a_bad_config_without_a_traceback(tmp_path: Path) -> None:
```

判定：一致。四个点名的函数均在所称文件存在；`bad config` 测试实际在 `tmp_path` 写入无效 config，并断言 exit code 1、无 `Traceback`、保留字段路径。

### 4.3 八份快照与所称提交的逐字节比较

文档原话：任务处置第 23～30、33～34 行：“八个 `.orig`/`.vN` 快照……每一个都对应一个已经落库的具体提交，上表逐行点名了是哪一个。”其中 `models.py.orig`、`models.py.v2` 均写“已提交于 `a46eb8d`”。

核对命令：

```bash
job=/home/xp/.claude/jobs/792a44f0/tmp
check_snapshot() {
  snapshot=$1; sha=$2; path=$3
  if git -C /home/xp/src/ghc-api-proxy-py show "$sha:$path" | cmp --silent - "$job/$snapshot"; then
    printf '%s == %s:%s\n' "$snapshot" "$sha" "$path"
  else
    printf '%s != %s:%s\n' "$snapshot" "$sha" "$path"
  fi
}
check_snapshot models.py.orig a46eb8d src/app/debug/models.py
check_snapshot models.py.v2 a46eb8d src/app/debug/models.py
check_snapshot models.py.v4 14a5012 src/app/debug/models.py
check_snapshot cli.py.v4 14a5012 src/app/cli.py
check_snapshot types.py.v3 883b104 src/app/model_provider/types.py
check_snapshot ghc.py.v3 883b104 src/app/model_provider/github_copilot.py
check_snapshot types.py.v5 a224654 src/app/model_provider/types.py
check_snapshot models.py.v6 a224654 src/app/debug/models.py
```

真实输出：

```text
models.py.orig != a46eb8d:src/app/debug/models.py
models.py.v2 != a46eb8d:src/app/debug/models.py
models.py.v4 == 14a5012:src/app/debug/models.py
cli.py.v4 == 14a5012:src/app/cli.py
types.py.v3 == 883b104:src/app/model_provider/types.py
ghc.py.v3 == 883b104:src/app/model_provider/github_copilot.py
types.py.v5 == a224654:src/app/model_provider/types.py
models.py.v6 == a224654:src/app/debug/models.py
```

为避免“不同于该 commit 但存在于另一可达提交”的歧义，再核对 blob object：

```bash
for f in models.py.orig models.py.v2; do
  hash=$(git -C /home/xp/src/ghc-api-proxy-py hash-object "/home/xp/.claude/jobs/792a44f0/tmp/$f")
  printf '%s %s ' "$f" "$hash"
  git -C /home/xp/src/ghc-api-proxy-py rev-list --all --objects | rg --fixed-strings --quiet "$hash" && printf 'reachable-blob=yes\n' || printf 'reachable-blob=no\n'
done
```

真实输出：

```text
models.py.orig 7b549f7760efe5dad8a851901093129c9b017427 reachable-blob=no
models.py.v2 740ccbf2a1b2d99b6be92251b1449c9d6edacf1c reachable-blob=no
```

判定：不一致，正确值为“6/8 快照有点名提交中的完全相同载体，2/8 没有”。`models.py.orig` 与 `models.py.v2` 不仅不等于 `a46eb8d`，其 blob 也没有出现在任何可达 ref；因此不能以“每一个已落库”作为它们的安全丢弃依据。其余六项的持久载体声称一致。

### 4.4 各点名提交确实包含被称文件

文档原话：任务处置第 23～30 行各称某个快照“已提交于”相应提交。

核对命令：

```bash
for spec in 'a46eb8d:src/app/debug/models.py' '14a5012:src/app/debug/models.py' '14a5012:src/app/cli.py' '14a5012:tests/unit/test_debug_models.py' '883b104:src/app/model_provider/types.py' '883b104:src/app/model_provider/github_copilot.py' 'a224654:src/app/model_provider/types.py' 'a224654:src/app/debug/models.py'; do
  sha=${spec%%:*}; path=${spec#*:}
  if git -C /home/xp/src/ghc-api-proxy-py cat-file -e "$sha:$path"; then printf '%s PRESENT\n' "$spec"; else printf '%s MISSING\n' "$spec"; fi
done
```

真实输出：

```text
a46eb8d:src/app/debug/models.py PRESENT
14a5012:src/app/debug/models.py PRESENT
14a5012:src/app/cli.py PRESENT
14a5012:tests/unit/test_debug_models.py PRESENT
883b104:src/app/model_provider/types.py PRESENT
883b104:src/app/model_provider/github_copilot.py PRESENT
a224654:src/app/model_provider/types.py PRESENT
a224654:src/app/debug/models.py PRESENT
```

判定：文件路径存在不等于快照内容相同。此项只能支持“对应路径在提交中存在”；不能挽回 §4.3 中两份 a46 快照的内容载体失配。

## 5. 两份文档的相互一致性

### 5.1 变异计数、轮数与状态词

文档原话：处置记录第 107 行“十四处（五轮）”；任务处置第 42 行“共 14 次，五轮，全部变红”。处置记录第 58 行列出的状态词为 `ok`、`disabled`、`no-endpoints`、`no-driver`、`malformed`、`policy:<state>`。

核对命令：

```bash
rg --line-number -i -e '五轮|第三轮|第五轮|变异' /home/xp/src/ghc-api-proxy-py/docs/tmp/260820-debug-models-review-disposition.md /home/xp/.claude/jobs/792a44f0/tmp/DISPOSITION.md
rg --line-number -e 'ROUTABLE|no-endpoints|no-driver|malformed|policy:' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py
```

真实输出摘录：

```text
…debug-models-review-disposition.md:108:- 变异检验十四处（五轮），全部确认能变红：
…DISPOSITION.md:42:| 已执行的变异（共 14 次，五轮，全部变红） | … |
src/app/debug/models.py:24:ROUTABLE = "ok"
src/app/debug/models.py:121:    if malformed:
src/app/debug/models.py:126:        return f"policy:{_printable(policy_state)}"
src/app/debug/models.py:128:        return "no-endpoints"
src/app/debug/models.py:130:        return "no-driver"
```

判定：14 与五轮在两份文档之间一致，状态词清单也与当前代码一致。

### 5.2 `no-endpoints` 的矛盾

文档原话：处置记录第 45 行：“`no-endpoints` 仅为这一种情况恢复。”第 58 行也把它列为对外状态词。任务处置第 39 行却把“用 `no-endpoints` 作为一个 STATUS 状态”称为“被推翻的路线”。

核对命令：

```bash
rg --line-number --context 3 --fixed-strings 'no-endpoints' /home/xp/src/ghc-api-proxy-py/src/app/debug/models.py /home/xp/src/ghc-api-proxy-py/tests/unit/test_debug_models.py
```

真实输出：

```text
src/app/debug/models.py:115:    `no-endpoints` does **not** mean the catalog left the key out. … It means upstream sent an explicit empty list …
src/app/debug/models.py:128:        return "no-endpoints"
tests/unit/test_debug_models.py:124:                _model("explicitly-none", supported_endpoints=[]),
tests/unit/test_debug_models.py:134:    assert rows["explicitly-none"].status == "no-endpoints"
```

判定：不一致。正确的历史裁决是“缺键不能再报 `no-endpoints`，因为 `None` 会被填默认 endpoint”；而 `no-endpoints` 本身仍是显式 `[]` 的现行状态。任务处置的表述把被去掉的一个适用条件扩大为整个状态被推翻。

### 5.3 “两份独立评审同样两条 major”的矛盾

文档原话：处置记录第 40 行：“两份独立发现了同样的两条 major。”

核对命令：

```bash
rg --line-number --context 3 -e 'Verdict：needs-fix' -e '^### F[0-9]' -e '^## Major' -e '^## Minor' /home/xp/src/ghc-api-proxy-py/docs/tmp/260820-review-endpoint-defaulting-gpt.md /home/xp/src/ghc-api-proxy-py/docs/tmp/260820-review-endpoint-defaulting.md
```

真实输出摘录：

```text
…endpoint-defaulting-gpt.md:7:**Verdict：needs-fix。** … 畸形值…严重度为 `Major`。显式空列表…报告把它叫作 `no-driver`…严重度为 `Minor`。
…endpoint-defaulting-gpt.md:13:### F1 — `Major`：畸形 `supported_endpoints` …
…endpoint-defaulting-gpt.md:21:### F2 — `Minor`：显式空列表路由虽 fail-closed，但报告误称 `no-driver`
…endpoint-defaulting.md:8:**结论：needs-fix。blocker 0 条，major 2 条，minor 5 条，nit 3 条。**
…endpoint-defaulting.md:26:## Major
…endpoint-defaulting.md:115:## Minor
```

判定：不一致。正确描述为：“两份评审独立发现同两项问题；同源评审将两项都定为 major，GPT 评审将畸形 fallback 定为 major、将 `no-driver` 误报定为 minor。”

### 5.4 提交清单的遗漏

文档原话：任务处置第 3 行只列 `a46eb8d`、`883b104`、`14a5012`；但它自己的第 30～31 行把两份 v5/v6 快照归于 `a224654`，处置记录第 40 行也称它为修复提交。

核对命令及输出：见 §1.1；其中 `a224654 reachability=yes subject=fix(model-provider): refuse an endpoint field we could not read instead of guessing one`。

判定：不完整。应把 `a224654` 加入该 session 的实现提交清单。它不是“不可达旧版本”，而是当前 HEAD 上的后续修复。

## 6. 绝对声称的证据边界

### 6.1 有可核实证据的绝对或全称说法

- “所有 0 blocker”：四个点名评审文件均存在；其结论段分别写 `未发现 blocker`、`0 blocker / …`、`blocker 0 条`。判定一致。
- “11 项即为全集”：在本次检查时，对该 job `tmp` 的 `find` 与 `fd` 均为 11，且名称逐项对应表。判定一致，但只支持当前目录状态，不追溯历史首次枚举。
- “每个采纳项已落地”：针对表中所有采纳项，§3 已给出当前代码/测试一手证据。判定一致。
- “`14a5012` 与 `3bcf14c` 是同一改动”：§1.2 的三文件 patch 逐字节相同。判定一致。

### 6.2 找不到可独立证据的绝对说法

以下不是已被反证，而是当前可用工件不足以独立确认；应保留它们的历史条件或降为“作者记录”。

1. 处置记录第 107 行与任务处置第 42 行：“全部确认能变红”。当前能确认 14 个列表及抽查守卫，找不到 14 次的变异执行日志、命令输出、退出码或每轮的持久测试结果。判定：无法核实历史全称。
2. 任务处置第 8 行：“首次枚举 8 项”。当前目录为 11，没有保留首次枚举输出。判定：无法核实。
3. 处置记录第 122～124 行的三段实跑数值：`8 entries → 4 models, 2 routable, 2 malformed (4 unreadable entries skipped)`、两个 config 错误路径、以及真实上游的 `42 models, 42 routable` 和 JSON 顶层键。前两类可由当前测试设计部分支撑，但没有本次历史运行输出；真实上游需要当时凭据、账户、上游响应和时间条件，不能由当前代码或提交复现。判定：无法独立核实，不应外推为当前或所有账户的事实。
4. 处置记录第 94 行与任务处置第 41 行的真实 catalog 全称“18 = 3 embeddings + 14 chat + 1 completion，且全目录无空列表”。任务处置自身已正确限定为单一账户单次读取；当前没有该原始响应或可重放凭据。判定：无法独立核实；该限制条件应继续保留。
5. 两份文档对两次 `git checkout` 造成损失的历史因果叙述。当前没有当时的 reflog、命令 transcript 或前后文件状态可归属。判定：无法核实。

## 7. 最终结论

本次对账发现 3 个明确事实不一致或不完整项：

1. `models.py.orig` 与 `models.py.v2` 不是任务处置所称的 `a46eb8d` 已提交版本，且其 blob 不可从任一可达 ref 找到；正确为 6/8 快照可由点名提交逐字节恢复。
2. “两份独立评审同样两条 major”错误；正确为同两项问题、不同严重度，GPT 是 1 major + 1 minor。
3. 任务处置把整个 `no-endpoints` 状态写成被推翻；正确为只推翻缺键使用该状态，显式空列表仍使用它。

另有 1 个清单遗漏：任务处置开头遗漏可达且已被它自身后文引用的第四个实现提交 `a224654`。

除上述项目以及无法独立核实的历史运行/变异全称外，提交身份、rebase patch、当前 14 条清单、当前 11 项 job population、点名测试函数、以及处置表中“采纳”的现行代码落地均与仓库状态一致。
