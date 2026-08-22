# pyright 主线现在有 21 个 error，全在 stream_cap 切片

**日期**：2026-08-22。**留条子的人**：retry-and-continuation 主题会话。**不是我的切片，我没动它。**

## 事实

`main` 的 `HEAD` 上跑 `uv run pyright src tests`（CLAUDE.md 里的验证命令之一）：

```
21 errors, 0 warnings, 0 informations
```

全部集中在两个文件，来自已提交的 `2b20be7`（`fix: keep the per-connection stream cap working under httpcore2`）与 `8703cad`（`feat: implement the proxy priority the authored config states, on the tier that was being discarded`）。**两个文件都不脏**（`git status --porcelain` 空），所以这是提交态而非某人手上的半成品——按「查残留要 grep 提交态」的教训，这一条是核过的。

| 文件 | 条数 |
|---|---|
| `src/app/upstream/stream_cap.py` | 3 |
| `tests/unit/upstream/test_stream_cap.py` | 18 |

## 性质：两类，都来自戳 httpx/httpcore 的私有内部

- **`reportPrivateUsage`（10 条）**：`client._transport`、`._mounts`、`._pool._requests`、`._pool.create_connection`。
- **`reportUnknownMemberType` / `reportUnknownVariableType`（11 条）**：上面那些私有属性在 httpx 的 stub 里没有类型，于是 `created = ...create_connection` 整条链路都是 unknown。

**这不是「代码写错了」**——per-connection stream cap 本来就只能从 httpx 的私有连接池上做，戳私有是这个功能的固有代价。所以修法多半是**局部 `# pyright: ignore[...]` 加一句为什么**，而不是改实现。

## 为什么留这张条子而不是顺手改

1. **不是我的切片**，而且那位同伴 2026-08-22 一直在这片工作，我改会撞车。
2. **他们未必会撞见**：本项目的规矩是「小改动跑定向测试，只有 squash 候选才跑一次全量」，而 pytest 是全绿的（1671 passed）——**只有全量 pyright 才看得见这 21 条**。所以它可能在主线上待很久没人发现。
3. 我不打算把它登记成任何主题的未闭合项：**它有明确的主人**，登记进我的主题只会制造第二个真相来源。

## 我核过什么、没核什么

- **核过**：错误条数与归属文件（`uv run pyright src tests`）、两个文件的提交归属（`git log -- <file>`）、两个文件不脏、以及**我自己两个提交碰的文件单独跑是 0 error**（`src/app/pipeline/delivery/stream.py`、`tests/unit/pipeline/delivery/test_stream_delivery.py`）。
- **没核**：这 21 条是不是从 httpx2 迁移那一刻开始的，还是更早就有。也没核 `.dev/exp/httpx2-migration/` 里那两个未提交的脚本与它有没有关系。

**证据等级：一手实测，确凿。有保质期**——同伴随时可能自己修掉；复述之前重跑一遍。
