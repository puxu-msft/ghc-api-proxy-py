# 顶层 tmp Bridge 证据迁移

日期：2026-09-08
依据：`.dev/docs/dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md` 的最终 disposition ledger。

## 处置

已将 ledger 指定的 11 份 `canonical history` 原件从 `.dev/docs/tmp/` 移至 `../history/` 的同名路径，未修改其内容。每份的来源、point-in-time 限定与 current carrier 已登记在 [`../history/README.md`](../history/README.md)。

| 原件 | SHA-256（移动前后相同） |
|---|---|
| `260807-final-review-current-main.md` | `791faa385af3883624c8791bbd0ae53e0b6e2ff85de524a2188df091f2b0ec0e` |
| `260807-resume-audit-systemd-bridge-overlap.md` | `81007af155bf691a40e88d0a2a696866984116aef28f2456f0b09419170d3458` |
| `260807-review-backup-r3-living-checkpoint.md` | `a41339f1b8465b3cb461a63c2c115bd9826fed2d3ba44237f9f6bd28b6e1b209` |
| `260807-review-identity-living-checkpoint.md` | `0d2358e8e06a91d8e02fdf974be657ed5244c2d51d8ab2327b07d1c107d1c43a` |
| `260807-review-living-after-main-replay-r2.md` | `c052905a3a7ed1be425ec906f7adda8df965804e5d007f86e542f8615f40da10` |
| `260807-review-main-foundations-systemd.md` | `f74e487c15239c9377fa777d61b7c13c554420e8adae1318fb57693be943e05a` |
| `260807-review-reservation-wiring-living.md` | `8c2fd1fcd0d9b3a08a104cdeaef3f994579190ed77476b2f610511022f2840d0` |
| `260807-review-resident-living-checkpoint.md` | `2ef648659534d9f39d5a5c4f859b8eae8efb24cc32c4fcc360c02ffcfee2354c` |
| `260807-verify-main-foundations-systemd.md` | `3399ce3143afc791f03017ea20f5d391f328fca679eac5fb4833309abd98dd23` |
| `260824-defer-loading-responses-leg-investigation.md` | `137f7c23e3ef8cf23bf3fe619473e9362283c3f87aa8d939d9846b04d4f4e44e` |
| `260824-tool-search-beta-400-investigation.md` | `dfafd476a8d93591ca029b28311cd211cae99b453dfa5eee4fa2099ff3183f98` |

## 验证

移动后逐项检查了 11 个 destination 存在、11 个 `tmp/` source 不存在，并将 destination 的 SHA-256 与移动前捕获的值逐项比较；全部匹配。未执行 `git add`、commit 或 push，且未移动、删除或修改这 11 项之外的 `tmp/` 文件。
