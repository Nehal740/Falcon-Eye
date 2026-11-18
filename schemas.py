"""Request bodies (validated automatically by FastAPI)."""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from catalog import CATEGORY_IDS

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACTION = re.compile(r"^[A-Za-z0-9_.:/\-]+$")
_PATTERN = re.compile(r"^[A-Za-z0-9_.:/\-*?\[\]]+$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")

Effect = Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL"]
Role = Literal["admin", "member", "viewer"]


def _check_password(value: str) -> str:
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Use at least one letter and one number.")
    return value


# ---------------------------------------------------------------- auth

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address, like you@example.com.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return _check_password(v)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return _check_password(v)


# ---------------------------------------------------------------- workspaces

class WorkspaceIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class WorkspaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    default_decision: Literal["BLOCK", "REQUIRE_APPROVAL"] | None = None


class MemberIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: Role = "member"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class MemberUpdateIn(BaseModel):
    role: Role


class AssistantConfigIn(BaseModel):
    enabled: bool = True
    custom_instructions: str = Field(default="", max_length=500)


# ---------------------------------------------------------------- agents

class AgentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=300)
    connection_type: Literal["http_api", "n8n", "python", "other"] = "http_api"

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class AgentUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    connection_type: Literal["http_api", "n8n", "python", "other"] | None = None
    status: Literal["active", "disabled"] | None = None


# ---------------------------------------------------------------- policies

class RuleIn(BaseModel):
    target_type: Literal["category", "action"]
    target_value: str = Field(min_length=1, max_length=100)
    resource_pattern: str = Field(default="*", min_length=1, max_length=200)
    effect: Effect

    @field_validator("target_value", "resource_pattern")
    @classmethod
    def _pattern(cls, v: str) -> str:
        v = v.strip()
        if not _PATTERN.match(v):
            raise ValueError("Use only letters, numbers and _ . : / - * ? characters.")
        return v

    def check(self) -> "RuleIn":
        if self.target_type == "category" and self.target_value.lower() not in CATEGORY_IDS:
            raise ValueError(f"'{self.target_value}' is not a known action category.")
        return self


class PolicyIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=300)
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)
    agent_id: int | None = None
    rules: list[RuleIn] = Field(default_factory=list, max_length=50)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class PolicyUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    agent_id: int | None = None
    assign_to_all_agents: bool = False
    rules: list[RuleIn] | None = Field(default=None, max_length=50)


class TemplateIn(BaseModel):
    template_id: str = Field(min_length=1, max_length=40)
    agent_id: int | None = None


class SimulateIn(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    resource: str = Field(default="", max_length=500)
    category: str | None = Field(default=None, max_length=50)
    agent_id: int | None = None

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        v = v.strip()
        if not _ACTION.match(v):
            raise ValueError("Use only letters, numbers and _ . : / - characters.")
        return v


# ---------------------------------------------------------------- firewall

class ActionIn(BaseModel):
    """What an AI agent sends when it wants to do something."""
    action: str = Field(min_length=1, max_length=100,
                        description="What the agent wants to do, e.g. send_external_email")
    resource: str = Field(default="", max_length=500,
                          description="What it wants to do it to, e.g. a file path or address")
    reason: str = Field(default="", max_length=500,
                        description="Why the agent wants to do this")
    category: str | None = Field(default=None, max_length=50,
                                 description="Optional action category")
    request_id: str | None = Field(default=None, max_length=64,
                                   description="Unique id per request; protects against duplicates and replays")
    metadata: dict | None = Field(default=None, description="Optional extra details (max 4 KB)")

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        v = v.strip()
        if not _ACTION.match(v):
            raise ValueError("Use only letters, numbers and _ . : / - characters.")
        return v

    @field_validator("request_id")
    @classmethod
    def _request_id(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _REQUEST_ID.match(v):
            raise ValueError("Use 1-64 letters, numbers and _ . : - characters.")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v, default=str)) > 4096:
            raise ValueError("Metadata must be 4 KB or smaller.")
        return v


class DecisionIn(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = Field(default="", max_length=300)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=1500)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)
