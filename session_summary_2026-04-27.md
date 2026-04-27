# Session 2026-04-27: empirical validation + PR #1795 verification

## Empirical validation runs (commits 2a83dac through 26f128c)
- Run 1: boundary mask is NOT identically zero — 50,000 control-token predecessors
- Run 1.5: three scoring modes still converge to 1.1671413 within 7.8e-9
- Run 2: yahya's byte-token bug verified PRESENT (256 byte tokens, 6 vs 1, 1.35M extra bytes in val)
- Run 3: yahya's exact LUT gives 1.1655 on our val, NOT 1.1770; gap to quoted 1.1746 unexplained

## Retraction (commit 45bce1b)
The audit's claim of "1.1770 within 0.2% of 1.1746" was retracted. Updated writeup, methodology, reviewer_readiness in agent-pgolf and the PR #1804 submission.

## PR #1795 verification (commit c9ff8f9 in agent-pgolf, a97f5c4 in parameter-golf)
- @OE-GOD replied to PR #1804 noting #1785 closed/superseded by #1795
- Verified PR #1795 at cb5ad95: lut_status CORRECT, all three properties match canonical
- Audit frontier moved from PR #1735 (1.04290) to PR #1795 (1.01252)
- v2.1 changelog entry documents the update

## State at end of session
- agent-pgolf: c9ff8f9, on origin/main
- parameter-golf: a97f5c4, on origin/audit-1698-lineage-bpb-bytecount
- PR #1804: updated, contains v2.1 audit
- Reply to @OE-GOD: drafted, ready to post

## Pending tomorrow
- Post reply to @OE-GOD on PR #1804
- Day 8 blog post draft
- Optional: re-audit other 3 OBFUSCATED PRs (#1758, #1738, #1771) for similar successors
