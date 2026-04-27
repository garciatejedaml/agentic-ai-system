# Carson dashboard · ops view wire-up

This is the implementation that adds three things on top of the existing
Carson dashboard:

1. **Jira intake → auto-routing.** A Jira webhook target that classifies
   each ticket (heuristic by default, swappable to Claude Haiku 4.5 via
   CDAOSDK) and emits an `J-XXXXXX` job id assigned to the right agent.
2. **Unified ops feed.** Three lanes — Jenkins, Spinnaker, GitHub PRs —
   on one page, fed by webhooks.
3. **Browser notifications for HITL.** Real `Notification` API. Per-rule
   toggles persisted server-side. Demo button included.

The new tab lives at `/dashboard#/ops`. The existing live, history, and
run-detail views are untouched.

---

## 1. Files in this PR

**New** in `carson_dashboard/`:

| Path | Purpose |
|---|---|
| `classifier.py` | Heuristic + Haiku Jira classifier. Same return shape on both backends. |
| `ops_db.py` | Adds three SQLite tables (`jira_tickets`, `ops_events`, `notification_rules`) on the existing DB. |
| `webhooks.py` | `receive_jira`, `receive_jenkins`, `receive_spinnaker`, `receive_github`, `request_hitl`. Each persists, publishes to the SSE bus, and fires notifications when rules match. |
| `static/ops.js` | Frontend ops view — Jira list, router viz, active-jobs panel, three lane feed, notification controls. Owns its own SSE connection. |

**Modified** in `carson_dashboard/`:

| Path | Change |
|---|---|
| `routes.py` | Adds `/api/jira/*`, `/api/ops/*`, `/api/notifications/rules*`, `/api/hitl/request` endpoints. Existing routes unchanged. |
| `simulator.py` | Adds `seed_ops_history()` and `ops_live_loop()` so the dashboard is populated even before real webhooks are wired. |
| `__main__.py` | Calls `ops_db.init_ops_db()` on boot and starts the ops simulator alongside the runs simulator. |
| `static/index.html` | Adds the `ops` tab + `tpl-ops` template + loads `ops.js`. |
| `static/dashboard.css` | Appends section 9 with all ops-view styles (uses existing tokens). |
| `static/dashboard.js` | Single line in `route()` to delegate `#/ops` to `window.showOps()`. |

No existing endpoint signatures or DB tables were changed.

---

## 2. Copy to the VDI

In the VDI, with the Carson repo `high-touch-agent-prompts` on branch
`feature/CREDITTECH-241864-agentic-ai-mcp-servers`:

**Option A — bulk copy from this branch.** Pull the branch into a temp
folder on the VDI, then copy `carson_dashboard/` over your existing
`carson_dashboard/`:

```powershell
# in DevShell on the VDI
cd C:\repos
git clone -b claude/carson-audit-2026-04-27 https://github.com/garciatejedaml/agentic-ai-system.git carson-ops-temp
robocopy carson-ops-temp\carson_dashboard high-touch-agent-prompts\carson_dashboard /E /XO /NFL /NDL
```

`robocopy /XO` only overwrites files older than the source — safer than
a blind `xcopy`. Inspect the diff before staging.

**Option B — file-by-file (if Copilot is doing this).** Have Copilot
fetch each of the four new files plus the six modified files from this
branch and write them to the matching paths. Use the table above.

---

## 3. Tell Copilot to wire it up

Paste this into Copilot Chat with `@carson-fixer`:

