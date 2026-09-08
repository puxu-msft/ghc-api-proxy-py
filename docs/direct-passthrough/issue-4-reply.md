# issue #4 的回复

状态：**已发出**，2026-09-01。<https://github.com/puxu-msft/ghc-api-proxy-py/issues/4#issuecomment-5499126649>

issue 本身**没有关闭**——用户要的是回复，关闭是另一个动作，留给用户。

发出版本引用的三个提交：`1fb37cd`（根因修复）、`fb5ed7f`（两半回归测试）、`a436c96`（opt-in 修补）。下面是发出的正文。

> **更正一条被记录下来的阻断观察**：`678d1af` 记着 issue #3 的回复因 `gh` 的 EMU 账号 `addComment` 返回 Unauthorized 而无法发出。2026-09-01 复查：`gh auth status` 有两个账号，活跃的是 `puxu-msft`，对本仓 `permissions` 为 `admin/push/maintain` 皆真，**本次 `gh issue comment 4` 一次成功**。所以那条限制是账号相关的，不是仓库相关的。**issue #3 的那份回复因此重新变得可发**，发不发由用户定。

---

## Root cause

Not the model, and not any of the Codex-specific request fields. It is a reasoning item whose `id` this proxy had rewritten.

`encrypted_content` is cryptographically bound to the item id upstream issued it under, and upstream verifies that binding when the item is sent back. The translating Responses leg minted its own ids — `f"rs_{response_id}_{output_index}"`, over a `uuid4` this proxy generates — while carrying upstream's seal unchanged. The pair a client stored was therefore self-contradictory from the moment it was written.

Replaying the attached 901,008-byte body against the upstream today returns a message that names the item directly:

```
400 invalid_request_body
The encrypted content for item rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0 could not be verified.
Reason: Encrypted content item_id did not match the target item id.
```

That id is `rs_` + a `uuid4` + `_0` — this proxy's spelling, not upstream's.

**One caveat on attribution.** The wording reported here (`The resource you requested was not found.`) differs from the wording a replay returns now. Both are 400 `invalid_request_body`, and the replay names an id this proxy is the only possible author of, but whether the two messages come from the same check upstream is not something the evidence closes. Treat the causal claim as high-confidence inference rather than direct observation.

**Why it looked like it appeared out of nowhere.** The failure is deferred. The turn that writes the bad pair is a clean 200 carrying a well-formed reasoning item; nothing is observable until a client that keeps a rollout history — Codex does — sends the item back. A conversation therefore works normally and then starts failing every turn, which is what was reported.

## Fixed

`1fb37cd` — the direct Responses leg now carries upstream's own events instead of round-tripping them through an Anthropic intermediate, so it mints no ids and the id/seal pair travels intact. That commit was made for issues #2 and #3; removing this defect was not known to be part of it at the time.

Both halves of the invariant are now pinned by regression tests in `fb5ed7f`: what the client is told, and what this proxy sends back upstream.

## What this does not fix

**A conversation that already contains one of these items stays broken, and upgrading does not repair it.** The bad pairs live in the client's own rollout history, not here; the client replays them every turn and upstream refuses them every turn. Verified: the attached body is still a 400 against the fixed build.

Two ways out.

1. **Start a new session.** Anything created after the fix is unaffected.
2. **Turn on the repair**, if a particular conversation is worth keeping: `hook_fix_responses_request.repair_minted_reasoning_ids: true` removes the `id` from an inbound reasoning item when it carries a seal *and* its id matches the exact shape this proxy used to mint. The seal and every other field are left alone, and the same body then succeeds. It is off by default and deliberately narrow — `rs_` is also how OpenAI spells a perfectly good reasoning item, so a looser pattern would break working conversations to fix broken ones.
