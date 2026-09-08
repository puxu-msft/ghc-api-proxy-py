# Graceful shutdown 与 systemd 子话题整理报告

## 范围与结论

- **范围**：仅核对并整理 `graceful-shutdown/`、`systemd-runtime/`、`systemd-rolling/`、`deployment-systemd/`，以及本报告；未修改 human-controlled 文档、源码、测试、配置或其他 repair 主题。
- **总体结论**：已完成文档状态对齐与安全整理。S3、S4 均已是当前 `main` 的祖先；`systemd-runtime` 唯一未闭合的运行时门为 S5。S7 已有独立的 `systemd-rolling` Spec／Plan，故已从 runtime 的当前计划移交出去。没有把单实例 `4141` 部署计划与动态 generation `4144` rolling 计划合并。
- **阻塞项**：0 个文档整理 blocker；S5 保持 `BLOCKED`，这是被记录的运行时环境前置缺失，不是本次文档工作受阻。

## 改动清单

1. **精确 pidfile 默认规则**：更新 `graceful-shutdown/restart-handover/README.md`。明确默认目录 `$XDG_DATA_HOME/ghc-api-proxy` 已正确；唯一不一致是 `config.example.yaml` 的中英文文件名示例以 `${GHC_API_PROXY_PORT}` 表示请求端口，而代码在 bind 后按最终生效端口命名。同步更新父 README 的遗留摘要，并移除两个已修项目的冗余遗留复述。
2. **刷新 runtime living status**：更新 `systemd-runtime/plan.md` 的顶部状态、看板、S5 阶段与 kick-off。当前状态基线为 `main@d0a4fc8b8fcc2306498f35601e73bb3a61f5983a`；明确 S3／S4 已落地，S5 是唯一未闭合运行时门，三个既有 minor 均为 non-blocking。
3. **移交 S7 而非混合计划**：从 `systemd-runtime/plan.md` 移除 S7 的现行计划内容，保留一条明确的 owner 链接；将旧的简略范围移到 `systemd-runtime/history/260908-s7-before-systemd-rolling-handoff.md`。现行 owner 为 `systemd-rolling/spec.md` 和 `systemd-rolling/plan.md`。
4. **建立单实例部署边界**：在 `deployment-systemd/README.md` 添加交叉链接与边界：它只解释 `contrib/systemd/` 单实例 `4141` 模板；S5 状态归 `systemd-runtime`；动态 generation `4144` 合同归 `systemd-rolling`。

## 合并／不合并决定

| 材料 | 决定 | 依据 |
|---|---|---|
| runtime 的旧 S7 摘要 | **移入 runtime `history/`** | 它只描述“未设计”的前置与验收意图，已被 rolling Spec／Plan 的完整合同取代；保留为可追溯历史，避免两个当前 owner。 |
| `systemd-runtime` 与 `systemd-rolling` 当前计划 | **不合并** | 前者是单实例 socket activation、S3／S4 provenance 与 S5 manager/cgroup smoke；后者是独立 `4144` 多 generation rolling。二者具有不同 listener、行为合同和验收门。 |
| `deployment-systemd` 与上述计划 | **不合并** | 它面向模板部署者，且明确是单实例 `Type=exec`；rolling 是独立 `Type=notify` 动态运行面。交叉链接比拼接当前计划更准确。 |
| `graceful-shutdown/restart-handover` 与 systemd 主题 | **不合并** | 此子话题仅覆盖 standalone pidfile／`--restart` 接替；systemd inherited-fd 路径跳过 pidfile。保留现有分界并更新父级摘要。 |

## 证据

- `git merge-base --is-ancestor c53849e2b5103c6426a67a8cbab687f2e45c1fa0 HEAD` 与对 `e9fb2771d6e040c761bb4074e3fcf2547caece28` 的同一检查均成功，证明 S3／S4 在 current `HEAD`。
- `src/app/config/paths.py:30-43` 返回 `user_data_path() / f"standalone-{port}.pid"`；`src/app/lifecycle/entry.py:101-102` 在 bind 后把 `address[1]` 传入。相对地，`docs/.human-controlled/config.example.yaml:226,229` 仍写 `standalone-${GHC_API_PROXY_PORT}.pid`。
- `systemd-runtime` 的历史 S5 执行记录与 live plan 均记录：独立 `systemd --user` 在 private control socket 创建前 `rc=1` 退出；调用进程在 root 所有、不可写 `/init.scope`，无安全可用的 delegated cgroup。因此真实 activation、effective cgroup、restart 与 manager stop 尚未执行。
- `systemd-rolling/spec.md` 明确说明其取代 runtime 的 S7 未决拓扑描述，且定义独立 `4144` 动态 generation 运行面；`systemd-rolling/plan.md` 是其实施计划。

## 待决项

1. **用户操作（范围外）**：在 `docs/.human-controlled/config.example.yaml:226,229` 把 `standalone-${GHC_API_PROXY_PORT}.pid` 改为表达最终生效端口的中英文措辞。目录默认值无需改动。
2. **S5 环境前置**：提供可销毁 VM/container、独立 login session/user manager 和 delegated cgroup v2，随后按 runtime Plan 继续真实 manager/cgroup smoke；不得以 static verify、direct-fd 或应用 HTTP 200 替代。
3. **三个 non-blocking minor**：config precedence 判别力、逐文件 atomicity 故障恢复回归、timeout facts 重复 owner 继续登记，但均不是 S5 的并列 gate。

## 验证面

- 复查 pidfile path 的代码、config 和两级 graceful-shutdown README。
- 复查 S3/S4 提交祖先关系、runtime S5 证据、runtime 看板和 S7 owner 链。
- 复查 deployment/runtime/rolling 的链接与 `4141`／`4144` 边界。
- 已运行 Markdown 改动的 whitespace 检查；未运行源码测试，因为本任务没有修改源码或测试。
