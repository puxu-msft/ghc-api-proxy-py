# `.dev/tools/`

会话间可复用的小工具。不参与主分支构建，也不随代码发布。

## `git-hunks.py`

把一个文件的 `git diff` 拆成 hunk 列出，或按序号重新拼成补丁输出到 stdout。

```bash
python3 .dev/tools/git-hunks.py <path>            # 列出 hunk：序号 + 头 + 前两行新增内容
python3 .dev/tools/git-hunks.py <path> 0,4        # 只输出第 0 和第 4 个 hunk 的补丁
python3 .dev/tools/git-hunks.py <path> 0,4 | git apply --cached   # 只把这两个 hunk 送进索引
```

**它解决什么**：主工作树同时有多个会话在改，同一个文件里常常混着两边的未提交改动。整文件 `git add` 会把同伴的在途工作卷进我的提交；`git commit -- <path>` 取工作树内容，同样会卷。逐 hunk 认领后只暂存自己的那些，是唯一能干净切分的做法。2026-08-20 用它在 5 个混合文件上切出过一次提交，事后核对同伴的改动原样保留。

**它不解决什么**：同一**行**被双方共同编辑时（例如两人各往同一句 import 里加了一个名字），hunk 粒度切不开——那种情况要手工构造「HEAD + 只有我的增量」的整份内容，再走 `git hash-object` + `git update-index`（见项目记忆 `git-commit-takes-the-whole-index`）。

**前提**：在仓库根目录运行；读的是工作树相对 HEAD 的 `git diff`，不读索引。
