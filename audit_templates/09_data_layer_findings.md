# Phase 8 · Data layer findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## RAG collections

| collection name | embedding model | chunk size | source | refresh strategy | size today |
|-----------------|------------------|-----------:|--------|------------------|----------:|
|                 |                  |            |        |                  |           |

---

## ChromaDB persistence

- Persist directory: `<path>`
- Backup strategy: <description>
- What happens on container rebuild: <description — flag if "embeddings lost">
- Versioning: <yes/no — if no, this is P1 minimum>

---

## SQLite paths

| file path | tables | who writes | who reads |
|-----------|--------|------------|-----------|
|           |        |            |           |

Flag any case where two paths are used by different code paths
(should be one canonical path).

---

## Git-sync persistence (carson_data)

- Branch: `<name>`
- What's synced: <list>
- Sync frequency: <every N min>
- Privacy issue (anyone with repo access reads everything): <yes/no>
- Bloat issue (commits/month at scale): <estimate>
- Retention policy: <description or "none">

---

## Hot vs cold tier

| tier | storage | retention | access pattern |
|------|---------|-----------|----------------|
| hot  |         |           |                |
| cold |         |           |                |

If "all in one tier", flag.

---

## Findings

### Finding DA-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 8-data
- **Location**: `<file>:<line>`
- **Category**: multiple_db_paths | unversioned_collections | privacy_in_git_sync | bloat_in_git | no_retention | hot_cold_missing | embeddings_lost_on_rebuild | other
- **Evidence**:
- **Why it's a problem**:
- **Proposed fix**:
- **Estimated fix time**:
- **Verification**:
- **Owner**:

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Single biggest data risk: <one-line>
