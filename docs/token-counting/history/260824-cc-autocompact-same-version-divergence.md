# 同版本（2.1.241）同 settings.json，为什么一台不主动压缩

- 日期：2026-08-24
- 前序报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260824-cc-autocompact-trigger-forensics.md`（其第 5.1 节的版本差异假设**已作废**，本文不再依赖它）
- 证据源：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`，所有行号均指该文件
- 场景固定：本地交互会话、`lo() === "firstParty"`（走 `ANTHROPIC_BASE_URL` 代理不改变这一点，见 `:64554`）、模型名为 `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`

---

## 0. 本轮最重要的三个新发现（先给结论）

1. **`YGv` 的第一项 `IA(e)` 只看模型名里有没有 `[1m]`**（`:73330`：`/\[1m\]/i.test(e)`）。只要模型字符串写成 `gpt-5.6-terra[1m]`，`_9` 会**同时**在 `FBd`（`:73401`）拿到 1e6 窗口、并在 `:155292` 被 `YGv` 挡掉 unknown-model 分支，落到 `"auto"` → **该机器永不主动压缩**。这是一处**不经过任何配置文件**的差异（模型名可以来自 `ANTHROPIC_DEFAULT_MODEL`、`--model`、`/model`、或 `~/.claude.json` 的会话残留）。
2. **`~/.claude.json` 顶层的 `env` 对象会被直接 `Object.assign` 进 `process.env`**（`:191818`）。所以「settings.json 一致」完全不能保证「环境变量一致」——`~/.claude.json` 是第二个环境变量来源，且它排在所有 settings 之前。
3. **在本地会话里，`rvl` 的经典压缩路径是死代码，压缩一定走 reactive**（`:366209` 的条件在 `zzw` 通过后恒真，推导见第 6 节）。因此 reactive 的额外闸门 `t_l`（`:305139`）里的 **`aborted`** 成了真正的最后一道门，而它失败会被记成 `consecutiveFailures`，**攒够 3 次就整个会话不再压缩**（`_Om = 3`，`:366245`）。这是「判定说该压缩了，但被吃掉」的唯一真实通道。

---

## 1. `_9` 完整读出（`:155275`–`:155294`）

```js
function _9(e /*model*/, t4 /*autoCompactWindow*/, r2 = zx() /*sdkBetas*/) {
    let n4 = $o(e), o4 = FC(e, r2);
    if (process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW) {
      let l = cQe("CLAUDE_CODE_AUTO_COMPACT_WINDOW", process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW, cyi, OFa);
      if (l.status !== "invalid") {
        let c = Math.max(cyi, l.effective);
        return { window: Math.min(o4, c), configured: c, source: "env" };
      }
    }
    if (t4 !== void 0) return { window: Math.min(o4, t4), configured: t4, source: "settings" };
    let i = XGv(n4);
    if (i.window !== null) return { window: Math.min(o4, i.window), configured: i.window, source: "clientdata" };
    let s = NFa(n4);
    if (s !== void 0) return { window: Math.min(o4, s), configured: s, source: "experiment" };
    if (o4 < 1e6 && (VGv.has(n4) || KGv(e) || rha(e, r2))) return { window: Math.min(o4, _ve), configured: _ve, source: "model-default" };
    let a = i.replacesDefault ? void 0 : qGv(n4);
    if (a !== void 0) return { window: Math.min(o4, a), configured: a, source: "model-default" };
    if (mL() && !q.CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT && !YGv(e, r2) && !_Br(e) && !Eht(e, n4)) return { window: o4, configured: o4, source: "unknown-model" };
    return { window: o4, configured: o4, source: "auto" };
}
```

各分支：

| 顺序 | return 条件 | source | window 值 | 本地状态来源 |
|---|---|---|---|---|
| 1 | `process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` 非空且 `cQe` 判定不是 `"invalid"` | `"env"` | `min(o4, max(1e5, clamp后的值))` | 环境变量 |
| 2 | 传入 `t4 !== undefined` | `"settings"` | `min(o4, t4)` | `--autocompact` CLI > `Qo().autoCompactWindow`（`:610940`）；`/autocompact` 写 userSettings（`:372566`） |
| 3 | `XGv(n4).window !== null` | `"clientdata"` | `min(o4, i.window)` | GrowthBook `rowan_thicket` + `~/.claude.json` 的 `autoCompactWindowsCache`（`:73413`） |
| 4 | `NFa(n4) !== undefined` | `"experiment"` | `min(o4, s)` | GrowthBook `tengu_amber_redwood2/3`，且 `:155249` 要求模型 `=== qOp`（`"claude-opus-4-8"`），**gpt-* 永不命中** |
| 5 | `o4 < 1e6 && (VGv.has(n4) \|\| KGv(e) \|\| rha(e, r2))` | `"model-default"` | `min(o4, 200000)` | `VGv` 是硬编码 Claude 名单（`:155348`）；`KGv(e) = jfe() && KZo(e)`（`:155261`）要求 `CLAUDE_CODE_DISABLE_1M_CONTEXT` 且模型能映射到 1M 型号；`rha` 见下 |
| 6 | `!i.replacesDefault && qGv(n4) !== undefined` | `"model-default"` | `min(o4, a)` | 硬编码表 `t1p`（`:155347`）只有 `claude-sonnet-5` |
| 7 | `mL() && !q.CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT && !YGv(e,r2) && !_Br(e) && !Eht(e,n4)` | **`"unknown-model"`** | `o4`（不再取 min） | 见第 2 节 |
| 8 | 兜底 | `"auto"` | `o4` | —— `X3e` 返回 false → `zzw` 第四道门 return false → **不主动压缩** |

