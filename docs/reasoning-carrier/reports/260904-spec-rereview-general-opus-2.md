# Reasoning carrier Spec 限定复评

## 快照与结论

- snapshot_time: `2026-09-04T06:05:05+08:00`
- reviewed_object: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`
- object_snapshot: mtime `2026-09-04T06:00:39.994957644+08:00`，size `28203` bytes
- disposition: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec-review-disposition.md`，mtime `2026-09-04T05:46:08.433644172+08:00`
- prior_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-spec-review-general-opus-1.md`
- source_rev: `990e3774e028affc75114d6ffe6e6889bc6747fd`
- verdict: `pass`
- closure_counts: original_closed=4，original_open=0，new_blocker=0，new_major=0，nonblocking_notes=2
- implementation_readiness: 可进入实施。

## 复评边界与证据

本轮先重读 prior report，只复核原 F-01～F-04、处置表相应行、当前 Spec 对应修订、commit `990e377` 对 `exp/carrier-v2/` 的降格，以及这些修订直接触及的 slot／classification／streaming／last-mile 相邻合同；没有重做全量规格评审。

- disposition 四项采纳记录位于 `spec-review-disposition.md:16-19`，与当前 Spec 和 source commit 逐项对账。
- `git show 990e377 -- exp/carrier-v2` 确认该 commit 只改两个历史实验，diff 与当前 `gen_v2_vectors.py:1-7,38`、`check_i_algorithm.py:1-6,45-48` 一致。
- 运行 `uv --directory /home/xp/src/ghc-api-proxy-py run python exp/carrier-v2/gen_v2_vectors.py | tail -n 1` 得到 `HISTORICAL ONLY: superseded ordinal-only vectors round-trip as originally specified`；`check_i_algorithm.py` 尾行同样输出 `HISTORICAL VERDICT`。
- 对安装的 OpenAI SDK 3.3.1 introspection 确认四类 summary event 均存在，且索引字段名为 `summary_index`：`ResponseReasoningSummaryPartAddedEvent`、`ResponseReasoningSummaryPartDoneEvent`、`ResponseReasoningSummaryTextDeltaEvent`、`ResponseReasoningSummaryTextDoneEvent`。这只支持字段与事件 shape，不冒充真实 upstream 时序测量；Spec 在 `:228` 保留了相同边界。

## 原 findings 复核

| Finding | 结果 | 复核依据 |
|---|---|---|
| F-01 layout omission／删除变异不可区分 | CLOSED | `spec.md:109` 禁止空-record payload；`:125-130` 强制每个 Anthropic-slot payload 恰好带 object-form layout，bare 是唯一无-layout spelling；`:157` 将 payload 缺 layout 定为 profile 非法；`:208,211,264` 使删除后分别落入 malformed／profile mismatch，而不再与合法 payload 等价。原信息论反例中的 `[encrypted, layout]` 删除 layout 后现为 profile mismatch。 |
| F-02 缺 slot profile、record 组合与 precedence | CLOSED | `spec.md:151-161` 完整列出两个 outer slots 的三种合法 profile、visible 约束、禁止组合以及 signature／redacted 互斥；`:205-217` 固定 structural malformed → unsupported → direction → profile → presentation 的首命中 precedence，并明确 extensions cardinality 属 malformed。原混合 records 与红acted-visible 反例现均有唯一分类和 send-before refusal。 |
| F-03 flatten 正控不是合法 wire | CLOSED | `spec.md:262-264` 的正控三个 part 均含 `type:"summary_text"`，expected 是独立写出的完整列表，并明确分别经过 buffered、streaming 与 request decoder；旧实现只因 flatten 为单 part 而失败。 |
| F-04 ordinal-only 实验冒充 current oracle | CLOSED | `spec.md:249` 将旧脚本具名降格为 historical counterexample；commit `990e377` 的两个 docstring 与终端输出都明确“not current contract／not acceptance oracle／superseded”，不再存在 current-canonical／frozen 自述。当前 vectors 归实施 patch，且 expected 不得调用产品 codec。 |

## 修订相邻合同检查

- payload layout 与 bare：empty、single、empty-part、multi-part、extensions 与 present-empty opaque 现在均有可编码路径；layout 的 lengths／extensions cardinality、UTF-8 边界和 visible projection 分层到 typed schema、profile、presentation 三层，未发现新的 blocker／major。
- opaque 方向与 carrier 泄漏：`spec.md:157-161,183-187,205-217` 同时约束 record 方向、profile 和 resident last-mile guard；normal translator 解包、direct bypass 拒绝、native foreign state 不误判三条终态闭合，未重开 F-02 或 C1/C2。
- streaming 与 block-level delivery：`spec.md:223-230` 使用 `summary_index`，将 closing item、part.done、text.done、delta／part.added 固定成 authority precedence，并明确 `summary: []` 与字段 absent 的区别；仍在完整 block 才交付，不需要 turn-total ordinal，未与 carrier 字段形成新的 blocker／major。
- subscriber owner：`spec.md:236-241,295-304` 给出 resident subscriber 的挂载、注册、composition、blank-text／guard-destack／trailing-assistant 顺序和统一 reasoning owner；没有发现会令 carrier 绕过 guard 或产生第二语义 owner 的 blocker／major。

## 非阻断清理提示

1. `spec.md:60` 仍把 unknown `carrier_records` 描述为“需要原样继续携带”，而 `:113,217` 明确当前没有代理间透明传输边界，unknown record 必须在 send 前拒绝。后者已给出唯一 observable 终态，因此不阻断实施；建议把 `:60` 收窄为“保留到分类／诊断完成，不得发往 provider”，避免实现出一个永远不能合法输出的 forwarding 字段。
2. `spec.md:130,146-159` 没有用一个 MUST 句明确“无 opaque record 的 canonical `[]`／单非空 part 必须选择 bare”，所以 layout-only payload 在 profile 表面仍可表达同一 summary。解码与 layout 删除检测已无歧义，故这是 canonical producer spelling 的 minor 收口，不是原 F-01 的信息丢失 blocker；实施时宜固定 producer 选择 bare，consumer 可继续按 profile 接受 layout-only payload。

## 最终判定

原 F-01～F-04 全部按处置表关闭；当前修订没有引入同类 blocker／major。剩余两点均为不影响可逆性、分类终态或 provider 边界的 minor 文义／canonicalization 收口，因此本轮 verdict 为 `pass`，可进入实施。
