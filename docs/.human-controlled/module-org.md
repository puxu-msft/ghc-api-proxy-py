# 项目的模块层次结构

得到用户追认的模块如下：（不代表子模块也被追认）

```
app
    cli                 # 命令行入口
        debug               # debug
        start               # start
    config
    core
    history
    lifecycle
        shutdown
    model_provider      # 上游模型提供方，提供抽象层。未来可能有其他提供方，提供不同的模型端点。
        ghc_client          # [GHC API 提供方](./ghc-api.md)
    observability
    pipeline
    server
        routes
```

尚未确认、有疑虑的模块如下：

```
app
    anthropic
    context
    openai
```

历史操作：

- 要求把 `app.auth` 移入 `app.ghc_client.auth`，因为它是 GHC API 的客户端认证逻辑；
- 要求把 `app.ghc_client` 整体移入 `app.model_provider.ghc_client`，因为它是一种模型提供方（目前唯一一种，未来会追加）。
