# `multi-provider-routing` 嵌套树冲突的手工合并处置

## 范围

re-root 前，嵌套 `.dev/.dev/docs/multi-provider-routing/` 中有三份未提交文档；活跃根 `docs/multi-provider-routing/` 同路径版本是先前全量合并保留的版本。本处置逐段对比两侧，不用时间戳替代内容判断。

## 结论

活跃根版本保留为 current 文档；嵌套树的两份不同原文已原样归档，第三份已与活跃树一致。

| 文件 | 手工合并结论 | 依据 |
|---|---|---|
| `deferred.md` | 保留活跃根版本 | 两侧均保留 D-3 的四项待确认边界。活跃根将 D-3 放在 D-4 后，并明确 secondary provider 的 `provider/model` 目录名已由 `52d57a09` 落地；嵌套版本没有当前实现/待确认的分层优势。 |
| `spec.md` | 保留活跃根版本 | 嵌套版本关于 secondary provider 限定名发现的规则已被活跃根完整承接；活跃根还补入 `3b223e8e` 的 `provider` 筛选、serviceability 区分和测试依据。嵌套版本较宽的“用户直接裁决”修订记录不回写：当前 `review-disposition.md` 只保留了当时的转述，未保留一手逐字来源，本次不能扩写或传播该归属。 |
| `review-disposition.md` | 无需合并 | 两侧 SHA-256 相同，嵌套工作树的未提交状态相对其旧 `dotdev` HEAD 已被活跃树内容吸收。 |

## 保全

为使 re-root 不丢失嵌套树当时的未提交措辞，两份不同原件保存于 [`../history/`](../history/)：

- `260908-nested-dotdev-deferred-before-reroot.md`：`bdabbd7a05e67e0359ceda73b3e66b01df8eace3a1a040a591c9efef02ba4b15`
- `260908-nested-dotdev-spec-before-reroot.md`：`9a9d2ba23f6b7e27ea6c4425e40552caf56e9b81e63bb524319a8968cf3f0adf`

两个 digest 均已与嵌套原件逐字匹配。快照是冲突前证据，不是 current authority。

## 未做

未改动嵌套树原文件，未删除 `.dev/.dev`，未执行 `git add`、commit 或 push。嵌套工作树将在完成 checkpoint 后随 re-root 的旧布局退役；其提交历史仍由 archive ref 保留。
