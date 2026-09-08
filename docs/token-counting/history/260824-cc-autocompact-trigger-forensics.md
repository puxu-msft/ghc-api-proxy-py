# Claude Code 自动压缩触发条件取证

- 日期：2026-08-24
- 证据源：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`（660402 行），对照 `claude-code-2.1.226`、`claude-code-2.1.207`
- 除非另行标注，所有行号均指 2.1.241 的 `app.pretty.js`
- 纪律：每条结论标注「代码这么写」还是「我推测」，并给出置信度

---

## 0. 首要更正：`Vyl` 不是自动压缩的判定入口

任务给出的起点里说「阈值判断入口是 `Vyl`」。**这一条不成立**，需要先纠正，否则后面的排查会一直查错分支。

- `Vyl`（`:304920`）最后一行是 `return a1p(...)`，但它前面第 5 个条件是 `if (!eZr()) return false;`（`:304925`）。`eZr`（`:304842`）是 **precomputed compaction（预计算压缩）** 的总开关：`mL() && VSe() && nt("tengu_sepia_moth", false) && ap("precomputeCompactionEnabled", XJr()).value`。
- `Vyl` 的两个调用点（`:312213`、`:312632`）都只用来决定**要不要提前在后台「预热」一份压缩摘要**：为真时走 `qyl(...)`（subagent 记账）或 `Kyl(...)`（`:304929`，真正启动 precompute）。
- **真正的自动压缩判定在 `zzw`（`:366191`）**，由 `rvl`（`:366199`，即 `m.autocompact`，注册于 `:311358`）调用，而 `rvl` 在主循环 `:312195` 被 `yield*`。

所以「有没有触发压缩」这个问题的判据函数是 `zzw`，`Vyl` 只影响「压缩发生时是不是瞬间完成（有预热）」。**置信度：高**（三处调用点与 `:311358` 的 `autocompact: rvl` 注册可交叉验证）。

---

## 1. 完整判定逻辑

### 1.1 `zzw` —— 真正的「要不要自动压缩」（`:366191`）

```js
async function zzw(e /*messages*/, t4 /*model*/, r2 /*autoCompactWindow*/, n4 /*querySource*/, o4 = 0 /*snipTokensFreed*/, i /*agentContext*/) {
    if (EWr(n4)) return false;
    if (QNt(n4)) return false;
    if (!mL()) return false;
    if (VSe() && !X3e(t4, r2)) return false;
    let s = eP(e, KR(t4)) - o4, a = Wet(s, t4, r2);
    return E(`autocompact: tokens=${s} level=${a.level} effectiveWindow=${KSe(t4, r2)}`), a.level === "compact" || a.level === "blocked";
}
```

逐条：

| # | 条件 | 返回 false（不压缩）的情形 | 定义 |
|---|---|---|---|
| 1 | `EWr(querySource)` | `querySource === "compact"`（压缩自身发起的请求） | `:155181` |
| 2 | `QNt(querySource)` | querySource ∈ {`prompt_suggestion`, `away_summary`, `agent_summary`, `narration`} | `:155171`，集合 `GGv` 定义于 `:155192` 附近（`syi` 初始化块） |
| 3 | `!mL()` | 自动压缩被关掉（见第 4 节） | `:155124` |
| 4 | `VSe() && !X3e(model, win)` | **窗口来源解析为 `"auto"`** | `VSe`:`:155147`；`X3e`:`:155295` |
| 5 | 阈值 | `Wet(...).level` 不是 `compact` 也不是 `blocked` | `:155221` |

**第 4 条是最容易被忽略的一条**，也是本次调查最重要的发现之一：

- `VSe()`（`:155147`）：只有 `q.CLAUDE_CODE_REMOTE` 为真时才可能返回 false（且要 gate `tengu_reactive_compact_remote` 关闭）。本地终端会话恒为 true。
- `X3e(model, win)`（`:155295`）= `_9(model, win).source !== "auto"`。
- 所以：**只要窗口来源是 `"auto"`，本地会话就永远不会主动压缩**。这不是 bug，是设计——此时 CC 走「reactive compact」（被上游 400 顶回来后才压），见 `:312324` 的 `et = mL() && VSe() && !X3e(...)` 与 `:312326` 的 `blocked` 分支：`et` 为真时连 blocking 提示都不出。

### 1.2 `rvl` 的其余前置条件（`:366199`）

即使 `zzw` 为真，下面几条仍会拦掉：

- `q.DISABLE_COMPACT` → `{kind:"not_needed"}`（`:366200`）
- `compactTracking.consecutiveFailures >= _Om`（`_Om = 3`，`:366245`）→ `failure_breaker_open`（`:366201`）
- rapid-refill 断路器：连续 3 次「压缩后 3 轮内又被填满」→ `rapid_refill_breaker_tripped`（`uyi`:`:155356`，`l1p = 3`:`:155366`）
- `Uzw`（`:366170`）检测到「固定前缀已超阈值，压缩帮不上忙」，只打 warn 不阻断

### 1.3 `Vyl` 的完整逻辑（问题 1 的字面回答，`:304920`）

```js
function Vyl(e) {
    if (e.autocompactRan) return false;                                  // 本轮已经压过/压失败
    if (e.isPreFirstCompactFork) return false;                           // 首次压缩前的 precompute fork
    if (e.hasAttemptedReactiveCompact) return false;                     // 本轮已尝试过 reactive 压缩
    if (e.lastTransitionReason === "precomputed_compact_swap") return false;
    if (!eZr()) return false;                                            // precompute 总开关
    return a1p(e.contextTokens, e.model, e.autoCompactWindow, e.querySource);
}
```

其中 `isPreFirstCompactFork` 在调用点算出（`:312189`）：`X.precomputeSourceKey !== void 0 && compactTracking?.compacted !== true && !Xto(querySource)`。

---

## 2. 阈值是怎么算出来的

### 2.1 上下文窗口 `_9(model, autoCompactWindow, sdkBetas = zx())`（`:155275`）

按优先级返回 `{window, configured, source}`：

| 顺序 | 条件 | source | 来源性质 |
|---|---|---|---|
| 1 | 环境变量 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`（合法值，clamp 到 [1e5, 1e6]） | `"env"` | **机器本地** |
| 2 | 传入的 `autoCompactWindow !== undefined` | `"settings"` | settings.json / `--settings` / `/autocompact` |
| 3 | `XGv(n4).window !== null`（`:155263`） | `"clientdata"` | **机器本地缓存 + GrowthBook** |
| 4 | `NFa(n4) !== undefined`（`:155248`） | `"experiment"` | **GrowthBook 实验**，且仅对 `claude-opus-4-8` |
| 5 | `o4 < 1e6 && (VGv.has(n4) \|\| KGv(e) \|\| rha(e, r2))` | `"model-default"`，窗口 200000 | 硬编码集合 `VGv`（`:155348`）= {claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-8, claude-opus-5} |
| 6 | `qGv(n4) !== undefined`（`:155259`，硬编码表 `t1p`，只有 `claude-sonnet-5`） | `"model-default"` | 静态 |
| 7 | `mL() && !CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT && !YGv(e,r2) && !_Br(e) && !Eht(e,n4)` | **`"unknown-model"`** | 对「CC 不认识的模型名」兜底 |
| 8 | 兜底 | `"auto"` | ← 到这里就永不主动压缩 |

