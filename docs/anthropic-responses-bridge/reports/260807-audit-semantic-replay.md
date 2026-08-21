# Semantic parity candidate 最终回放审计

- **评审范围**：只读审计 `/home/xp/src/ghc-api-proxy-py-semantic-parity` 的 `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 相对 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖两提交 range、review／verification、paths、stable patch-id、blobs、current-main preimage、archive target及相对 bridge-next route／block 的依赖。本轮不执行 Git 操作或运行态动作；唯一写入是本报告。
- **总体 verdict**：**可进入下一阶段；semantic candidate 为 0 major，明确可回放。** Exact candidate 已取得代码复评 `0 blocker／0 major／0 minor` 与独立验收 `PASS`，本轮身份对账未发现问题。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **唯一顺序建议**：**semantic 先行，随后 route，再随后 block。** Semantic 内部固定 `1cde3d58338eeefb3cf8040f970c3612d451668b → f5bca39ac582911b61d278fd678ec9298ad0c08e`。旧 bridge-next `a23081c…` 仍为 `1 major／FAIL`，须先形成并放行 successor，之后才可按 route → block 回放。
- **archive 结论**：回放及 main-side gate 通过后，immutable archive target 必须精确为 reviewed pre-squash HEAD `f5bca39ac582911b61d278fd678ec9298ad0c08e`，不得改指 main squash 或 integration commit。当前没有 archive ref 指向该对象，只有活动分支 `fix/responses-semantic-parity` 指向它；本轮不创建 ref。

## 双视角覆盖证据

### 机械核对

- 主树固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`；semantic 树固定为 clean `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`。
- 提交图严格为 `80bc8f2… → 1cde3d5… → f5bca39…`，range 内恰有 2 个 non-merge commits、0 个 merge commits。
- Range 只修改 `src/app/openai/responses_stream_parser.py` 与 `tests/unit/test_responses_stream_parser.py`；`git diff --check` 通过。
- 每个提交的 stable patch-id 均由 `git show --binary` 与 `git diff --binary parent commit` 两种入口交叉验证；整个 range 也独立计算 patch-id。
- 两个 path 的 current main commit、index、worktree 与 semantic 首提交 parent blobs 四层精确一致。
- Code review R2 SHA-256 为 `97e79e3826a863320dada383ced36c1eddce25dc9fd5b4a56566b292da4ba366`，绑定 exact HEAD并给出 `0 blocker／0 major／0 minor`、可 squash。
- Verification R2 SHA-256 为 `3948065b70cca09409573e152c9cd18dc593115dfd5e7a5ff9377ec57d8f2886`，绑定 exact HEAD并给出 `PASS`。
- Bridge-next 两提交严格为 route `1e3233cf23c07088469e3aa336c2e6031ce1315b` 后接 block `a23081c5d5f48143bf3015182d8f00e1f6297755`，且与 semantic 两个 paths 零重叠。旧组合 review 为 `0 blocker／1 major／0 minor`，verification 为 `FAIL`，当前不可回放。

### 第一人称执行

- 从 current main 回放 semantic 时，第一提交 preimage 与 main 三层 bytes一致，第二提交 parent精确承接第一提交 postimage，不需要冲突猜测或整文件选边。
- 精确 R2 已执行 unknown／future summary typed reject、authoritative conflict、真正 item.done-only function、empty／encrypted-only reasoning 与 permissive 正控；同时核对合法输入未被 strict gate误拒，覆盖 false-green 与 false-red。
- Parser 只产出 attempt-local immutable semantic facts，不渲染 Anthropic wire、不推进 delivery frontier；delivery消费这些 facts，route建立生产入口。因此 semantic 是 route／block 的上游语义基座。
- 先回放 semantic 不触碰 route／block paths，也不会掩盖旧 bridge-next 的 hooks `ERROR／FINALIZE` major。若等待旧 bridge-next，会让已达 0／0＋PASS且 preimage闭合的独立 slice 被无关 FAIL阻塞。
- Semantic 回放后仍须在 route／block实际动作前重验 main HEAD 与 touched paths；零路径重叠不替代执行时 gate。

## 两提交身份账本

### Commit 1

- Commit：`1cde3d58338eeefb3cf8040f970c3612d451668b`。
- Parent：`80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- Subject：`fix: enforce responses stream semantic parity`。
- Tree：`5d18465fd3584137da16c29a6f67ecfc086979da`。
- Stable patch-id：`46aca51800fb72fb9792d832466867eae292cd04`。

| Path | Parent preimage | Commit postimage |
|---|---|---|
| `src/app/openai/responses_stream_parser.py` | `f1eb3a0c901111ee24b363869e97ee0a3d6b2337` | `7cabcdad96b845f4c9e17b19251cc2f8b05613c6` |
| `tests/unit/test_responses_stream_parser.py` | `a0d045df8225904fe3ce941091d4715a0253ab97` | `909bd14ad27918980ccdbdf7b2b64104dc2ee239` |

### Commit 2

- Commit：`f5bca39ac582911b61d278fd678ec9298ad0c08e`。
- Parent：`1cde3d58338eeefb3cf8040f970c3612d451668b`。
- Subject：`fix: reject unsupported reasoning summary parts`。
- Tree：`84cc08959fc61ede4b03d835ac07b696b5662204`。
- Stable patch-id：`f037d26f6c39e808aea163ec0e8a77f11f2669db`。

| Path | Parent preimage | Commit postimage |
|---|---|---|
| `src/app/openai/responses_stream_parser.py` | `7cabcdad96b845f4c9e17b19251cc2f8b05613c6` | `df3353f1a1882fd4035657563280bfa5f93989ab` |
| `tests/unit/test_responses_stream_parser.py` | `909bd14ad27918980ccdbdf7b2b64104dc2ee239` | `bb77e15edce5c05f4abbf9c1a9b819635b804ec8` |

- Range stable patch-id：`4e7b96c163311c775ad68b95057195c5a5f66202`。

## Current main preimage

- `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` tree：`a149d1dc5fdfca36e09c938380e95df34faa77dd`。
- `src/app/openai/responses_stream_parser.py` 的 main commit／index／worktree／semantic first parent均为 `f1eb3a0c901111ee24b363869e97ee0a3d6b2337`。
- `tests/unit/test_responses_stream_parser.py` 的四层 blob均为 `a0d045df8225904fe3ce941091d4715a0253ab97`。

## 事实性发现

未发现问题。Semantic candidate、current-HEAD review／verification、两提交身份与 current-main preimage均满足回放前置门。

## 主观建议

无。唯一顺序已由 exact verdict、提交依赖、数据流方向与路径集合共同约束，不保留并列备选。

## 结论

**0 blocker／0 major／0 minor；`fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 明确可回放。** 唯一执行顺序为 **semantic `1cde3d… → f5bca39…` 先行；bridge-next successor 自身取得 0 major／PASS 后，再按 route → block 回放**。Archive target固定为`f5bca39…`；本报告不创建ref、不修改Git，也不外推完整产品PASS或部署授权。