```
@carson-fixer apply OPS-WIREUP

Context:
  - Branch claude/carson-audit-2026-04-27 on garciatejedaml/agentic-ai-system
    contains a complete carson_dashboard/ implementation that adds:
    a) Jira ticket auto-routing (classifier.py + webhooks.receive_jira)
    b) Unified ops feed for Jenkins/Spinnaker/GitHub (ops_db.py + webhooks.py)
    c) Browser notifications for HITL (rules + Notification API in ops.js)
  - The existing live/history/run-detail views and the runs/steps/tool_calls
    schema must NOT change. The new tables coexist on the same SQLite file.

Task — apply in 4 steps, verifying after each:

  Step 1. Pull the four new files from claude/carson-audit-2026-04-27:
            carson_dashboard/classifier.py
            carson_dashboard/ops_db.py
            carson_dashboard/webhooks.py
            carson_dashboard/static/ops.js
          and write them at the same paths in the VDI repo.

  Step 2. Apply the diffs to the six modified files (routes.py, simulator.py,
          __main__.py, static/index.html, static/dashboard.css, static/dashboard.js)
          from the same branch. Preserve all unrelated content.

  Step 3. Run the dashboard locally:  python -m carson_dashboard
          Verify in a browser at http://127.0.0.1:8765/dashboard#/ops :
            - jira intake list shows tickets with classification badges
            - router signals appear bottom-left of the router panel
            - three ops lanes show events
            - rule toggles flip and persist (refresh page → state survives)
            - "enable browser notifications" prompts the OS
            - "trigger demo HITL alert" fires an OS-level notification

  Step 4. When verification passes, open ONE PR titled
          "feat(dashboard): jira auto-routing + ops feed + HITL notifications"
          targeting feature/CREDITTECH-241864-agentic-ai-mcp-servers.

Constraints (per carson-fixer guardrails):
  - One PR. Do not split.
  - Stop and report if any step fails — do not patch around errors.
  - Do not modify the runs/steps/tool_calls schema.
  - Do not touch any agent code outside carson_dashboard/.
  - Do not enable Haiku classifier yet (heuristic ships first).
```

---

## 4. After it's running on the VDI

### a) Point real Jira at it

In Jira **Admin → System → WebHooks → Create**:
- Name: `carson-router`
- URL: `https://<your-carson-host>/api/jira/webhook`
- Events: `Issue created`, `Issue updated`
- JQL filter: `project IN (CRED, INF) AND status = "To Do"`
- Body: leave default (Atlassian sends the full issue payload — the
  receiver tolerates that exact shape).

Test with:
```bash
curl -X POST https://<carson-host>/api/jira/webhook \
  -H "Content-Type: application/json" \
  -d '{"key":"CRED-9999","summary":"Reindex Athena Hydra","labels":["athena"]}'
```

### b) Point Jenkins at it

In Jenkins, install the **Notification** plugin and point it at:
`https://<carson-host>/api/ops/jenkins/webhook`. Use the `JSON` format —
the receiver expects `{name, build:{number, phase, status}}`.

### c) Point Spinnaker at it

Add an **Echo webhook** stage at the end of every pipeline pointing to
`/api/ops/spinnaker/webhook` with body
`{"application":"$pipeline","environment":"$env","status":"$status"}`.

### d) Point GitHub at it

In each team repo, **Settings → Webhooks → Add webhook**:
- URL: `https://<carson-host>/api/ops/github/webhook`
- Content type: `application/json`
- Events: `Pull requests`

### e) Switch the classifier to Haiku

When you're ready to take CDAOSDK Bedrock spend on routing:
```bash
export CARSON_CLASSIFIER_BACKEND=haiku
export CARSON_BEDROCK_REGION=us-east-1
```
Restart the dashboard. The new backend kicks in for the next ticket. If
Bedrock errors or CDAOSDK isn't importable, it falls back to heuristic
silently — no requests are dropped.

### f) Wire HITL from real agents

Carson agents that need approval call:
```python
import requests
requests.post("http://127.0.0.1:8765/api/hitl/request",
              json={"job_id":"J-2417", "summary":"coder·aquiles staged a PR"})
```
(Or import `webhooks.request_hitl(...)` directly if running in-process.)

---

## 5. What's NOT done yet (intentional)

- **Auth.** All endpoints are open. For prod, gate webhooks behind shared
  secrets and gate the dashboard behind JPMC SSO. The CARSON_AUDIT_FIXES
  document already covers this in Tier 0 / Cloud track.
- **Service worker for notifications.** Currently the page must be open
  to fire a notification. A service worker would let alerts arrive even
  with the tab closed. Optional Sprint-25 polish.
- **Cross-tab dedup.** If the dashboard is open in three tabs, a single
  HITL fires three notifications. Use the same `tag` (already done — see
  `carson-hitl-${jobId}`) and the browser will collapse them.
- **Bitbucket vs GitHub.** The receiver is named `github` but accepts
  Bitbucket's PR webhook payload too — the field shapes are similar
  enough. If you need true Bitbucket-specific normalization, fork
  `webhooks.receive_github` into `receive_bitbucket`.
