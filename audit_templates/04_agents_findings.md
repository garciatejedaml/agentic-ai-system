# Phase 3 · Per-agent findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## Per-agent checklist

For each `agents/*.py` file, fill in this matrix. The columns are
the checklist from §4 of `CARSON_AUDIT_PLAYBOOK.md`.

| agent | identity | boundaries | tools docstrings | failure modes | hitl | budget | caching | pii safe | tested |
|-------|---------:|-----------:|-----------------:|--------------:|-----:|-------:|--------:|--------:|-------:|
| aquiles |  |  |  |  |  |  |  |  |  |
| sdlc    |  |  |  |  |  |  |  |  |  |
| brandson |  |  |  |  |  |  |  |  |  |
| jenkins  |  |  |  |  |  |  |  |  |  |
| spinnaker |  |  |  |  |  |  |  |  |  |
| inspector |  |  |  |  |  |  |  |  |  |
| confluence |  |  |  |  |  |  |  |  |  |
| jira |  |  |  |  |  |  |  |  |  |
| router |  |  |  |  |  |  |  |  |  |
| bob     |  |  |  |  |  |  |  |  |  |
| hydra   |  |  |  |  |  |  |  |  |  |
| csb     |  |  |  |  |  |  |  |  |  |
| pixie   |  |  |  |  |  |  |  |  |  |
| studio  |  |  |  |  |  |  |  |  |  |
| (add rows for any agent the audit discovers) |  |  |  |  |  |  |  |  |  |

`✓` = fulfilled, `✗` = missing → finding card, `~` = partial.

---

## Cross-agent overlaps

Two agents claiming the same responsibility → finding:

| agent A | agent B | overlapping responsibility | recommended boundary |
|---------|---------|----------------------------|----------------------|
|         |         |                            |                      |

---

## Findings

### Finding A-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 3-agents
- **Location**: `agents/<file>:<line>`
- **Category**: prompt_overlap | hardcoded_path | dated_examples | bloat_prompt | missing_tools | overscoped_tools | budget_unset | other
- **Evidence**:
- **Why it's a problem**:
- **Proposed fix**:
- **Estimated fix time**:
- **Verification**:
- **Owner**:

(Repeat A-02, A-03, ...)

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Agents with > 3 findings (highest debt):
- Agents with 0 findings (gold standard, use as template):
