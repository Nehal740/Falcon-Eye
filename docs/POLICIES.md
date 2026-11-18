# Policy Configuration Guide

## How a decision is made
1. Falcon Eye works out the action's **category** from its name (for example `send_external_email` is *external email*). If the agent also declares a category, Falcon Eye checks the rules against **both** readings, so an agent cannot hide a dangerous action behind a harmless label.
2. It collects the **enabled** policies that apply to the agent: workspace-wide policies, plus policies assigned to that agent.
3. Every rule in those policies is checked. A rule matches when its action type or action name matches **and** its resource pattern matches (a blank resource pattern means any resource).
4. Among matching rules, the policy with the **lowest priority number** wins (1 is checked first). If several matching rules share that priority, the **stricter** one wins: BLOCK beats REQUIRE_APPROVAL beats ALLOW. The order of rules inside a policy does not matter.
5. **Default deny:** if no rule matches, the workspace default applies. It is BLOCK unless an admin changed it to REQUIRE_APPROVAL. It can never be ALLOW, so unknown actions are never allowed. A new workspace with no policies blocks everything until you add a policy.

## Rules
A rule has an **effect** (ALLOW, BLOCK or REQUIRE_APPROVAL), a **target** (either an *action type* or an *action name pattern*) and an optional **resource pattern**.

Patterns are case-insensitive wildcards: `*` matches anything, `?` matches one character. Examples: `delete_*`, `send_*_email`, `/finance/*`. Only letters, numbers and `_ . : / - * ?` are allowed.

## Action types
`external_email`, `file_access`, `data_export`, `external_api`, `database_operation`, `sensitive_data`, `other`.

The type is inferred from whole words in the action name, for example `send_external_email` → external_email, `read_file` → file_access, `export_report` → data_export, `run_sql_query` → database_operation, `access_financial_records` → sensitive_data. Anything not recognised is `other`; use an action name pattern for those. Use the **Policy tester** on the Policies page to see exactly how an action is categorised and decided.

## Scope, priority and history
- Leave "Applies to" on *All agents* for a workspace-wide policy, or pick one agent.
- Turning a policy off keeps it but stops it applying.
- Every change creates a new version. Open **History** on a policy to see who changed what and when.
- Deleting an agent also deletes policies that applied only to that agent.

## Examples
| Goal | Rule |
|---|---|
| Let agents read documents | ALLOW, action name `read_*` |
| Never delete anything | BLOCK, action name `delete_*` |
| Human review for outside email | REQUIRE_APPROVAL, action type *external email* |
| Block one folder, allow the rest of file access | Policy A (priority 1): BLOCK, type *file access*, resource `/finance/*`. Policy B (priority 10): ALLOW, type *file access* |

Start from a template, then try your own examples in the tester before relying on a policy.
