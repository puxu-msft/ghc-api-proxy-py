# Reasoning carrier Spec 第三轮限定复评

复评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`、`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec-review-disposition.md`。

基准报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-spec-rereview-gpt-opus-2.md`。本轮仅复核 R1～R3、第二轮处置、对应 event／classifier／profile 合同，以及同批两条 wire minor；未扩展为全量新评审。

## Verdict

**PASS，可进入实施。** R1～R3 均已闭合，未发现修订引入的 blocker／major。仅余 1 项不阻断实施的 wire spelling minor，按当前明确语义即可直接实现。

## R1～R3 复核

### R1 — PASS：summary event authority 已覆盖 baseline 与 incomplete
- `spec.md:237-243` 以 `summary_index` 分 state，固定 closing summary → `part.done` → `text.done` → added baseline＋delta precedence；`part.added.text`现在是最低级文本基线，delta只在其后追加，done与closing均为替换而非重复拼接。
- `spec.md:240` 明确 incomplete `part.done`不形成完整part；无closing summary时进入既有截断／失败 lifecycle，不得从低层 accumulator制造lossless carrier；有更高closing summary时仅由该内容authority接管。
- `spec.md:280,294` 用完整合法summary、非空added baseline＋delta、incomplete done的失败正控以及closing override正控约束实现，足以区分第二轮指出的两种错误。

### R2 — PASS：resident guard 已覆盖两套 synthetic namespaces 的全部已支持形态
- `spec.md:197-200` 要求guard调用共享classifier，并逐项纳入项目v1／v2／unknown／malformed与兼容`copilot-api` v1 payload prefix／bare prefix／legacy bare sentinel；不再以单一项目prefix替代分类。
- `spec.md:288` 把任一项目carrier或兼容v1 payload／bare／legacy sentinel出现在provider wire定义为失败，并要求项目v2与兼容v1两个namespace各有last-mile正控。
- 这与现有classifier常量和分支一一对应（`src/app/pipeline/translation_driver/reasoning_carrier.py:10-16,77-100`）；same-format路径不再有第二轮R2所述漏网形态。

### R3 — PASS：profile 与 presentation 已成为互斥分类层
- `spec.md:153-163` 的profile只判断outer slot、known record family、组合与record cardinality；visible关系已全部移入独立的presentation contracts（`spec.md:165-173`）。
- precedence在`spec.md:218-228`按 structural malformed → unsupported → direction → profile结构 → presentation跨字段执行，第二轮反例`lengths:[1]`配`thinking:"ab"`现在只命中presentation。
- `spec.md:271-275` 分开列出profile和presentation独立literal vectors，并要求classification vectors经translation driver、兼容facade和streaming projection的同一classifier入口；expected不由产品encoder生成，路径一致性不再靠codec自证。

## 同批 wire minor 复核

- **Unknown records：PASS。** `spec.md:60,113` 已把未知record的寿命收窄到分类／诊断并在send前拒绝；没有透明代理边界，不再让`carrier_records`暗示可继续发往provider。
- **Canonical bare producer：PASS。** `spec.md:125-130,146-151` 规定无`encrypted_content`且summary为canonical `[]`或单个非空无extensions part时producer必须bare；layout-only payload仅为consumer兼容输入，不能成为第二个canonical producer spelling。

## 非阻断 minor

- `spec.md:239` 写`part.done`的`status`“缺失或为completed”时完整；OpenAI SDK 3.3.1 的该事件字段实际是`Optional[Literal["incomplete"]]`，正常完成以字段缺失表达（`.venv/lib/python3.14/site-packages/openai/types/responses/response_reasoning_summary_part_done_event.py:42-47`），没有`"completed"` spelling。实施时应按“缺失＝完成、`incomplete`＝不完整”编码，后续可删掉文档中的“或为completed”。
- 该措辞不使合法输入的行为未决，也不改变R1验收。相邻的`response.output_item.done.item.status == "incomplete"`仍由现有item-level cut-short lifecycle负责；closing summary的优先级只裁summary内容来源，不应覆盖item自身的incomplete终态。

## 实施放行结论

第二轮处置表三项与当前Spec一致，R1～R3无剩余 blocker／major。以上 minor 可随实施同步澄清，但不是前置条件；**本规格可进入独立 worktree 实施。**

边界结清判断：本轮仅产生这份限定复评报告，没有源码、Spec、测试、临时资产或Git状态需要清理／归档，不启动额外closeout。