### `o4` 到底是多少 token

`o4 = FC(e, r2)`（`:73384`）：

```js
function FC(e, t4) {
    let r2 = NBd();               // :73390
    if (r2 !== void 0) return r2; // 仅当 q.DISABLE_COMPACT 且 CLAUDE_CODE_MAX_CONTEXT_TOKENS > 0
    if (rha(e, t4)) return _ve;   // 200000
    return FBd(e, t4);            // :73400
}
function FBd(e, t4) {
    if (IA(e)) return 1e6;                                  // 模型名含 [1m]
    if (t4?.includes(a7.header) && l7(e)) return 1e6;        // sdkBetas 含 context-1m-2025-08-07
    if (ZU(e)) return 1e6;                                   // 原生 1M 模型
    let r2 = YZo(e);                                         // GrowthBook kelp_forest_sonnet，仅 sonnet-4-6
    if (r2 !== null) return r2;
    let n4 = q.CLAUDE_CODE_MAX_CONTEXT_TOKENS;
    if (n4 !== void 0 && n4 > 0 && !$o(vs(e)).startsWith("claude-")) return n4;
    return y2r;                                              // 200000（:73454）
}
```

**对 `gpt-5.6-terra`、交互会话、无相关环境变量：`o4 = 200000`。**（`zx()` 在交互会话恒为 `undefined`，见 2.3；`ZU` 需 `$Bd(e)` 能映射到已知 1M 型号，gpt-* 不行；`YZo` 只认 sonnet-4-6。）**置信度：高。**

若设了 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=N`（模型名不以 `claude-` 开头，gpt-* 满足）：`o4 = N`。若同时 `KPr()`（1M 额度被封的会话内闩锁，`:415228` 触发）为真且 `N > 200000`，`rha` 会把它压回 200000（`:73397`）。

常量：`cyi = 1e5`、`OFa = 1e6`、`_ve = 2e5`、`y2r = 2e5`（`:155346`、`:73454`）。

---

## 2. `:155292` 五项逐个解析 ★本轮核心

### 2.1 `mL()` —— 自动压缩总开关（`:155124`）

```js
function mL() { if (KOp()) return false; return ap("autoCompactEnabled", true).value; }
function KOp() { return Boolean(q.DISABLE_COMPACT || q.DISABLE_AUTO_COMPACT); }   // :155121
```

**读什么本地状态**（`ap`,`:92721`，优先级高→低）：

1. `policySettings` — Linux `/etc/claude-code/managed-settings.json`（`:42836` + `cQ_()`）
2. `flagSettings` — `--settings` 指定的文件/内联（`:40474` 显示为 `"cli flag"`）
3. `localSettings` — cwd 下 `.claude/settings.local.json`（`:43050`）
4. `projectSettings` — cwd 下 `.claude/settings.json`（`:43048`）
5. `userSettings` — `~/.claude/settings.json`
6. `legacyGlobalConfig` — **`~/.claude.json` 顶层 `autoCompactEnabled`**，仅当 `!== zve.autoCompactEnabled`（默认 `true`，`:93159`、`:94474`）
7. 默认 `true`

**什么情况下让分支不成立**：以上任一层把它设成 `false`，或环境里有 `DISABLE_COMPACT`/`DISABLE_AUTO_COMPACT`。注意 `!mL()` 同时也是 `zzw` 的第三道门，所以此时症状是「彻底不压缩」而不是「掉到 auto」。**置信度：高。**

**机器间差异可能性：高。** `~/.claude.json` 与 `.claude/settings.local.json` 都不在「settings.json 一致」的比对范围内。

### 2.2 `q.CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT`（`:155292`）

- `q` 是 `process.env` 的惰性带 parser 视图（`wYs`,`:21747`；`q = wYs(UU_, eOr)`,`:21777`）。该键的 shape 在 `:21708` 注册为 `VB_`。
- **只要它为真值，unknown-model 分支立刻跳过 → `"auto"` → 不主动压缩。**
- CC 自己的文案确认了这个语义（`:610148`）：`CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 restores the previous wait-for-the-API behavior.`
- **来源不止 shell**：`~/.claude.json` 的 `env` 对象（`:191818`）、各层 settings 的 `env`（`:191819`–`:191824`）都会 `Object.assign` 进 `process.env`。

**机器间差异可能性：高**（纯 shell 环境变量，比对 settings.json 完全看不见）。

### 2.3 `YGv(e, r2)`（`:155263`）

```js
function YGv(e, t4) { return IA(e) || t4?.includes(a7.header) === true && l7(e); }
```

**第一项 `IA(e)`（`:73330`）**：

```js
function IA(e) { if (jfe()) return false; return /\[1m\]/i.test(e); }
function jfe() { return q.CLAUDE_CODE_DISABLE_1M_CONTEXT; }   // :73327
```

即：**模型字符串里出现 `[1m]`（大小写不敏感）就为真**，且 `CLAUDE_CODE_DISABLE_1M_CONTEXT` 未设。注意这是对**原始字符串 `e`** 做正则，不经过 `$o` 归一化——所以 `gpt-5.6-terra[1m]` 直接命中。

命中的后果是双重的：`FBd` 第一行返回 `1e6`（`:73401`）→ 第 5 步 `o4 < 1e6` 不成立；第 7 步 `!YGv` 不成立 → **落 `"auto"`，永不主动压缩**。

**第二项 `r2?.includes(a7.header) && l7(e)`**：

- `a7.header = "context-1m-2025-08-07"`（`:71249`）
- `r2 = zx()`（`:4344`）= `CP()?.sdkBetas ?? br.surfaceCapabilities.sdkBetas()`。`CP` 在本 build 里恒 `return;`（`:5333`），`$4s` 的 `#i` 初值是 `void 0`（`:2435`），唯一写入点是 `i5s`（`:4347`），唯一调用点是 `:624791`，位于 headless/SDK 启动函数 `y8y`（`:624706`，末尾 `runHeadless`）。
  → **交互 REPL 会话中 `zx()` 恒为 `undefined`，第二项恒假。**（置信度：高）
  → **但 `-p` / SDK / stream-json 会话中 `sdkBetas` 由调用方给定**；若其中含 1M beta header，第二项取决于 `l7(e)`。
