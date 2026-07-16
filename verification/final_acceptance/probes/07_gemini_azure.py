#!/usr/bin/env python3
"""Phase 8: Gemini 与 Azure 协议验证"""

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
    print("=== Gemini & Azure Protocol Validation ===")
    
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
    
    # 2. Gemini /v1beta 路径
    print("[2/5] Testing Gemini /v1beta paths...")
    with httpx.Client(timeout=10.0) as client:
        # generateContent
        resp = client.post(
            f"{base_url}/v1beta/models/gemini-1.5-pro:generateContent",
            json={
                "contents": [{"parts": [{"text": "test"}]}],
            },
            headers={"Content-Type": "application/json"},
        )
        # 不应 404
        if resp.status_code == 404:
            print(f"FAIL: Gemini generateContent not found (404)")
            proc.terminate()
            sys.exit(1)
        
        # streamGenerateContent
        resp = client.post(
            f"{base_url}/v1beta/models/gemini-1.5-pro:streamGenerateContent",
            json={
                "contents": [{"parts": [{"text": "test"}]}],
            },
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 404:
            print(f"FAIL: Gemini streamGenerateContent not found (404)")
            proc.terminate()
            sys.exit(1)
    
    print("✓ Gemini /v1beta paths registered")
    
    # 3. Azure deployment 路径
    print("[3/5] Testing Azure deployment paths...")
    with httpx.Client(timeout=10.0) as client:
        # Classic: /openai/deployments/{deployment}/chat/completions
        resp = client.post(
            f"{base_url}/openai/deployments/test-deployment/chat/completions?api-version=2024-02-01",
            json={
                "messages": [{"role": "user", "content": "test"}],
            },
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 404:
            print(f"FAIL: Azure classic deployment path not found (404)")
            proc.terminate()
            sys.exit(1)
    
    print("✓ Azure deployment paths registered")
    
    # 4. 配置脱敏测试（黑盒：检查 /api/config 是否脱敏）
    print("[4/5] Testing config sanitization...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{base_url}/api/config")
        if resp.status_code == 200:
            config = resp.json()
            # 检查是否包含敏感字段（如 github_token）
            config_str = str(config).lower()
            if "ghu_" in config_str or "ghp_" in config_str:
                print(f"FAIL: Config contains unsanitized GitHub token")
                proc.terminate()
                sys.exit(1)
            print("✓ Config appears sanitized")
        else:
            print(f"  /api/config not available (status {resp.status_code})")
    
    # 5. 清理
    print("[5/5] Shutting down...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✓ Server shut down")
    
    print("=== Gemini & Azure validation passed ===")

if __name__ == "__main__":
    run_probe()