`o4 = FC(e, r2)`（`:73384`）是模型的最大上下文：
- `NBd()`（`:73390`）：`DISABLE_COMPACT` 且 `CLAUDE_CODE_MAX_CONTEXT_TOKENS > 0` 时直接用它
- `rha()`（`:73397`）：1M 额度被封时压回 200000
- `FBd()`（`:73400`）：1M 判定 → 否则 `YZo(e)`（GrowthBook `kelp_forest_sonnet`，仅 sonnet-4-6）→ 否则 **`CLAUDE_CODE_MAX_CONTEXT_TOKENS`（仅当归一化模型名不以 `claude-` 开头时生效）** → 否则 `y2r = 200000`（`:73454`）

### 2.2 有效窗口与阈值

- `KSe(model, win)`（`:155301`）= `_9(...).window - min(Hlr(model), 20000)`（`o1p = 2e4`，`:155341`）
- `Hlr(model)`（`:429738`）= 模型 max_output_tokens，受 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 覆盖（`cQe`:`:96774`，上限 clamp 到 `xMt(e).upperLimit`）；未知模型走默认 `B5b = 32000` / 上限 `U5b = 128000`（`:73443`、`:73454`）
- `lyi(window, opts)`（`:155197`）= `window - 13000`；若 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` ∈ (0,100] 则取 `min(floor(window * pct/100), window - 13000)`
- `PFa(tokens, effWin, opts, blockingBase = effWin, thresholdOverride)`（`:155205`）：
  - `compact` 阈值 `i = lyi(effWin, opts)`
  - `warn` 阈值 `a = i - 20000`
  - `blocked` 阈值 `c = CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE ?? (blockingBase - 3000)`，其中 `blockingBase = n1p(model)`（`:155305`）= `FC(model, zx()) - min(Hlr(model), 20000)`，**注意它绕过 `_9`，用的是模型原生窗口而不是配置窗口**
- `Wet(tokens, model, win)`（`:155221`）把上面串起来

**未知模型的具体数字（推算，置信度中高）**：`FC = 200000` → `Hlr = 32000` → `min(32000,20000) = 20000` → `effWin = 180000` → compact 阈值 `167000`，blocked 阈值 `177000`，warn 阈值 `147000`。

### 2.3 `a1p` 与 `FFa`（precompute 侧，问题 2 的字面回答）

`a1p(tokens, model, win, querySource)`（`:155342`）：

```js
let o4 = BFa(t4, r2, n4);                   // {enabled: mL(), precomputeBufferFraction: QGv(...), testPctOverride, testBlockingOverride}
let i = o4.enabled ? r2 : void 0, s = KSe(t4, i);
if (!X3e(t4, r2)) return e >= DFa(s, o4);   // 窗口来源是 "auto" 时仍然会 arm
let { window: a } = _9(t4, i);
if (a < _ve) return false;                  // _ve = 200000；配置窗口小于 200k 就不预热
return e >= DFa(s, o4);
```

`DFa(s, o4)`（`:155202`）= `min(s - round(s * fraction), lyi(s, o4))`，即比真实压缩阈值提前 `fraction` 比例。

`FFa(model, win, querySource)`（`:155317`）给出 `fraction` 与 `source`：

| `source` | 触发条件 | fraction |
|---|---|---|
| `"scalar"` | GrowthBook feature `tengu_amber_moleskin`（`JGv`,`:155343`）为 null/undefined | `$Fa()`：feature `tengu_amber_rokovoko`，默认 `ayi = 0.2`（`:155215`、`:155313`） |
| `"malformed"` | 该 feature 存在但 `QOp` 解析失败（非对象/数组/子项非法） | `$Fa()`，并上报 `tengu_precompute_arm_table_malformed` |
| `"table_exact"` | 表里有 key 恰好等于 `_9(model, win).window` | `entry[querySource === "sdk" ? "sdk" : "repl"]`，附带 `matchedWindowKey` |
| `"table_default"` | 没有精确 key，但表里有 `default` 条目 | 同上 |
| `"table_no_match"` | 既无精确 key 也无 `default` | `$Fa()` |

表的形状由 `QOp`（`:155175`）+ `WGv`（`:155169`）约束：`{ "<windowSize>": {repl: n, sdk: n}, "default": {repl: n, sdk: n} }`，每个 fraction 必须是 `[0, 1)` 的有限数。

---

## 3. `autoCompactWindowsCache` 的完整生命周期 ★

**这是问题 3 的答案，也是我认为机器间差异最值得先查的两处之一。**

### 3.1 存在哪个文件

`~/.claude.json`（全局配置文件），**不是** `~/.claude/settings.json`，**不是** `~/.claude/` 下的任何独立 json。

证据链：
- `:73413` `function UBd() { if (lo() !== "firstParty") return null; return cr().autoCompactWindowsCache ?? null; }`
- `cr()`（`:93593`）读全局配置缓存，未命中时 `W2n(hQ())`；文件路径 `Ib()`（`:21388`）→ `UXe().getGlobalClaudeFile()`（`:21554`）
- 路径构造在 `ex_()`（`:21383`）：优先 `<Hn()>/.config.json`，否则 `path.join(process.env.CLAUDE_CONFIG_DIR || os.homedir(), ".claude" + PXe() + ".json")`
- 默认全局配置 `hQ()`（`:93158`）里没有 `autoCompactWindowsCache` 键，缺失时读出 `undefined`

**置信度：高。**

### 3.2 由什么代码写入

唯一写入点：`AAt`（`:372715`，Bootstrap）的 `on((D) => ({...}))` 回调，`:372738`：

```js
autoCompactWindowsCache: r2 && !m ? b : D.autoCompactWindowsCache ?? null
```

其中（`:372728`）：
- `r2 = lo() === "firstParty"`
- `b = m ? l.autoCompactWindowsCache ?? null : s.auto_compact_windows ?? null`
- `m = c && s.auto_compact_windows == null`，`c = s.narrowed ?? a`（`a` = 走了无 profile scope 的 OAuth）

数据来自 `GET {BASE_API_URL}/api/claude_cli/bootstrap` 的 `auto_compact_windows` 字段（`kqw`,`:372679`）。

清空点：`:403220`（登出/账号重置时整批 `= void 0`）。

### 3.3 什么时候刷新

`AAt` 的调用点：

| 行号 | 场景 |
|---|---|
| `:611388` | 启动时的 background prefetch。受 `ig()`（`CLAUDE_CODE_SIMPLE` / `--bare`）与节流 `nt("tengu_cicada_nap_ms", 0)` vs `cr().startupPrefetchedAt` 控制（`:611386`） |
| `:611390` | 上面被节流跳过时的补偿：`!ig() && lo() === "firstParty" && xDl() && !HAa()` 才补 fetch |
| `:372955`/`:372972` | 切模型 |
| `:454383` | 其他 |

`kqw` 里的**提前返回**（这些情形 cache 永不更新）：
- `lo() === "gateway"` 且未设 `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`
- `ha()` —— 设了 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`（`:17398`）
- `lo() !== "firstParty"` —— 设了 `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY` / `_MANTLE` 等
- 既无 OAuth accessToken 也无 API key
- 设了 `ANTHROPIC_UNIX_SOCKET`

