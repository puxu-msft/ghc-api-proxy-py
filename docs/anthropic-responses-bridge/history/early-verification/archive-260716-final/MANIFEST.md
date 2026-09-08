# 验收资产清单

## 目录结构

```
verification/final_acceptance/
├── README.md           # 验收概述与矩阵
├── REPORT.md           # 最终验收报告（含实证）
├── run_all.sh          # 执行所有探针的总脚本
└── probes/             # 黑盒探针脚本集
    ├── 00_cli_smoke.sh
    ├── 01_dynamic_port_startup.py
    ├── 02_anthropic_protocol.py
    ├── 03_openai_three_prefixes.py
    ├── 04_responses_websocket.py
    ├── 05_history_metrics.py
    ├── 06_approval_system.py
    └── 07_gemini_azure.py
```

## 探针设计原则

1. **独立性**: 不依赖项目内测试，使用临时脚本
2. **黑盒**: 只验证用户可观察行为（HTTP 端点、CLI 输出、退出码）
3. **动态端口**: 使用 `socket.bind(('', 0))` 避免冲突
4. **无凭据**: 所有探针在无真实 token 的空壳模式下运行
5. **只读**: 不修改仓库文件，不杀用户进程
6. **实证**: 每个验收项包含明确的失败证据（命令+输出+退出码）

## 快速执行

```bash
# 执行所有探针
bash verification/final_acceptance/run_all.sh

# 执行单个探针
python verification/final_acceptance/probes/02_anthropic_protocol.py
```

## 验收结果

详见 [REPORT.md](REPORT.md)

**结论**: ✅ 验收通过（0 blocker / 0 major）
