# Phase 0 · Repo map

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

If partial or failed, reason: <one-line>

---

## Top-level tree

```
<paste output of `tree -L 2 -I '.venv|__pycache__|.pytest_cache|node_modules|.git'`>
```

---

## LOC by directory

| directory | files | code lines | notes |
|-----------|-------|------------|-------|
| agents              |  |  |  |
| carson_dashboard    |  |  |  |
| carson_data         |  |  |  |
| confluence-oauth-setup |  |  |  |
| dcd-spec            |  |  |  |
| docs                |  |  |  |
| langgraph-system    |  |  |  |
| mcp-servers         |  |  |  |
| mcp-test-harness    |  |  |  |
| scripts             |  |  |  |
| skills              |  |  |  |
| vscode-extension    |  |  |  |
| **TOTAL**           |  |  |  |

---

## Recently modified files (last 14 days)

```
<paste output of `find . -type f -name "*.py" -mtime -14 -not -path "./.venv/*" -not -path "./.git/*"`>
```

These are the highest-priority audit targets — recent changes are
where bugs and inconsistencies typically hide.

---

## Markdown docs at root

```
<paste output of `ls -la *.md`>
```

---

## Session logs (Copilot self-recorded sessions)

```
<paste output of `ls -la SESSION-*.md`>
```

---

## Notes

- Folders > 5K LOC or > 100 files (proportional audit depth):
- Folders newly added in the last 30 days:
- Folders that disappeared (compare to `CARSON_AUDIT_FIXES.md` v3.0):