注意 URL：OAuth/API-key 主路径用的是 `ol().BASE_API_URL`（`:372699`，prod 即 `https://api.anthropic.com`，`:17285`），**不读 `ANTHROPIC_BASE_URL`**；只有 WIF 分支（`:372686`）才用 `q.ANTHROPIC_BASE_URL`。

另外 `clientDataCacheSlots` 有 24 小时过期（`zQd = 864e5`，`:92408`），但 `autoCompactWindowsCache` 本身**没有独立 TTL**——它只随一次成功的 bootstrap 整体覆盖。

### 3.4 没有它时的行为

`XGv(model)`（`:155263`）：

```js
let n4 = r2(BBd()?.rowan_thicket);   // GrowthBook/clientData 里的 rowan_thicket
let o4 = r2(UBd());                  // autoCompactWindowsCache
return { window: n4.window ?? o4.window, replacesDefault: o4.present };
```

`r2(i)` 要求 `Object.hasOwn(i, model)` 且值经 `s1p` 解析后是 `[1e5, 1e6]` 内的整数，否则 `{window: null, present: false}`。

所以缺失时：`_9` 跳过 `"clientdata"`，继续往下走 5→6→7→8。**并且 `replacesDefault` 变成 false，这会把第 6 步的硬编码表 `qGv` 重新放行**（`:155289`：`let a = i.replacesDefault ? void 0 : qGv(n4)`）——即缓存的存在与否不仅影响第 3 步，还会反向影响第 6 步。

