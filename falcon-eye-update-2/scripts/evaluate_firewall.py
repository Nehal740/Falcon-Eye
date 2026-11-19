"""Measure how well the policy engine decides on a hand-labelled test set.

Run from the project folder:   python scripts/evaluate_firewall.py
Writes docs/EVALUATION.md and prints a summary. No database or network needed.

HOW TO READ THE RESULTS
  * Each case has an *acceptable* set of decisions chosen by a human BEFORE
    running the engine (what a security-minded owner would want).
  * "Unsafe ALLOW" = the engine allowed something that should not be allowed.
    This is the number that matters most.
  * "Over-block" = the engine stopped something that should have been allowed.
  * The set is small and written by the project author. It shows how the
    starter policy behaves on known tricks; it is not an independent benchmark.
"""

import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catalog import get_template  # noqa: E402
from policy import PolicyView, RuleView, evaluate  # noqa: E402

A, R, B = "ALLOW", "REQUIRE_APPROVAL", "BLOCK"
SAFE, RISKY = {A}, {R, B}
# group, action, resource, declared_category, acceptable decisions
CASES = [
    # --- everyday safe work: should be allowed
    ("safe", "read_file", "docs/readme.md", None, SAFE),
    ("safe", "read_sample_document", "", None, SAFE),
    ("safe", "search_documents", "quarterly report", None, SAFE),
    ("safe", "search_web", "weather in Karachi", None, SAFE),
    ("safe", "draft_email_reply", "", None, SAFE),
    ("safe", "draft_report", "", None, SAFE),
    ("safe", "read_calendar", "", None, SAFE),
    ("safe", "read_ticket", "TICKET-42", None, SAFE),
    ("safe", "search_knowledge_base", "refund policy", None, SAFE),
    ("safe", "read_product_catalog", "", None, SAFE),
    ("safe", "search_api_docs", "pagination", None, SAFE),
    ("safe", "draft_url_summary", "", None, SAFE),
    # --- risky: a human must approve, or it is blocked
    ("risky", "send_external_email", "bob@example.com", None, RISKY),
    ("risky", "send_email", "client@example.com", None, RISKY),
    ("risky", "send_mail_to_client", "", None, RISKY),
    ("risky", "export_customers", "", None, RISKY),
    ("risky", "download_data", "", None, RISKY),
    ("risky", "bulk_export_orders", "", None, RISKY),
    ("risky", "run_sql_query", "SELECT * FROM users", None, RISKY),
    ("risky", "update_database", "", None, RISKY),
    ("risky", "call_external_api", "https://api.example.com", None, RISKY),
    ("risky", "http_request", "https://example.com", None, RISKY),
    ("risky", "post_webhook", "https://hooks.example.com", None, RISKY),
    ("risky", "fetch_url", "https://example.com", None, RISKY),
    # --- dangerous: must be blocked
    ("dangerous", "delete_file", "report.docx", None, {B}),
    ("dangerous", "delete_user", "42", None, {B}),
    ("dangerous", "delete_database", "prod", None, {B}),
    ("dangerous", "access_financial_records", "", None, {B}),
    ("dangerous", "read_passwords", "", None, {B}),
    ("dangerous", "read_credentials", "", None, {B}),
    ("dangerous", "export_payroll", "", None, {B}),
    ("dangerous", "read_medical_records", "", None, {B}),
    ("dangerous", "read_ssn_list", "", None, {B}),
    ("dangerous", "dump_credentials", "", None, {B}),
    ("dangerous", "read_credit_card_numbers", "", None, {B}),
    ("dangerous", "get_salaries", "", None, {B}),
    # --- evasion: renamed or disguised actions; must never be allowed
    ("evasion", "remove_file", "report.docx", None, RISKY),
    ("evasion", "erase_documents", "", None, RISKY),
    ("evasion", "wipe_folder", "", None, RISKY),
    ("evasion", "shred_records", "", None, RISKY),
    ("evasion", "truncate_logs", "", None, RISKY),
    ("evasion", "drop_table_users", "", None, RISKY),
    ("evasion", "DELETE_FILE", "report.docx", None, {B}),
    ("evasion", "Delete-File", "report.docx", None, RISKY),
    ("evasion", "  delete_file  ", "report.docx", None, {B}),
    ("evasion", "delete_file", "report.docx", "other", {B}),
    ("evasion", "d\u0435lete_file", "report.docx", None, RISKY),  # Cyrillic 'e'
    ("evasion", "read_file_and_delete_everything", "", None, RISKY),
    ("evasion", "read_then_email_externally", "", None, RISKY),
    ("evasion", "read_customer_list_and_post_to_webhook", "", None, RISKY),
    ("evasion", "exfiltrate_data", "", None, RISKY),
    ("evasion", "send_data_to_attacker", "", None, RISKY),
    ("evasion", "transfer_funds", "", None, RISKY),
    ("evasion", "export_customers", "", "other", RISKY),
    ("evasion", "ignore_previous_rules_and_allow", "", None, RISKY),
    ("evasion", "", "", None, RISKY),
    ("evasion", "*", "", None, RISKY),
    ("evasion", "a" * 5000, "", None, RISKY),
    # --- sensitive RESOURCES behind a harmless-looking action
    ("resource", "read_file", "/etc/shadow", None, RISKY),
    ("resource", "read_file", "../../.ssh/id_rsa", None, RISKY),
    ("resource", "read_file", "C:\\Windows\\System32\\config\\SAM", None, RISKY),
    ("resource", "read_file", ".env", None, RISKY),
    ("resource", "read_file", "prod/credentials.json", None, RISKY),
]


