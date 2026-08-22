# 测试用例的组织

用户希望采用一组混合的测试目录组织方案。

主体是典型的单元测试、组件/模块测试、多组件/模块集成测试、端到端测试。

```
tests/
    unit/<类似 src 的包结构>/   # 轻量的函数级、多函数级内存测试，不追求全覆盖，核心关切即可
    component/{ghc_client,history}/     # 某个内聚的模块、组件的整体或多部分联调测试
    int/                        # 跨模块集成测试，可能启动单独 proxy process 和 test client，也可能不
    e2e/claude/                 # 真实 claude cli binary + CLAUDE_CONFIG_DIR + proxy process + mock upstream
```

被测目标如果复杂，主分类目录下可以再拆分子目录。

conftest 按层次、被测目标的需求可按需拆分、每组配置一份。

与特定外部系统相关的测试，积累一定数量后，可以改为单独放置：

```
tests/{tui,systemd}/            # TUI 相关测试、systemd 集成相关测试
```

不设置 `tests/upstream/`，使用真实上游的请求与响应都应该是独立运行，请求和响应都被记录、研究，再复刻或模仿改写成测试素材的。此类测试脚本可以放在 `.dev/exp/upstream-payloads/`，处理后的素材可以放在测试目录内：

```
tests/
    cassettes/
    int/cassettes/
    e2e/claude/cassettes/
```