**判定：`autoCompactWindowsCache` 只有在模型名恰好是它的一个 key 时才影响结果。**对 Copilot 代理下的 `gpt-*` 之类模型名，这个缓存**几乎肯定命不中**，因此它**不是**本案最可能的差异源。**置信度：中高**（依据是 key 必须 `Object.hasOwn` 精确匹配归一化后的模型名，而该表由 Anthropic 服务端下发，只会包含 Claude 模型名）。

---

## 4. `autoCompactEnabled` 从哪读 ★

`mL()`（`:155124`）：

```js
function mL() {
    if (KOp()) return false;                       // q.DISABLE_COMPACT || q.DISABLE_AUTO_COMPACT
    return ap("autoCompactEnabled", true).value;
}
```

`ap(key, default)`（`:92721`）：

```js
let r2 = I_();                                     // ["userSettings","projectSettings","localSettings","flagSettings","policySettings"] 过滤后
let n4 = r2.includes("userSettings") && Qbe();
for (let o4 = r2.length - 1; o4 >= 0; o4--) {      // 从后往前 = 优先级从高到低
    let i = r2[o4];
    if (i === "projectSettings" && n4) continue;
    let s = _n(i)?.[e];
    if (s !== void 0) return { value: s, source: i };
}
if (Bor.includes(e)) {                             // Bor 含 "autoCompactEnabled"，:92740
    let i = cr()[e];
    if (i !== void 0 && i !== zve[e]) return { value: i, source: "legacyGlobalConfig" };
}
return { value: t4, source: "default" };
```