- `l7(e)`（`:73377`）对 `gpt-5.6-terra`：`jfe()` 假 → `AMt` 假 → `KH(catalog)` 查不到 → 落到 `return t7(Iw(e))`；`Iw(e)`（`:64571`）在无 bedrock/mantle 时返回 `lo()` = `"firstParty"`；`t7`（`:64591`）对 `"firstParty"` 返回 **true**。
  → **所以在 SDK 会话里只要 betas 带了 1M header，`YGv` 就为真，同样落 `"auto"`。**（置信度：高）

**什么让分支不成立**：模型名带 `[1m]`；或 headless/SDK 会话且 sdkBetas 含 1M header。
**什么让它恢复成立**：设 `CLAUDE_CODE_DISABLE_1M_CONTEXT`（会让 `IA` 恒假），但那会连带改变 `KGv`/`ZU`/`l7`。

**机器间差异可能性：高**（模型名差一个后缀，或一台在交互模式、一台在 `-p` 模式）。

### 2.4 `_Br(e)`（`:64441`）

```js
function _Br(e) { return e.includes("application-inference-profile") && typeof EQt(fd(e)) !== "string"; }
```

Bedrock inference profile 专用。对 `gpt-5.6-*` **恒为 false**，不构成差异源。**置信度：高。**

### 2.5 `Eht(e, n4)`（`:72989`）

```js
function Eht(e, t4 = $o(e)) { return kBd(t4); }
function kBd(e) { let t4 = Qa(e); return KH(t4) !== void 0 || R5b.has(t4) || t4 === J9o; }   // :72985
```

- `KH`（`:8157`）查 **baked-in 模型目录**（`FVs()`,`:8144`，源自静态常量 `Fjo`）——两台机器必然相同。
- `R5b` = `{claude-3-opus, claude-3-sonnet, claude-3-haiku}`（`:73211`），`J9o = "claude-mythos-preview"`（`:60242`）。
- **真正的变量在 `n4 = $o(e)`（`:73008`）**：

```js
function $o(e, t4) {
    let r2 = t4?.overridesMap !== void 0 ? Nma(t4.overridesMap, e, true) : Nma(L5b(), e, false);
    if (r2 === void 0 && t4?.overridesMap === void 0) { let n4 = VDt(); r2 = Nma(n4, e, true); }
    if (r2 !== void 0) return r2;
    ...
    return D4(e);
}
```

- `L5b()`（`:73001`）= `Qo().modelOverrides` —— settings 层的 `modelOverrides`（用户已确认 `~/.claude/settings.json` 一致，但 **project/local/policy 层同样能提供**）
- `VDt()`（`:44280`）= `VYu(zR())` = `store.policy.pairedModelOverrides` —— **来自 policy/managed settings**（`:43148`），即 `/etc/claude-code/managed-settings.json`，完全不在 `~/.claude/settings.json` 里
- `D4(e)`（`:72954`）做子串匹配：模型名里若含 `claude-opus-4-5` 之类子串会被归一化成已知模型

