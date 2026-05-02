# Phase 6 · Security findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

> **Important**: do not paste actual secret values. Replace with
> `<redacted-NN-chars>` placeholders.

---

## Hardcoded credential / URL inventory

| file:line | what | redaction | severity |
|-----------|------|-----------|---------:|
|           |      |           |          |

Examples of "what":
- `proxy_url`, `bedrock_endpoint`, `confluence_base_url` (hardcoded URL)
- `api_key`, `client_secret` (literal value)
- `martin@jpmc`, `F702937` (PII)
- `I:/repositories/...` (env-specific path)

---

## .env hygiene

- `.env` in `git ls-files`? <yes/no> — if yes, immediate P0
- `.env.template` in sync with `.env` keys? <yes/no>
- Keys in `.env.template` with no actual fallback in code? <list>

---

## Logging and PII

- Are full prompts logged (including user-provided text)? <yes/no>
- Is there a redaction step before logs leave the process? <yes/no>
- Sample log line that contains PII (redacted): `<sample>`

---

## IAM and scoping

For each role / service principal Carson uses:

| role | what it can do | what it actually needs | over-scoped? |
|------|----------------|------------------------|-------------:|
|      |                |                        |              |

---

## Audit trail completeness

For each state-changing action (PR merge, deploy, secret read,
schema migration), is there an `audit_log` row?

| action | audit hook present? | location |
|--------|--------------------:|----------|
|        |                     |          |

---

## Findings

### Finding SE-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 6-security
- **Location**: `<file>:<line>`
- **Category**: hardcoded_secret | hardcoded_pii | unscoped_iam | log_pii_leak | env_committed | audit_gap | broad_token_scope | other
- **Evidence**: <redacted>
- **Why it's a problem**:
- **Proposed fix**:
- **Estimated fix time**:
- **Verification**:
- **Owner**:

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Top priority: <id> — must fix before any external demo
- Acceptable risk for now: <ids> with mitigation plan
