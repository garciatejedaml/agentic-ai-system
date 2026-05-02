# Carson · self-audit · executive summary

**Audit run**: <YYYY-MM-DD HH:MM>
**Branch audited**: <branch>
**Commit SHA**: <short-sha>
**Auditor**: Carson Copilot · automated self-audit
**Playbook version**: CARSON_AUDIT_PLAYBOOK.md (5c2d979 or later)

---

## One-page summary

Five most critical findings across all 10 phases:

1. **<area>** · <one-line title> · <severity> · `<location>` — <one-sentence why it matters>
2. **<area>** · <one-line title> · <severity> · `<location>` — <one-sentence why it matters>
3. **<area>** · <one-line title> · <severity> · `<location>` — <one-sentence why it matters>
4. **<area>** · <one-line title> · <severity> · `<location>` — <one-sentence why it matters>
5. **<area>** · <one-line title> · <severity> · `<location>` — <one-sentence why it matters>

---

## Top 10 blockers for the demo (next week)

Issues that, if hit during the demo, would visibly fail or contradict
the narrative of "Carson is enterprise-grade":

| # | Finding | Severity | Demo impact |
|---|---------|----------|-------------|
| 1 |         |          |             |
| 2 |         |          |             |
| 3 |         |          |             |
| 4 |         |          |             |
| 5 |         |          |             |
| 6 |         |          |             |
| 7 |         |          |             |
| 8 |         |          |             |
| 9 |         |          |             |
| 10|         |          |             |

---

## Quick wins (≤ 2h fix, high visible impact)

Findings that pay off out of proportion to fix time:

- [ ] **<finding-id>** · <one-line title> · est. <X min>
- [ ] **<finding-id>** · <one-line title> · est. <X min>
- [ ] **<finding-id>** · <one-line title> · est. <X min>

---

## Strategic debt (≥ 1 sprint to fix)

Findings P0/P1 that require focused work over multiple days. Flag
for **post-demo** sprint planning:

- **<finding-id>** · <title> · est. <X days>
  - Why it can't be a quick fix:
  - Acceptable interim mitigation:

---

## Clean-up debt (P3, batch in a single janitor PR)

Cosmetic / consistency findings that can be batched after the demo:

- <finding-id> · <title>
- <finding-id> · <title>
- <finding-id> · <title>

---

## Risk register (decisions for leadership)

Findings that aren't an engineering decision — they're a product /
strategy / org call:

| risk | description | recommended decision | needed by |
|------|-------------|----------------------|-----------|
|      |             |                      |           |

---

## Audit completeness check

| phase | output file | findings count | status |
|-------|-------------|----------------|--------|
| 0 — repo map        | 01_repo_map.md             |     | complete / partial / failed |
| 1 — strands         | 02_strands_findings.md     |     | complete / partial / failed |
| 2 — deterministic   | 03_deterministic_findings.md |   | complete / partial / failed |
| 3 — agents          | 04_agents_findings.md      |     | complete / partial / failed |
| 4 — langgraph       | 05_langgraph_findings.md   |     | complete / partial / failed |
| 5 — mcp             | 06_mcp_findings.md         |     | complete / partial / failed |
| 6 — security        | 07_security_findings.md    |     | complete / partial / failed |
| 7 — observability   | 08_observability_findings.md |   | complete / partial / failed |
| 8 — data layer      | 09_data_layer_findings.md  |     | complete / partial / failed |
| 9 — testing         | 10_testing_findings.md     |     | complete / partial / failed |

If any phase is `partial` or `failed`, the per-phase MD has a
`Phase incomplete` banner at the top and a `Reason` line explaining
which command errored or which area was inaccessible.

---

## Severity totals

| severity | count |
|----------|-------|
| P0 (broken)             |  |
| P1 (broken at runtime)  |  |
| P2 (works but risky)    |  |
| P3 (polish)             |  |
| **Total**               |  |

---

## Next action

- [ ] Martin reviews this summary
- [ ] Martin picks 1-3 cluster PRs to ship before demo
- [ ] Other clusters get scheduled for post-demo sprint
- [ ] Janitor PR planned for the P3 cleanup batch

The audit is read-only. **No fixes have been applied.** All proposed
fixes live in `99_fix_manifest.md` waiting for direction.
