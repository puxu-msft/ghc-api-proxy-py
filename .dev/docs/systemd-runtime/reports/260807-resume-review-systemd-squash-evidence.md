# Systemd 逐片 squash 回放证据一致性复核

- **评审范围**：只读对账 `docs/tmp/260807-resume-review-systemd-rebuild.md`、`docs/tmp/260807-resume-verify-systemd-rebuild.md` 与 `docs/tmp/260807-resume-audit-systemd-squash-r2.md`。身份固定为主树 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 integration `d3fabfadfba57af6c2d63e543e3198444777df54`。
- **总体 verdict**：**可进入下一阶段。三份文档在本轮限定命题上相互一致，0 blocker／0 major。**
- **blocker 数**：0。
- **major 数**：0。
- **测试边界**：本轮未重跑测试；只复用既有 review 与 verification 文档中的已冻结结论。
- **写入边界**：唯一写入为本文件；未修改被复核文档、代码、Git index、HEAD、branch 或 refs，未执行部署或 cutover。

## 双视角覆盖证据

### 机械核对视角

- 对账 review 的 `0 blocker／0 major` verdict 与逐片 squash 边界：`260807-resume-review-systemd-rebuild.md:4-6,35-37`。
- 对账 verification 的 exact-tip `PASS` 与未部署／未 cutover 边界：`260807-resume-verify-systemd-rebuild.md:5,53-59,68-70`。
- 对账 audit 的 non-merge 逐片重建、reviewed-source archive targets 与 `NO CUTOVER`：`260807-resume-audit-systemd-squash-r2.md:3-8,88-100,102-115,137-139`。
- 三份文档没有把 review `0 major` 或 verification `PASS` 外推为已部署、已安装、已切流或可省略未来 main-side gates。

### 第一人称执行视角

- 作为回放执行者，我会把既有 review `0 major` 与 exact-tip verification `PASS` 作为回放证据输入，但仍按 S3、S4 顺序逐片执行未来 main-side identity／preimage／tests gates；任一片失败即停。
- 我不会 merge、fast-forward、cherry-pick或把两片合成一个 commit；S3 与 S4 分别在 actual main 上重建为新的 non-merge 单一语义 commit，并保留片间停止点。
- 我只会把 reviewed source commit 作为 archive provenance target：S3 指向 `865a5b71210e2436b36786b5de67146939d1e0f5`，S4 指向 `e16c2a700f23f66535e7347ab7357518eb8e56bd`；不会把 candidate、old code-only 或未来 main commit 当成替代 archive target。
- 我不会把 squash、archive、review `0 major` 或 verification `PASS` 解释为部署、manager／cgroup 生效、production `4141` 接管、rolling 或 cutover 授权。

## 一致性结论

| 限定命题 | 复核结果 | 文档证据 |
|---|---|---|
| Review 为 `0 major` | **一致确认** | Review `:4-6,35-37`；Audit `:3-7,137-139` |
| Verification 为 `PASS` | **一致确认** | Verify `:5,68-70`；Audit `:3` 将 exact-tip verify `PASS` 明确列为既有证据 |
| `0 major` 可作为回放证据 | **一致确认** | Audit `:3-4` 明确把 merged-state review `0 blocker／0 major` 与 exact-tip verify `PASS` 作为既有回放证据；Review `:4,37` 与 Audit `:139` 同时保留未来逐片 main-side gate，不把既有证据误写成免检 |
| 逐片 squash，非 merge | **一致确认** | Review `:4,37`；Audit `:4,88,97,102-106,117-123,139` 明确要求两个新的 non-merge commits，并禁止 merge、FF、cherry-pick及两片合一 |
| Reviewed-source archive targets | **一致确认** | Audit `:20,91,100,108-115`：S3 target 为 `865a5b71210e2436b36786b5de67146939d1e0f5`；S4 target 为 `e16c2a700f23f66535e7347ab7357518eb8e56bd`；冻结的是 target 与时序，不代表 archive ref 已创建 |
| `NO CUTOVER` | **一致确认** | Review `:4,29`；Verify `:5,53-59`；Audit `:8,30,137-139` 均明确不授权部署或 cutover |

## 事实性发现

未发现问题。限定范围内三份文档不存在相互矛盾、残留 merge 路线、archive target 混用或 cutover 授权外推。

## 主观建议

无。

## 最终结论

**0 blocker／0 major；既有 review `0 major` 与 exact-tip verification `PASS` 可以作为逐片 squash 回放证据。** 正确历史路线仍是 S3、S4 逐片在 actual main 上重建新的 non-merge commits，并逐片通过 main-side gates；reviewed-source archive targets 分别固定为 `865a5b71210e2436b36786b5de67146939d1e0f5` 与 `e16c2a700f23f66535e7347ab7357518eb8e56bd`。**NO CUTOVER。**
