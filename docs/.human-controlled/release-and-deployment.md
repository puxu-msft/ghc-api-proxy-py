# 发布与部署

如果需要固定依赖版本：

```bash
# 导出运行期依赖，来源就是 uv.lock
uv export --frozen --format requirements.txt --no-emit-project --no-hashes --no-dev -o constraints.txt

# 安装时带上它
uvx --from git+https://github.com/puxu-msft/ghc-api-proxy-py.git --refresh \
    --constraints https://raw.githubusercontent.com/<owner>/<repo>/<ref>/constraints.txt \
    ghc-api-proxy start --port 4141
```

因为 uv tool/uvx 装的是构建出来的分发包，它只带 pyproject.toml 里的依赖声明；uv.lock 描述的是工作区环境，既不进分发包，也不被 tool 安装路径查阅。没有任何开关能让它去读那个文件。
