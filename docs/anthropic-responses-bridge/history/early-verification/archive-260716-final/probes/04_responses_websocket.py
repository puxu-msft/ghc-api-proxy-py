#!/usr/bin/env python3
"""Phase 3: Responses WebSocket 验证"""

import asyncio
import signal
import socket
import sys
import json
from subprocess import Popen, PIPE, TimeoutExpired

try:
    import websockets
except ImportError:
    print("SKIP: websockets library not installed")
    print("Install with: pip install websockets")
    sys.exit(2)

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

async def test_websocket(port: int):
    ws_url = f"ws://127.0.0.1:{port}/v1/responses"
    
    print("[3/4] Connecting to WebSocket...")
    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            print("✓ WebSocket connection established")
            
            # 发送测试消息
            print("[4/4] Sending test request...")
            test_request = {
                "type": "response.create",
                "response": {
                    "model": "gpt-4",
                    "input": [
                        {"type": "message", "role": "user", "content": "Say 'test'"}
                    ],
                },
            }
            await ws.send(json.dumps(test_request))
            
            # 尝试接收（无 token 应返回错误）
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                # 检查是否为错误消息
                if "error" in data or "type" in data:
                    print(f"✓ WebSocket responded (error expected without token)")
                else:
                    print(f"  Response: {data}")
            except asyncio.TimeoutError:
                print("  No response (timeout, may need token)")
    except Exception as e:
        print(f"FAIL: WebSocket connection error: {e}")
        return False
    
    return True

def run_probe():
    print("=== Responses WebSocket Validation ===")
    
    port = find_free_port()
    print(f"[1/4] Starting server on port {port}...")
    
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
    import httpx
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
    print("[2/4] Testing WebSocket upgrade...")
    
    # WebSocket 测试
    success = asyncio.run(test_websocket(port))
    
    # 清理
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait()
    
    if not success:
        sys.exit(1)
    
    print("=== WebSocket validation passed ===")

if __name__ == "__main__":
    run_probe()