若 `$o("gpt-5.6-terra")` 因 override 变成某个已知 Claude 模型 → `Eht` 为真 → unknown-model 分支跳过。但注意此时会命中第 5 步（`VGv.has`）拿到 `"model-default"`/200k，**仍然会压缩**——所以 `Eht` 为真通常不导致「不压缩」，除非映射到的模型既不在 `VGv` 也不在 `t1p` 里（例如 `claude-opus-4-5`、`claude-sonnet-4-5`、`claude-haiku-4-5`），那才落 `"auto"`。**置信度：中高**（机制确凿；「映射到哪个型号」需实测）。

CC 自己的提示文案也点名了这条路（`:610148`）：`map it in the modelOverrides setting`。

### 2.6 五项的机器间差异排序（问题 2 的直接答案）

| 排名 | 项 | 理由 |
|---|---|---|
| 1 | **`YGv` 的 `IA(e)`** —— 模型名带不带 `[1m]` | 不经任何配置文件；一台写 `gpt-5.6-terra[1m]` 就够。且后果是「彻底不压缩」而非「阈值不同」 |
| 2 | **`q.CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT`** | 纯环境变量；且可从 `~/.claude.json` 的 `env` 注入（`:191818`），比对 settings.json 看不见 |
| 3 | **`mL()`** —— `~/.claude.json` 顶层 `autoCompactEnabled` / `.claude/settings.local.json` / managed-settings | 三个都在「settings.json 一致」的比对盲区里 |
| 4 | **`Eht`** —— managed-settings 的 `modelOverrides`（`VDt`） | 机制确凿，但要映射到特定型号才导致不压缩，条件较窄 |
| 5 | `_Br` | 对 gpt-* 恒 false，排除 |

另加一项非本条件、但同样导致「看起来不压缩」的：`YGv` 第二项在 **headless/SDK 会话**下由 `sdkBetas` 决定（2.3）。若两台一台跑 `claude` 交互、一台跑 `claude -p`，行为会不同。

---

## 3. 分支成立后的阈值计算

设 `source === "unknown-model"`、`window = o4 = 200000`。

```js
function Wet(e, t4, r2, n4) {                                   // :155221
    if (n4 !== void 0) return PFa(e, n4.effectiveWindow, {...}, n1p(t4), n4.threshold);
    let o4 = BFa(t4, r2), i = o4.enabled ? r2 : void 0;
    return PFa(e, KSe(t4, i), o4, n1p(t4));
}
function KSe(e, t4) { let r2 = Math.min(Hlr(e), o1p), n4 = mL() ? t4 : void 0, { window: o4 } = _9(e, n4); return o4 - r2; }   // :155301
function n1p(e) { let t4 = Math.min(Hlr(e), o1p); return FC(e, zx()) - t4; }                                                   // :155305
function lyi(e, t4) { let r2 = e - 13e3; let n4 = t4.testPctOverride; if (n4 valid) return Math.min(Math.floor(e*(n4/100)), r2); return r2; }  // :155197
function PFa(e, t4, r2, n4 = t4, o4) {                          // :155205
    let i = o4 ?? lyi(t4, r2), s = r2.enabled ? i : t4, a = s - 2e4;
    let l = r2.testBlockingOverride, c = (l valid) ? l : n4 - 3e3;
    let u = Math.max(0, Math.round((s - e) / s * 100));
    if (e >= c) return { level: "blocked", pctLeft: u };
    if (r2.enabled && e >= i) return { level: "compact", pctLeft: u };
    if (e >= a) return { level: "warn", pctLeft: u };
    return { level: "ok" };
}
```

**`Math.min(Hlr(e), o1p)` 是什么**：为模型的一次输出预留的空间，封顶 `o1p = 2e4`（`:155341`）。含义是「有效上下文 = 窗口 − 本次可能产出的最大输出」。

**`Hlr(e)` 读什么**（`:429738`）：

```js
function Hlr(e) {
    let t4 = xMt(e);
    return cQe("CLAUDE_CODE_MAX_OUTPUT_TOKENS", process.env.CLAUDE_CODE_MAX_OUTPUT_TOKENS, t4.default, t4.upperLimit).effective;
}
```

`xMt(e)`（`:73437`）：目录里查不到该模型 → `default = B5b = 32000`，`upperLimit = U5b = 128000`（`:73454`）；再被 `G5b`（GrowthBook `heather_vale`）与 `DBd`（本版本死代码，`VZo()` 恒 false，`:73232`）可能调整。环境变量 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 若合法则覆盖，超 `upperLimit` 被 clamp（`cQe`,`:96774`）。

**具体数字（未知模型、无相关环境变量）**：

| 量 | 值 |
|---|---|
| `o4 = FC` | 200000 |
| `Hlr` | 32000 |
| `min(Hlr, 20000)` | 20000 |
| `KSe` = 有效窗口 | **180000** |
| `n1p` = blocking 基准 | 180000 |
| `lyi(180000)` = compact 阈值 `i` | **167000** |
| `warn` 阈值 `a = i - 20000` | 147000 |
| `blocked` 阈值 `c = n1p - 3000` | **177000** |

