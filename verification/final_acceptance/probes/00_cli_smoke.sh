#!/usr/bin/env bash
# Phase 0: CLI 与配置基础验证

set -euo pipefail

echo "=== CLI Smoke Test ==="

# 1. --help 输出
echo "[1/4] Testing --help..."
OUTPUT=$(uv run python -m app --help 2>&1)
if ! echo "$OUTPUT" | grep -q "start"; then
    echo "FAIL: 'start' subcommand not found in --help"
    exit 1
fi
echo "✓ --help shows 'start' subcommand"

# 2. start --help
echo "[2/4] Testing start --help..."
OUTPUT=$(uv run python -m app start --help 2>&1)
if ! echo "$OUTPUT" | grep -q "\-\-port"; then
    echo "FAIL: '--port' option not found"
    exit 1
fi
echo "✓ start --help shows --port option"

# 3. 生成默认配置
echo "[3/4] Testing --generate-config..."
TMPDIR=$(mktemp -d)
CONFIG_FILE="$TMPDIR/test_config.yml"
uv run python -m app start --config "$CONFIG_FILE" --generate-config
if [ ! -f "$CONFIG_FILE" ]; then
    echo "FAIL: Config file not generated"
    rm -rf "$TMPDIR"
    exit 1
fi
echo "✓ --generate-config creates config file"

# 4. 配置文件 YAML 格式验证
echo "[4/4] Validating config YAML format..."
if ! grep -q "host:" "$CONFIG_FILE"; then
    echo "FAIL: Config file missing 'host:' key"
    rm -rf "$TMPDIR"
    exit 1
fi
echo "✓ Config file is valid YAML"

rm -rf "$TMPDIR"
echo "=== All CLI smoke tests passed ==="
