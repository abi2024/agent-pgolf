# Re-check of OBFUSCATED PRs — 2026-04-29

Following the verification handshake with OE-GOD on PR #1795 (which superseded
the closed/OBFUSCATED PR #1785), I re-fetched the three other top-10 OBFUSCATED
entries to check whether their authors had similarly converted to readable
source. They have not.

| PR | HEAD commit | submission folder | wrapper | classification |
|---|---|---|---|---|
| #1758 | `fa8c6fb` | `2026-04-20_SP8192_PreQuantTTT_Unfrozen_LR1e3` | `import lzma; exec(L.decompress(B.b85decode(...)))` | OBFUSCATED (unchanged) |
| #1738 | `fdf270e` | `2026-04-19_SP8192_PreQuantTTT_CaseOps_V15` | `import lzma; exec(L.decompress(B.b85decode(...)))` | OBFUSCATED (unchanged) |
| #1771 | `0fc6ebb` | `2026-04-22_SP8192_CaseOps_V13_L2_LoRA_TTT` | `import lzma, runpy, tempfile; runpy on decompressed file` | OBFUSCATED (different wrapper variant) |

**Static check:** All three files start with `import lzma` and execute or
runpy a base85-decoded LZMA-compressed payload. The audit tool returns
OBFUSCATED on all three, same as the original 2026-04-23 snapshot.

**No re-classification needed.** The audit's per_pr_v2/{1758,1738,1771}.json
remain accurate.

**Note on PR #1771's wrapper variant:** Uses `tempfile.mkdtemp()` + `runpy`
rather than direct `exec()`. The audit tool flags both patterns as OBFUSCATED
since neither permits static LUT inspection. A future tool extension could
attempt sandboxed execution of these wrappers to extract the inner
`build_sentencepiece_luts` for analysis, but that is out of scope here.

**Status of the audit's classifications:** The 2026-04-23 snapshot's
classifications remain valid as of 2026-04-29 except for the explicitly
documented update to PR #1785 → PR #1795 (audit v2.1, see changelog_v2.md).