所以 `contextTokens >= 167000` 即 `level === "compact"` → `zzw` 返回 true。**置信度：中高**（公式是代码事实；32000 这个 default 依赖「目录里查不到 gpt-5.6-*」，这一点我按 `KH` 查 baked catalog 推断，未逐条枚举目录内容）。

**`DFa` 只用于 precompute 侧**（`:155202`）：`DFa(s, o4) = min(s - round(s * fraction), lyi(s, o4))`，`fraction` 由 `FFa` 给（默认 `ayi = 0.2`，`:155215`）。即预热在 `min(144000, 167000) = 144000` 就 arm。它**不改变**真正的压缩阈值。

---

## 4. `zzw` 前三道门

```js
if (EWr(n4)) return false;
if (QNt(n4)) return false;
if (!mL()) return false;
```

| 门 | 定义 | 条件 | 什么本地状态触发 |
|---|---|---|---|
| `EWr(querySource)` | `:155181`：`if (e === "compact") return true; return false;` | querySource 恰为 `"compact"` | 会话内状态（压缩自身发起的请求），不构成机器差异 |
| `QNt(querySource)` | `:155171`：`e !== void 0 && GGv.has(e)`，`GGv = new Set(["prompt_suggestion","away_summary","agent_summary","narration"])`（`:155192` 所在的 `syi` 初始化块） | querySource 属于四个辅助来源 | 会话内状态；这些辅助请求永不触发压缩 |
| `!mL()` | 见 2.1 | 自动压缩被关 | **`~/.claude.json` / 各层 settings / `DISABLE_COMPACT` / `DISABLE_AUTO_COMPACT`** |

前两道门只跟当前这一次请求的性质有关，**不是机器间差异源**（置信度：高）。第三道门是。

---

## 5. 同版本同 settings.json 下所有可能的差异输入

### 5.1 `~/.claude.json`（`Ib()`,`:21388` → `ex_()`,`:21383`；路径受 `CLAUDE_CONFIG_DIR` 影响）

| 键 | 参与方式 | 行号 |
|---|---|---|
| **`autoCompactEnabled`** | `ap` 的 `legacyGlobalConfig` 回退（键在 `Bor` 里，`:92740`），决定 `mL()` | `:92730` |
| **`env`** | `applySafeConfigEnvironmentVariables` 第一步 `Object.assign(process.env, filterSettingsEnv(cr().env, "globalConfig"))` —— **可注入本节 5.3 的任意环境变量** | `:191818` |
| `autoCompactWindowsCache` | `UBd()` → `XGv` → `_9` 第 3 步；缺失时还会通过 `replacesDefault` 反向放行第 6 步 | `:73415`、`:155270`、`:155289` |
| `cachedGrowthBookFeatures` | 所有 `nt(...)` 的离线取值（`tengu_amber_moleskin`、`tengu_amber_rokovoko`、`tengu_sepia_moth`、`tengu_reactive_compact_remote`、`tengu_amber_redwood2/3`、`tengu_cicada_nap_ms`、`heather_vale`） | `:91752`、`:91830` |
| `cachedExperimentFeatures` / `cachedExperimentData` / `cachedGrowthBookFeaturesAt` | 同上的配套 | `:91745`、`:91830`、`:92939` |
| `clientDataCacheSlots` / `clientDataCache` | `rT()` / `JZo()` → `BBd()?.rowan_thicket`（`_9` 第 3 步）与 `YZo` 的 `kelp_forest_sonnet`（`FBd`） | `:94414`、`:73418` |
| `startupPrefetchedAt` | 决定启动时是否重新拉 bootstrap（进而刷新上面两项） | `:611386` |
| `oauthAccount` | 参与 GrowthBook 分桶属性 `EEa()`（org/account/subscription） | `:94398` |
| `projects[<path>]` | 只涉及 trust，不进压缩链路 | `:93190` |

另外 GrowthBook 分桶输入含 **`deviceId`**（`EEa()`,`:94399` 的 `e.deviceId`），**逐机必然不同**——所以同账号两台机器完全可能落进不同实验组。

### 5.2 其他文件

- `.claude/settings.local.json`（cwd，gitignored） —— `localSettings`，可提供 `autoCompactEnabled`、`autoCompactWindow`、`modelOverrides`、`env`、`hooks`
- `.claude/settings.json`（cwd） —— `projectSettings`，同上；**两台机器如果在不同仓库/不同目录里跑，这一层天然不同**
- `/etc/claude-code/managed-settings.json` —— `policySettings`，优先级最高；还额外提供 `VDt()` 的 `pairedModelOverrides`（`:43148`）
- `--settings <file>` 指定的 `flagSettings`

### 5.3 被读到的环境变量（全部机器本地）

