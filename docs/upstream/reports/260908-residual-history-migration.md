# 2026-09-08 residual History canonical-history migration

## Scope and authority

- **Ledger authority**: `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md`, `history` section, lines 276–288 at execution time.
- **Selected rows**: exactly the 13 rows whose disposition is `canonical history` and whose destination is under `.dev/docs/upstream/retry-and-continuation/history/history-forensics/` (EF-HISTORY-FORENSICS).
- **Excluded**: the same ledger's delete rows (`history/decisions.md` and `history/spec.md`), all EF-HISTORY-BRIDGE rows, and every other topic. No directory was removed. No `git add`, commit, or push was run.

## Procedure and controls

Before any destination directory was created or source was renamed, every exact source was required to be a regular file and every exact destination was required not to exist (strict destination no-clobber). SHA-256 was then recorded from each source. Each exact source was renamed to its ledger destination, with a second immediately-before-rename destination check. SHA-256 was recomputed from the destination. A row passes only when its pre/post SHA-256 values match, the source is absent, and the destination is a regular file.

The table records source text preservation through the matching hash. `source_absent=true` and `destination_present=true` are post-migration observations, not a request to delete the residual `history` directory; its non-ledger files remain untouched.

## Itemized results

| # | Exact source | Exact destination | Pre SHA-256 | Post SHA-256 | source absent | destination present | Result |
|---:|---|---|---|---|---|---|---|
| 1 | `.dev/docs/history/proposal.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/proposal.md` | `0f4f3ef5c3a6981b9db962eb6d27eda579fa3451704a4401b9392c2e7922296b` | `0f4f3ef5c3a6981b9db962eb6d27eda579fa3451704a4401b9392c2e7922296b` | true | true | pass |
| 2 | `.dev/docs/history/reports/260820-forensic-demand-audit.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-forensic-demand-audit.md` | `cf2ab156077c4b2d070e84e27d43fd6c7d4b963522b92d2e39b62ea0c2edcc08` | `cf2ab156077c4b2d070e84e27d43fd6c7d4b963522b92d2e39b62ea0c2edcc08` | true | true | pass |
| 3 | `.dev/docs/history/reports/260820-history-as-fixture-source.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-history-as-fixture-source.md` | `5f42957618505c2cdc8ca513538130bda5eaffdb1c54a38ecf71f44ac086a42b` | `5f42957618505c2cdc8ca513538130bda5eaffdb1c54a38ecf71f44ac086a42b` | true | true | pass |
| 4 | `.dev/docs/history/reports/260820-history-wiring-audit.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-history-wiring-audit.md` | `942170077dd1ab8cc101ebdc4c297005df3acfd5926ab7ade3c0257cdb2146a1` | `942170077dd1ab8cc101ebdc4c297005df3acfd5926ab7ade3c0257cdb2146a1` | true | true | pass |
| 5 | `.dev/docs/history/reports/260820-review-history-forensics-proposal-r2.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-proposal-r2.md` | `d423a8182f72822be9e952ab2c1c5ac79afbe5054880abd603568acd8204743a` | `d423a8182f72822be9e952ab2c1c5ac79afbe5054880abd603568acd8204743a` | true | true | pass |
| 6 | `.dev/docs/history/reports/260820-review-history-forensics-proposal.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-proposal.md` | `32a690f9b9fdb0ebc05734aaa806772b5a1f31883356e509a7ac7b5e408c2a1a` | `32a690f9b9fdb0ebc05734aaa806772b5a1f31883356e509a7ac7b5e408c2a1a` | true | true | pass |
| 7 | `.dev/docs/history/reports/260820-review-history-forensics-r3-spotcheck.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-r3-spotcheck.md` | `97c19bbed7c993aaf42e3583df7e9c91e0103419514f71443eec8b5b29fe1d22` | `97c19bbed7c993aaf42e3583df7e9c91e0103419514f71443eec8b5b29fe1d22` | true | true | pass |
| 8 | `.dev/docs/history/reports/260820-review-history-forensics-scope-r2.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-scope-r2.md` | `2b646a31b4b32e8e95c39a7b01a5610642724ffd02107186b464012fd475b8bf` | `2b646a31b4b32e8e95c39a7b01a5610642724ffd02107186b464012fd475b8bf` | true | true | pass |
| 9 | `.dev/docs/history/reports/260820-review-history-forensics-scope.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-scope.md` | `5cc5fce9ea764a130237462378e66311ca60bc264490083cbd83708013191387` | `5cc5fce9ea764a130237462378e66311ca60bc264490083cbd83708013191387` | true | true | pass |
| 10 | `.dev/docs/history/reports/260821-gone-scenario-persistence.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-gone-scenario-persistence.md` | `e3adb1a145fe8dc04624dd5919bd599e1546a5d9b725b86e105ed5ca90976492` | `e3adb1a145fe8dc04624dd5919bd599e1546a5d9b725b86e105ed5ca90976492` | true | true | pass |
| 11 | `.dev/docs/history/reports/260821-review-spec-facts.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-review-spec-facts.md` | `0641a00679e9193d40478faf6ee6e52b6e56a19c94da559e1b8102e14dc00b12` | `0641a00679e9193d40478faf6ee6e52b6e56a19c94da559e1b8102e14dc00b12` | true | true | pass |
| 12 | `.dev/docs/history/reports/260821-review-spec-scope.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-review-spec-scope.md` | `bdafcb3cb7cabef373843b1bd2b03cc30996ab7604197d5098b8ce23c1ba832b` | `bdafcb3cb7cabef373843b1bd2b03cc30996ab7604197d5098b8ce23c1ba832b` | true | true | pass |
| 13 | `.dev/docs/history/reports/260821-structured-logging-design.md` | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-structured-logging-design.md` | `d340f1dfb2c984ed068788ae040b796c759c5c9b68ca98cd4af64b0df2b32020` | `d340f1dfb2c984ed068788ae040b796c759c5c9b68ca98cd4af64b0df2b32020` | true | true | pass |

## Target history index

Created [`../retry-and-continuation/history/history-forensics/README.md`](../retry-and-continuation/history/history-forensics/README.md) and updated [`../retry-and-continuation/history/README.md`](../retry-and-continuation/history/README.md). Together they state:

1. **Provenance**: the source retired topic, the EF-HISTORY-FORENSICS residual-ledger authority, the exact 13-file scope, and the SHA-256-preserved migration.
2. **Evidence boundary**: these are point-in-time raw evidence and obsolete-design context, not current authority or a revival of the retired History topic.
3. **Current carrier**: `upstream/retry-and-continuation/status.md` owns current behavior and verified state; `upstream/retry-and-continuation/deferred.md` §24–§26 owns pending forensic/query/replay work and current decisions.

## Final verification

- 13/13 exact ledger sources are absent.
- 13/13 exact ledger destinations are present regular files.
- 13/13 pre/post SHA-256 pairs match; source contents are preserved.
- 13/13 destinations were absent at the strict preflight; no destination was overwritten.
- The source `history` directory itself was not deleted. At this migration's preflight, its 15 non-selected files (13 EF-HISTORY-BRIDGE files plus the two ledger delete rows) were outside this migration's ownership and scope.
