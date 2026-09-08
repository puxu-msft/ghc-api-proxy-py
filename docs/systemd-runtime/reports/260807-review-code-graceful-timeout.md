# Graceful timeout 独立代码评审

- **评审范围**：`ghc-api-proxy-py-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖 config／YAML／env／CLI 优先级、Uvicorn timeout 接线、systemd deadline 单源与测试、真实短 timeout probe、SIGTERM／lifespan，以及旧 `ShutdownManager` 未接线边界；rolling 不在范围。
- **总体 verdict**：**可进入下一阶段；可以 squash。**
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。

## 双视角覆盖证据

### 机械核对视角

- 清点 base→HEAD 全部 10 个变更路径，检查完整 diff 与 `git diff --check`。
- 对账 `AppSettings.shutdown.graceful_timeout`、loader `SECTION_PATHS`、env nested mapping、CLI override，以及 host／port 与 inherited-fd 两个 `uvicorn.run()` 分支。
- 从 unit 反解 `--graceful-timeout 300` 与 `TimeoutStopSec=330s`，核对 Python 默认 `300`、margin `30`、计算值 `330` 和严格不等式，并检查 equal-deadline 负控。
- 全局扫描 `ShutdownManager`／lifespan／SIGTERM：生产 `server.py`／`cli.py` 未消费旧 manager，文档如实声明四阶段、重复信号升级与 rolling 未接线。
- 核对锁定 Uvicorn `0.40.0`：`Server.shutdown()` 先停止 accept、等待／取消在途 task，再调用 lifespan shutdown。

### 第一人称执行视角

- 独立逐层 probe 得到 `default 300 → YAML 11 → env 12 → CLI 13`，并确认 `0`／负值被拒绝。systemd 显式 CLI `300` 有意遮蔽同名 env，部署文档已明确提示。
- 两种 CLI 启动路径均把 effective timeout 传给 Uvicorn。
- 真实短 timeout smoke 阻塞生产 `/v1/messages` 请求，`--graceful-timeout 1` 进程收到 SIGTERM 后命中 Uvicorn timeout，随后完成 lifespan shutdown 并有界退出；正常 SIGTERM smoke 继续证明 History／tokenization cleanup 落盘。
- timeout helper 的正确 `300＋30=330` 样本通过；非正 margin、CLI 值漂移和 stop deadline 漂移均会被比较结构拒绝。

## 验证结果

- 定向 pytest：`30 passed`。该数量仅记录命令输出，未作第二原理计数。
- 全仓 pytest：`437 passed`；独立 `--collect-only` 同口径计得 `437` 个 node IDs。
- Ruff 通过；Pyright 为 `0 errors, 0 warnings, 0 informations`。
- 临时仅替换未安装 `/opt/.../python` 路径后的 `systemd-analyze verify` 返回 `0`；不外推为 unit 已安装或 manager 已加载。

## 事实性发现

[minor] `tests/unit/test_config_loader.py:92-109` — shutdown 专属优先级测试只断言最终 CLI 值 `13`，不能独立证明 YAML `11` 与 env `12` 被消费 — 即使 shutdown 的 YAML／env source 同时失效，CLI nested override 仍会产出 `13`，该用例仍绿。独立 runtime probe 已确认当前产品行为正确，因此这是测试判别力缺口，不是运行时错误 — 拆成 default-only、YAML-only、YAML＋env、YAML＋env＋CLI 四层断言，或参数化验证 `300／11／12／13`。

未发现阻断性问题。除上述 minor 外，未发现配置合并、Uvicorn 接线、systemd deadline、SIGTERM／lifespan、旧 `ShutdownManager` 边界或范围陈述缺陷。

## 主观建议

未提出额外主观建议。rolling 已明确排除，且文档保留为后续独立切片。

## 结构与方案反思

- **结构怪味**：扫描 CLI、config、graceful constants、server、旧 shutdown helper、systemd unit、测试与文档。唯一发现是上述复合优先级测试假绿面。unit 文本与 Python 常量的值重复已有机械对账。
- **内部替代方案**：复用 Uvicorn 原生 graceful timeout 与 FastAPI lifespan，优于新增 signal owner 或接入未冻结的四阶段 manager。
- **判据判别力**：短 timeout probe 与 systemd 对账可区分目标正误；配置专属用例对中间层不足，已列 minor。
- **成熟方案**：使用 Uvicorn 与 systemd 原生能力，未发现不必要的自研 timeout scheduler。

## 最终结论

`865a5b71210e2436b36786b5de67146939d1e0f5` 达到 **0 blocker／0 major**，**可以 squash**。唯一 minor 不改变当前运行时合同，也不阻塞 squash。本 verdict 仅覆盖仓库内 graceful-timeout 切片，不表示真实 manager、安装态、cutover 或 rolling 已完成。