| 变量 | 读取点 | 对压缩的影响 |
|---|---|---|
| `DISABLE_COMPACT` | `:155122`、`:73391`、`:73351`、`:366200` | 彻底关闭 |
| `DISABLE_AUTO_COMPACT` | `:155122` | 彻底关闭 |
| **`CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT`** | `:155292` | 未知模型落 `"auto"` → 不主动压缩 |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | `:155277` | source 变 `"env"`，窗口 clamp [1e5,1e6] |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | `:73392`、`:73406`、`:610140` | 非 `claude-` 前缀模型的窗口直接由它决定；设大 → 阈值高到实际达不到 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `:429740` | 改 `min(Hlr, 20000)` 的扣减（只有调到 <20000 才有影响） |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `:155334` | 直接改 compact 阈值 |
| `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | `:155334` | 改 blocked 阈值 |
| `CLAUDE_CODE_DISABLE_1M_CONTEXT` | `:73328` | 改 `IA`/`l7`/`ZU`/`KZo`/`KGv` |
| `CLAUDE_CODE_REMOTE` | `:155148` | `VSe()` 可能 false，第四道门与 reactive 路由都变 |
| `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY` / `_MANTLE` / `_ANTHROPIC_AWS` / `_ANTHROPIC_GOOGLE_CLOUD` / `_GATEWAY` | `:64554` | `lo() !== "firstParty"` → `UBd()` 恒 null、bootstrap 跳过；也改 `t7`/`Iw` |
| `ANTHROPIC_DEFAULT_MODEL` / `ANTHROPIC_MODEL` | `:72674`（`TMt`） | 决定 `mainLoopModel` 字面值 —— **含不含 `[1m]` 就在这里定** |
| `ANTHROPIC_BASE_URL` | `:64599`（`Zmt`） | 影响 `Fm()`/`Fq()`，进而 `ZU` 的 1M 判定 |
| `_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL` | `:64598` | 同上 |
| `ANTHROPIC_BETAS` | `:610110`（`Ce0`） | 仅影响 cap-enforcement 提示文案，**不进 `YGv`** |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` / `DISABLE_TELEMETRY` / `DO_NOT_TRACK` | `:17393` | bootstrap 与 GrowthBook 停更 |
| `ANTHROPIC_UNIX_SOCKET` | `:372694` | bootstrap 跳过 |
| `CLAUDE_CONFIG_DIR` | `:21385` | 换掉 `~/.claude.json` 位置 → 上面 5.1 整片状态换一套 |
| `CLAUDE_CODE_ENTRYPOINT` | `:155252`（`s1p`） | 影响 clientdata/硬编码窗口表的 surface 取值 |
| `CLAUDE_CODE_SIMPLE` / `--bare` | `:8236` | 跳过 startup prefetch |
| `CLAUDE_CODE_COLD_COMPACT` | `:366189` | 只影响压缩时是否 strip 非必要内容 |
| `CLAUDE_CODE_SESSION_KIND` | `:611360` | 决定 unknown-model 提示是 TUI 提示还是只进日志 |

**注意环境变量的来源不止 shell**：`~/.claude.json` 的 `env`、以及 globalConfig → userSettings → projectSettings → localSettings → flagSettings → policySettings 各层 `env`，都会依次 `Object.assign(process.env, ...)`（`:191818`–`:191824`），随后再对通过 `eNr` 白名单（`:40786`）的键做一次覆盖写（`:191830`）。**settings 的 `env` 覆盖 shell 的同名变量**（`Object.assign` 方向）。`filterSettingsEnv`（`:191790` 附近）会按 project-scope / provider-strip / host-managed 三道过滤器裁剪，具体谓词我未逐条展开。**置信度：中高。**

### 5.4 CLI 与会话形态

- `--autocompact <auto|500k|1m|N>`（`aWn`,`:155232` + `i1p`,`:155243`，在 `:610940` 汇入 `options.autoCompactWindow`）
- `--model` / `/model` 决定 `mainLoopModel` 字面值
- `--continue` / `--resume` → **抑制 unknown-model 提示的显示**（`:611358` 的条件），但不改变行为 —— 这会让「一台看到提示、一台没看到」变成假线索
- 交互 REPL vs `-p`/SDK → `zx()`（sdkBetas）有无，见 2.3

### 5.5 代理侧（不在 CC 内，但会造成同样症状）

- usage 映射：若 `input_tokens` 已含 cached 又另填 `cache_read_input_tokens`，`UVe`（`:367014`）双计 → 提前压缩；若完全不填 usage，`eP`（`:367083`）退化为纯本地估算
- `message.id` 稳定性：`MOm`（`:367088`）会沿相同 id 把锚点前移，id 不稳定或复用都会让 `eP` 偏差很大

---

## 6. reactive 路由：会不会把压缩吃掉 ★本轮第二重点

### 6.1 本地会话里 reactive 是唯一路径

`rvl` 的分叉（`:366209`）：

```js
let f = AWr(a, l), m = Gzw(a, l);
if (n4 !== void 0 && f !== "auto" && VSe()) { /* reactive */ }
```

