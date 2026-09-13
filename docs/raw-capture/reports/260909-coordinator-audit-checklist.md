# Raw capture 当前实现独立审查清单

日期：2026-09-09
审查对象：当前共享工作树中的 raw-capture 实现与测试
依据：`.dev/docs/raw-capture/spec.md` ACTIVE v22

这份清单是协调者在接收独立报告后使用的核查范围，不是新的自动化门禁。每一项都必须回到当前源码、测试或可复现实验判断；不能因为报告写了 pass 就跳过。

## 必查契约

1. 选择规则：默认无 capture；SQLite 规则持久化；provider、实际 model-id、session-id 和可选 agent-id 精确匹配；agent 缺省与显式值的语义不混淆；规则 CRUD 的状态码、幂等性、删除不存在项和下一次查询生效行为成立。
2. 匹配时机：请求 body 已完整读取且路由已经解析 provider/model-id 后、第一次 upstream attempt 前匹配；普通 inference 与 count_tokens 入口都能触发；未命中、解析失败和无 session-id 不创建文件或保存 body。
3. 补录和 wire 证据：命中后补录完整入站 body；实际发出的每个 upstream request body、实际收到的每个 upstream response body、客户端实际收到的 response body 都进入同一 capture；重试、失败 attempt、非流式聚合和响应 cleanup failure 不被 synthetic response 替代或漏掉。
4. 文件格式：只创建 `.cborseq.zst`；每个独立 zstd frame 恰好包含一个 CBOR map；body 是原生 CBOR byte string；reader 能逐条读取完整 frame，截断尾部不会伪装成完整记录；旧 JSONL 不参与新格式读取或配额。
5. 分组和身份：session、agent 路径只含 hash；缺失 agent 有不可碰撞的独立 namespace；原始 session/agent 值不进入普通日志或路径名；请求头和认证信息不落盘。
6. 配额和异步写入：单文件配额按已落盘加已排队压缩 frame reservation 计算；队列满、关闭、编码/压缩失败、mkdir/open/write/close 失败和短写的 reservation 回滚与 capture incomplete 诊断成立；partial zstd frame 会 poison 共享 path；新 store 首次 append 会用生产 reader 验证已有文件。
7. 完成诊断：每个不完整 request 恰好一次安全 warning；首个丢失原因、首个丢失 event、writer_error 布尔值和 response body 完整性语义一致；合法 reason 仅来自规格 v22 §6 封闭枚举；不含 body、header、token、原始 identity 或异常回显 payload。
8. 生命周期与配置：store、rule database 的启动/关闭和异常路径可释放；`enabled: true` 不会重新成为全量开关；废弃 `max_total_bytes` 兼容行为与当前 schema/example 一致；管理 API 未配置 store 时错误明确。
9. 测试分辨力：关键正路径和失败机制有直接测试；至少抽查一个反向控制或变异证明测试确实会在缺陷实现下失败；测试不能只验证自家 serializer 生成的同一预期。
10. 交付判断：区分“主路径已实现”“全部规格已实现”“部署或真实 upstream 尚未覆盖”；若仍有缺口，给出最小可实施的设计修订和优先级，不把无关同伴改动算入本轮。

## 报告接收后的核查

- 核对报告的 `reviewed_at_rev`、范围、稳定 finding ID、证据与尾部交付声明。
- 对每一条 blocker/major/minor 主张重新运行或读取独立证据，判断它是否仍存在于当前工作树。
- 将采纳、拒绝或延期写入 raw-capture 处置账；不在聊天中丢弃报告发现。
- 不把报告中的测试计数或“已验证”原样当作当前事实，命令必须可重新运行。
