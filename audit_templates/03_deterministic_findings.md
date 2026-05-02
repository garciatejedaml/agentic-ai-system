# Phase 2 · Deterministic-mode findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## Where the flag lives

| layer | file | reference | default | who can override? |
|-------|------|-----------|---------|-------------------|
| agent class field      |  |  |  |  |
| dispatch payload       |  |  |  |  |
| environment variable   |  |  |  |  |
| YAML / JSON config     |  |  |  |  |
| CLI / API arg          |  |  |  |  |

---

## Decision path

Trace the call path from a user request (chat / Jira webhook / CLI)
through the router, through the agent dispatcher, to the agent run.
Mark every branch where the deterministic flag is read or set:

```
[user input]
    │
    ▼
<location 1: who reads the flag here?>
    │
    ▼
<location 2: who can override here?>
    │
    ▼
<location N: agent run, deterministic = ?>
```

---

## Per-agent appropriateness

For each agent, what should the default be and why:

| agent | should default to | reason |
|-------|-------------------|--------|
| aquiles |        |        |
| sdlc    |        |        |
| inspector (terraform) |  |  |
| spinnaker (deploy) |  |  |
| brandson (git) |  |  |
| jenkins |        |        |
| confluence |     |        |
| jira |           |        |
| bob, hydra, csb, pixie, studio (athena knowledge agents) |  |  |
| router |         |        |

Flag mismatches between the recommended default and the actual code.

---

## Observability of mode choice

- Is there a log line for every run stating which mode it ran in? <yes/no>
- Is the mode visible in the dashboard's run detail / replay view? <yes/no>
- Is the mode in the audit_log table? <yes/no>

If any of those are no, that's a finding.

---

## Findings

### Finding D-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 2-deterministic
- **Location**: `<file>:<line>`
- **Category**: flag_in_wrong_layer | unsafe_default | mixed_semantics | untested_transition | no_per_request_override | cost_not_captured | other
- **Evidence**:
  ```{lang}
  <excerpt>
  ```
- **Why it's a problem**: <paragraph>
- **Proposed fix**: <paragraph or short patch>
- **Estimated fix time**:
- **Verification**:
- **Owner**:

(Repeat D-02, D-03, ...)

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Most-affected files:
- Critical finding for the demo: <id>
- Recommended cluster for first fix PR:
