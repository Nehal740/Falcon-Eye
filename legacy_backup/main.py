
import os
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from pwdlib import PasswordHash
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, engine, Base
from models import User
import crud


# Create database tables
Base.metadata.create_all(bind=engine)


# Initialize application
app = FastAPI(
    title="AI Agent Firewall - Learning MVP",
    version="0.3.0",
)


# Password hashing
password_hash = PasswordHash.recommended()


# ==============================
# REQUEST MODELS
# ==============================

class ActionRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)
    resource: str = Field(default="sample", max_length=200)
    reason: str = Field(default="", max_length=500)


class ActionDecision(BaseModel):
    event_id: str
    decision: Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL"]
    message: str


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]


class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: str
    password: str


# ==============================
# USER REGISTRATION
# ==============================

@app.post("/register")
def register_user(
    request: UserRegister,
    db: Session = Depends(get_db)
):
    email = request.email.strip().lower()

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email is already registered."
        )

    user = User(
        full_name=request.full_name.strip(),
        email=email,
        hashed_password=password_hash.hash(request.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "User registered successfully.",
        "user_id": user.id,
        "email": user.email
    }


# ==============================
# USER LOGIN
# ==============================

@app.post("/login")
def login_user(
    request: UserLogin,
    db: Session = Depends(get_db)
):
    email = request.email.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user or not password_hash.verify(
        request.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    secret_key = os.getenv("JWT_SECRET_KEY")

    if not secret_key:
        raise HTTPException(
            status_code=500,
            detail="Login security configuration is missing."
        )

    token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
        },
        secret_key,
        algorithm="HS256"
    )

    return {
        "message": "Login successful.",
        "access_token": token,
        "token_type": "bearer"
    }


# ==============================
# GENERAL ENDPOINTS
# ==============================

@app.get("/")
def root():
    return {
        "message": "AI Agent Firewall is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# ==============================
# FIREWALL EVALUATION
# ==============================

@app.post("/evaluate", response_model=ActionDecision)
def evaluate(
    request: ActionRequest,
    db: Session = Depends(get_db)
):
    from policy import evaluate_policy

    decision = evaluate_policy(
        request.agent_id,
        request.action
    )

    if decision == "REQUIRE_APPROVAL":
        crud.create_approval(db, {
            "approval_id": str(uuid4()),
            "agent_id": request.agent_id,
            "action": request.action,
            "resource": request.resource,
            "reason": request.reason,
            "status": "PENDING"
        })

    event_id = str(uuid4())

    crud.create_firewall_event(db, {
        "event_id": event_id,
        "agent_id": request.agent_id,
        "action": request.action,
        "resource": request.resource,
        "decision": decision
    })

    messages = {
        "ALLOW": "Policy permits this demo action.",
        "BLOCK": "Policy blocks this action.",
        "REQUIRE_APPROVAL": "A human must approve this action first."
    }

    return ActionDecision(
        event_id=event_id,
        decision=decision,
        message=messages[decision]
    )


# ==============================
# EVENT HISTORY
# ==============================

@app.get("/events")
def get_events(
    db: Session = Depends(get_db)
):
    records = crud.get_all_events(db)

    return {
        "events": [
            {
                "event_id": item.event_id,
                "agent_id": item.agent_id,
                "action": item.action,
                "resource": item.resource,
                "decision": item.decision,
                "created_at": item.created_at.isoformat()
            }
            for item in records
        ]
    }


# ==============================
# APPROVAL MANAGEMENT
# ==============================

@app.get("/approvals")
def view_approvals(
    db: Session = Depends(get_db)
):
    records = crud.get_pending_approvals(db)

    return {
        "pending_approvals": [
            {
                "approval_id": item.approval_id,
                "agent_id": item.agent_id,
                "action": item.action,
                "resource": item.resource,
                "reason": item.reason,
                "status": item.status,
                "created_at": item.created_at.isoformat()
            }
            for item in records
        ]
    }


@app.get("/approvals/history")
def approval_history(
    db: Session = Depends(get_db)
):
    records = crud.get_all_approvals(db)

    return {
        "all_approvals": [
            {
                "approval_id": item.approval_id,
                "agent_id": item.agent_id,
                "action": item.action,
                "resource": item.resource,
                "reason": item.reason,
                "status": item.status,
                "created_at": item.created_at.isoformat()
            }
            for item in records
        ]
    }


@app.post("/approvals/{approval_id}/decision")
def update_approval(
    approval_id: str,
    request: ApprovalDecision,
    db: Session = Depends(get_db)
):
    result = crud.decide_approval(
        db,
        approval_id,
        request.decision
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found or already processed."
        )

    return {
        "message": "Approval status updated successfully.",
        "approval": {
            "approval_id": result.approval_id,
            "status": result.status
        }
    }
