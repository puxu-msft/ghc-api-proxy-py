# Current docs 相对 Markdown 文件链接审计

- **评审范围**：current worktree 中 `docs/agents/anthropic-responses-bridge/*.md` 的 6 份 Markdown 文档，以及 `docs/agents/documentation-restructure/plan.md`；仅审计这些 source 内指向相对 `.md` 路径的 Markdown 链接。外部 URL、绝对路径、图片、纯文本路径及同页 `#fragment` 不在本轮对象内。
- **总体 verdict**：**可进入最终 docs 提交**。审计集合中的相对 Markdown 文件链接未发现断链或错误 fragment。
- **blocker 数**：0。
- **major 数**：0。
- **事实性发现**：**未发现问题。** 按本轮约定，只报告断链或错误 fragment 的 blocker／major；未产生其他级别发现。
- **审计基线**：每次 shell 调用均在同一次调用内验证物理 repository root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。审计对象是该 gate 下的 **current worktree bytes**，不是仅限 HEAD blobs。

## 双视角覆盖证据

### 机械核对

1. 使用项目 `.venv` 中锁定的 `markdown-it-py 4.2.0`、`MarkdownIt("commonmark")` 解析完整 source 文档，并从 token 流的 `link_open` 提取链接；只保留无 scheme、无 netloc、非 `/` 起始且 URL-decoded path 以 `.md` 结尾的 destination。该方法避开 fenced code、inline code 和普通文本中的伪链接。
2. 将 URL-decoded path 相对于 source 文件目录解析并规范化，要求规范化结果仍位于 repository root 内，且目标是当前 worktree 中存在的 regular file。
3. 独立使用逐行词法扫描重新提取当前语料中的 inline Markdown 文件链接，再直接查询文件系统。两种原理得到相同结果：55 条链接、29 个唯一目标、0 条带 fragment、0 个非 regular-file 目标。
4. 对 target、heading fragment、GitHub-style line fragment 三类 gate 分别做了内存正反控制；三类均为已知正确样本 PASS、注入对应错误样本 RED。控制不写入仓库文件。

### 第一人称执行模拟

1. 从每个 source 所在目录出发，按读者点击链接时的相对路径语义逐条解析 55 个 destination，并打开其规范化后的 current-worktree 文件目标；55 条均可到达 regular file。
2. 模拟带 fragment 的点击分支：先打开目标文件，再将 fragment 分派为 `L<start>`／`L<start>-L<end>` 行号形式或 heading slug 形式；当前 55 条文件链接均没有 fragment，因此这两个分支在 current corpus 中没有实际输入，不能把正反控制冒充 current 文档具有 fragment 覆盖。
3. 模拟迁移后的常见失败：不存在的 `.md` 目标会由 regular-file gate 判红；越界、倒序或 `L0` 行号会由 line gate 判红；不存在的标题 slug 会由 heading-ID gate 判红。

## 输入快照

以下 SHA-256 均对 `main@ed77c9d191df81c451c25161420515cca52ce6a4` gate 下的 current worktree bytes 计算：

