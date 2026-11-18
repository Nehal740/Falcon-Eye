"""Pure-Python helpers: agent keys, rate limiter, category inference, retrieval."""

from agent_keys import generate_agent_key, hash_key, parse_agent_key, verify_agent_key
from catalog import infer_category, normalize_category
from rate_limiter import SlidingWindowLimiter
import retrieval


def test_agent_key_roundtrip():
    key, prefix, key_hash = generate_agent_key()
    assert key.startswith(prefix + "_") and parse_agent_key(key) == prefix
    assert verify_agent_key(key, key_hash)
    assert not verify_agent_key(key + "x", key_hash)
    assert key not in key_hash and len(key_hash) == 64


def test_agent_keys_are_unique_and_malformed_ones_rejected():
    assert generate_agent_key()[0] != generate_agent_key()[0]
    for bad in (None, "", "abc", "fe_live_", "fe_live_zzzzzzzzzzzz_" + "a" * 43,
                "fe_live_" + "a" * 12 + "_short"):
        assert parse_agent_key(bad) is None
    assert hash_key("a") != hash_key("b")


def test_rate_limiter_blocks_then_recovers():
    lim = SlidingWindowLimiter()
    assert all(lim.hit("k", 3, 60, now=100.0 + i)[0] for i in range(3))
    allowed, retry = lim.hit("k", 3, 60, now=104.0)
    assert not allowed and retry >= 1
    assert lim.hit("k", 3, 60, now=161.0)[0]          # window has passed
    assert lim.hit("other", 3, 60, now=104.0)[0]      # keys are independent


def test_category_inference():
    cases = {"send_external_email": "external_email", "export_customers": "data_export",
             "access_financial_records": "sensitive_data", "run_sql_query": "database_operation",
             "call_external_api": "external_api", "read_sample_document": "file_access",
             "capitalize_text": "other", "draft_email": "other"}
    for action, expected in cases.items():
        assert infer_category(action) == expected, action
    assert normalize_category("Data Export") == "data_export"
    assert normalize_category("nonsense") is None


def test_retrieval_finds_the_right_section():
    docs = """# Guide

## Connecting an agent
Open Agents, choose Add agent and copy the key shown once.

## Approvals
Open the Approvals page to approve or reject a pending request from an agent.
"""
    chunks = retrieval.split_markdown("guide.md", docs)
    top = retrieval.search(chunks, "how do I approve a pending request?", k=1)
    assert top and top[0][1].title == "Approvals"
    assert retrieval.search(chunks, "zzzz qqqq") == []