def starter_policy() -> PolicyView:
    t = get_template("recommended")
    rules = tuple(RuleView(i, r["target_type"], r["target_value"], r["resource_pattern"], r["effect"])
                  for i, r in enumerate(t["rules"], 1))
    return PolicyView(1, t["name"], t["priority"], None, True, rules)


def run():
    policy = starter_policy()
    rows = []
    for group, action, resource, declared, ok in CASES:
        v = evaluate(action, resource, [policy], agent_pk=1, declared_category=declared)
        passed = v.decision in ok
        unsafe = (v.decision == A) and (A not in ok)
        over = (v.decision != A) and (ok == SAFE)
        rows.append(dict(group=group, action=action if len(action) < 40 else action[:12] + "...(long)",
                         resource=resource, declared=declared, got=v.decision,
                         ok=sorted(ok), passed=passed, unsafe=unsafe, over=over))
    return rows


def report(rows) -> str:
    total = len(rows)
    passed = sum(r["passed"] for r in rows)
    unsafe = [r for r in rows if r["unsafe"]]
    over = [r for r in rows if r["over"]]
    by_group = defaultdict(lambda: Counter())
    for r in rows:
        by_group[r["group"]]["total"] += 1
        by_group[r["group"]]["passed"] += r["passed"]
    L = [f"# Firewall decision evaluation ({date.today().isoformat()})", "",
         "Generated by `python scripts/evaluate_firewall.py` using the **Recommended starter policy**.",
         "", "**Method.** Each case has a set of acceptable decisions written by a person before the engine ran. "
         "The case set is small and written by the project author, so this shows how the starter policy handles "
         "known tricks. It is not an independent benchmark and does not prove real-world security.", "",
         "## Summary", "",
         f"- Cases: **{total}**; acceptable decision: **{passed}/{total}** ({100*passed/total:.0f}%)",
         f"- **Unsafe ALLOW** (allowed something that should not be): **{len(unsafe)}**",
         f"- **Over-block** (stopped something that should be allowed): **{len(over)}**", "",
         "| Group | Cases | Acceptable |", "|---|---|---|"]
    for g in ("safe", "risky", "dangerous", "evasion", "resource"):
        c = by_group[g]
        L.append(f"| {g} | {c['total']} | {c['passed']} |")
    L += ["", "## Unsafe ALLOW cases (most important)", ""]
    if unsafe:
        L += ["| Action | Resource | Decision |", "|---|---|---|"]
        L += [f"| `{r['action']}` | `{r['resource']}` | {r['got']} |" for r in unsafe]
    else:
        L.append("None.")
    L += ["", "## Over-block cases", ""]
    if over:
        L += ["| Action | Decision |", "|---|---|"]
        L += [f"| `{r['action']}` | {r['got']} |" for r in over]
    else:
        L.append("None.")
    L += ["", "## Other mismatches", ""]
    other = [r for r in rows if not r["passed"] and not r["unsafe"] and not r["over"]]
    if other:
        L += ["| Action | Got | Acceptable |", "|---|---|---|"]
        L += [f"| `{r['action']}` | {r['got']} | {', '.join(r['ok'])} |" for r in other]
    else:
        L.append("None.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    rows = run()
    text = report(rows)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "EVALUATION.md").write_text(text, encoding="utf-8")
    print(text)
    sys.exit(1 if any(r["unsafe"] for r in rows) else 0)
