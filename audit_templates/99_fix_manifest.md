# Carson · self-audit · fix manifest

**Generated**: <YYYY-MM-DD HH:MM>
**Audit branch**: `<audit-branch>`
**Source commit**: `<short-sha>`
**Total findings**: <N>

---

This is a flat ordered list of every finding card across all 10
phases. Sort: severity (P0 → P3), then by estimated fix time
(shortest first within each severity).

Use this manifest to plan fix-cluster PRs (see
§13 of `CARSON_AUDIT_PLAYBOOK.md`).

---

## P0 — Broken

- [ ] **S-04** (`agents/aquiles.py:42`) — Add `@tool` decorator to `_run_tests`. Est: 5 min. Verify: `grep "@tool" agents/aquiles.py | wc -l` returns 8.
- [ ] **{ID}** (`<file>:<line>`) — <one-line title>. Est: <X>. Verify: `<one-line>`.

(Add P0 entries from each phase.)

---

## P1 — Broken at runtime

- [ ] **{ID}** (`<file>:<line>`) — <one-line title>. Est: <X>. Verify: `<one-line>`.

---

## P2 — Works but inconsistent / risky

- [ ] **{ID}** (`<file>:<line>`) — <one-line title>. Est: <X>. Verify: `<one-line>`.

---

## P3 — Polish

- [ ] **{ID}** (`<file>:<line>`) — <one-line title>. Est: <X>. Verify: `<one-line>`.

---

## Suggested fix clusters (one PR each)

| cluster | findings | approx total time | ship by |
|---------|----------|------------------:|---------|
| A — strands P0      | S-01, S-04, S-07         |       | demo |
| B — deterministic P0 | D-01, D-03              |       | demo |
| C — security P0     | SE-02, SE-05             |       | demo |
| D — agents P1 by-area | A-* per agent          |       | post-demo sprint 1 |
| E — mcp P1          | M-* per server           |       | post-demo sprint 1 |
| F — observability P1 | O-*                     |       | post-demo sprint 2 |
| G — testing P1      | T-*                      |       | post-demo sprint 2 |
| H — P2 polish (janitor PR) | mixed              |       | rolling |
| I — P3 polish (janitor PR) | mixed              |       | rolling |

Each cluster PR title: `fix(carson): audit cluster X — <area> · <count> findings`.

Each cluster PR description copies its findings from this manifest
with each marked `[x]` after the fix is in the diff. Verification
output (the grep / test command + its result) is attached per finding.

---

## Sign-off

The audit phase is **done** when this manifest is complete. **No
fixes have been applied yet.** Each cluster goes to a separate fix
PR following the protocol in §13 of `CARSON_AUDIT_PLAYBOOK.md`.

If any cluster's verification fails, **stop**, revert the cluster PR,
file the failed verification as a new P0 finding in a separate
audit follow-up MD. Do not improvise.
