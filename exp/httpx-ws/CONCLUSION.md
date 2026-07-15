# httpx-ws PoC 结论

## 环境

- Python 3.14.2
- httpx-ws 0.9.0
- httpx 0.28.1

## 判据

1. `httpx_ws.aconnect_ws()` 可复用现有 `httpx.AsyncClient`。
2. `ASGIWebSocketTransport` 可在无真实网络与无凭据环境驱动完整 WebSocket 升级。
3. 服务端分两次发送的 JSON 消息由客户端逐消息收到，没有整体缓冲。
4. `queue_size=1` 可建立显式 bounded queue/backpressure 边界。
5. async context manager 退出时关闭会话并等待内部 reader/keepalive 任务，不遗留裸 task。

## 结果

运行 `uv run python exp/httpx-ws/poc.py` 通过全部断言。正式实现采用 httpx-ws；上游连接复用项目 HTTPX client，连接生命周期由 async context manager 持有，客户端桥接逐消息发送，不创建无管理 fire-and-forget task。