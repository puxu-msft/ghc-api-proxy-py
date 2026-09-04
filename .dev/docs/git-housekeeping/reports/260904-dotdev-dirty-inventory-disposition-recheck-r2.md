# `.dev` 脏文件处置窄复评第二轮

日期：2026-09-04。
范围：只复核首轮 `M-1`、`M-2`，以及当前 `docs/direct-passthrough/spec.md` 的相邻 §5.3、§6.3、§9.2 与 v22 修订记录；未重做 A／B／C／D 全量盘点。
结论：**pass**。blocker=0，major=0；两条原 major 均关闭，未发现修正引入相邻 blocker／major。

## 原发现闭合核验

### M-1：closed

`spec.md:277-287` 仍先按 finalization outcome 二分原 ending 与 continuation ending；`:350-352` 现把原样承诺明确限定到 `EMIT_UPSTREAM_ENDING`，并把 `EMIT_CONTINUATION` 写成具名、互斥的 synthetic-terminal 例外。前者不得合成，后者隐藏原 terminal 后只合成一个 proxy-owned terminal；原先“同一 terminal 必须原样且必须合成”的矛盾已消失。v22 修订记录 `:762` 同步登记了这项修正。

### M-2：closed

`spec.md:696-705` 现明确把 non-stream Responses synthetic `function_call` 追加到 `output` 数组末尾，以数组索引表达位置，并逐字规定 item 本身不增加 event-level `output_index` 字段。Streaming §5.3 `:287` 继续把 `output_index` 留在 `added`／arguments／`done` 事件序列，两个层级不再混同。v22 修订记录 `:762` 同步登记了这项修正。

## 相邻复核

没有发现上述分流与 §5.3 的唯一 terminal、§9.2 的 whole-body 投影或 v22 摘要产生新的 blocker／major。一个非阻断的 minor 是：§6.3 使用的两个 action 名只在 plan §11.1 显式枚举，Spec §5.3 以语义分支而非同名 enum 表述；行为边界仍然唯一、可解码，不影响本轮 pass。另一个纯记录级 minor 是 v22 表格的“条款”列未列 §6.3，但同一行正文已明确登记 §6.3 修正；两者均不重开原 major。

## 交付声明

verdict: pass
closed_major_count: 2
remaining_blocker_count: 0
remaining_major_count: 0
minor_count: 2
