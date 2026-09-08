# 最终独立只读验收

**验收日期**: 2026-07-16
**验收范围**: ghc-api-proxy-py HEAD (Phase 0-8 完整实现)
**验收依据**: IMPLEMENTATION_PLAN Phase 0-8 用户可观察 oracle

## 验收约束

- ✅ 只读验证（不改仓库）
- ✅ 动态端口分配
- ✅ 无真实凭据
- ✅ 不杀用户进程
- ✅ 黑盒探针（不依赖现有测试）

## 验收矩阵

从 Spec 推导的 11 个验收域：

1. **CLI 与配置** - Phase 0 基础设施
2. **动态端口启动与健康检查** - Phase 0 服务骨架
3. **优雅关闭** - Phase 5 韧性
4. **Anthropic 协议** - Phase 2/4
5. **OpenAI 三前缀** - Phase 3
6. **Responses WebSocket** - Phase 3
7. **History/Metrics** - Phase 6
8. **Approval** - Phase 7
9. **Gemini/Azure** - Phase 8
10. **配置脱敏** - 安全要求
11. **无 token 空壳** - 无凭据模式

## 执行计划

所有验证使用临时探针脚本，不依赖项目内测试。
