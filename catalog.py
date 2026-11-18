"""Action categories and starter policy templates.

Pure Python (no framework imports) so it can be unit-tested on its own.
"""

from __future__ import annotations

import re

CATEGORIES: list[dict] = [
    {
        "id": "external_email",
        "label": "Sending external emails",
        "description": "The agent sends an email to someone outside your organisation.",
        "examples": ["send_external_email", "send_email"],
    },
    {
        "id": "file_access",
        "label": "File access",
        "description": "The agent reads, writes or deletes files and documents.",
        "examples": ["read_file", "delete_file", "read_sample_document"],
    },
    {
        "id": "data_export",
        "label": "Data exports",
        "description": "The agent exports or downloads a large amount of data.",
        "examples": ["export_customers", "download_data"],
    },
    {
        "id": "external_api",
        "label": "External API requests",
        "description": "The agent calls a web service or API outside your systems.",
        "examples": ["call_external_api", "http_request"],
    },
    {
        "id": "database_operation",
        "label": "Database operations",
        "description": "The agent queries or changes records in a database.",
        "examples": ["run_sql_query", "update_database"],
    },
    {
        "id": "sensitive_data",
        "label": "Sensitive information",
        "description": "Financial, personal, medical or credential data.",
        "examples": ["access_financial_records", "read_passwords"],
    },
    {
        "id": "other",
        "label": "Anything else",
        "description": "Actions that do not fit another category.",
        "examples": [],
    },
]

CATEGORY_IDS = {c["id"] for c in CATEGORIES}

# Order matters: the first match wins, most sensitive first.
# Single words are compared with whole words of the action name (so "api"
# does not match "capitalize"); phrases are matched inside the whole name.
_WORDS: list[tuple[str, frozenset[str], tuple[str, ...]]] = [
    ("sensitive_data",
     frozenset({"financial", "payroll", "password", "secret", "credential",
                "pii", "ssn", "medical", "salary", "salarie", "creditcard"}),
     ("credit_card",)),
    ("external_email", frozenset(),
     ("external_email", "send_email", "send_mail", "email_external")),
    ("data_export", frozenset({"export", "download", "dump", "bulk"}), ()),
    ("database_operation",
     frozenset({"database", "sql", "db", "query", "table"}), ()),
    ("external_api", frozenset({"api", "http", "https", "webhook", "url"}), ()),
    ("file_access",
     frozenset({"file", "document", "folder", "directory"}), ()),
]


def normalize_category(value: str | None) -> str | None:
    """Return a known category id, or None if the value is empty/unknown."""
    if not value:
        return None
    cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
    return cleaned if cleaned in CATEGORY_IDS else None


def infer_category(action: str) -> str:
    """Guess a category from the action name an agent sent."""
    name = (action or "").strip().lower()
    words = {w for w in re.split(r"[^a-z0-9]+", name) if w}
    singular = {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}
    for category, keywords, phrases in _WORDS:
        if keywords & (words | singular) or any(p in name for p in phrases):
            return category
    return "other"


def _rule(target_type, target_value, effect, resource="*"):
    return {
        "target_type": target_type,
        "target_value": target_value,
        "resource_pattern": resource,
        "effect": effect,
    }


POLICY_TEMPLATES: list[dict] = [
    {
        "id": "recommended",
        "name": "Recommended starter policy",
        "description": "Safe everyday defaults: reading and searching are allowed, "
                       "risky actions need a human, and sensitive data is blocked.",
        "priority": 100,
        "rules": [
            _rule("category", "sensitive_data", "BLOCK"),
            _rule("action", "delete_*", "BLOCK"),
            _rule("category", "external_email", "REQUIRE_APPROVAL"),
            _rule("category", "data_export", "REQUIRE_APPROVAL"),
            _rule("category", "database_operation", "REQUIRE_APPROVAL"),
            _rule("category", "external_api", "REQUIRE_APPROVAL"),
            _rule("action", "read_*", "ALLOW"),
            _rule("action", "search_*", "ALLOW"),
            _rule("action", "draft_*", "ALLOW"),
        ],
    },
    {
        "id": "strict",
        "name": "Strict - ask a human for everything",
        "description": "Nothing happens without review, except blocked actions. "
                       "Best for brand-new agents you do not trust yet.",
        "priority": 100,
        "rules": [
            _rule("category", "sensitive_data", "BLOCK"),
            _rule("action", "delete_*", "BLOCK"),
            _rule("action", "*", "REQUIRE_APPROVAL"),
        ],
    },
    {
        "id": "read_only",
        "name": "Read-only agents",
        "description": "Agents may only read and search. Everything else is blocked.",
        "priority": 100,
        "rules": [
            _rule("category", "sensitive_data", "BLOCK"),
            _rule("action", "read_*", "ALLOW"),
            _rule("action", "search_*", "ALLOW"),
            _rule("action", "*", "BLOCK"),
        ],
    },
]


def get_template(template_id: str) -> dict | None:
    for template in POLICY_TEMPLATES:
        if template["id"] == template_id:
            return template
    return None
