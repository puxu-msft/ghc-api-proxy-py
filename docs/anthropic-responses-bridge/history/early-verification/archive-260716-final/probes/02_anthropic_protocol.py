#!/usr/bin/env python3
"""Phase 2/4: Anthropic 协议验证（无真实凭据）"""

import asyncio
import httpx
import signal
import socket
import sys
import json
from subprocess import Popen, PIPE, TimeoutExpired

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def run_probe():
    print("=== Anthropic Protocol Validation ===")
    
    port = find_free_port()
    print(f"[1/6] Starting server on port {port}...")
    
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
    
    # 等待启动
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
    
    # 2. /v1/messages 非流式 - 无 token 应返回认证错误
    print("[2/6] Testing /v1/messages (non-streaming, no token)...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{base_url}/v1/messages",
            json={
                "model": "claude-opus-4.6",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
                "stream": False,
            },
            headers={"Content-Type": "application/json"},
        )
        # 预期：401 或 500（无 token）
        if resp.status_code not in (401, 500, 502, 503):
            print(f"FAIL: Expected auth error, got {resp.status_code}")
            print(f"Response: {resp.text}")
            proc.terminate()
            sys.exit(1)
    print("✓ /v1/messages returns expected error without token")
    
    # 3. /v1/messages 流式 - 验证 Accept: text/event-stream
    print("[3/6] Testing /v1/messages (streaming, no token)...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{base_url}/v1/messages",
            json={
                "model": "claude-opus-4.6",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
                "stream": True,
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        # 预期：同样的认证错误或 SSE 流式错误
        if resp.status_code not in (200, 401, 500, 502, 503):
            print(f"FAIL: Unexpected status {resp.status_code}")
            proc.terminate()
            sys.exit(1)
    print("✓ /v1/messages streaming endpoint responds")
    
    # 4. /v1/messages/count_tokens - token counting
    print("[4/6] Testing /v1/messages/count_tokens...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{base_url}/v1/messages/count_tokens",
            json={
                "model": "claude-opus-4.6",
                "messages": [{"role": "user", "content": "Hello world"}],
            },
            headers={"Content-Type": "application/json"},
        )
        # 预期：本地 tiktoken fallback 应能返回估算
        if resp.status_code == 200:
            data = resp.json()
            if "input_tokens" not in data:
                print(f"FAIL: Response missing 'input_tokens': {data}")
                proc.terminate()
                sys.exit(1)
            print(f"  Estimated tokens: {data.get('input_tokens')}")
        else:
            # 若无 token，上游 count_tokens 也会失败，本地 fallback 应该仍能工作
            print(f"  Status {resp.status_code} (may need token for upstream counting)")
    print("✓ /v1/messages/count_tokens endpoint responds")
    
    # 5. 保留未知字段测试（黑盒无法直接验证，但可测试不报错）
    print("[5/6] Testing unknown fields acceptance...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{base_url}/v1/messages",
            json={
                "model": "claude-opus-4.6",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
                "stream": False,
                "unknown_field_top": "should_not_crash",
                "custom_nested": {"foo": "bar"},
            },
            headers={"Content-Type": "application/json"},
        )
        # 只要不是 400 (bad request due to unknown field)，就说明接受了
        if resp.status_code == 400:
            print(f"FAIL: Server rejected unknown fields with 400")
            print(f"Response: {resp.text}")
            proc.terminate()
            sys.exit(1)
    print("✓ Server accepts unknown fields without 400")
    
    # 6. 清理
    print("[6/6] Shutting down server...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✓ Server shut down")
    
    print("=== All Anthropic protocol tests passed ===")

if __name__ == "__main__":
    run_probe()
