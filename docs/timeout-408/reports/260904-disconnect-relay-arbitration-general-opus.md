# 技术仲裁报告

## 裁决

**选择 B。** 跨阶段 `receive` relay 不是当前 Uvicorn 修复的 blocker/major；它属于尚未支持的 ASGI server 或自定义 receive wrapper 扩展，应记录重开条件。

**置信度：高，约 95%，强到足以据此合并当前修复。** 裁决依据是当前产品合同、实际接线和 Uvicorn 0.52.4 的确定控制流，不是实现成本，也不依赖假设未来 actor。

## 具体依据

1. 当前受支持的生产入口是项目 CLI 的直接运行和 systemd-managed 两种部署，合同见 `docs/.human-controlled/lifecycle.md`。两条生产接线最终都构造 Uvicorn server，见 `src/app/cli.py` 和 `src/app/lifecycle/entry.py`。
2. 锁定依赖是 Uvicorn 0.52.4，仅依赖 `h11`，没有 `httptools`。生产代码未指定 `http=`，该版本的 `auto` 在没有 `httptools` 时选择 `H11Protocol`，因此当前锁定组合的 downstream 是 HTTP/1.x，不支持 downstream H2。
3. Uvicorn H11 的 disconnect 不是唯一、取走即失的队列元素，而是 `RequestResponseCycle.disconnected` 上的持续状态。`connection_lost()` 设置该 flag 并唤醒 `message_event`；后续每次 `receive()` 只要该 flag 为真都会再次返回 `http.disconnect`。
4. 被争议的取消窗口在当前 H11 实现中不能吞掉唯一消息。若 listener 尚阻塞于 `message_event.wait()`，取消后 `disconnected` flag 仍保留；若已恢复，则清 event、检查 flag到返回 `http.disconnect` 之间没有 await，应用 listener 从取得 message 到 `stop("disconnect")` 之间也没有 await。
5. StreamingResponse 在 Uvicorn 发布的 ASGI spec 2.3 scope 下成为下一任 receive owner；Starlette 1.6.0 对 `<2.4` 并行运行 `stream_response()` 与 `listen_for_disconnect()`。
6. 当前应用接线中没有会消费并延迟转交 receive message 的 middleware。项目 middleware 均原样传递 receive，FastAPI Request 也保存原始 callable。
7. Reviewer 的通用反例在更宽 ASGI 组合中可以构造，但当前没有这样的 actor。已安装 Starlette `BaseHTTPMiddleware` 也会锁存 disconnect，而本项目当前未使用它。

## 重开条件

出现以下任一事实时，应重新把 relay 作为当前缺陷评估：

- 产品正式支持 Uvicorn 以外且 disconnect 只交付一次的 ASGI server。
- 引入会调用底层 `receive()`、随后经过 cancellation checkpoint 才返回消息，并且没有锁存或 replay 的 middleware/wrapper。
- `create_pipeline_app()` 被确立为可在任意 ASGI host 上部署的受支持公共合同。
- Uvicorn 版本、`http=` 配置或 protocol implementation 改变，使 disconnect 不再由持续 flag 重复报告。
- 当前 Uvicorn H11 上出现可复现证据：pre-response listener 被 operation-win 取消后，后续 Starlette listener 无法读到已经发生的 disconnect。

## H2→H1 测试 scope 核验

测试改为 `http_version="1.1"`，与锁定 Uvicorn H11 接线及现场 10 条均为 H1 的记录一致；fake receive 在首次请求体后持续返回 `http.disconnect`，符合 H11 持久 flag 语义。原先伪造 downstream H2 无法支撑生产路径声称，改成 H1 是正确的。ASGI spec 同步为 Uvicorn 实际发布的 2.3。

## 最终处置

驳回“当前任务必须实现跨阶段 relay”的 major；将其降为带上述重开条件的未来兼容项。当前修复可按 Uvicorn 0.52.4＋H11＋无 receive-consuming middleware 的明确产品范围收口。此次仅做指定分歧的只读仲裁，未修改文件、Git、运行进程或网络状态。