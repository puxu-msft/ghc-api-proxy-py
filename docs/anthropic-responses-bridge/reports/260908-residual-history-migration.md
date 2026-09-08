# 2026-09-08 residual canonical-history migration

## 范围与判据

- **输入 ledger**：`.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 中全部 33 条 `disposition = canonical history` 且精确 destination 前缀为 `.dev/docs/anthropic-responses-bridge/history/` 的行。
- **操作**：仅对该 33 条精确 source/destination 配对执行原样 `mv`；先建立 destination 父目录，未覆盖既有 destination，未删除任何 source 以外的文件或目录。
- **逐项判据**：迁移前 source 为 regular file、destination 不存在；迁移后 source absent、destination 为 regular file；表中每个 `pre/post SHA-256` 是迁前 source hash 与迁后 destination hash 的相等值。
- **不在范围内**：不处理该 residual ledger 的其它 destination、不处理删除行、不删除空目录、不改 ledger、不执行 `git add`、commit 或 push。

## 结果摘要

| family | 条目数 | 原始来源 | 点时边界 | current carrier |
|---|---:|---|---|---|
| early verification | 15 | `early-verification/archive-260715-phase3/`、`early-verification/archive-260716-final/` | 260715 Phase 3 的 blocker/major 验收及 260716 Phase 0–8 final（含 WS skip）；runner/probes 是当时方法资产。 | 无 direct；current verification 以根规则与 `tests/` 为准，bridge 行为以 `spec.md`／`implementation.md` 为准。 |
| legacy History bridge | 13 | `history/archive-260807-legacy-chain/reports/` | 260807 staged/squash candidate、exact tip review 与 scoped verification；只覆盖各原件明确范围。 | 无 direct；当前约束与行为分别回到 bridge `architecture.md` 与 `spec.md`。 |
| pipeline rewrite parity | 5 | `pipeline-rewrite-parity/reports/` | 260818–260819 固定源码、DB、reference project 与真实 probe 的差异调查，不是 current plan。 | 无 direct；bridge design/implementation/spec 及各具体 living topic 承接 current 状态。 |
| **总计** | **33** |  |  |  |

`history/README.md` 已逐 family 索引上述原始来源、点时边界和 current carrier；目录链接保留 family 内证据的导航，不将任何历史原件提升为 current authority。

## 逐项迁移与完整性记录

每行状态均为 `source absent; destination present; SHA-256 equal`。

| ledger 行 | source | destination | pre/post SHA-256 |
|---:|---|---|---|
| 195 | `.dev/docs/early-verification/archive-260715-phase3/PHASE3_ACCEPTANCE_REPORT.md` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260715-phase3/PHASE3_ACCEPTANCE_REPORT.md` | `c8933035a15635a87010794105517c1d5e31a720d44b775bb39faf03ba2b4e91` |
| 196 | `.dev/docs/early-verification/archive-260715-phase3/phase3_acceptance.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260715-phase3/phase3_acceptance.py` | `bc7eb4f245bff7571d25d14df3ea7f8228685d715771e73c6961ae7bf34b10b5` |
| 197 | `.dev/docs/early-verification/archive-260716-final/MANIFEST.md` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/MANIFEST.md` | `d949e31381d5fcbfc82b761910040770ca2b96999c95bcbe9fd8e67eb09be113` |
| 198 | `.dev/docs/early-verification/archive-260716-final/README.md` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/README.md` | `9aaccf60ea5225922b84aacbe6495862ce373b66ea322f634772a6239476e41e` |
| 199 | `.dev/docs/early-verification/archive-260716-final/REPORT.md` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/REPORT.md` | `f4009de08a02f1f2cd9d414507506fdb9f71d1d518e36447c21ea3a06aec1d4f` |
| 200 | `.dev/docs/early-verification/archive-260716-final/SUMMARY.md` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/SUMMARY.md` | `fe15e71c414bb913b5d078cc4c096f16fd7679f9ff3d11d5914b6d78ed269ada` |
| 201 | `.dev/docs/early-verification/archive-260716-final/probes/00_cli_smoke.sh` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/00_cli_smoke.sh` | `e0a5503ffde50b4ab79902a2188256d02627f87b04856a14133abc09fc9a8a1f` |
| 202 | `.dev/docs/early-verification/archive-260716-final/probes/01_dynamic_port_startup.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/01_dynamic_port_startup.py` | `360385b4f20ee7beffff3b53f0f1374e7474153d8e7a38ebd043c6abf19a2461` |
| 203 | `.dev/docs/early-verification/archive-260716-final/probes/02_anthropic_protocol.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/02_anthropic_protocol.py` | `bc559c6f6daade22557ca7845fb5110da553e4817ae50991835c72b8fc974124` |
| 204 | `.dev/docs/early-verification/archive-260716-final/probes/03_openai_three_prefixes.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/03_openai_three_prefixes.py` | `266efb773799b52f7f6325d89dca055bf3c84db468b802121385a35c42da4cc7` |
| 205 | `.dev/docs/early-verification/archive-260716-final/probes/04_responses_websocket.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/04_responses_websocket.py` | `26a9beb9230d310099036df4cd1793058e77493d35985ceffdae3ee937785b75` |
| 206 | `.dev/docs/early-verification/archive-260716-final/probes/05_history_metrics.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/05_history_metrics.py` | `09f04810e808f346beed5fbd28b115cf03981538bdc6042f9a30ae7b59ab35db` |
| 207 | `.dev/docs/early-verification/archive-260716-final/probes/06_approval_system.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/06_approval_system.py` | `fb1f78e03729cc85a09f76ba5e9c14fe318e892e2597a49344749ca88baa1f01` |
| 208 | `.dev/docs/early-verification/archive-260716-final/probes/07_gemini_azure.py` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/07_gemini_azure.py` | `5b35a585c2f9d4dbdc93c3bf54963766f40ad689015d8dfd66b7f1d16bed8ba9` |
| 209 | `.dev/docs/early-verification/archive-260716-final/run_all.sh` | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/run_all.sh` | `068c912eb8f117a36d3bd064826760fb6e35b0bfb7978bc90879b0fd36727e50` |
| 262 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-audit-history-squash-prep.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-audit-history-squash-prep.md` | `8e1eaae82d0b06bf54c80e4bc97d9024f90d85a8fe6c635fba0c185113523d4d` |
| 263 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-audit-history-squash-r2.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-audit-history-squash-r2.md` | `bec9eef53cc4f640810c2ab77ebd8da66a25de6ac955f4d4c71d1179e0905542` |
| 264 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-capability-history-integration.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-capability-history-integration.md` | `5967a04b07a3a830f3e0baf1777af8026e76328bbfc7ef47c43c1717785e3ed0` |
| 265 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r2.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r2.md` | `3a6756482c4cc2b042ee5acfb6b236e2d197aab08e3a5ea56da316e1caf3d127` |
| 266 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r3.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r3.md` | `156ab1c49d288ff865158e31339ad3b4d3fa6bb2cff60cab3d4304a22d70a523` |
| 267 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r4.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r4.md` | `5cc153d5c67f29622c97c0ee732f0c98310f0f5d3b592540766eef0929b1ce54` |
| 268 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts.md` | `44422ec2c58b97f11304d88bec00296d3c847a2f209d1f28a0934da237269c27` |
| 269 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-squash-evidence.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-squash-evidence.md` | `97be00d057926cdb7d38b78715bdff56e46a8bd2c8df8cff2b629c81ca82a843` |
| 270 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-stream-integration-r2.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-stream-integration-r2.md` | `3f7f6c45ee5f5f3a226ec14ff7517ac3d9427635fc78214d7bb8493bc2af6494` |
| 271 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-review-history-stream-integration.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-stream-integration.md` | `4c254ff6e00feb8038c73f37bb3bece6516dfcc838dbb202f6875e47e8c0d969` |
| 272 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-verify-history-facts-r2.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-facts-r2.md` | `50b4a2702fd48d913d12ba7f20a176b48fa436a4d980dad2bbd2675443865086` |
| 273 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-verify-history-facts.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-facts.md` | `e8a9f7ab6138b7a74424526e148c54ec19100d50db141f43508485dd757bdd6c` |
| 274 | `.dev/docs/history/archive-260807-legacy-chain/reports/260807-resume-verify-history-stream-integration.md` | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-stream-integration.md` | `b0f7a79948f591dba27989a8ba70202fdc60dd48183cbca54c4405f69c5cdcdf` |
| 313 | `.dev/docs/pipeline-rewrite-parity/reports/260818-cache-control-translation.md` | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-cache-control-translation.md` | `7357e2922201cd359cd8e426af2dfe36b163a5c57f3b62a5f23340e4b5def9c4` |
| 314 | `.dev/docs/pipeline-rewrite-parity/reports/260818-ops-gap.md` | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-ops-gap.md` | `543350bb9e85b4e0f7afe1854eb761fdbd1211dc72ea5b0924e5be3f90500a2d` |
| 315 | `.dev/docs/pipeline-rewrite-parity/reports/260818-retry-gap.md` | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-retry-gap.md` | `829cdf565df2d95e04a79d0e2d9415e26cdfb0780a5e5d31b78240362015181d` |
| 316 | `.dev/docs/pipeline-rewrite-parity/reports/260818-traffic-feature-gap.md` | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-traffic-feature-gap.md` | `2207155c87059eb3da494f4465ffa1d6ce327429eb395d703cbc837392806feb` |
| 317 | `.dev/docs/pipeline-rewrite-parity/reports/260819-copilot-api-js-ir-architecture.md` | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260819-copilot-api-js-ir-architecture.md` | `05a4b89c24f53fc18fc4cf729971b6aa832112213453b82bf9e3b7b2fa72109e` |

## 最终核验

1. ledger 过滤结果为 33 条；33 个 source 均已 absent，33 个 destination 均为 present regular file。
2. 逐 destination 重算 SHA-256 并与迁前记录比较，33/33 相等。
3. `history/README.md` 的 local Markdown file links 全部可解析；family directory links 是已有目录。
4. 本次未执行 `git add`、commit 或 push；未删除任何目录。