**结论：`autoCompactEnabled` 是 settings.json 的键，但不止于此。** 完整来源与优先级（高→低）：

1. `policySettings` —— Linux 下 `/etc/claude-code/managed-settings.json`（`Pq()`:`:42836`，`cQ_()`:`:42838` 附近给出三平台路径）
2. `flagSettings` —— `--settings` CLI 参数（`T8()`:`:40474` 显示为 `"cli flag"`）
3. `localSettings` —— 项目内 `.claude/settings.local.json`（`:43050`）
4. `projectSettings` —— 项目内 `.claude/settings.json`（`:43048`）
5. `userSettings` —— `~/.claude/settings.json`
6. **`legacyGlobalConfig` —— `~/.claude.json` 顶层的 `autoCompactEnabled` 字段**（仅当它不等于默认值 `true` 时生效；默认值定义在 `hQ()`:`:93159`，`zve = hQ()`:`:94474`）
7. 默认 `true`

**第 6 条是最强的候选机器间差异源。** 它不在 `settings.json` 里，用户比对 `settings.json` 一致时完全看不到它。历史上 `/config` 面板写的就是这里（`ume`/`ba("userSettings",...)` 是新写法，`Bor` 这套 legacy 回退说明老版本写在全局配置）。

另外 `LFa()`（`:155129`）专门区分「用户显式关掉」与「其他原因」，也印证了 `legacyGlobalConfig` 是一条真实存在的落盘路径。

**置信度：高。**

---

## 5. 其他跟本地状态走的输入

按「我认为的可疑度」排序。

### 5.1 CC 版本本身（最高可疑度，且用户很可能没查）★★★

`"unknown-model"` 这条窗口来源分支**是在 2.1.207 之后、2.1.226 之前引入的**：

- 2.1.241：`:155292` 有 `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` + `source: "unknown-model"`
- 2.1.226：`:131321` 同上
- 2.1.207：`rg '"unknown-model"'` **零命中**；其 `_9` 等价函数（`:298841`、`:298843`）从 model-default 直接落到 `"auto"`

而 2.1.207 的 `zzw` 等价函数 `j1y`（`:298955`）同样带 `if (mhe() && !k6e(t2, r)) return false;` 这条门。

**推论**：同一个 Copilot 代理、同一份 `settings.json`，跑 2.1.207 的机器窗口来源是 `"auto"` → **永不自动压缩**；跑 2.1.226+ 的机器窗口来源是 `"unknown-model"` → **会在约 167k tokens 压缩**。这精确匹配用户描述的「一台没触发」。

**置信度：高**（代码差异是硬事实；「这就是本案原因」是推测，需要用户核对两台的 `claude --version`）。

### 5.2 `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` ★★

`:155292`。设了它，未知模型直接落到 `"auto"` → 不压缩。纯环境变量，不在任何配置文件里。**置信度：高。**

### 5.3 `~/.claude.json` 里的 `autoCompactEnabled` ★★

见第 4 节。**置信度：高。**

### 5.4 其他环境变量（全部机器本地）★★

