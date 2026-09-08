#!/usr/bin/env node
// PoC: 复现 Claude Code 2.1.241 «上下文超限» 判据链，喂入不同错误信封，看它归到哪一类。
// 源：/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js
// 下面每个函数都是从该文件逐字抄来的，行号标在注释里。运行：node 260824-cc-context-limit-predicate-probe.mjs

// ---- L8356-8362  $s.makeMessage(status, body, fallbackMsg) ----
function makeMessage(e, t4, r2) {
  let n4 = t4?.message ? typeof t4.message === "string" ? t4.message : JSON.stringify(t4.message) : t4 ? JSON.stringify(t4) : r2;
  if (e && n4) return `${e} ${n4}`;
  if (e) return `${e} status code (no body)`;
  if (n4) return n4;
  return "(no status code or body)";
}

// ---- L116836  var myp = "capability_rejected: " ----
const myp = "capability_rejected: ";

// ---- L116746-116748  Oxa ----
function Oxa(e) {
  return `${myp}${e}`;
}

// ---- L116749-116759  A3 —— 带 token 边界的 "capability_rejected: <class>" 匹配 ----
function A3(e, t4) {
  let r2 = Oxa(t4), n4 = 0;
  for (;;) {
    let o4 = e.indexOf(r2, n4);
    if (o4 === -1) return false;
    let i = e[o4 + r2.length];
    if (i === void 0 || !/[A-Za-z0-9_:.-]/.test(i)) return true;
    n4 = o4 + 1;
  }
}

// ---- L116762-116765  Eci ----
function Eci(e) {
  let t4 = e.toLowerCase();
  return t4.includes("prompt is too long") || t4.includes("input is too long for requested model");
}

// ---- L116766-116768  Aci ----
function Aci(e) {
  return e.toLowerCase().includes("context window");
}

// ---- L116769-116771  Nxa ----
function Nxa(e) {
  return e.toLowerCase().includes("input length and `max_tokens` exceed context limit");
}

// ---- L414920-414923  jXr（prompt too long 谓词，无状态码门）----
function jXr(err) {
  if (!(err instanceof Error)) return false;
  return Eci(err.message) || A3(err.message, "prompt_too_long");
}

// ---- L414924-414926  qhr（max_tokens 溢出谓词，无状态码门）----
function qhr(err) {
  return err instanceof Error && (Nxa(err.message) || A3(err.message, "max_tokens_context_overflow"));
}

// ---- L414951-414953  Mah —— 注意：status === 413 ----
function Mah(err) {
  return err.isAPIError === true && err.status === 413;
}

// ---- L415528  Y9 ----
const Y9 = "Prompt is too long";

// 造一个等价的 APIError（$s）：message 由 makeMessage 生成，见 L8353。
function makeApiError(status, body) {
  const err = new Error(makeMessage(status, body, undefined));
  err.status = status;
  err.isAPIError = true;
  err.type = body?.error?.type ?? null;
  return err;
}

// ---- YvE (L415215) 中与上下文超限相关的两个决策点，按源码顺序 ----
// L415249: if (jXr(e) || qhr(e)) return Xd({ content: Y9, error: "invalid_request", ... })
// L415265: if (Mah(e)) { if (Aci(e.message) || A3(e.message, "prompt_too_long")) return Xd({ content: Y9, ... }) ... }
function YvE_contextBranch(err) {
  if (jXr(err) || qhr(err)) return { display: Y9, error: "invalid_request", via: "L415249 jXr||qhr" };
  if (Mah(err)) {
    if (Aci(err.message) || A3(err.message, "prompt_too_long")) return { display: Y9, error: "invalid_request", via: "L415265 Mah && (Aci||A3)" };
    return { display: "<request_too_large 分支>", error: "invalid_request", via: "L415270 Mah fallthrough" };
  }
  return { display: `API Error: ${err.message}`, error: "unknown", via: "L415356 泛化兜底" };
}

