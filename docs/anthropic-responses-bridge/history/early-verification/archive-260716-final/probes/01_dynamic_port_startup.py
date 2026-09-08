#!/usr/bin/env python3
"""Phase 0: 动态端口启动、健康检查、优雅关闭"""

import asyncio
import httpx
import signal
import socket
import sys
from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired

def find_free_port() -> int:
    """找到可用的动态端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def run_probe():
    print("=== Dynamic Port Startup & Health Check ===")
    
    # 1. 分配动态端口
    port = find_free_port()
    print(f"[1/5] Allocated dynamic port: {port}")
    
    # 2. 启动服务（无 token 模式）
    print(f"[2/5] Starting server on port {port}...")
    # 使用 --no-rate-limit --no-history 避免依赖外部资源
    proc = Popen(
        [
            "uv", "run", "python", "-m", "app", "start",
            "--port", str(port),
            "--host", "127.0.0.1",
            "--no-rate-limit",
            "--no-history",
        ],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
    )
    
    # 3. 等待启动
    print("[3/5] Waiting for startup (max 10s)...")
    base_url = f"http://127.0.0.1:{port}"
    startup_ok = False
    
    for _ in range(20):  # 20 * 0.5s = 10s
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(f"{base_url}/health/liveness")
                if resp.status_code == 200:
                    startup_ok = True
                    break
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        asyncio.run(asyncio.sleep(0.5))
    
    if not startup_ok:
        print("FAIL: Server did not start within 10s")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except TimeoutExpired:
            proc.kill()
        sys.exit(1)
    
    print(f"✓ Server started on port {port}")
    
    # 4. 健康检查端点验证
    print("[4/5] Testing health endpoints...")
    with httpx.Client(timeout=5.0) as client:
        # /health/liveness - 必须返回 200
        resp = client.get(f"{base_url}/health/liveness")
        if resp.status_code != 200 or resp.json().get("status") != "ok":
            print(f"FAIL: /health/liveness returned {resp.status_code} or invalid JSON")
            proc.terminate()
            sys.exit(1)
        print("  ✓ /health/liveness OK")
        
        # /health 和 /health/readiness - 无 token 时可能返回 503（not ready）
        resp = client.get(f"{base_url}/health")
        if resp.status_code == 200:
            print("  ✓ /health OK (ready)")
        elif resp.status_code == 503:
            print("  ✓ /health returns 503 (not ready, expected without token)")
        else:
            print(f"FAIL: /health returned unexpected status {resp.status_code}")
            proc.terminate()
            sys.exit(1)
        
        resp = client.get(f"{base_url}/health/readiness")
        if resp.status_code == 200:
            print("  ✓ /health/readiness OK (ready)")
        elif resp.status_code == 503:
            print("  ✓ /health/readiness returns 503 (not ready, expected without token)")
        else:
            print(f"FAIL: /health/readiness returned unexpected status {resp.status_code}")
            proc.terminate()
            sys.exit(1)
    
    print("✓ All health endpoints respond correctly")
    
    # 5. 优雅关闭 (SIGTERM)
    print("[5/5] Testing graceful shutdown (SIGTERM)...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
        exit_code = proc.returncode
        if exit_code != 0:
            print(f"WARN: Process exited with code {exit_code} (expected 0)")
        else:
            print(f"✓ Graceful shutdown OK (exit code {exit_code})")
    except TimeoutExpired:
        print("FAIL: Server did not shut down within 15s")
        proc.kill()
        proc.wait()
        sys.exit(1)
    
    print("=== All startup/health/shutdown tests passed ===")

if __name__ == "__main__":
    run_probe()
