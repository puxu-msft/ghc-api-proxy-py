#!/usr/bin/env python3
"""Phase 3: OpenAI 三前缀路由验证"""

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
    print("=== OpenAI Three Prefixes Validation ===")
    
    port = find_free_port()
    print(f"[1/5] Starting server on port {port}...")
    
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
    
    print("✓ Server started")
    
    # 2. 三个前缀：无前缀, /v1, /openai/v1  (根据 multi-protocol.md 和 server.py)
    test_cases = [
        ("", "root (no prefix)"),
        ("/v1", "/v1 prefix"),
        ("/openai/v1", "/openai/v1 prefix"),
    ]
    
    for i, (prefix, desc) in enumerate(test_cases, start=2):
        print(f"[{i}/5] Testing {desc}: {prefix}")
        
        # /chat/completions
        with httpx.Client(timeout=10.0) as client:
            path = f"{prefix}/chat/completions" if prefix else "/chat/completions"
            resp = client.post(
                f"{base_url}{path}",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "test"}],
                },
                headers={"Content-Type": "application/json"},
            )
            # 无 token 应返回认证错误，但不应 404
            if resp.status_code == 404:
                print(f"FAIL: {path} not found (404)")
                proc.terminate()
                sys.exit(1)
        
        # /models
        with httpx.Client(timeout=10.0) as client:
            path = f"{prefix}/models" if prefix else "/models"
            resp = client.get(f"{base_url}{path}")
            # 同上
            if resp.status_code == 404:
                print(f"FAIL: {path} not found (404)")
                proc.terminate()
                sys.exit(1)
        
        print(f"✓ {desc} endpoints registered")
    
    # 5. 清理
    print("[5/5] Shutting down...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✓ Server shut down")
    
    print("=== All three prefixes validated ===")

if __name__ == "__main__":
    run_probe()
