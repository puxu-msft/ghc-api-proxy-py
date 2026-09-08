# Next Implementation delta

- **Git 锚点**：主仓当前为 `main@380c757087dcb8688d98619e7ad8c4d572b6f040`。Checkpoint `380c757` 已进入 `main`，提交内容包括 current `implementation.md`、systemd-runtime Plan 与 service-cutover readiness；不要重复回放 foundations 或 systemd。
- **待提交文档**：工作树现有未提交修改为 `docs/agents/anthropic-responses-bridge/README.md` 与 `docs/agents/service-cutover/plan.md`。两者正在把旧 `cf53334…` 导航／计划快照同步到 current Implementation 事实；当前 index 为空。主会话提交前应按精确 pathspec复核并只提交这两份文件，不要顺带纳入现有 `docs/tmp/` 或 `verification/` 未跟踪资产。
- **下一产品动作——happy 四片**：消费 clean `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 的既有线性链，顺序固定为 `1ed13ad7e19385b9f86a1cd292547438f6137179` → `80b3cfade000cd9e1626074d14b1f9c9d5294891` → `c950912ad739f85c39397ab0f2c4d25b82dddcb7` → `7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。不要从 source refs重建第二条 integration；逐片执行 current Implementation 规定的 main-side gate与归档。
- **随后 usage**：clean `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857` 的精确 parent 是 happy HEAD `7e4b642…`。仅在 happy 四片全部进入 `main` 且逐片 gate／归档完成后消费，再执行 usage main-side gate并归档 source。
- **后继方向**：happy → usage之后进入 route wiring，再继续完整 Acceptance；完整 bridge仍为 `UNVERIFIED`，部署仍为 `NO_CUTOVER`。
- **接续方式**：主会话完成 README／Plan 提交后，先重新 gate `HEAD == refs/heads/main`、确认 happy／usage identities与 clean 状态未漂移；若均未漂移，可从 happy 四片回放直接继续，无需再次全文冷读 Implementation。若 HEAD、dirty paths、候选 HEAD或 parent任一变化，再回读对应 living 段落并重建 gate。
