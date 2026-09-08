# Reasoning carrier Spec 极窄最终确认

## 快照与结论

- snapshot_time: `2026-09-04T06:15:29+08:00`
- reviewed_object: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`
- object_snapshot: mtime `2026-09-04T06:13:40.742380392+08:00`，size `31779` bytes
- source_rev: `39274d7bc3601f2236ffdfc52ea6f34f885ba405`
- prior_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-spec-rereview-general-opus-2.md`
- scope: 只复核第二轮两条 nonblocking notes，以及 profile／presentation 拆分是否重开 F-01／F-02；未做全量重审。
- verdict: `pass`
- findings: blocker=0，major=0
- implementation_readiness: 可进入实施。

## 限定核验

### 1. Unknown `carrier_records` 已收窄

`spec.md:60` 现明确 unknown、grammar-valid records“只保留到分类与诊断完成”，并明确当前不存在允许其发往 provider 或代理间透明转交的边界；这与 `spec.md:113` 的 `unsupported_record`＋send-before refusal，以及 `spec.md:230` 的所有失败分类在 send 前拒绝一致。第二轮 note 1 已关闭，没有 forwarding owner、嵌套 carrier 或升级死路被重新引入。

### 2. Canonical bare producer 与兼容 consumer 已分开

`spec.md:149` 以 MUST 规则固定：Responses source 无 `encrypted_content` 且 summary 为 canonical `[]` 或单个非空、无 extensions part 时，v2 producer 必须选择 bare，不得输出 layout-only payload；`spec.md:150` 单独允许 consumer 接受 profile 合法的 layout-only payload，并明确该兼容不授权 producer，也不形成第二个 canonical vector。第二轮 note 2 已关闭；canonical producer spelling 唯一，同时兼容输入不损失 layout 恢复能力。

### 3. Profile／presentation 拆分未重开 F-01／F-02

`spec.md:157-163` 将 profile 严格限定为 outer slot、known record family、组合与 cardinality；`spec.md:165-173` 将 layout↔thinking、canonical summary 和 redacted-visible 关系独立定义为 presentation，并规定 presentation 失败不得被 profile 吞掉。`spec.md:218-230` 的 precedence 对应为 malformed → unsupported → direction → profile → presentation，首个命中停止；`spec.md:271-275` 又用独立 profile／presentation vectors 和三路径共享 classifier 验收该边界。

F-01 仍保持关闭：Anthropic payload 必须带 layout，删 layout 落 profile mismatch；bare producer 选择现已唯一。F-02 仍保持关闭：record 组合、slot 方向、visible 跨字段关系和冲突 precedence 各有唯一分类与 send-before refusal。此次拆分只是把原来混在 profile 的 visible 关系移到专门的 presentation contract，没有恢复任何二义性。

## 最终判定

三项定点修订彼此一致，未发现 blocker／major。Verdict 为 `pass`，可进入实施。
