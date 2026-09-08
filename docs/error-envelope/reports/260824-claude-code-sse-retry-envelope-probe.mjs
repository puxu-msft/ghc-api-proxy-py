// 原样照抄 app.pretty.js:8432 (iIn) 与 app.pretty.js:8356 (makeMessage)
const iIn = (e) => { try { return JSON.parse(e); } catch (t) { return; } };
function makeMessage(e, t4, r2) {
  let n4 = t4?.message ? (typeof t4.message === "string" ? t4.message : JSON.stringify(t4.message)) : t4 ? JSON.stringify(t4) : r2;
  if (e && n4) return `${e} ${n4}`;
  if (e) return `${e} status code (no body)`;
  if (n4) return n4;
  return "(no status code or body)";
}
// app.pretty.js:9346 —— 流内 error 帧的构造
function streamErrorMessage(rawData) {
  const l = iIn(rawData) ?? rawData;
  const type = l?.error?.type ?? null;          // → APIError.type
  return { message: makeMessage(undefined, l, undefined), type };
}
const RETRY = (m) => m?.includes('"type":"overloaded_error"');   // 273469 / 155911

const cases = {
  "A 嵌套信封, 紧凑":      '{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}',
  "B 嵌套信封, 带空格":    '{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}',
  "C 嵌套信封, 缩进换行":  JSON.stringify({type:"error",error:{type:"overloaded_error",message:"Overloaded"}}, null, 2),
  "D 扁平信封":            '{"type":"overloaded_error","message":"Overloaded"}',
  "E 扁平, 无 message":    '{"type":"overloaded_error"}',
  "F 非法 JSON":           '{"type":"error","error":{"type":"overloaded_error",}',
  "G 嵌套 rate_limit":     '{"type":"error","error":{"type":"rate_limit_error","message":"slow down"}}',
};
for (const [name, data] of Object.entries(cases)) {
  const { message, type } = streamErrorMessage(data);
  console.log(`${RETRY(message) ? "重试 ✓" : "不重试 ✗"}  ${name.padEnd(22)} APIError.type=${String(type).padEnd(18)} message=${JSON.stringify(message).slice(0,72)}`);
}