| Source | SHA-256 | 提取到的相对 `.md` 链接 |
|---|---|---:|
| `docs/agents/anthropic-responses-bridge/README.md` | `b7281a1fe078e2fcbf1d1f0402f00c0bb64f3386188d70cd813db127ef40b804` | 11 |
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` | 0 |
| `docs/agents/anthropic-responses-bridge/architecture.md` | `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327` | 0 |
| `docs/agents/anthropic-responses-bridge/implementation.md` | `5b20c8abf04a74854a8fefc777652d759744250eceb42c423a7de80af56fa38e` | 44 |
| `docs/agents/anthropic-responses-bridge/research.md` | `54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e` | 0 |
| `docs/agents/anthropic-responses-bridge/spec.md` | `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` | 0 |
| `docs/agents/documentation-restructure/plan.md` | `b3235905bb824d6d6acc272dae1eaf61724a5c71b49818ef107f1f6d9ef8ccab` | 0 |
| **合计** | — | **55** |

计数口径：7 个 source、55 次链接引用、29 个规范化后的唯一目标；55 条均为 target-only，heading fragment 为 0，GitHub-style line fragment 为 0。目标存在性按 current worktree 检查，不要求目标已被 Git 跟踪。

## 三类判据

### 1. 文件 target

- 对 destination 做 URL decode，再以 source 的 parent directory 为基准解析。
- 规范化结果必须留在 repository root 内，且 `Path.is_file()` 为真；目录、缺失路径和逃逸 repository root 均判为断链。
- current 结果：55／55 PASS，覆盖 29／29 个唯一 regular-file 目标。

### 2. Heading fragment

- 非空且不匹配 line-fragment grammar 的 fragment 归为 heading fragment。
- 标题由 CommonMark parser 的 heading token 识别；可见 inline text 转为小写，移除 GitHub slugger 风格标点，将空白替换为 `-`，并按文档出现顺序为重复 slug 追加 `-1`、`-2` 等后缀；URL-decoded fragment 必须精确匹配计算出的 heading ID。
- current 结果：0 条。该分支没有参与 current verdict 的实际 PASS 计数，只通过代表性正反控制验证 gate 会区分匹配与不匹配。

### 3. GitHub-style line fragment

- 仅接受 `L<start>` 或 `L<start>-L<end>`，其中行号为从 1 开始的十进制正整数。
- 目标文件按 UTF-8 文本的 physical lines 计数，并要求 `1 <= start <= end <= line_count`；`L0`、倒序区间及越界终点均判为错误 fragment。
- current 结果：0 条。该分支没有参与 current verdict 的实际 PASS 计数，只通过边界正反控制验证。

## Renderer、slug 方法与 false-positive 边界

- **Renderer／parser**：本轮没有调用 GitHub 服务或 GitHub HTML renderer；链接识别使用项目依赖 `markdown-it-py 4.2.0` 的 CommonMark token stream。它适合排除 code span／fence 中形似链接的文本，但不证明 GitHub 对所有扩展语法的渲染行为完全相同。
- **Heading slug**：本轮使用显式的 GitHub-slugger-style 核心变换与重复后缀规则，而非已安装的 `github-slugger` 包；本机未发现该包。对 Unicode 标点、emoji、HTML entity、内嵌 HTML、复杂 inline markup 或 GitHub 将来调整 slug 规则的边界输入，计算值可能与 GitHub renderer 不同，可能产生 false positive 或 false negative。current 文件链接不带 heading fragment，因此该边界不影响本轮 55 条 target-only 链接的 verdict；若最终改动新增 heading fragment，应使用 GitHub 实渲染或官方 `github-slugger` 实现重新审计。
- **Line fragment**：`Lx`／`Lx-Ly` 是 GitHub source-view 的行锚点风格，不是 rendered Markdown heading anchor。直接打开 rendered Markdown 时，GitHub 是否保留或解释该行锚点属于平台行为边界；本轮只机械验证 grammar 与物理行范围。current 文件链接不带 line fragment，因此该边界不影响本轮 verdict。
- **相对路径与编码**：检查按 POSIX current-worktree 路径、UTF-8 和 URL decoding 执行；未通过 GitHub 仓库 URL 路由验证大小写折叠、Unicode normalization 或 percent-encoding 的平台差异。当前 55 条 destination 均无 fragment，且不存在 percent-encoded path。
- **语料边界**：独立词法扫描只作为交叉检查，不作为 acceptance oracle；它不覆盖 reference-style links、多行 destination 或嵌套 bracket 的所有 Markdown 语法。主结论来自 parser token stream。当前两种方法计数一致，降低了 current corpus 中抽取漏项的风险，但不证明任意 Markdown 语料零误报。

## 最终机械结论

在上述输入哈希和 `main@ed77c9d191df81c451c25161420515cca52ce6a4` gate 下：

- relative Markdown file links：55；
- unique normalized targets：29；
- target-only：55，全部 PASS；
- heading fragments：0；
- GitHub-style line fragments：0；
- broken targets：0；
- bad fragments：0；
- blocker：0；
- major：0。

若任一 source SHA-256 改变，本报告不应继续作为最终 docs 提交的 current-link 证据，应在新 bytes 上重新执行审计。
