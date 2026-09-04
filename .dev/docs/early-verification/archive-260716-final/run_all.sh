#!/usr/bin/env bash
# 最终独立只读验收 - 执行所有探针脚本

set -euo pipefail

PROJECT_ROOT="/home/xp/src/ghc-api-proxy-py"
PROBES_DIR="$PROJECT_ROOT/verification/final_acceptance/probes"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "ghc-api-proxy-py 最终独立只读验收"
echo "=========================================="
echo ""

PASS=0
FAIL=0
SKIP=0

run_probe() {
    local name="$1"
    local script="$2"
    
    echo ">>> 执行: $name"
    if bash "$script" 2>&1; then
        echo "✓ $name PASS"
        ((PASS+=1))
    else
        echo "✗ $name FAIL"
        ((FAIL+=1))
    fi
    echo ""
}

run_python_probe() {
    local name="$1"
    local script="$2"
    
    echo ">>> 执行: $name"
    if python "$script" 2>&1; then
        echo "✓ $name PASS"
        ((PASS+=1))
    else
        local exit_code=$?
        if [ $exit_code -eq 2 ]; then
            echo "⊘ $name SKIP"
            ((SKIP+=1))
        else
            echo "✗ $name FAIL"
            ((FAIL+=1))
        fi
    fi
    echo ""
}

# 执行所有探针
run_probe "00. CLI Smoke Test" "$PROBES_DIR/00_cli_smoke.sh"
run_python_probe "01. Dynamic Port Startup" "$PROBES_DIR/01_dynamic_port_startup.py"
run_python_probe "02. Anthropic Protocol" "$PROBES_DIR/02_anthropic_protocol.py"
run_python_probe "03. OpenAI Three Prefixes" "$PROBES_DIR/03_openai_three_prefixes.py"
run_python_probe "04. Responses WebSocket" "$PROBES_DIR/04_responses_websocket.py"
run_python_probe "05. History & Metrics" "$PROBES_DIR/05_history_metrics.py"
run_python_probe "06. Approval System" "$PROBES_DIR/06_approval_system.py"
run_python_probe "07. Gemini & Azure" "$PROBES_DIR/07_gemini_azure.py"

echo "=========================================="
echo "验收结果汇总"
echo "=========================================="
echo "通过: $PASS"
echo "失败: $FAIL"
echo "跳过: $SKIP"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✅ 验收通过（无阻断或重大缺陷）"
    exit 0
else
    echo "❌ 验收失败（存在阻断或重大缺陷）"
    exit 1
fi
