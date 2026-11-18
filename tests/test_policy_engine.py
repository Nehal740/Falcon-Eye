"""The policy engine is pure Python, so these tests need no database."""

from catalog import POLICY_TEMPLATES, get_template
from policy import PolicyView, RuleView, evaluate


def rule(target_type, value, effect, resource="*", rid=None):
    return RuleView(rid, target_type, value, resource, effect)


def policy(rules, priority=100, agent_pk=None, enabled=True, pid=1, name="P"):
    return PolicyView(pid, name, priority, agent_pk, enabled, tuple(rules))


def template_policy(template_id="recommended"):
    t = get_template(template_id)
    rules = [RuleView(i, r["target_type"], r["target_value"], r["resource_pattern"], r["effect"])
             for i, r in enumerate(t["rules"], 1)]
    return policy(rules, name=t["name"])


# ---- the three decisions (the original MVP's behaviour, now data-driven)

def test_allowed_action():
    v = evaluate("read_sample_document", "x", [template_policy()])
    assert v.decision == "ALLOW"


def test_blocked_action():
    assert evaluate("delete_file", "x", [template_policy()]).decision == "BLOCK"


def test_blocked_sensitive_category():
    assert evaluate("access_financial_records", "", [template_policy()]).decision == "BLOCK"


def test_approval_required():
    v = evaluate("send_external_email", "bob@evil.test", [template_policy()])
    assert v.decision == "REQUIRE_APPROVAL"
    assert v.policy_name == "Recommended starter policy"


def test_unknown_action_is_blocked_by_default():
    v = evaluate("transfer_money", "", [template_policy()])
    assert v.decision == "BLOCK" and v.used_default


def test_no_policies_blocks_everything():
    assert evaluate("read_file", "a", []).decision == "BLOCK"


def test_default_can_require_approval_but_never_allow():
    assert evaluate("x", "", [], default_decision="REQUIRE_APPROVAL").decision == "REQUIRE_APPROVAL"
    assert evaluate("x", "", [], default_decision="ALLOW").decision == "BLOCK"
    assert evaluate("x", "", [], default_decision="garbage").decision == "BLOCK"


# ---- matching

def test_action_patterns_are_case_insensitive_wildcards():
    p = policy([rule("action", "Read_*", "ALLOW")])
    assert evaluate("READ_notes", "", [p]).decision == "ALLOW"
    assert evaluate("write_notes", "", [p]).decision == "BLOCK"


def test_resource_pattern_limits_a_rule():
    p = policy([rule("action", "read_file", "ALLOW", resource="/public/*")])
    assert evaluate("read_file", "/public/a.txt", [p]).decision == "ALLOW"
    assert evaluate("read_file", "/private/a.txt", [p]).decision == "BLOCK"


def test_category_rule_matches_inferred_and_declared_category():
    p = policy([rule("category", "data_export", "BLOCK")])
    assert evaluate("export_customers", "", [p]).decision == "BLOCK"  # inferred
    assert evaluate("do_thing", "", [p], declared_category="data_export").decision == "BLOCK"


def test_declaring_a_harmless_category_cannot_hide_a_dangerous_action():
    p = policy([rule("category", "data_export", "BLOCK"),
                rule("category", "file_access", "ALLOW")])
    v = evaluate("export_everything", "", [p], declared_category="file_access")
    assert v.decision == "BLOCK"  # strictest wins at equal priority


# ---- priority and strictness

def test_lower_priority_number_wins():
    strict = policy([rule("action", "*", "BLOCK")], priority=50, pid=1, name="Strict")
    loose = policy([rule("action", "*", "ALLOW")], priority=10, pid=2, name="Loose")
    assert evaluate("anything", "", [strict, loose]).policy_name == "Loose"


def test_strictest_effect_wins_at_equal_priority():
    p = policy([rule("action", "send_*", "ALLOW"), rule("action", "send_external_email", "BLOCK")])
    assert evaluate("send_external_email", "", [p]).decision == "BLOCK"
    q = policy([rule("action", "x", "ALLOW"), rule("action", "x", "REQUIRE_APPROVAL")])
    assert evaluate("x", "", [q]).decision == "REQUIRE_APPROVAL"


def test_disabled_policy_is_ignored():
    p = policy([rule("action", "*", "ALLOW")], enabled=False)
    assert evaluate("read_file", "", [p]).decision == "BLOCK"


def test_policy_assigned_to_one_agent_only_applies_to_that_agent():
    p = policy([rule("action", "*", "ALLOW")], agent_pk=7)
    assert evaluate("x", "", [p], agent_pk=7).decision == "ALLOW"
    assert evaluate("x", "", [p], agent_pk=8).decision == "BLOCK"


def test_corrupt_rule_effect_is_ignored_not_trusted():
    p = policy([rule("action", "*", "ALOW")])
    assert evaluate("x", "", [p]).decision == "BLOCK"


def test_verdict_explains_itself():
    v = evaluate("send_external_email", "", [template_policy()])
    assert "Recommended starter policy" in v.reason and v.category == "external_email"


def test_all_templates_are_valid():
    for t in POLICY_TEMPLATES:
        assert t["rules"]
        for r in t["rules"]:
            assert r["effect"] in ("ALLOW", "BLOCK", "REQUIRE_APPROVAL")
