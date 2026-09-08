# Reasoning carrier Spec 评审处置

状态：closed。两条评审线最终均为 PASS，可进入实施。

对象：`.dev/docs/reasoning-carrier/spec.md`。

评审报告：

- `reports/260904-spec-review-general-opus-1.md`
- `reports/260904-spec-review-gpt-opus-1.md`

## 第一轮处置

| Finding | 处置 | 级别 | 依据与修订 |
|---|---|---|---|
| wire F-01：layout omission 与删除变异不可区分 | 采纳 | C | payload envelope 内强制携带 `summary_text_layout`，包括 `[]` 和单 part；bare v2 是唯一无 layout spelling。删除 layout 后不再与合法 payload 等价。 |
| wire F-02／implementation M4：缺少 slot profile、record 组合和分类优先级 | 采纳 | C | 增加 Anthropic signature slot 与 Responses encrypted slot 的完整 profile；signature／redacted records 互斥；增加 profile mismatch；冻结 structural malformed → unsupported record → direction mismatch → profile mismatch → presentation mismatch precedence。 |
| wire F-03／implementation M5：summary 正控缺 `type` | 采纳 | C | 正控改为三个完整 `summary_text` objects，并分别要求经过 buffered、streaming、request decoder。 |
| wire F-04：ordinal-only v2 实验仍自称 canonical | 采纳 | C | 本轮同步把 `exp/carrier-v2/` 两个脚本改为 superseded historical counterexample；当前 v2 独立 vectors 在实施时按本 Spec 新建，旧脚本不再冒充 oracle。 |
| implementation M1：streaming 错用 `content_index` 且漏 summary events | 采纳 | C | 改为 `summary_index`；冻结 closing item summary、part.done、text.done、delta／part.added 的 authority precedence与 extensions 合并。明确仓内 cassette 尚无该事件样本，SDK wire types是本轮结构依据。 |
| implementation M2：same-format direct bypass 可让 carrier 到达 provider | 采纳 | C | 新增所有 target 都经过的 `attempt.prepare` resident guard。正常跨格式必须在 translator内解包；last-mile仍见任何项目 carrier均在 upstream send前以稳定错误拒绝，避免 direct路径缺少 Conversion sink时静默drop。 |
| implementation M3：漏 streaming IR与subscriber owner | 采纳 | C | 实施范围补 `delivery/assembling.py`、`delivery/blocks.py`、subscriber模块／注册、composition配置；规定 blank-text先运行，carrier guard＋Anthropic destack后运行，trailing-assistant最后读取成形列表。 |
| implementation M6：旧 helper处置未裁定 | 采纳 | C | 统一core为唯一reasoning语义owner；旧protocol facade若暂留，只能薄委托，不保留独立v2分支。旧helper测试迁移到core，只保留facade delegation smoke test。 |

没有不采纳项，没有需要用户追加裁决的分歧。

## 第二轮处置

| Finding | 处置 | 级别 | 依据与修订 |
|---|---|---|---|
| R1：summary events漏`part.added.text`且未处置`part.done.status=incomplete` | 采纳 | C | `part.added.text`成为最低级baseline，delta在其后追加；done覆盖。无closing summary兜底时，incomplete part进入截断／失败生命周期，不形成lossless carrier。 |
| R2：resident guard未覆盖`copilot-api` synthetic v1 | 采纳 | C | Guard调用共享classifier并覆盖项目全部versions／forms及兼容upstream v1 prefix／bare／legacy，不靠单一字符串prefix；last-mile capture增加两套namespace正控。 |
| R3：profile visible约束与presentation mismatch重叠 | 采纳 | C | Profile只判outer slot、known record family、组合和record cardinality；所有record↔visible跨字段关系移入presentation。增加profile与presentation独立vectors和跨路径一致性验收。 |

没有不采纳项。

## 最终复评

- `reports/260904-spec-rereview-general-opus-3.md`：PASS，blocker 0，major 0；两条wire minor已闭合，profile／presentation拆分未重开旧finding。
- `reports/260904-spec-rereview-gpt-opus-3.md`：PASS，R1～R3全部闭合，blocker 0，major 0。其唯一minor是SDK 3.3.1的`part.done.status`没有`"completed"` spelling；Spec已在进入实施前修正为“字段缺失＝完成、`incomplete`＝不完整”，并明确closing summary不覆盖item-level incomplete终态。

全部采纳项已进入living Spec，没有暂定驳回或未处置finding。
