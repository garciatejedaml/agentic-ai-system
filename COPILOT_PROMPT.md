# Copilot Execution Prompt for Carson Full Review v2

Use this prompt in a fresh Claude session (Opus recommended) with the Carson codebase mounted.

---

## Prompt

```
Read the file CARSON_REVIEW_V2_SPEC.md in this repository completely before writing any code. This is a self-contained implementation specification for refactoring the Carson multi-agent LangGraph system running on AWS Bedrock at JPMC.

Critical constraints you MUST follow:
- NEVER use boto3 directly — only use `cdao.bedrock_byoa_invoke_model(data, payload)`
- NEVER use Converse API format — only Anthropic Messages API (snake_case: tool_use, tool_result)
- The `converse()` method in bedrock_client.py uses InvokeModel under the hood, NOT the AWS Converse API
- jira_agent.py is the GOLDEN TEMPLATE — all other agents must match its pattern exactly

Execution plan:
1. Read the full spec first — do NOT start coding until you understand all 6 work streams
2. Start with Stream A (bedrock_client.py refactor) and Stream E (dead code removal) — these are independent
3. Then Stream B (update all agents to golden template) — depends on A being complete
4. Then Streams C (prompt improvements) and D (workflow/state cleanup) in parallel
5. Finally Stream F (confirmation node) — depends on all others

For each file you modify:
- Show me the diff before applying
- Do NOT auto-commit — I will review and commit manually
- If you're unsure about a CDAO SDK behavior, ask me rather than guessing

The target codebase is at: I:\repositories\high-touch-agent-prompts\langgraph-system\

After completing all streams, run the verification checklist in Section 8 of the spec.
```

---

## Tips

- **One stream at a time**: If context gets large, you can feed one stream at a time: "Execute only Stream A from CARSON_REVIEW_V2_SPEC.md"
- **Token efficiency**: The spec is designed to be self-contained — no need to explain the architecture, just tell it to read the spec
- **If using Cowork**: Mount the `langgraph-system` folder and also have the spec file accessible
- **If using Claude Code CLI**: Run from the `langgraph-system` directory with the spec file in it