| 变量 | 效果 | 行号 |
|---|---|---|
| `DISABLE_COMPACT` / `DISABLE_AUTO_COMPACT` | `mL()` 直接 false，压缩全关 | `:155121` |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | 窗口 source 变 `"env"`，值 clamp 到 [1e5,1e6] | `:155278` |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | 非 `claude-` 前缀模型的窗口直接由它决定 | `:73407` |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 改变有效窗口的扣减量（未知模型下扣 20000 封顶，只有把它调到 <20000 才有影响） | `:429738` |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 直接改 compact 阈值百分比 | `:155334` |
| `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | 改 blocked 阈值 | `:155334` |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关掉 bootstrap，clientdata 窗口与 GrowthBook 都停更 | `:17393` |
| `CLAUDE_CODE_USE_BEDROCK/_VERTEX/_FOUNDRY/_MANTLE/_ANTHROPIC_AWS/...` | `lo() !== "firstParty"` → `UBd()` 恒 null，bootstrap 跳过 | `:64554` |
| `CLAUDE_CODE_DISABLE_1M_CONTEXT` | 改 `IA/l7/ZU/KZo`，进而改 `FC` 与 `_9` 第 5 步 | `:73327` |
| `CLAUDE_CONFIG_DIR` | 换掉 `~/.claude.json` 的位置，间接换掉上面所有 legacy/缓存状态 | `:21385` |
| `CLAUDE_CODE_ENTRYPOINT` | 参与 `s1p` 的 surface 选择，影响 clientdata/硬编码窗口表取值 | `:155252` |
| `ANTHROPIC_UNIX_SOCKET` | bootstrap 跳过 | `:372694` |
| `CLAUDE_CODE_REMOTE` | `VSe()` 可能 false → 第 4 条门失效，反而恢复主动压缩 | `:155147` |
| `CLAUDE_CODE_SIMPLE` / `--bare` | 跳过 startup prefetch | `:8236` |

### 5.5 GrowthBook feature flags（机器本地缓存）★★

`nt(key, default)`（`:92127`）→ `vve` → `fQ().getFeatureValueWithSource`。离线/未刷新时读 **`~/.claude.json` 的 `cachedGrowthBookFeatures`**（`:91752`），写回在 `:91830`（同时写 `cachedGrowthBookFeaturesAt`）。

影响压缩链路的 key：

- `tengu_amber_moleskin`（`JGv`）—— precompute arm 表
- `tengu_amber_rokovoko` —— precompute fraction 默认值
- `tengu_sepia_moth` —— precompute 总开关（`eZr`）
- `tengu_reactive_compact_remote` —— `VSe()` 在 remote 下的开关
- `tengu_amber_redwood2` / `redwood3`（`VOp`,`:155118`）—— `NFa` 的实验窗口，仅 `claude-opus-4-8`
- `tengu_cicada_nap_ms` —— startup prefetch 节流
- clientData 里的 `rowan_thicket`（`XGv`）与 `kelp_forest_sonnet`（`YZo`,`:73418`）

两台机器的 GrowthBook 分桶依赖 `EEa()`（`:94398`）里的 `deviceId`、`accountUUID`、`organizationUUID`、`subscriptionType` 等 —— **`deviceId` 天然逐机不同**，所以同账号的两台机器完全可能落进不同实验组。**置信度：高**（分桶输入含 deviceId 是代码事实；「本案由分桶差异造成」是推测，且如 5.1 所述我认为版本差异可能性更大）。

### 5.6 `mainLoopModel` 怎么定 ★

`X.options.mainLoopModel` 初值链：`:534586` 起自 `o4`，根源是 `Fi()`（`:72412`）= `gB() ?? KS()`，其中 `wht()`（`:72649`）按 org → env(`ANTHROPIC_DEFAULT_MODEL`) → enforced → entitlement → tier 定档。会话中还会被 `:312321`、`:312674` 的 model fallback / live switch **就地改写**。

跑代理时通常由 `ANTHROPIC_DEFAULT_MODEL` 或 `--model` 决定，两台机器如果一个用别名一个用全名，`$o()` 归一化结果不同 → `_9` 的表查找结果不同。**置信度：中**（机制确凿，是否为本案原因未验证）。

`autoCompactWindow` 本身：`:610940` `let K = i1p(t4.autocompact, Qo().autoCompactWindow)` —— CLI `--autocompact`（`aWn` 解析 `auto`/`500k`/`1m`/裸数字，`:155232`）优先于 settings 的 `autoCompactWindow`（schema 见 `:41764`，`int().min(1e5).max(1e6)`）。`/autocompact` 命令写入 **userSettings**（`:372566`）。

### 5.7 `querySource` ★

主循环传 `l`，取值包括 `"repl_main_thread*"`、`"sdk"`、`"agent:*"`、`"compact"` 等（`:312189` 的 `ze` 判断、`:304931` 的 `Xto`）。SDK / 非交互模式与 REPL 的 precompute fraction 取值不同（`FFa` 的 `repl`/`sdk` 分列），且 `"compact"` 与四个 auxiliary source 直接被 `zzw` 前两条门排除。

### 5.8 `isPreFirstCompactFork` ★

`:312189`。依赖 `X.precomputeSourceKey`（会话级，来自 sidecar rehydrate `:304863` 一带）与 `compactTracking`。纯会话内状态，跨机不稳定但不构成「一台永不压缩」。

### 5.9 已排除的可能性

- **`~/.claude/cache/model-capabilities.json`** —— `DBd`（`:73280`）第一行 `if (!VZo()) return;`，而 `VZo()`（`:73232`）在 2.1.241 里 `return false`。**该缓存在本版本完全不生效**，排除。**置信度：高。**
- **模型目录（model catalog）** —— `FVs()`（`:8144`）从 baked-in 常量 `Fjo` 构建，无磁盘/网络来源；只有 `HMr().runtimeCapabilityLookup` 可被宿主注入，普通 CLI 会话下为 undefined。排除为机器差异源。**置信度：中高。**
- **statsig** —— 本版本用的是 GrowthBook（`fQ()`/`Z8()`），没有独立 statsig 通路。任务提示里的 "statsig" 应理解为 GrowthBook，见 5.5。
- **`~/.claude/settings.json` 之外的 `~/.claude/*.json`** —— 压缩链路上没有任何其它 `~/.claude/` 下的 json 参与。排除。

---

## 6. `input_tokens` 小、`cache_read_input_tokens` 大：`UVe` 算得对吗？

### 6.1 `UVe` 本身：对

`:367014`：

```js
function UVe(e) {
    return e.input_tokens + (e.cache_creation_input_tokens ?? 0) + (e.cache_read_input_tokens ?? 0) + e.output_tokens;
}
```

四项全加，cache 字段缺失按 0。**Copilot 形态没有问题。置信度：高。**

### 6.2 有没有只看 `input_tokens` 的地方？

我检查了压缩链路上所有读 usage 的函数：

| 函数 | 行号 | 公式 | 用途 | 判断 |
|---|---|---|---|---|
| `UVe` | `:367014` | in + cc + cr + out | `eP` 的主项 | 正确 |
| `aie` | `:367021` | 走 `UVe` | 显示 | 正确 |
| `Nrn` | `:367043` | 四项都取（返回结构体） | `Uzw` | 正确 |
| `Uzw` | `:366173` | `in + cr + cc`（**不含 out**） | 「固定前缀是否已超阈值」warn | 有意为之，只影响一条 warn 日志 |
| `hvl` | `:367030` | `in + out`（**不含 cache**） | task budget 扣减 | **不在压缩判定路径上**；对 Copilot 会低估 budget 消耗 |
| `POm` | `:367049` | `in + cc + out`（**不含 cache_read**） | 按 message id 去重的累计统计 | 不在压缩判定路径上 |
| `XZo` | `:73427` | `in + cc + cr`（不含 out） | 百分比展示 | 展示用 |
| `:312637` | `Cu = in + cc + cr` | 与本地估算比对，算 `estimateGapTokens` | 遥测 | 无影响 |

**结论：自动压缩判定路径（`zzw` → `eP` → `UVe`）没有漏掉 cache 字段。置信度：高。**

### 6.3 但代理侧有一个真实的双计风险（推测，需代理侧核对）

OpenAI Responses 的 `usage.input_tokens` 是**含缓存命中在内的完整 prompt tokens**，`input_tokens_details.cached_tokens` 是其中命中的部分。如果代理把它映射成

```
input_tokens = usage.input_tokens          # 已含 cached
cache_read_input_tokens = cached_tokens    # 又加一遍
```

那么 `UVe` 会 **双计** cached 部分 → `contextTokens` 虚高 → **压缩比预期更早触发**。正确映射应是 `input_tokens = usage.input_tokens - cached_tokens`。

反过来，如果代理**完全不填 cache 字段**而 `input_tokens` 已是全量，`UVe` 结果是正确的。

这一项是「两台机器跑不同版本的代理」时的另一个差异源。**置信度：中**（映射语义是 OpenAI 侧的既定事实，但本项目代理当前如何映射我没有查，属于待核对项）。

### 6.4 另一个更隐蔽的风险：`message.id` 与 `MOm` 锚点

`eP`（`:367083`）：

```js
function eP(e, t4) {
    let r2 = MOm(e);
    if (!r2) return w2(e, t4);
    return UVe(r2.usage) + w2(e.slice(r2.anchorIndex + 1), t4);
}
```

`MOm`（`:367088`）找到最后一条带 usage 的 assistant 后，**会沿 `message.id` 相同的前驱继续往前挪 `anchorIndex`**。含义：

- 若代理对每条 assistant 消息都发**同一个 `message.id`**（例如固定字符串或复用 upstream response id），`anchorIndex` 会一路滑到很早的位置 → `w2` 会把大量历史消息按字符数**重新估算一遍并加到 usage 上** → **严重高估** → 过早压缩。
- 若代理**根本不带 usage**，`MOm` 返回 null → `eP` 退化为纯本地估算 `w2(全部消息)`，除以 `KR(model)`（`:73028`，未知模型返回 3，Claude 模型返回 4）。这时压不压缩完全取决于字符数/3 是否越过 167k。

**这是我认为除版本差异外，第二值得实测的点。置信度：中**（代码机制确凿；两台代理是否行为不同未验证）。

---

## 7. 未知模型名（如 `gpt-5.6-terra`）的影响

### 7.1 对 `BVe` —— 无影响

`ID = "<synthetic>"`（`:75095`）。

```js
function BVe(e) {
    if (e?.type === "assistant" && "usage" in e.message
        && !(e.message.content[0]?.type === "text" && Twt.has(e.message.content[0].text))
        && e.message.model !== ID) return e.message.usage;
    return;
}
```

`e.message.model !== ID` 只是在**排除 CC 自己本地合成的 assistant 消息**（`Twt` 是一组本地占位文本的集合，`:418747`）。任何真实模型名——认识的或不认识的——都通过。**置信度：高。**

`URl`（`:367010`）同理。

### 7.2 对窗口查找 —— 有决定性影响

未知模型名会依次落空：

- `KH(model)`（`:8157`）在 baked catalog 里查不到 → `Hlr` 走默认 32000/128000
- `_9` 的第 3、4、5、6 步全部落空（`XGv` 要 `Object.hasOwn`，`VGv`/`t1p` 是硬编码 Claude 名单）
- 到第 7 步 `Eht(e, n4)`（`:72989` → `kBd`,`:72985`）判定「CC 认不认识这个模型」→ 未知模型返回 false → **进入 `"unknown-model"` 分支**，`window = FC(model) = 200000`（除非设了 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`）
- 在 2.1.207 上没有第 7 步，落到 `"auto"` → **永不主动压缩**

另外 `KR(model)`（`:73028`）对未知模型返回 3（Claude 模型返回 4），即本地字符估算按 3 字符/token，比 Claude 模型**高估约 33%**。这会让未知模型在同样文本量下更早越过阈值。**置信度：高。**

---

## 8. 给用户的排查顺序（按 ROI）

1. **`claude --version` 对比两台**。若一台 ≤2.1.207 而另一台 ≥2.1.226，本案基本闭合（第 5.1 节）。
2. **`jq '.autoCompactEnabled' ~/.claude.json` 对比两台**（注意 `CLAUDE_CONFIG_DIR`）。为 `false` 即命中第 4 节。
3. **对比两台的相关环境变量**：`env | grep -E 'CLAUDE_CODE_(DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT|AUTO_COMPACT_WINDOW|MAX_CONTEXT_TOKENS|MAX_OUTPUT_TOKENS|DISABLE_NONESSENTIAL_TRAFFIC|REMOTE|SIMPLE)|DISABLE_(AUTO_)?COMPACT|CLAUDE_AUTOCOMPACT_PCT_OVERRIDE|CLAUDE_CONFIG_DIR|ANTHROPIC_DEFAULT_MODEL'`
4. **看两台工作目录下的 `.claude/settings.local.json`**（gitignored，天然逐机不同），以及 `/etc/claude-code/managed-settings.json`。
5. **开 `--debug` 看那行日志**：`autocompact: tokens=<n> level=<lvl> effectiveWindow=<w>`（`:366197`）。这一行是最直接的证据——如果一台机器**根本不打这行**，说明卡在了 `zzw` 的前 4 条门之一（大概率是第 4 条 `X3e`），而不是阈值没到。
6. `/context` 或 `/autocompact` 面板会显示 `Auto-compact window: ...` 及其来源（`:372555`、`:489699`：`"auto"` / `"from CLAUDE_CODE_AUTO_COMPACT_WINDOW"` / `"from settings"` / `"default for an unrecognized model"` / `"default for ..."`）。**这是不开 debug 时读出 `source` 的最快途径。**
7. 最后才查代理侧的 usage 映射与 `message.id` 稳定性（第 6.3、6.4 节）。

---

## 9. 未验证 / 待办

- 本报告全部基于**静态阅读**，没有在任一台机器上实跑验证。第 8 节的每一步都是「去测什么」，不是「已经测出什么」。
- `Qbe()`（`ap` 里 projectSettings 是否 alias userSettings 的判定）未展开。
- `s1p` 的 surface 维度（`CLAUDE_CODE_ENTRYPOINT` × `uc()` 订阅档位）只对 clientdata/硬编码表生效，未展开细读。
- 2.1.226 与 2.1.241 之间是否还有影响本链路的差异，未逐条比对（只比对了 `unknown-model` 一处）。
