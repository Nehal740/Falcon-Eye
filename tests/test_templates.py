"""Every built-in policy template must be accepted by the same validator the API uses.

(A template with a pattern the validator rejects makes 'create from template' fail.)
"""

import pytest

pytest.importorskip("pydantic")

from catalog import POLICY_TEMPLATES, get_template  # noqa: E402
from policy import PolicyView, RuleView, evaluate  # noqa: E402
from schemas import RuleIn  # noqa: E402


@pytest.mark.parametrize("template", POLICY_TEMPLATES, ids=lambda t: t["id"])
def test_every_template_rule_passes_the_api_validation(template):
    for rule in template["rules"]:
        RuleIn(**rule).check()


def test_windows_sam_file_is_still_blocked_by_the_starter_policy():
    t = get_template("recommended")
    rules = tuple(RuleView(i, r["target_type"], r["target_value"], r["resource_pattern"], r["effect"])
                  for i, r in enumerate(t["rules"], 1))
    policy = PolicyView(1, t["name"], t["priority"], None, True, rules)
    for resource in ("C:\\Windows\\System32\\config\\SAM", "c:/windows/system32/config/sam"):
        assert evaluate("read_file", resource, [policy], agent_pk=1).decision == "BLOCK"


def test_long_earlier_answers_are_accepted_as_chat_history():
    from schemas import AssistantIn
    body = AssistantIn(message="hello", history=[{"role": "assistant", "text": "x" * 9000}])
    assert len(body.history[0].text) == 9000