- `n4` 是 `rvl` 的第 4 个参数 = querySource，主循环 `:312195` 传的是 `l`，恒为字符串 → `n4 !== void 0` 恒真
- `VSe()` 非远程恒真（`:155145`）
- `f !== "auto"`：`zzw` 第四道门已保证（`VSe()` 真时 `X3e` 必须为真才走到这里）

**推论：在本地会话中，只要自动压缩触发，就一定走 reactive；`:366216` 起的经典 `tzi` 路径是死代码。置信度：高。**

### 6.2 用户在界面上看到什么

`zFi`（`:305142`）依次发出：

- `onCompactEvent({type:"compact_progress", event:{type:"hooks_start", hookType:"pre_compact"}})`
- `onCompactEvent({type:"sdk_status", status:"compacting"})`
- `onCompactEvent({type:"compact_progress", event:{type:"compact_start", hintText: u}})`
- 结束时 `compact_end` + `sdk_status: null`（成功带 `metadata.compactResult: "success"`，失败带 `"failed"` 与 `compactError`）

`hintText` 来自 `Gzw(a, l)`（`:366240`）：

```js
function Gzw(e, t4) {
    let r2 = $o(e);
    if (NFa(r2) === void 0) return null;
    ...
    return `Compacting at auto window (${ic(o4)} tokens) · /autocompact to configure`;
}
```

`NFa`（`:155248`）要求模型 `=== "claude-opus-4-8"`，所以**未知模型下 `hintText` 恒为 null**——用户看到的是不带说明文字的压缩提示。**置信度：高。**

成功后主循环 `:312200` 会 emit `tengu_auto_compact_succeeded` 并渲染压缩结果消息；用户能看到压缩确实发生。

### 6.3 什么条件下 reactive 也不发生

`t_l`（`:305139`）是 reactive 的额外闸门：

```js
function t_l(e) {
    return !e.hasAttempted && !EWr(e.querySource)
        && (e.hasPrecomputedSwap === true || !QNt(e.querySource))
        && mL() && VSe() && !e.aborted;
}
```

对照 `zzw` 已经检查过的项，**唯一新增的是 `!e.aborted`**（`:366212` 传的是 `H.abortController.signal.aborted`）。

因此存在这样一条通道：

1. `zzw` 判定「该压缩了」
2. 进 reactive，此时 abortController 已被中止（用户按 ESC、上一次工具调用触发了 abort、或 `:366213` 的 `tsi = 600000`ms 恢复超时把 signal abort 掉，`:96648`）
3. `t_l` 返回 false → `zFi` 立刻 `return { result: null, hookBlocked: false }`
4. `rvl` 走到 `:366215` `return yOm(o4, true, f, w)` → `{kind:"failed", consecutiveFailures: n+1}`
5. 主循环把它记成 `Ze = true`（`:312212` `We.kind === "compacted" || We.kind === "failed"`），并把 `consecutiveFailures` 写回 `compactTracking`（`:312210`）
6. **累计到 3 次，`:366201` 的 `failure_breaker_open` 从此对整个会话生效，再也不压缩**（`_Om = 3`,`:366245`）

`yOm`（`:366168`）只在**恰好第 3 次**打一条 warn 日志与 `tengu_auto_compact_circuit_breaker` 遥测；前两次静默。**这就是「判定说该压缩了，但被吃掉」的真实机制。置信度：高**（代码路径确凿；「本案由它造成」是推测，需要 `--debug` 日志佐证）。

另外两条会吞掉压缩、但会留下痕迹的路径：

- **PreCompact hook 阻断**：`vFe(...)` 返回 `blockedBy` → `zFi` 返回 `hookBlocked: true` → `rvl` 返回 `{kind:"hook_blocked"}`，日志 `Reactive compact blocked by PreCompact hook: ...`（`:305156`）。**hooks 可以来自 `.claude/settings.local.json` 或插件，是机器本地的。**
- **压缩 API 调用失败**：`r_l` → `DFi` 失败 → 同样计入 `consecutiveFailures`。**在 Copilot 代理下，压缩用的那次调用如果被代理拒绝（例如上下文太长），这里会连续失败 3 次然后永久熄火。这是我认为在本项目场景下第二值得实测的点。置信度：中。**

### 6.4 reactive 与非 reactive 的可观测差异

`tengu_auto_compact_succeeded` 带 `routedThroughReactive: true`（`:312200`）；reactive 另有 `tengu_reactive_compact_triggered` / `_succeeded` / `_failed`。`--debug` 下可见 `autocompact: routing through reactive (thresholdSource=unknown-model)`（`:366210`）。

---

## 7. 我否决了什么

