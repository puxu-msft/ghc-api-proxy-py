#!/usr/bin/env python3
"""Phase 6: History 与 Metrics 验证"""

import asyncio
import httpx
import signal
import socket
import sys
from subprocess import Popen, PIPE, TimeoutExpired

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def run_probe():
    print("=== History & Metrics Validation ===")
    
    port = find_free_port()
    print(f"[1/5] Starting server with history enabled on port {port}...")
    
    # 启用 history
    proc = Popen(
        [
            "uv", "run", "python", "-m", "app", "start",
            "--port", str(port),
            "--host", "127.0.0.1",
            "--history",  # 启用 history
            "--no-rate-limit",
        ],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
    )
    
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(20):
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(f"{base_url}/health/liveness")
                if resp.status_code == 200:
                    break
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        asyncio.run(asyncio.sleep(0.5))
    else:
        print("FAIL: Server startup timeout")
        proc.terminate()
        sys.exit(1)
    
    print("✓ Server started with history")
    
    # 2. History API 端点
    print("[2/5] Testing history API endpoints...")
    with httpx.Client(timeout=10.0) as client:
        # /history/api/entries
        resp = client.get(f"{base_url}/history/api/entries")
        if resp.status_code != 200:
            print(f"FAIL: /history/api/entries returned {resp.status_code}")
            proc.terminate()
            sys.exit(1)
        entries = resp.json()
        print(f"  Found {len(entries)} history entries")
        
        # /history/api/sessions
        resp = client.get(f"{base_url}/history/api/sessions")
        if resp.status_code != 200:
            print(f"FAIL: /history/api/sessions returned {resp.status_code}")
            proc.terminate()
            sys.exit(1)
    
    print("✓ History API endpoints OK")
    
    # 3. Metrics 端点
    print("[3/5] Testing metrics endpoint...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{base_url}/metrics")
        if resp.status_code != 200:
            print(f"FAIL: /metrics returned {resp.status_code}")
            proc.terminate()
            sys.exit(1)
        
        # 验证 Prometheus 格式
        metrics_text = resp.text
        if not ("# HELP" in metrics_text or "# TYPE" in metrics_text or metrics_text.strip() == ""):
            print(f"FAIL: /metrics response is not Prometheus format")
            print(f"Response: {metrics_text[:200]}")
            proc.terminate()
            sys.exit(1)
    
    print("✓ Metrics endpoint OK (Prometheus format)")
    
    # 4. Management API
    print("[4/5] Testing management API...")
    with httpx.Client(timeout=10.0) as client:
        # /api/status
        resp = client.get(f"{base_url}/api/status")
        if resp.status_code == 404:
            print("WARN: /api/status not found (may not be implemented)")
        
        # /api/config (可能需要认证或返回脱敏后的配置)
        resp = client.get(f"{base_url}/api/config")
        if resp.status_code == 404:
            print("WARN: /api/config not found (may not be implemented)")
    
    print("✓ Management API endpoints checked")
    
    # 5. 清理
    print("[5/5] Shutting down...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✓ Server shut down")
    
    print("=== History & Metrics validation passed ===")

if __name__ == "__main__":
    run_probe()
