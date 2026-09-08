# Residual canonical-history migration

日期：2026-09-08

## 范围与执行约束

本次只执行 residual ledger 中 destination 属于 `ghe-device-flow` 的 `canonical history` 行。按 ledger 的 exact source/destination 移动 4 份 `copilot-token-identity` 原件；`delete` 行不处理。未修改、移动或删除其它路径，未执行 `git add`、commit 或 push。

执行采用 no-clobber：迁移前确认 4 个 exact source 均为 regular file，4 个 exact destination 均不存在；随后仅创建 destination 所需目录并执行逐项 `mv`。

## Ledger rows

| exact source | exact destination | SHA-256 before | SHA-256 after | source absent | destination present | unique |
|---|---|---|---|---|---|---|
| `.dev/docs/copilot-token-identity/reports/260807-audit-token-identity-squash.md` | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-audit-token-identity-squash.md` | `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b` | `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b` | yes | yes | yes |
| `.dev/docs/copilot-token-identity/reports/260807-review-token-exchange-identity-r2.md` | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-review-token-exchange-identity-r2.md` | `7ad13e6ab9cec92253de301b4b3106a8dddc9dcde8808822b15c545bf1dca2d6` | `7ad13e6ab9cec92253de301b4b3106a8dddc9dcde8808822b15c545bf1dca2d6` | yes | yes | yes |
| `.dev/docs/copilot-token-identity/reports/260807-review-token-exchange-identity.md` | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-review-token-exchange-identity.md` | `389221551c98dcdd2f1f7130fa82dcafa06ff53dc7fea8cd7a62d297adc91ea5` | `389221551c98dcdd2f1f7130fa82dcafa06ff53dc7fea8cd7a62d297adc91ea5` | yes | yes | yes |
| `.dev/docs/copilot-token-identity/reports/260807-verify-token-exchange-identity.md` | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-verify-token-exchange-identity.md` | `f0cd41289ddb6f35761632b3eab5645268eebc73b3bc367056097dc3828743d3` | `f0cd41289ddb6f35761632b3eab5645268eebc73b3bc367056097dc3828743d3` | yes | yes | yes |

## Result

- Migration count: 4.
- All four destination blobs match their before hashes exactly.
- All four sources are absent and all four destinations are present.
- Destination paths are unique within `ghe-device-flow/history/`; no basename/path collision was introduced.
- The history index was updated to expose the new family and link this report.

## Verification

- Destination `sha256sum`: `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b`.
- The `.dev` git current `HEAD` old-source blob and index old-source blob both hash to `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b`; both match the destination.
- Only this report was corrected; the historical source/destination original was not modified, and no `git add`, commit, or push was performed.