// ---- L415388 Nnt —— 归类成遥测/停止原因字符串 ----
// 只抄与上下文超限相关的三行，其余分支以 null 表示「本探针不覆盖」。
function Nnt_contextBranch(err) {
  if (err instanceof Error && (err.message.toLowerCase().includes(Y9.toLowerCase()) || jXr(err) || qhr(err))) return "prompt_too_long";  // L415397
  if (Mah(err)) return Aci(err.message) || A3(err.message, "prompt_too_long") ? "prompt_too_long" : "request_too_large";                  // L415409
  return null;
}

// ---- L116816 Tci —— 网关侧分类器（生成 capability_rejected: 前缀那一侧）----
function Tci(status, msg) {
  if (status === 413) return Aci(msg) || Eci(msg) ? "prompt_too_long" : void 0;
  if (status !== 400) return;
  if (Eci(msg)) return "prompt_too_long";
  if (Nxa(msg)) return "max_tokens_context_overflow";
  return;
}

const cases = [
  {
    name: "A  上游原样（用户实测）400 + Copilot 措辞",
    status: 400,
    body: { error: { message: "Your input exceeds the context window of this model. Please adjust your input and try again again.", code: "invalid_request_body" } },
  },
  {
    name: "B  代理改写成 anthropic 信封，但沿用 Copilot 措辞",
    status: 400,
    body: { type: "error", error: { type: "invalid_request_error", message: "Your input exceeds the context window of this model. Please adjust your input and try again again." } },
  },
  {
    name: "C  代理改写成 anthropic 信封 + 'prompt is too long' 措辞",
    status: 400,
    body: { type: "error", error: { type: "invalid_request_error", message: "prompt is too long: 210000 tokens > 200000 maximum" } },
  },
  {
    name: "D  同 C 但状态码 413",
    status: 413,
    body: { type: "error", error: { type: "invalid_request_error", message: "prompt is too long: 210000 tokens > 200000 maximum" } },
  },
  {
    name: "E  413 + 'context window' 措辞（Aci 唯一能生效的组合）",
    status: 413,
    body: { type: "error", error: { type: "invalid_request_error", message: "Your input exceeds the context window of this model." } },
  },
  {
    name: "F  400 + 'input is too long for requested model'",
    status: 400,
    body: { type: "error", error: { type: "invalid_request_error", message: "input is too long for requested model" } },
  },
  {
    name: "G  400 + max_tokens 溢出措辞",
    status: 400,
    body: { type: "error", error: { type: "invalid_request_error", message: "input length and `max_tokens` exceed context limit: 195000 + 32000 > 200000" } },
  },
  {
    name: "H  400 + 大写 'Prompt Is Too Long'（验 toLowerCase）",
    status: 400,
    body: { type: "error", error: { type: "invalid_request_error", message: "Prompt Is Too Long: 210000 tokens > 200000 maximum" } },
  },
  {
    name: "I  400 + 顶层扁平 message（验 makeMessage 第一分支）",
    status: 400,
    body: { type: "invalid_request_error", message: "prompt is too long: 210000 tokens > 200000 maximum" },
  },
];

const pad = (s, n) => (s + " ".repeat(n)).slice(0, n);
console.log("Claude Code 2.1.241 上下文超限判据链 —— 逐信封判定\n");
for (const c of cases) {
  const err = makeApiError(c.status, c.body);
  const y = YvE_contextBranch(err);
  const n = Nnt_contextBranch(err);
  console.log(`【${c.name}】`);
  console.log(`  err.message   = ${JSON.stringify(err.message)}`);
  console.log(`  Eci=${pad(String(Eci(err.message)), 6)} Aci=${pad(String(Aci(err.message)), 6)} Nxa=${pad(String(Nxa(err.message)), 6)} jXr=${pad(String(jXr(err)), 6)} qhr=${pad(String(qhr(err)), 6)} Mah=${Mah(err)}`);
  console.log(`  YvE 展示      = ${JSON.stringify(y.display)}  (error=${y.error}, via ${y.via})`);
  console.log(`  Nnt 归类      = ${JSON.stringify(n)}`);
  console.log(`  Tci 网关归类  = ${JSON.stringify(Tci(c.status, err.message) ?? null)}`);
  console.log("");
}
