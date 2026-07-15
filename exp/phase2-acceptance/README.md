# Phase 2 验收资产

本目录包含 Phase 2 独立只读验收的完整资产。

## 文件清单

### 1. [SUMMARY.md](SUMMARY.md) - 执行总结 ⭐

**中文总结报告**，快速了解验收结论、方法、覆盖范围、缺陷汇总。

- ✅ 通过（0 blocker / 0 major）
- 154 个测试全部通过
- 8 大类验收项 100% 符合 Spec

### 2. [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md) - 验收矩阵

从冻结 Spec 推导的用户可观察验收判据清单：

- **A1**: Messages 模型深层 extra/null 保真（5 项）
- **A2**: Tool blocks 处理（5 项）
- **A3**: Raw stream 未消费（2 项）
- **A4**: SSE 零缓冲直通（4 项）
- **A5**: Token counting（4 项）
- **A6**: Pipeline states（3 项）
- **A7**: HTTP endpoints（5 项）
- **A8**: RuntimeState bootstrap（4 项）

每项都标注了 Spec 来源和验证方法。

### 3. [verify_acceptance.py](verify_acceptance.py) - 黑盒验证脚本

独立可运行的 Python 脚本，不依赖真实凭据：

```bash
# 运行验收测试
uv run exp/phase2-acceptance/verify_acceptance.py

# 输出: 8/8 通过，生成 ACCEPTANCE_REPORT.json
```

**验证策略**:
- 使用 mock/stub 模拟上游
- 单元测试式调用核心函数
- 构造边界输入证伪行为
- 收集实际执行证据

### 4. [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md) - 详细报告

每个验收项的完整实证，包括：

- Spec 条款引用
- 实证代码片段（含文件:行号）
- 测试路径（`tests/unit/test_*.py::test_*`）
- 关键断言和结果

**示例**:
```
A2.2 孤儿 tool_use（无 tool_result）被过滤 ✅

证据:
  verify_acceptance.py:238-253
  assert result.orphaned_tool_uses_removed == 1

测试:
  tests/unit/test_anthropic_sanitize.py::test_orphan_tool_blocks_and_empty_text_are_removed
```

### 5. [ACCEPTANCE_REPORT.json](ACCEPTANCE_REPORT.json) - JSON 日志

机器可读的完整执行记录，包含所有证据和失败信息。

## 验收方法

按 verifier 角色纪律：

1. **先读 Spec 推导 oracle** - 不看实现，独立列出验收判据
2. **再看实现** - 读取代码和现有测试
3. **设计并运行验证** - 黑盒脚本 + 单元测试调用
4. **报告实证** - 每个缺陷必须同时给出「Spec 条款 + 失败证据（文件:行 + 结果）」

## Spec 来源

- [IMPLEMENTATION_PLAN.md Phase 2](../../docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md#phase-2--核心管道最小闭环-walking-skeleton)
- [streaming.md](../../docs/2604-rewrite/streaming.md)
- [sanitize-pipeline.md](../../docs/2604-rewrite/sanitize-pipeline.md)
- [anthropic-compat.md](../../docs/2604-rewrite/anthropic-compat.md)

## 测试覆盖

**全量测试**: `uv run pytest tests -q`

```
154 passed in 2.32s
```

**关键模块**:
- ✅ `app/models/anthropic.py` - extra="allow" 保真
- ✅ `app/anthropic/sanitize/` - tool blocks + empty text
- ✅ `app/streaming/sse.py` - 零缓冲 + cleanup
- ✅ `app/anthropic/token_counting.py` - upstream/fallback
- ✅ `app/runtime.py` - RuntimeState DI
- ✅ `app/routes/anthropic.py` - HTTP 端点

## 验收结论

**✅ Phase 2 完全符合冻结 Spec，0 blocker / 0 major，可进入 Phase 3。**

---

**生成时间**: 2026-07-15  
**验收者**: Verifier Agent