| 否决项 | 理由 |
|---|---|
| **CC 版本差异**（上一轮的主假设） | 协调方给出新事实：两台都是 2.1.241。作废。 |
| `autoCompactWindowsCache` 是主因 | `XGv` 的 `r2(i)` 要求 `Object.hasOwn(i, $o(model))` 精确命中（`:155268`），该表由 Anthropic 服务端下发、只含 Claude 模型名；`gpt-5.6-*` 命不中。且 `lo()==="firstParty"` 时两台都能拉到同一份。**置信度：中高。** |
| `~/.claude/cache/model-capabilities.json` | `DBd` 首行 `if (!VZo()) return;`，`VZo()` 恒 `return false`（`:73232`）。本版本死代码。**置信度：高。** |
| 模型目录（catalog）差异 | `FVs()`（`:8144`）从 baked-in 常量 `Fjo` 构建，无磁盘/网络来源；`HMr().runtimeCapabilityLookup` 初值 undefined（`:8123`）且 `KH` 不读它。**置信度：高。** |
| `_Br(e)` | 只对含 `application-inference-profile` 的 Bedrock 模型名为真，与 gpt-* 无关。**置信度：高。** |
| `NFa` / `tengu_amber_redwood2/3` 实验窗口 | `:155249` 硬性要求 `e !== qOp` 时 return，`qOp = "claude-opus-4-8"`。gpt-* 永不命中。**置信度：高。** |
| `KPr()`（1M 额度闩锁） | 只在 `FBd(e,t4) > 200000` 时才通过 `rha` 起作用（`:73397`）；未设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 时 `FBd = 200000`，不满足。**置信度：高。** |
| `ANTHROPIC_BETAS` 影响 `YGv` | `YGv` 只读第二参 `r2`（= `zx()`），不读 `ANTHROPIC_BETAS`；后者只出现在 `Ce0`（`:610110`），那是 cap-enforcement 提示的判据。**置信度：高。** |
| `zzw` 前两道门（`EWr`/`QNt`）作为机器差异源 | 二者只看当前请求的 querySource，跟机器状态无关。**置信度：高。** |

---

## 8. 建议的实测顺序

1. **在两台各跑一次并看启动提示**。unknown-model 分支成立时 CC 会打（`:611359` → `Ie0`,`:610137`）：
   > `"gpt-5.6-terra" is not a model this version of Claude Code recognizes, so auto-compact will keep this session within 200K tokens (the context window it assumes). ...`
   **有这行 = 分支成立（会压缩）；没有这行 = 要么落了 `"auto"`，要么被 `--continue`/`--resume` 抑制显示（`:611358`），要么设了 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`（`:610141` 会 return null）。**
2. `/context` 面板读 `Auto-compact window:` 后面的来源词（`:372555`、`:489699`）：`auto` / `from CLAUDE_CODE_AUTO_COMPACT_WINDOW` / `from settings` / `default for an unrecognized model` / `default for ...`。**这是不开 debug 直接读出 `source` 的最快途径。**
3. 精确核对两台的模型字面值（`/status` 或 `echo $ANTHROPIC_DEFAULT_MODEL`），**特别注意有没有 `[1m]` 后缀**。
4. `jq '{autoCompactEnabled, env, autoCompactWindowsCache}' "${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json"` 两台对比。
5. `env | grep -E 'CLAUDE_CODE_(DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT|AUTO_COMPACT_WINDOW|MAX_CONTEXT_TOKENS|MAX_OUTPUT_TOKENS|DISABLE_1M_CONTEXT|REMOTE|USE_)|DISABLE_(AUTO_)?COMPACT|CLAUDE_AUTOCOMPACT_PCT_OVERRIDE|CLAUDE_CONFIG_DIR|ANTHROPIC_(DEFAULT_)?MODEL|ANTHROPIC_BASE_URL'`
6. 检查两台 cwd 下的 `.claude/settings.local.json`、`.claude/settings.json`，以及 `/etc/claude-code/managed-settings.json`。
7. `--debug` 抓这两行：
   - `autocompact: tokens=<n> level=<lvl> effectiveWindow=<w>`（`:366197`）—— **没有这行说明卡在 `zzw` 前四道门**
   - `autocompact: routing through reactive (thresholdSource=...)`（`:366210`）
   - `autocompact: circuit breaker tripped after 3 consecutive failures (reactive path)`（`:366168`）—— 命中即第 6.3 节
8. 最后才查代理侧的 usage 映射与 `message.id`（第 5.5 节）。

---

## 9. 未验证 / 局限

- 全部基于静态阅读，**未在任一台机器上实跑**。第 8 节是「去测什么」，不是「已测出什么」。
- 第 3 节的 `Hlr = 32000` 依赖「baked catalog 里没有 `gpt-5.6-*`」，我按 `KH` 的查表逻辑推断，未枚举 `Fjo` 的内容。
- `filterSettingsEnv`（`:191790` 一带）的三道过滤器谓词未逐条展开，因此「`~/.claude.json` 的 `env` 能注入任意 `CLAUDE_CODE_*`」这一条我标为中高置信度而非高。
- `t_l` 的 `aborted` 在实际 REPL 里多久触发一次、是否真的能连攒 3 次，未做时序验证。
