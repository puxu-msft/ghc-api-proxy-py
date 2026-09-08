# 最小真实 Copilot canary 独立复跑

## 判定

**PASS**。验证对象为 `main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1`，执行时间为 `2026-08-08T08:14:58Z`。本轮没有切换生产流量，也没有修改旧 Bun 服务。

- readiness 状态：`200`。
- `/api/models` 状态：`200`；模型总数：`32`；明确声明 Responses endpoint 的模型数：`10`。
- 选用模型 ID：`gpt-5.3-codex`。选择条件仅为 `/api/models` 的 `supported_endpoints` 明确包含 `responses` 或 `/responses`。
- nonstream 状态：`200`；content block types：`text`；usage keys：`cache_creation_input_tokens`, `cache_read_input_tokens`, `input_tokens`, `output_tokens`。
- stream 状态：`200`；event types（按序）：`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`；content block types：`thinking`；delta types：`signature_delta`；usage keys：`cache_creation_input_tokens`, `cache_read_input_tokens`, `input_tokens`, `output_tokens`。
- stream 序列判定：`PASS`，legal Anthropic message sequence。

## 隔离与清理

- token 来源文件仅做权限与非空检查，确认 mode 为 `0600`；值未打印、未写入本报告。token 被复制到临时 `XDG_DATA_HOME/ghc-api-proxy/github_token`，副本 mode 为 `0600`。
- 使用显式临时 config：`auth.account_type: individual`、`anthropic.route_override: responses`；child 环境中移除了三个 token 环境变量，认证只能来自临时 XDG token 副本。
- `4142` 启动前空闲：`True`。父进程先绑定 `127.0.0.1:4142` 并把监听 FD 传给精确 Python child，以避免检查后的抢占窗口。
- Python child PID：`2696688`；通过该 `Popen` 精确 handle 发送 SIGTERM：`True`；`wait()` 完成并 reap：`True`；return code：`-15`。
- 清理后 `4142` 已释放：`True`；临时 HOME／XDG root 最终已删除：`True`。
- 第一次临时根检查为 `False`：验证驱动先退出 `TemporaryDirectory`，随后才向仍在 shutdown flush 阶段的 child 发送 SIGTERM，child 因而在已清空的根下重建了状态目录。确认 child PID 已不存在、`4142` 已释放、残留根是当前用户所有且为本轮唯一近期 `ghc-real-canary-*` 目录后，删除该根并复验不存在。此项是验证驱动的清理时序缺陷，不是 Python 请求路径失败。
- canary 对旧 Bun 4141 发送信号数：`0`。驱动的唯一 signal 调用目标是上述 Python child handle。
- 旧 Bun 前置 incarnation：PID=`2603551`；starttime=`5938704`；cwd digest=`0bba4db87d1cf2e8`；cgroup digest=`778ccdf3058cfbe3`；listener count=`1`。
- 旧 Bun 后置 incarnation：PID=`2603551`；starttime=`5938704`；cwd digest=`0bba4db87d1cf2e8`；cgroup digest=`778ccdf3058cfbe3`；listener count=`1`。
- 旧 Bun incarnation 前后相同：`True`；祖先链观察到外部 `--restart` wrapper：`True`。

## 数据最小化

本报告及终端输出均未记录 GitHub token、Copilot token、生成正文、reasoning、tool arguments 或任何 response body。服务 stdout／stderr 直接指向 `/dev/null`；HTTP body 仅在验证进程内解析为允许的状态、模型 ID／数量、block／event types 与 usage key names，未另行落盘。

## 未验证边界

- 未扩展 retry、quota、rate-limit、backpressure 或故障注入矩阵。
- 未执行 tool-use、tool arguments、reasoning／thinking、vision、image 或多轮会话矩阵。
- 未验证生产切换、旧 Bun 请求承载等价性、systemd manager／cgroup 激活或零停机迁移。
- 未验证 kernel-level partial-write、客户端中途断连或长流 idle timeout。
- 这是单次最小真实 canary，不代表完整产品验收或部署就绪。
